import { useEffect, useState } from "react";
import { getQaRun, getRunArtifacts, startQaRun } from "../api/qa";
import type { Artifact, Run, StartRunInput } from "../api/types";

export function useQaRun() {
  const [submitting, setSubmitting] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    const currentRunId = runId;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const next = await getQaRun(currentRunId, controller.signal);
        if (controller.signal.aborted) return;
        setRun(next);
        setError(null);
        if (next.status === "queued" || next.status === "running") {
          timer = setTimeout(poll, 1200);
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(
          cause instanceof Error ? cause.message : "Could not load run status",
        );
        timer = setTimeout(poll, 3000);
      }
    }

    void poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (!run || run.status !== "completed") return;
    const controller = new AbortController();
    const completedRunId = run.run_id;

    async function loadArtifacts() {
      try {
        const next = await getRunArtifacts(completedRunId, controller.signal);
        if (!controller.signal.aborted) setArtifacts(next);
      } catch {
        // The report remains available even if artifact listing fails.
      }
    }

    void loadArtifacts();
    return () => controller.abort();
  }, [run]);

  async function startRun(input: StartRunInput) {
    setSubmitting(true);
    setError(null);
    setRun(null);
    setRunId(null);
    setArtifacts([]);
    try {
      const accepted = await startQaRun(input);
      setRunId(accepted.run_id);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not start the run",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return {
    runId,
    run,
    artifacts,
    error,
    submitting,
    active: run?.status === "queued" || run?.status === "running",
    startRun,
  };
}
