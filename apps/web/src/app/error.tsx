"use client";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--paper)] px-6">
      <section className="max-w-lg border border-[var(--ink)] bg-white p-8 shadow-[8px_8px_0_var(--citrine)]">
        <p className="eyebrow">Application error</p>
        <h1 className="mt-3 font-[var(--font-display)] text-4xl text-[var(--ink)]">
          The audit workspace could not be displayed.
        </h1>
        <button className="button-primary mt-6" onClick={reset} type="button">
          Try again
        </button>
      </section>
    </main>
  );
}
