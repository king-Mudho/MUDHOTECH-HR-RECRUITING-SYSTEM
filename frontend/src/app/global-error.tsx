"use client";

/**
 * Last-resort boundary when the root layout itself fails. No providers or i18n are available
 * here, so the copy is inline (English).
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{ fontFamily: "system-ui, sans-serif", padding: "4rem 1rem", textAlign: "center" }}
      >
        <main>
          <h1>Something went wrong on our side</h1>
          <p>
            Please try again. If the problem continues, contact support and quote the reference
            below.
          </p>
          {error.digest ? (
            <p style={{ fontFamily: "monospace" }}>Reference: {error.digest}</p>
          ) : null}
          <button type="button" onClick={reset} style={{ minHeight: 40, padding: "0 1rem" }}>
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
