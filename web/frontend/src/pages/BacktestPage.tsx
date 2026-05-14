import { ConsolePageLayout } from "../components/console";
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
  return (
    <ConsolePageLayout
      pageKey="backtest"
      titleKey="console.backtest.title"
      taskTypeFilter={BACKTEST_TASK_TYPES}
      tabs={{
        execute: (
          <div className="space-y-6">
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
