"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ background: "#0f172a", color: "#e2e8f0", padding: "2rem", fontFamily: "sans-serif" }}>
        <h2 style={{ marginBottom: "0.75rem" }}>Dashboard error</h2>
        <p style={{ color: "#94a3b8", marginBottom: "1rem" }}>
          {error.message || "A critical error occurred."}
        </p>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            background: "#3b82f6",
            color: "white",
            border: "none",
            borderRadius: "6px",
            padding: "0.5rem 1rem",
            cursor: "pointer",
          }}
        >
          Reload dashboard
        </button>
      </body>
    </html>
  );
}
