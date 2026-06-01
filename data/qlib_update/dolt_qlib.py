"""Refresh qlib binary data from chenditc/investment_data via Dolt."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from utils.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE_DIR = PROJECT_ROOT / "qlib_data"
DEFAULT_QLIB_DIR = DEFAULT_WORKSPACE_DIR / "qlib_bin"
DEFAULT_QLIB_REPO = "https://github.com/microsoft/qlib.git"
DEFAULT_DOLT_REPO = "chenditc/investment_data"
DEFAULT_MYSQL_URL = "mysql+pymysql://root:@127.0.0.1/investment_data"
INDEX_MAP = {
    "csi300": "399300.SZ",
    "csi500": "000905.SH",
    "csi800": "000906.SH",
    "csi1000": "000852.SH",
    "csiall": "000985.SH",
}


@dataclass
class UpdatePaths:
    workspace_dir: Path
    qlib_dir: Path
    qlib_repo_dir: Path
    dolt_parent_dir: Path
    dolt_repo_dir: Path
    source_dir: Path
    normalize_dir: Path
    index_dir: Path
    tarball_path: Path


@dataclass
class UpdateOptions:
    qlib_repo: str
    dolt_repo: str
    mysql_url: str
    max_workers: int
    shallow_dolt_clone: bool
    clone_depth: int
    skip_exists: bool
    skip_dolt_pull: bool
    allow_stale_on_pull_failure: bool
    reuse_dolt_server: bool
    install_dolt: bool
    create_tarball: bool
    repair_dolt_clone: bool
    output_dir: Optional[Path]
    python: str
    supplement_source: str  # "none" | "akshare" | "eastmoney"
    force: bool  # skip staleness check, always re-run full pipeline


def resolve_path(path: str, base: Path = PROJECT_ROOT) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def build_paths(config: Dict[str, Any], args: argparse.Namespace) -> UpdatePaths:
    update_config = config.get("data_update", {}).get("qlib_bin", {})
    qlib_dir = resolve_path(
        args.qlib_dir
        or update_config.get("qlib_dir")
        or config.get("qlib", {}).get("provider_uri")
        or str(DEFAULT_QLIB_DIR)
    )
    workspace_dir = resolve_path(
        args.workspace_dir
        or update_config.get("workspace_dir")
        or str(DEFAULT_WORKSPACE_DIR)
    )

    source_dir = resolve_path(
        update_config.get("source_dir", str(workspace_dir / "qlib_source")), workspace_dir
    )
    normalize_dir = resolve_path(
        update_config.get("normalize_dir", str(workspace_dir / "qlib_normalize")), workspace_dir
    )
    index_dir = resolve_path(
        update_config.get("index_dir", str(workspace_dir / "qlib_index")), workspace_dir
    )
    qlib_repo_dir = resolve_path(
        update_config.get("qlib_repo_dir", str(workspace_dir / "qlib")), workspace_dir
    )
    dolt_parent_dir = resolve_path(
        update_config.get("dolt_parent_dir", str(workspace_dir / "dolt")), workspace_dir
    )
    dolt_repo_dir = resolve_path(
        update_config.get("dolt_repo_dir", str(dolt_parent_dir / "investment_data")),
        workspace_dir,
    )
    tarball_path = resolve_path(
        update_config.get("tarball_path", str(workspace_dir / "qlib_bin.tar.gz")),
        workspace_dir,
    )

    return UpdatePaths(
        workspace_dir=workspace_dir,
        qlib_dir=qlib_dir,
        qlib_repo_dir=qlib_repo_dir,
        dolt_parent_dir=dolt_parent_dir,
        dolt_repo_dir=dolt_repo_dir,
        source_dir=source_dir,
        normalize_dir=normalize_dir,
        index_dir=index_dir,
        tarball_path=tarball_path,
    )


def build_options(config: Dict[str, Any], args: argparse.Namespace) -> UpdateOptions:
    update_config = config.get("data_update", {}).get("qlib_bin", {})
    output_dir = args.output_dir or os.environ.get("OUTPUT_DIR") or update_config.get("output_dir")
    return UpdateOptions(
        qlib_repo=args.qlib_repo or update_config.get("qlib_repo", DEFAULT_QLIB_REPO),
        dolt_repo=args.dolt_repo or update_config.get("dolt_repo", DEFAULT_DOLT_REPO),
        mysql_url=args.mysql_url or update_config.get("mysql_url", DEFAULT_MYSQL_URL),
        max_workers=args.max_workers or int(update_config.get("max_workers", 16)),
        shallow_dolt_clone=args.shallow_dolt_clone,
        clone_depth=args.clone_depth or int(update_config.get("clone_depth", 1)),
        skip_exists=args.skip_exists,
        skip_dolt_pull=args.skip_dolt_pull,
        allow_stale_on_pull_failure=args.allow_stale_on_pull_failure
        or bool(update_config.get("allow_stale_on_pull_failure", False)),
        reuse_dolt_server=args.reuse_dolt_server,
        install_dolt=args.install_dolt,
        create_tarball=not args.no_tarball,
        repair_dolt_clone=args.repair_dolt_clone,
        output_dir=resolve_path(output_dir) if output_dir else None,
        python=args.python or sys.executable,
        supplement_source=args.supplement_source or update_config.get("supplement_source", "none"),
        force=args.force,
    )


def run(
    command: list[str],
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=str(cwd) if cwd else None, env=env, check=True)


def _redact_signed_url_noise(text: str) -> str:
    """Keep Dolt pull diagnostics readable without leaking signed URL tokens."""
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        if "?X-Amz-" in line:
            line = line.split("?X-Amz-", 1)[0] + "?[REDACTED]"
        lines.append(line)
    return "\n".join(lines)


def run_capture(
    command: list[str],
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def command_ok(command: list[str], cwd: Path) -> bool:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_command(command: str, install_dolt: bool = False) -> None:
    if shutil.which(command):
        return
    if command == "dolt" and install_dolt:
        install_script_url = "https://github.com/dolthub/dolt/releases/latest/download/install.sh"
        run(["bash", "-c", f"curl -L {install_script_url} | bash"])
        if shutil.which(command):
            return
    raise RuntimeError(
        f"Required command not found: {command}. Install it first, or pass --install-dolt for dolt."
    )


def ensure_repositories(paths: UpdatePaths, options: UpdateOptions) -> None:
    ensure_command("git")
    ensure_command("dolt", install_dolt=options.install_dolt)

    paths.workspace_dir.mkdir(parents=True, exist_ok=True)
    paths.dolt_parent_dir.mkdir(parents=True, exist_ok=True)

    ensure_dolt_repository(paths, options)
    ensure_git_repository(paths.qlib_repo_dir, options.qlib_repo)


def ensure_dolt_repository(paths: UpdatePaths, options: UpdateOptions) -> None:
    if paths.dolt_repo_dir.exists():
        if is_dolt_repository_locked(paths.dolt_repo_dir):
            if (paths.dolt_repo_dir / ".dolt").exists():
                return
            raise RuntimeError(dolt_lock_message(paths.dolt_repo_dir))
        if is_valid_dolt_repository(paths.dolt_repo_dir):
            return
        message = (
            f"Found an incomplete Dolt repository at {paths.dolt_repo_dir}. "
            "This usually happens when the first `dolt clone` is interrupted. "
            "Dolt can pull incrementally after a complete clone, but this partial "
            "initial clone cannot be resumed reliably."
        )
        if not options.repair_dolt_clone:
            raise RuntimeError(
                message
                + " Re-run with --repair-dolt-clone to move it aside and start "
                "a new clone."
            )
        backup = paths.dolt_repo_dir.with_name(
            f"{paths.dolt_repo_dir.name}.partial.{time.strftime('%Y%m%d_%H%M%S')}"
        )
        print(f"{message} Moving partial clone to {backup}")
        shutil.move(str(paths.dolt_repo_dir), str(backup))

    clone_cmd = ["dolt", "clone"]
    if options.shallow_dolt_clone:
        clone_cmd.append("--single-branch")
    if options.shallow_dolt_clone and options.clone_depth > 0:
        clone_cmd.extend(["--depth", str(options.clone_depth)])
    clone_cmd.extend([options.dolt_repo, str(paths.dolt_repo_dir)])
    run(clone_cmd, cwd=paths.dolt_parent_dir)


def is_valid_dolt_repository(path: Path) -> bool:
    valid = (path / ".dolt").exists() and command_ok(["dolt", "status"], cwd=path)
    # dolt status creates a LOCK file but doesn't clean it up.
    # Remove the stale lock so start_dolt_server doesn't trip over it.
    dolt_lock_path(path).unlink(missing_ok=True)
    return valid


def dolt_lock_path(path: Path) -> Path:
    return path / ".dolt" / "noms" / "LOCK"


def is_dolt_repository_locked(path: Path) -> bool:
    lock = dolt_lock_path(path)
    if not lock.exists():
        return False
    # dolt status (and some other commands) leave behind a stale LOCK file.
    # If no lock-holding dolt process is actually running, treat it as unlocked.
    result = subprocess.run(
        ["pgrep", "-f", "dolt sql-server|dolt clone|dolt pull"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        lock.unlink(missing_ok=True)
        return False
    return True


def dolt_lock_message(path: Path) -> str:
    return (
        f"Dolt repository is locked: {path}\n"
        "Another Dolt process is holding the database write lock, usually an "
        "unfinished `dolt sql-server`, `dolt clone`, `dolt pull`, or another "
        "`run_update_qlib_data.py`.\n"
        "If that process is still intentionally running, wait for it to finish. "
        "If it is an abandoned SQL server, stop it first, then re-run this update.\n"
        "Useful local checks:\n"
        "  ps aux | grep '[d]olt'\n"
        "  lsof -i :3306\n"
        "  pkill -f 'dolt sql-server'   # only if you are sure no update is running\n"
        "If you intentionally want to export from an already-running Dolt SQL "
        "server without pulling new data, pass --reuse-dolt-server."
    )


def ensure_git_repository(path: Path, repo_url: str) -> None:
    if path.exists() and command_ok(["git", "rev-parse", "--is-inside-work-tree"], cwd=path):
        return
    if path.exists():
        backup = path.with_name(f"{path.name}.partial.{time.strftime('%Y%m%d_%H%M%S')}")
        print(f"Found incomplete git repository at {path}. Moving it to {backup}")
        shutil.move(str(path), str(backup))
    if not path.exists():
        run(["git", "clone", repo_url, str(path)])


def wait_for_database(mysql_url: str, timeout_seconds: int = 30) -> None:
    from sqlalchemy import create_engine, text

    deadline = time.time() + timeout_seconds
    last_error: Optional[Exception] = None
    while time.time() < deadline:
        try:
            engine = create_engine(mysql_url, pool_recycle=3600)
            with engine.connect() as conn:
                conn.execute(text("select 1"))
            engine.dispose()
            return
        except Exception as exc:  # pragma: no cover - depends on local Dolt server
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Dolt SQL server did not become ready: {last_error}")


def _dolt_head_commit(dolt_repo_dir: Path) -> Optional[str]:
    """Return the current HEAD commit hash of the Dolt repo, or None on failure."""
    try:
        result = subprocess.run(
            ["dolt", "log", "--format=%H", "-1"],
            cwd=str(dolt_repo_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _source_cutoff_date(source_dir: Path, sample_size: int = 5) -> Optional[str]:
    """Return the latest tradedate across a sample of source CSVs.

    Used to check whether the existing source data is already up-to-date
    without reading every file.
    """
    csv_files = sorted(source_dir.glob("*.csv"))
    if not csv_files:
        return None
    # Prefer liquid large-cap stocks for a fast representative sample
    preferred = ["SH600000.csv", "SH600519.csv", "SH601318.csv", "SZ000001.csv"]
    candidates: list[Path] = []
    for name in preferred:
        p = source_dir / name
        if p.exists():
            candidates.append(p)
    for f in csv_files:
        if len(candidates) >= sample_size:
            break
        if f not in candidates:
            candidates.append(f)
    latest: Optional[str] = None
    for f in candidates:
        try:
            df = pd.read_csv(f, usecols=["tradedate"], parse_dates=["tradedate"], nrows=1)
            if df.empty:
                continue
            # Read just the last line for the latest date
            with open(f, "r") as fh:
                last_line = fh.readlines()[-1].strip()
            date_str = last_line.split(",")[0]  # first column is tradedate
            if latest is None or date_str > latest:
                latest = date_str
        except Exception:
            continue
    return latest


def _data_is_stale(paths: UpdatePaths, dolt_had_updates: bool) -> bool:
    """Check whether the downstream pipeline needs to re-run.

    Returns True if the pipeline should run, False if data is already current.
    """
    # If dolt pull brought new commits, always re-run
    if dolt_had_updates:
        return True
    # Compare source CSV cutoff vs today
    cutoff = _source_cutoff_date(paths.source_dir)
    if cutoff is None:
        return True  # no source data at all
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    if cutoff >= today:
        print(f"Source data is current (cutoff={cutoff}), skipping full pipeline.")
        return False
    print(f"Source data cutoff={cutoff} < today={today}, re-running pipeline.")
    return True


def start_dolt_server(paths: UpdatePaths, options: UpdateOptions) -> Tuple[Optional[subprocess.Popen[str]], bool]:
    """Start a Dolt SQL server for data export.

    Returns
    -------
    (process, dolt_had_updates)
        process: the Popen handle (or None if reusing an existing server)
        dolt_had_updates: True if ``dolt pull`` fetched new commits
    """
    dolt_had_updates = False

    if is_dolt_repository_locked(paths.dolt_repo_dir):
        if options.reuse_dolt_server:
            wait_for_database(options.mysql_url)
            return None, True  # assume stale when reusing external server
        raise RuntimeError(dolt_lock_message(paths.dolt_repo_dir))

    if not options.skip_dolt_pull:
        head_before = _dolt_head_commit(paths.dolt_repo_dir)
        pull_result = run_capture(["dolt", "pull", "origin"], cwd=paths.dolt_repo_dir)
        if pull_result.returncode != 0:
            message = _redact_signed_url_noise(
                "\n".join(part for part in [pull_result.stdout, pull_result.stderr] if part)
            )
            if not options.allow_stale_on_pull_failure:
                raise subprocess.CalledProcessError(
                    pull_result.returncode,
                    pull_result.args,
                    output=pull_result.stdout,
                    stderr=pull_result.stderr,
                )
            print(
                "WARNING: `dolt pull origin` failed; continuing with existing local "
                "Dolt data because --allow-stale-on-pull-failure is set."
            )
            if message:
                print(message)
        else:
            if pull_result.stdout:
                print(pull_result.stdout, end="")
            if pull_result.stderr:
                print(pull_result.stderr, end="")
        head_after = _dolt_head_commit(paths.dolt_repo_dir)
        dolt_had_updates = head_before != head_after
        if dolt_had_updates:
            print(f"Dolt pull: new commits detected ({head_before[:8] if head_before else 'none'} -> {head_after[:8] if head_after else 'none'})")
        else:
            print("Dolt pull: already up-to-date, no new commits.")

    process = subprocess.Popen(
        ["dolt", "sql-server"],
        cwd=str(paths.dolt_repo_dir),
        text=True,
    )
    try:
        wait_for_database(options.mysql_url)
    except BaseException:
        stop_dolt_server(process)
        raise
    return process, dolt_had_updates


def open_db(mysql_url: str):
    from sqlalchemy import create_engine

    engine = create_engine(mysql_url, pool_recycle=3600)
    return engine, engine.raw_connection()


def dump_stock_source(paths: UpdatePaths, options: UpdateOptions) -> None:
    paths.source_dir.mkdir(parents=True, exist_ok=True)
    engine, connection = open_db(options.mysql_url)
    try:
        stock_df = pd.read_sql(
            "select *, amount/volume*10 as vwap from final_a_stock_eod_price",
            connection,
        )
    finally:
        connection.close()
        engine.dispose()

    for symbol, df in stock_df.groupby("symbol"):
        filename = paths.source_dir / f"{symbol}.csv"
        if options.skip_exists and filename.exists():
            continue
        print("Dumping to file:", filename)
        df.to_csv(filename, index=False)


def dump_index_weight(paths: UpdatePaths, options: UpdateOptions) -> None:
    paths.index_dir.mkdir(parents=True, exist_ok=True)
    engine, connection = open_db(options.mysql_url)
    try:
        for index_name, index_code in INDEX_MAP.items():
            filename = paths.index_dir / f"{index_name}.txt"
            if options.skip_exists and filename.exists():
                continue

            print("Dumping to file:", filename)
            change_date_sql = f"""
                select min(trade_date) as change_date from
                (
                    select trade_date, MD5(GROUP_CONCAT(stock_code)) as signature
                    from ts_index_weight
                    where index_code = '{index_code}'
                    group by trade_date
                ) date_sig_table
                group by signature
                order by change_date
            """
            change_dates = pd.read_sql_query(change_date_sql, connection)["change_date"]
            result_frames = []
            for i, change_date in enumerate(change_dates):
                start_date = change_date.strftime("%Y-%m-%d")
                if i == len(change_dates) - 1:
                    end_date = pd.Timestamp.today().strftime("%Y-%m-%d")
                else:
                    end_date = (change_dates[i + 1] - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

                sql = (
                    "select concat(substr(stock_code, 8, 2), substr(stock_code, 1, 6)), "
                    f"'{start_date}' as start_date, '{end_date}' as end_date "
                    "from ts_index_weight "
                    f"where index_code = '{index_code}' and trade_date = '{start_date}'"
                )
                stock_df = pd.read_sql_query(sql, connection)
                if stock_df.empty:
                    raise RuntimeError(f"No data for SQL: {sql}")
                result_frames.append(stock_df)

            if result_frames:
                pd.concat(result_frames).to_csv(filename, index=False, header=False, sep="\t")
    finally:
        connection.close()
        engine.dispose()


def dump_calendar(paths: UpdatePaths, options: UpdateOptions) -> None:
    old_days_file = paths.qlib_dir / "calendars/day.txt"
    if not old_days_file.exists():
        raise FileNotFoundError(f"Cannot find existing qlib day calendar: {old_days_file}")

    old_calendar_df = pd.read_csv(old_days_file, header=None)
    min_date = pd.to_datetime(old_calendar_df.iloc[0][0])

    engine, connection = open_db(options.mysql_url)
    try:
        sql = "select date from ts_trade_day_calendar where exchange = 'SSE' and is_open = 1"
        calendar_df = pd.read_sql(sql, connection)
    finally:
        connection.close()
        engine.dispose()

    calendar_df["date"] = pd.to_datetime(calendar_df["date"])
    calendar_df.drop(calendar_df[calendar_df["date"] < min_date].index, inplace=True)

    filename = paths.qlib_dir / "calendars/day_future.txt"
    print("Dumping to file:", filename)
    calendar_df.to_csv(filename, index=False, header=False, sep="\t")


def qlib_scripts_env(paths: UpdatePaths) -> dict[str, str]:
    env = os.environ.copy()
    qlib_paths = [
        str(paths.qlib_repo_dir),
        str(paths.qlib_repo_dir / "scripts"),
    ]
    env["PYTHONPATH"] = os.pathsep.join(qlib_paths + [env.get("PYTHONPATH", "")])
    env["QLIB_REPO_DIR"] = str(paths.qlib_repo_dir)
    return env


def normalize_source(paths: UpdatePaths, options: UpdateOptions) -> None:
    paths.normalize_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            options.python,
            "-m",
            "data.qlib_update.normalize",
            "--source-dir",
            str(paths.source_dir),
            "--normalize-dir",
            str(paths.normalize_dir),
            "--max-workers",
            str(options.max_workers),
            "--date-field-name",
            "tradedate",
        ],
        cwd=PROJECT_ROOT,
        env=qlib_scripts_env(paths),
    )


def dump_bin(paths: UpdatePaths, options: UpdateOptions) -> None:
    dump_bin_script = paths.qlib_repo_dir / "scripts/dump_bin.py"
    if not dump_bin_script.exists():
        raise FileNotFoundError(f"Cannot find qlib dump_bin.py: {dump_bin_script}")
    run(
        [
            options.python,
            str(dump_bin_script),
            "dump_all",
            "--data_path",
            str(paths.normalize_dir),
            "--qlib_dir",
            str(paths.qlib_dir),
            "--date_field_name",
            "tradedate",
            "--exclude_fields",
            "tradedate,symbol",
        ],
        env=qlib_scripts_env(paths),
    )


def copy_index_files(paths: UpdatePaths) -> None:
    instruments_dir = paths.qlib_dir / "instruments"
    instruments_dir.mkdir(parents=True, exist_ok=True)
    for index_file in paths.index_dir.glob("csi*.txt"):
        target = instruments_dir / index_file.name
        print(f"Copying {index_file} -> {target}")
        shutil.copy2(index_file, target)


def create_tarball(paths: UpdatePaths, options: UpdateOptions) -> None:
    paths.tarball_path.parent.mkdir(parents=True, exist_ok=True)
    if paths.tarball_path.exists():
        paths.tarball_path.unlink()

    print("Creating tarball:", paths.tarball_path)
    with tarfile.open(paths.tarball_path, "w:gz") as tar:
        tar.add(paths.qlib_dir, arcname=paths.qlib_dir.name)

    if options.output_dir and options.output_dir.exists():
        target = options.output_dir / paths.tarball_path.name
        shutil.move(str(paths.tarball_path), target)
        print("Moved tarball to:", target)
    else:
        print("Generated tarball at:", paths.tarball_path)


def stop_dolt_server(process: Optional[subprocess.Popen[str]]) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def supplement_source_data(paths: UpdatePaths, options: UpdateOptions) -> None:
    """Fill any gap between the Dolt dump and today using a supplementary source.

    Runs after ``dump_stock_source`` so newly-fetched rows are processed by the
    same normalize → dump_bin pipeline as the Dolt data.
    """
    source_name = options.supplement_source
    if source_name == "none":
        return

    from data.sources.gap_filler import GapFiller, detect_source_cutoff

    if source_name == "akshare":
        from data.sources.akshare_source import AkshareSource
        data_source = AkshareSource()
    elif source_name == "eastmoney":
        from data.sources.eastmoney_source import EastMoneySource
        data_source = EastMoneySource()
    else:
        raise ValueError(
            f"Unknown supplement_source '{source_name}'. "
            "Choose: akshare | eastmoney | none"
        )

    filler = GapFiller(
        source_dir=paths.source_dir,
        data_source=data_source,
        max_workers=options.max_workers,
    )
    end_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    stats = filler.fill(end_date=end_date)
    print(
        f"[supplement:{source_name}] filled={stats['filled']} "
        f"skipped={stats['skipped']} errors={stats['errors']}"
    )


def refresh_qlib_bin(paths: UpdatePaths, options: UpdateOptions) -> None:
    ensure_repositories(paths, options)
    dolt_process, dolt_had_updates = start_dolt_server(paths, options)
    try:
        # Staleness check: skip pipeline if dolt had no new commits and source is current
        if not options.force and not _data_is_stale(paths, dolt_had_updates):
            print("Data is up-to-date and --force not set. Skipping full pipeline.")
            # Still update calendar and index files (cheap, always useful)
            dump_calendar(paths, options)
            copy_index_files(paths)
            return

        dump_stock_source(paths, options)
        supplement_source_data(paths, options)
        normalize_source(paths, options)
        dump_bin(paths, options)
        dump_index_weight(paths, options)
        dump_calendar(paths, options)
        copy_index_files(paths)
        if options.create_tarball:
            create_tarball(paths, options)
    finally:
        stop_dolt_server(dolt_process)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Optional YAML config override.")
    parser.add_argument(
        "--qlib-dir",
        default=None,
        help=f"Target qlib_bin directory. Default: {DEFAULT_QLIB_DIR}.",
    )
    parser.add_argument(
        "--workspace-dir",
        default=None,
        help=(
            "Working directory for Dolt, qlib clone and temp files. "
            f"Default: {DEFAULT_WORKSPACE_DIR}."
        ),
    )
    parser.add_argument("--qlib-repo", help=f"qlib git repository. Default: {DEFAULT_QLIB_REPO}")
    parser.add_argument("--dolt-repo", help=f"Dolt repository. Default: {DEFAULT_DOLT_REPO}")
    parser.add_argument("--mysql-url", help=f"Dolt SQL URL. Default: {DEFAULT_MYSQL_URL}")
    parser.add_argument("--max-workers", type=int, help="Normalize worker count.")
    parser.add_argument(
        "--shallow-dolt-clone",
        action="store_true",
        help="Use `dolt clone --single-branch --depth N` for the first clone.",
    )
    parser.add_argument(
        "--clone-depth",
        type=int,
        help="Depth used only with --shallow-dolt-clone. Default: config value, usually 1.",
    )
    parser.add_argument("--python", help="Python executable used for qlib helper scripts.")
    parser.add_argument("--output-dir", help="Directory to receive qlib_bin.tar.gz if it exists.")
    parser.add_argument(
        "--skip-exists",
        action="store_true",
        help="Skip existing CSV/index outputs.",
    )
    parser.add_argument(
        "--skip-dolt-pull",
        action="store_true",
        help="Do not run `dolt pull origin` before exporting.",
    )
    parser.add_argument(
        "--allow-stale-on-pull-failure",
        action="store_true",
        help=(
            "If `dolt pull origin` fails, continue from the existing local Dolt "
            "checkout instead of aborting the qlib refresh."
        ),
    )
    parser.add_argument(
        "--reuse-dolt-server",
        action="store_true",
        help=(
            "Reuse an already-running Dolt SQL server and skip starting/stopping "
            "one in this script. This also skips `dolt pull` when a lock is present."
        ),
    )
    parser.add_argument(
        "--install-dolt",
        action="store_true",
        help="Install dolt if the command is missing.",
    )
    parser.add_argument(
        "--repair-dolt-clone",
        action="store_true",
        help="Move an incomplete first Dolt clone aside and start a new clone.",
    )
    parser.add_argument("--no-tarball", action="store_true", help="Do not create qlib_bin.tar.gz.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run the full pipeline even if data is already up-to-date.",
    )
    parser.add_argument(
        "--supplement-source",
        choices=["none", "akshare", "eastmoney"],
        default=None,
        help=(
            "Fill trading-day gaps after the Dolt dump using a supplementary "
            "source.  'none' (default) skips supplementation.  'akshare' uses "
            "the akshare library; 'eastmoney' uses the built-in crawler SDK."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    paths = build_paths(config, args)
    options = build_options(config, args)
    refresh_qlib_bin(paths, options)


if __name__ == "__main__":
    main()
