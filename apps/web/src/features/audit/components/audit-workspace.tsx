"use client";

import { useState } from "react";

import {
  auditRequestSchema,
  type ClinicalGapReport,
  type CriterionStatus,
} from "@medv/api-client";

import { sampleClinicalNote, samplePolicyRubric } from "../fixtures";
import { useAuditStream } from "../use-audit-stream";

const statusStyles: Record<CriterionStatus, string> = {
  met: "border-[#4d9078] bg-[#dff2e9] text-[#245743]",
  unclear: "border-[#b59b28] bg-[#fff7c7] text-[#6c5b0e]",
  missing: "border-[#cc5945] bg-[#ffe1da] text-[#7e2d20]",
};

function formatDuration(milliseconds: number | null): string {
  if (milliseconds === null) return "--";
  return `${(milliseconds / 1000).toFixed(2)}s`;
}

function ReportView({ report }: { report: ClinicalGapReport }) {
  const counts = report.evaluations.reduce(
    (current, evaluation) => ({
      ...current,
      [evaluation.status]: current[evaluation.status] + 1,
    }),
    { met: 0, unclear: 0, missing: 0 },
  );

  return (
    <div className="space-y-5" data-testid="audit-report">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--line)] pb-4">
        <div>
          <p className="eyebrow">Validated report</p>
          <h2 className="mt-1 font-[var(--font-display)] text-3xl">{report.rubric_id}</h2>
        </div>
        <div className="flex gap-2 text-xs font-bold uppercase tracking-wide">
          <span className="border border-[#4d9078] bg-[#dff2e9] px-2 py-1">{counts.met} met</span>
          <span className="border border-[#b59b28] bg-[#fff7c7] px-2 py-1">{counts.unclear} unclear</span>
          <span className="border border-[#cc5945] bg-[#ffe1da] px-2 py-1">{counts.missing} missing</span>
        </div>
      </div>

      {report.missing_or_unclear_summary.length > 0 && (
        <section className="border-l-4 border-[var(--coral)] bg-[#fff8f1] p-4">
          <h3 className="text-sm font-extrabold uppercase tracking-wide">Clarification queue</h3>
          <ul className="mt-2 space-y-2 text-sm text-[var(--ink-soft)]">
            {report.missing_or_unclear_summary.map((gap, index) => (
              <li className="flex gap-2" key={`${index}-${gap}`}>
                <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="space-y-3">
        {report.evaluations.map((evaluation, index) => (
          <article className="border border-[var(--line)] bg-white/75 p-4" key={`${index}-${evaluation.criterion}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex gap-3">
                <span className="font-[var(--font-display)] text-2xl text-[var(--ink-soft)]">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="pt-1 font-bold">{evaluation.criterion}</h3>
              </div>
              <span className={`border px-2 py-1 text-[0.65rem] font-extrabold uppercase tracking-wider ${statusStyles[evaluation.status]}`}>
                {evaluation.status}
              </span>
            </div>

            {evaluation.evidence && (
              <blockquote className="mt-4 border-l-2 border-[var(--mint)] pl-3 font-[var(--font-display)] text-lg italic text-[var(--ink-soft)]">
                &ldquo;{evaluation.evidence}&rdquo;
              </blockquote>
            )}

            <p className="mt-3 text-sm leading-6 text-[var(--ink-soft)]">{evaluation.explanation}</p>

            {evaluation.suggested_clarification && (
              <p className="mt-3 bg-[var(--paper)] px-3 py-2 text-sm">
                <strong>Request:</strong> {evaluation.suggested_clarification}
              </p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

export function AuditWorkspace() {
  const [clinicalNote, setClinicalNote] = useState(sampleClinicalNote);
  const [policyRubric, setPolicyRubric] = useState(samplePolicyRubric);
  const [rubricId, setRubricId] = useState("MRI_PA_001");
  const [temperature, setTemperature] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const { state, elapsedMs, active, start, cancel, reset } = useAuditStream();

  function submitAudit() {
    const parsed = auditRequestSchema.safeParse({
      clinical_note: clinicalNote,
      policy_rubric: policyRubric,
      rubric_id: rubricId.trim() || undefined,
      temperature,
    });

    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Review the audit inputs.");
      return;
    }

    setFormError(null);
    void start(parsed.data);
  }

  function clearWorkspace() {
    if (active) cancel();
    setClinicalNote("");
    setPolicyRubric("");
    setRubricId("");
    setFormError(null);
    reset();
  }

  return (
    <main className="min-h-screen px-4 py-5 sm:px-7 lg:px-10 lg:py-8">
      <header className="mx-auto flex max-w-[1500px] items-center justify-between border-b border-[var(--ink)] pb-4">
        <div className="flex items-baseline gap-3">
          <span className="font-[var(--font-display)] text-3xl font-bold">MedVigil</span>
          <span className="hidden text-xs font-bold uppercase tracking-[0.18em] text-[var(--ink-soft)] sm:inline">
            Documentation Review Desk
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide">
          <span className="h-2 w-2 bg-[#3e9a73]" aria-hidden="true" />
          FastAPI connected
        </div>
      </header>

      <section className="mx-auto mt-7 grid max-w-[1500px] gap-6 xl:grid-cols-[minmax(0,0.92fr)_minmax(520px,1.08fr)]">
        <div className="border border-[var(--ink)] bg-[var(--paper)] shadow-[7px_7px_0_var(--ink)]">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--ink)] bg-[var(--citrine)] p-5">
            <div>
              <p className="eyebrow">Case intake</p>
              <h1 className="mt-1 max-w-xl font-[var(--font-display)] text-4xl leading-none sm:text-5xl">
                Test the record against the rule.
              </h1>
            </div>
            <button className="button-secondary bg-white/50" onClick={clearWorkspace} type="button">
              Clear
            </button>
          </div>

          <div className="space-y-5 p-5 sm:p-6">
            <div>
              <label className="field-label" htmlFor="clinical-note">Clinical note</label>
              <textarea
                className="field-control min-h-52 resize-y text-sm leading-6"
                disabled={active}
                id="clinical-note"
                onChange={(event) => setClinicalNote(event.target.value)}
                spellCheck={false}
                value={clinicalNote}
              />
              <p className="mt-1 text-right text-xs text-[var(--ink-soft)]">{clinicalNote.length} characters</p>
            </div>

            <div>
              <label className="field-label" htmlFor="policy-rubric">Policy rubric</label>
              <textarea
                className="field-control min-h-64 resize-y text-sm leading-6"
                disabled={active}
                id="policy-rubric"
                onChange={(event) => setPolicyRubric(event.target.value)}
                spellCheck={false}
                value={policyRubric}
              />
              <p className="mt-1 text-right text-xs text-[var(--ink-soft)]">{policyRubric.length} characters</p>
            </div>

            <details className="border-y border-[var(--line)] py-3">
              <summary className="cursor-pointer text-xs font-extrabold uppercase tracking-[0.14em]">
                Advanced settings
              </summary>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="field-label" htmlFor="rubric-id">Rubric ID</label>
                  <input
                    className="field-control"
                    disabled={active}
                    id="rubric-id"
                    onChange={(event) => setRubricId(event.target.value)}
                    value={rubricId}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="temperature">Temperature: {temperature.toFixed(1)}</label>
                  <input
                    className="mt-3 w-full accent-[var(--coral)]"
                    disabled={active}
                    id="temperature"
                    max="2"
                    min="0"
                    onChange={(event) => setTemperature(Number(event.target.value))}
                    step="0.1"
                    type="range"
                    value={temperature}
                  />
                </div>
              </div>
            </details>

            {formError && (
              <p className="border-l-4 border-[var(--coral)] bg-[#ffe1da] px-3 py-2 text-sm" role="alert">
                {formError}
              </p>
            )}

            <div className="flex flex-wrap gap-3">
              <button className="button-primary flex-1" disabled={active} onClick={submitAudit} type="button">
                Start clinical audit
              </button>
              <button className="button-secondary" disabled={!active} onClick={cancel} type="button">
                Stop
              </button>
            </div>
          </div>
        </div>

        <section className="min-h-[680px] border border-[var(--ink)] bg-white/65">
          <div className="grid grid-cols-2 border-b border-[var(--ink)] sm:grid-cols-4">
            <Metric label="State" value={state.phase} />
            <Metric label="First token" value={formatDuration(state.ttftMs)} />
            <Metric label="Elapsed" value={formatDuration(elapsedMs)} />
            <Metric label="Chunks" value={String(state.chunks)} />
          </div>

          <div className="flex items-center gap-3 border-b border-[var(--line)] bg-white/75 px-5 py-3" aria-live="polite">
            <span className={`h-2.5 w-2.5 ${active ? "animate-pulse bg-[var(--coral)]" : state.phase === "complete" ? "bg-[#3e9a73]" : "bg-[var(--ink-soft)]"}`} aria-hidden="true" />
            <p className="text-sm font-bold">{state.statusMessage}</p>
            {state.retries > 0 && <span className="ml-auto text-xs">Retries: {state.retries}</span>}
          </div>

          <div className="p-5 sm:p-6">
            {state.phase === "idle" && (
              <div className="grid min-h-[520px] place-items-center text-center">
                <div className="max-w-sm">
                  <span className="mx-auto grid h-20 w-20 place-items-center border border-[var(--ink)] bg-[var(--mint)] font-[var(--font-display)] text-4xl shadow-[5px_5px_0_var(--ink)]" aria-hidden="true">
                    Rx
                  </span>
                  <h2 className="mt-7 font-[var(--font-display)] text-3xl">Evidence before inference.</h2>
                  <p className="mt-3 text-sm leading-6 text-[var(--ink-soft)]">
                    Submit the note to receive a criterion-by-criterion documentation review. The final panel only renders validated output.
                  </p>
                </div>
              </div>
            )}

            {(state.phase === "connecting" || state.phase === "streaming") && (
              <div className="space-y-5">
                <div className="border-l-4 border-[var(--citrine)] bg-[var(--paper)] p-4">
                  <p className="eyebrow">Live evaluation</p>
                  <p className="mt-2 font-[var(--font-display)] text-2xl">{state.statusMessage}</p>
                </div>
                <details className="border border-[var(--line)] bg-[#15282a] text-[#dce8df]" open={state.phase === "streaming"}>
                  <summary className="cursor-pointer px-4 py-3 text-xs font-bold uppercase tracking-wider">Raw structured stream</summary>
                  <pre className="max-h-[460px] overflow-auto whitespace-pre-wrap border-t border-white/15 p-4 text-xs leading-5">
                    {state.rawText || "Waiting for the first provider chunk..."}
                  </pre>
                </details>
              </div>
            )}

            {state.phase === "complete" && state.report && <ReportView report={state.report} />}

            {state.phase === "error" && (
              <div className="border border-[#cc5945] bg-[#ffe1da] p-5" role="alert">
                <p className="eyebrow">Evaluation failed</p>
                <h2 className="mt-2 font-[var(--font-display)] text-3xl">No report was accepted.</h2>
                <p className="mt-3 text-sm leading-6">{state.error}</p>
                <button className="button-secondary mt-5 bg-white/50" onClick={reset} type="button">Reset panel</button>
              </div>
            )}

            {state.phase === "cancelled" && (
              <div className="border border-[var(--line)] bg-[var(--paper)] p-5">
                <p className="eyebrow">Request stopped</p>
                <h2 className="mt-2 font-[var(--font-display)] text-3xl">The audit was cancelled.</h2>
                <p className="mt-3 text-sm text-[var(--ink-soft)]">Partial stream text was not treated as a clinical report.</p>
              </div>
            )}

            {state.rawText && !active && (
              <details className="mt-6 border border-[var(--line)]">
                <summary className="cursor-pointer px-4 py-3 text-xs font-bold uppercase tracking-wider">Stream diagnostics</summary>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-[var(--line)] bg-[#15282a] p-4 text-xs text-[#dce8df]">
                  {state.rawText}
                </pre>
              </details>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-r border-[var(--ink)] px-4 py-3 last:border-r-0">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 truncate font-[var(--font-display)] text-xl capitalize">{value}</p>
    </div>
  );
}
