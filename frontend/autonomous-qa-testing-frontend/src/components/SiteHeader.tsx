import type { Theme } from "../hooks/useTheme";
import "./SiteHeader.css";

type SiteHeaderProps = {
  theme: Theme;
  onToggleTheme: () => void;
};

export function SiteHeader({ theme, onToggleTheme }: SiteHeaderProps) {
  return (
    <header className="topbar">
      <a className="brand" href="/" aria-label="Autonomous QA home">
        <span className="brand-icon" aria-hidden="true">◈</span>
        <span>autonomous<span className="brand-accent">qa</span></span>
      </a>
      <span className="topbar-caption">A clearer view of every test</span>
      <button
        className="theme-toggle"
        type="button"
        onClick={onToggleTheme}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      >
        <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
        <span>{theme === "dark" ? "Light" : "Dark"} mode</span>
      </button>
      <span className="workspace-pill">
        <span className="workspace-dot" /> Local workspace
      </span>
    </header>
  );
}
