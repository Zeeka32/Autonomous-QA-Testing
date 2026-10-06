import "./SiteHeader.css";

export function SiteHeader() {
  return (
    <header className="topbar">
      <a className="brand" href="/" aria-label="Autonomous QA home">
        <span className="brand-icon" aria-hidden="true">◈</span>
        <span>autonomous<span className="brand-accent">qa</span></span>
      </a>
      <span className="topbar-caption">A clearer view of every test</span>
      <span className="workspace-pill">
        <span className="workspace-dot" /> Local workspace
      </span>
    </header>
  );
}
