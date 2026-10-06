import { useState, type FormEvent } from "react";
import type { Provider, StartRunInput } from "../api/types";
import "./RunForm.css";

type RunFormProps = {
  active: boolean;
  submitting: boolean;
  onStart: (input: StartRunInput) => Promise<void>;
};

export function RunForm({ active, submitting, onStart }: RunFormProps) {
  const [url, setUrl] = useState("");
  const [request, setRequest] = useState("");
  const [provider, setProvider] = useState<Provider>("gemini");
  const disabled = submitting || active;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onStart({ url, request, provider });
  }

  return (
    <section className="panel setup-panel" aria-labelledby="setup-heading">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">01 / SETUP</p>
          <h2 id="setup-heading">New test run</h2>
        </div>
        <span className="panel-symbol" aria-hidden="true">↗</span>
      </div>

      <form onSubmit={submit}>
        <label htmlFor="site-url">Website URL</label>
        <input
          id="site-url"
          type="url"
          inputMode="url"
          placeholder="https://example.com"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          required
          disabled={disabled}
        />
        <p className="field-help">The page where the test run begins.</p>

        <label htmlFor="test-request">What would you like to test?</label>
        <textarea
          id="test-request"
          rows={5}
          maxLength={2000}
          placeholder="E.g. Check basic navigation and whether the main menu opens"
          value={request}
          onChange={(event) => setRequest(event.target.value)}
          disabled={disabled}
        />
        <p className="field-help">
          Leave blank for the deterministic page-load and title checks.
        </p>

        <label htmlFor="provider">AI provider</label>
        <select
          id="provider"
          value={provider}
          onChange={(event) => setProvider(event.target.value as Provider)}
          disabled={disabled}
        >
          <option value="gemini">Gemini</option>
          <option value="openai">OpenAI</option>
          <option value="cohere">Cohere</option>
        </select>
        <p className="field-help">Only used when you enter a test request.</p>

        <button className="run-button" type="submit" disabled={disabled}>
          <span>
            {submitting
              ? "Starting…"
              : active
                ? "Run in progress…"
                : "Start test run"}
          </span>
          <span aria-hidden="true">→</span>
        </button>
      </form>
    </section>
  );
}
