import { ConsolePageLayout } from "../components/console";
import { useTranslation } from "react-i18next";
import { CompareConsole } from "./backtest/CompareConsole";
import { GridConsole } from "./backtest/GridConsole";
import { ResultDetail } from "./backtest/ResultDetail";
import { ResultsHistory } from "./backtest/ResultsHistory";
import { WFVConsole } from "./backtest/WFVConsole";

const BACKTEST_TASK_TYPES = [
  "grid_search",
  "wfv",
  "compare",
  "grid_search_dry_run",
  "wfv_dry_run",
  "compare_dry_run",
];

export function BacktestPage() {
  const { t } = useTranslation();
  return (
    <ConsolePageLayout
      pageKey="backtest"
      titleKey="console.backtest.title"
      taskTypeFilter={BACKTEST_TASK_TYPES}
      tabs={{
        execute: (
          <div className="space-y-6">
            <div className="rounded-sm border border-terminal-border bg-terminal-raised/40 px-4 py-3">
              <div className="grid grid-cols-1 gap-3 font-mono text-xs text-terminal-text-dim md:grid-cols-3">
                <div>
                  <span className="block uppercase">{t("console.backtest.primaryRankMetric")}</span>
                  <span className="text-terminal-green">information_ratio</span>
                </div>
                <div>
                  <span className="block uppercase">{t("console.backtest.curveDiagnostics")}</span>
                  <span className="text-terminal-text">{t("console.backtest.curveDiagnosticsValue")}</span>
                </div>
                <div>
                  <span className="block uppercase">{t("console.backtest.executionMode")}</span>
                  <span className="text-terminal-text">{t("console.backtest.executionModeValue")}</span>
                </div>
              </div>
            </div>
            <GridConsole />
            <WFVConsole />
            <CompareConsole />
          </div>
        ),
        history: <ResultsHistory />,
        inspect: <ResultDetail />,
      }}
    />
  );
}
