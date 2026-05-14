import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Activity, ListChecks } from "lucide-react";
import { TaskDrawer } from "./TaskDrawer";

export type PageKey = "data" | "models" | "backtest" | "signals";
export type ConsoleTab = "overview" | "execute" | "history" | "inspect";

export type ConsolePageLayoutProps = {
  pageKey: PageKey;
  titleKey: string;
  tabs: {
    overview?: ReactNode;
    execute: ReactNode;
    history: ReactNode;
    inspect?: ReactNode;
  };
  taskTypeFilter: string[];
  initialTab?: ConsoleTab;
};

export function ConsolePageLayout({
  pageKey,
  titleKey,
  tabs,
  taskTypeFilter,
  initialTab = "execute",
}: ConsolePageLayoutProps) {
  const { t } = useTranslation();
  const [active, setActive] = useState<ConsoleTab>(initialTab);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const openDrawer = () => setDrawerOpen(true);
    window.addEventListener("console:task-created", openDrawer);
    return () => window.removeEventListener("console:task-created", openDrawer);
  }, []);

  const tabList: { key: ConsoleTab; available: boolean; labelKey: string }[] = [
    { key: "overview", available: !!tabs.overview, labelKey: "console.tabs.overview" },
    { key: "execute", available: true, labelKey: "console.tabs.execute" },
    { key: "history", available: true, labelKey: "console.tabs.history" },
    { key: "inspect", available: !!tabs.inspect, labelKey: "console.tabs.inspect" },
  ];

  return (
    <div className="space-y-4">
      <header className="quant-panel flex items-center justify-between gap-4 rounded-sm px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center border border-terminal-green/30 bg-terminal-green-glow text-terminal-green">
            <Activity className="h-4 w-4" />
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-terminal-text-dim">
              quant research console
            </p>
            <h1 className="text-xl font-semibold text-terminal-text-bright" data-i18n={titleKey}>
              {t(titleKey)}
            </h1>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          data-testid="open-task-drawer"
          className="inline-flex items-center gap-2 border border-terminal-border bg-terminal-surface px-3 py-2 text-xs font-mono text-terminal-text-bright transition-colors hover:border-terminal-green hover:text-terminal-green"
        >
          <ListChecks className="h-4 w-4" />
          {t("console.tasks.drawerTitle")}
        </button>
      </header>
      <nav className="border-b border-terminal-border">
        <ul className="flex gap-1">
          {tabList
            .filter((tab) => tab.available)
            .map((tab) => (
              <li key={tab.key}>
                <button
                  type="button"
                  onClick={() => setActive(tab.key)}
                  data-testid={`tab-${tab.key}`}
                  className={`px-4 py-3 text-xs font-mono transition-colors ${
                    active === tab.key
                      ? "border-b-2 border-terminal-green text-terminal-green"
                      : "text-terminal-text-dim hover:text-terminal-text-bright"
                  }`}
                >
                  {t(tab.labelKey)}
                </button>
              </li>
            ))}
        </ul>
      </nav>
      <main data-testid={`tab-panel-${active}`} className="min-h-[520px]">
        {active === "overview" && tabs.overview}
        {active === "execute" && tabs.execute}
        {active === "history" && tabs.history}
        {active === "inspect" && tabs.inspect}
      </main>
      <TaskDrawer
        pageKey={pageKey}
        taskTypeFilter={taskTypeFilter}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
