import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageToggle } from "./LanguageToggle";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Database,
  FlaskConical,
  LineChart,
  Radio,
  Brain,
  Bot,
  Settings,
  Terminal,
} from "lucide-react";
import { clsx } from "clsx";

const NAV_ITEMS = [
  { icon: LayoutDashboard, key: "overview", to: "/" },
  { icon: Database, key: "dataExplorer", to: "/data-explorer" },
  { icon: FlaskConical, key: "research", to: "/research" },
  { icon: Brain, key: "models", to: "/models" },
  { icon: LineChart, key: "backtest", to: "/backtest" },
  { icon: Radio, key: "signals", to: "/signals" },
  { icon: Bot, key: "agentRuns", to: "/agents" },
  { icon: Settings, key: "config", to: "/config" },
  { icon: Terminal, key: "system", to: "/system" },
] as const;

export function Sidebar() {
  const { t } = useTranslation();

  return (
    <aside
      className="sticky top-0 z-40 flex h-screen w-[224px] shrink-0 flex-col overflow-hidden border-r border-[#20342c] bg-[#111d18] text-[#d7e3dc]"
    >
      {/* Logo */}
      <div className="flex h-14 items-center gap-3 border-b border-[#20342c] px-4">
        <span className="grid h-8 w-8 shrink-0 place-items-center border border-terminal-green/40 bg-terminal-green-glow text-sm font-mono font-bold tracking-tight text-[#75d9ad]">
          QX
        </span>
        <div className="min-w-0">
          <div className="whitespace-nowrap text-sm font-semibold tracking-wide text-[#f3f7f4]">
            quant_ex
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#8ca59a]">
            research console
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 overflow-y-auto overflow-x-hidden px-2 py-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              clsx(
                "relative flex items-center gap-3 px-3 py-2.5 text-xs font-mono transition-colors",
                isActive
                  ? "bg-[#1b3028] text-[#78ddb0]"
                  : "text-[#9eb0a7] hover:bg-[#172720] hover:text-[#eef6f1]"
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div
                    layoutId="sidebar-indicator"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-terminal-green rounded-full"
                    transition={{ type: "spring", stiffness: 500, damping: 35 }}
                  />
                )}
                <item.icon size={16} className="shrink-0" />
                <span className="whitespace-nowrap">{t(`nav.${item.key}`)}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Language */}
      <LanguageToggle />
    </aside>
  );
}
