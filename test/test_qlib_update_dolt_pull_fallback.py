from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from data.qlib_update import dolt_qlib


def _options(*, allow_stale_on_pull_failure: bool) -> dolt_qlib.UpdateOptions:
    return dolt_qlib.UpdateOptions(
        qlib_repo="",
        dolt_repo="",
        mysql_url="mysql+pymysql://root:@127.0.0.1/investment_data",
        max_workers=1,
        shallow_dolt_clone=False,
        clone_depth=1,
        skip_exists=False,
        skip_dolt_pull=False,
        allow_stale_on_pull_failure=allow_stale_on_pull_failure,
        reuse_dolt_server=False,
        install_dolt=False,
        create_tarball=False,
        repair_dolt_clone=False,
        output_dir=None,
        python="python",
        supplement_source="none",
        force=False,
    )


def test_dolt_pull_failure_can_continue_with_local_checkout(monkeypatch, tmp_path, capsys):
    calls = []
    paths = SimpleNamespace(dolt_repo_dir=tmp_path)

    monkeypatch.setattr(dolt_qlib, "is_dolt_repository_locked", lambda _path: False)
    monkeypatch.setattr(dolt_qlib, "_dolt_head_commit", lambda _path: "abc12345")

    def fake_run_capture(command, cwd=None, env=None):
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="fetch failed: https://example.test/blob?X-Amz-Security-Token=secret\n",
            stderr="context canceled\n",
        )

    monkeypatch.setattr(dolt_qlib, "run_capture", fake_run_capture)

    def fake_wait(mysql_url):
        calls.append(mysql_url)

    monkeypatch.setattr(dolt_qlib, "wait_for_database", fake_wait)

    process, had_updates = dolt_qlib.start_dolt_server(
        paths, _options(allow_stale_on_pull_failure=True)
    )

    try:
        assert process is not None
        assert had_updates is False
        assert calls == ["mysql+pymysql://root:@127.0.0.1/investment_data"]
        output = capsys.readouterr().out
        assert "continuing with existing local Dolt data" in output
        assert "[REDACTED]" in output
        assert "secret" not in output
    finally:
        dolt_qlib.stop_dolt_server(process)


def test_dolt_pull_failure_is_strict_by_default(monkeypatch, tmp_path):
    paths = SimpleNamespace(dolt_repo_dir=tmp_path)
    monkeypatch.setattr(dolt_qlib, "is_dolt_repository_locked", lambda _path: False)
    monkeypatch.setattr(dolt_qlib, "_dolt_head_commit", lambda _path: "abc12345")
    monkeypatch.setattr(
        dolt_qlib,
        "run_capture",
        lambda command, cwd=None, env=None: subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr="context canceled",
        ),
    )

    try:
        dolt_qlib.start_dolt_server(paths, _options(allow_stale_on_pull_failure=False))
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("expected strict Dolt pull failure to raise")


def test_cli_accepts_allow_stale_on_pull_failure(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["run_update_qlib_data.py", "--allow-stale-on-pull-failure"],
    )
    args = dolt_qlib.parse_args()
    assert args.allow_stale_on_pull_failure is True
