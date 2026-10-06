import { Intro } from "./components/Intro";
import { RunForm } from "./components/RunForm";
import { RunOverview } from "./components/RunOverview";
import { SiteHeader } from "./components/SiteHeader";
import { useQaRun } from "./hooks/useQaRun";
import { useTheme } from "./hooks/useTheme";
import "./App.css";

function App() {
  const qa = useQaRun();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="app-shell">
      <SiteHeader theme={theme} onToggleTheme={toggleTheme} />
      <main className="main-content">
        <Intro />
        <div className="workspace-grid">
          <RunForm
            active={qa.active}
            submitting={qa.submitting}
            onStart={qa.startRun}
          />
          <RunOverview
            runId={qa.runId}
            run={qa.run}
            artifacts={qa.artifacts}
            error={qa.error}
            active={qa.active}
          />
        </div>
      </main>
      <footer className="footer">
        <span>Autonomous QA · Local test workspace</span>
        <span>Browser-backed results, one test at a time.</span>
      </footer>
    </div>
  );
}

export default App;
