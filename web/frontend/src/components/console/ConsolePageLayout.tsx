import type { ReactNode } from "react";
import { useState } from "react";
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
  const [active, setActive] = useState<ConsoleTab>(initialTab);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const tabList: { key: ConsoleTab; available: boolean; labelKey: string }[] = [
    { key: "overview", available: !!tabs.overview, labelKey: "console.tabs.overview" },
    { key: "execute", available: true, labelKey: "console.tabs.execute" },
    { key: "history", available: true, labelKey: "console.tabs.history" },
    { key: "inspect", available: !!tabs.inspect, labelKey: "console.tabs.inspect" },
  ];

  return (
    <div className="p-6">
      <header className="mb-4 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold" data-i18n={titleKey}>
          {titleKey}
        </h1>
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          data-testid="open-task-drawer"
          className="rounded border px-3 py-1.5"
        >
          Tasks
        </button>
      </header>
      <nav className="mb-4 border-b">
        <ul className="flex gap-4">
          {tabList
            .filter((tab) => tab.available)
            .map((tab) => (
              <li key={tab.key}>
                <button
                  type="button"
                  onClick={() => setActive(tab.key)}
                  data-testid={`tab-${tab.key}`}
                  className={`pb-2 ${
                    active === tab.key ? "border-b-2 border-blue-600 font-medium" : ""
                  }`}
                >
                  {tab.labelKey}
                </button>
              </li>
            ))}
        </ul>
      </nav>
      <main data-testid={`tab-panel-${active}`}>
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
