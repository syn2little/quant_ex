import { clsx } from "clsx";

type CardAccent = "green" | "amber" | "red" | "cyan" | "default";

interface CardProps {
  title?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  accent?: CardAccent;
  className?: string;
}

const accentMap: Record<CardAccent, string> = {
  green: "border-t-terminal-green",
  amber: "border-t-terminal-amber",
  red: "border-t-terminal-red",
  cyan: "border-t-terminal-cyan",
  default: "",
};

export function Card({ title, children, actions, accent = "default", className = "" }: CardProps) {
  return (
    <div
      className={clsx(
        "quant-panel rounded-sm",
        accent !== "default" && "border-t-2",
        accentMap[accent],
        className
      )}
    >
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-terminal-border-dim px-4 py-2.5">
          {title && (
            <h3 className="text-xs font-mono font-medium text-terminal-text-dim uppercase tracking-wider">
              {title}
            </h3>
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
