"use client";

export default function GlobalError(props: { error: Error & { digest?: string }; reset: () => void }) {
  const { error, reset } = props;
  return (
    <main className="pv-shell">
      <section className="pv-panel">
        <h2>Page Error</h2>
        <p className="pv-error">A route failed to render. Try again.</p>
        <p className="pv-muted">{error.message || "Unknown error"}</p>
        <button type="button" onClick={reset}>
          Retry
        </button>
      </section>
    </main>
  );
}
