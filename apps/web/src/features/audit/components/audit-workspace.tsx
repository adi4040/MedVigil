"use client";

import { useState } from "react";

import {
  auditRequestSchema,
  type ClinicalGapReport,
} from "@medv/api-client";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Progress,
  Textarea,
} from "@medv/ui";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Clock,
  FileSearch,
  FileText,
  Layers,
  Menu,
  Play,
  RotateCcw,
  ShieldCheck,
  Sliders,
  Sparkles,
  Square,
  Terminal,
  XCircle,
} from "lucide-react";

import { AppSidebar } from "./app-sidebar";
import { sampleClinicalNote, samplePolicyRubric } from "../fixtures";
import { useAuditStream } from "../use-audit-stream";

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
    <div className="space-y-6" data-testid="audit-report">
      <Card className="border-border/80 shadow-xs">
        <CardHeader className="border-b bg-muted/20 pb-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs uppercase tracking-wider font-semibold">
                  Validated Report
                </Badge>
                <span className="text-xs text-muted-foreground font-mono">ID: {report.rubric_id}</span>
              </div>
              <CardTitle className="mt-2 text-2xl font-bold tracking-tight">
                {report.rubric_id}
              </CardTitle>
            </div>
            <div className="flex gap-2">
              <Badge variant="met" className="px-3 py-1 text-xs font-semibold shadow-xs">
                <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                {counts.met} Met
              </Badge>
              <Badge variant="unclear" className="px-3 py-1 text-xs font-semibold shadow-xs">
                <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
                {counts.unclear} Unclear
              </Badge>
              <Badge variant="missing" className="px-3 py-1 text-xs font-semibold shadow-xs">
                <XCircle className="mr-1.5 h-3.5 w-3.5" />
                {counts.missing} Missing
              </Badge>
            </div>
          </div>
        </CardHeader>
      </Card>

      {report.missing_or_unclear_summary.length > 0 && (
        <Alert variant="warning" className="border-amber-500/30 bg-amber-500/10 text-amber-900 shadow-xs">
          <AlertCircle className="h-4 w-4 text-amber-600" />
          <div className="ml-2">
            <AlertTitle className="text-sm font-semibold tracking-wide">
              Physician Clarification Queue ({report.missing_or_unclear_summary.length} items)
            </AlertTitle>
            <AlertDescription className="mt-2">
              <ul className="space-y-1.5 text-xs text-amber-900/90 leading-relaxed">
                {report.missing_or_unclear_summary.map((gap, index) => (
                  <li className="flex items-start gap-2" key={`${index}-${gap}`}>
                    <span className="font-mono font-bold text-amber-700">{String(index + 1).padStart(2, "0")}.</span>
                    <span>{gap}</span>
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </div>
        </Alert>
      )}

      <div className="space-y-4">
        {report.evaluations.map((evaluation, index) => (
          <Card
            className="border-border/80 shadow-xs transition-shadow hover:shadow-sm"
            key={`${index}-${evaluation.criterion}`}
          >
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 p-4 pb-3 border-b bg-muted/15">
              <div className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-xs font-bold font-mono text-muted-foreground">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <CardTitle className="text-base font-semibold text-foreground">
                  {evaluation.criterion}
                </CardTitle>
              </div>
              <Badge variant={evaluation.status} className="px-2.5 py-0.5 text-xs font-semibold capitalize">
                {evaluation.status === "met" && <CheckCircle2 className="mr-1 h-3 w-3" />}
                {evaluation.status === "unclear" && <AlertTriangle className="mr-1 h-3 w-3" />}
                {evaluation.status === "missing" && <XCircle className="mr-1 h-3 w-3" />}
                {evaluation.status}
              </Badge>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              {evaluation.evidence && (
                <div className="rounded-md border-l-4 border-emerald-500 bg-emerald-500/10 p-3 text-sm italic text-foreground">
                  <span className="block text-[10px] font-bold uppercase tracking-wider text-emerald-700 not-italic mb-1">
                    Extracted Verbatim Evidence
                  </span>
                  &ldquo;{evaluation.evidence}&rdquo;
                </div>
              )}

              <p className="text-sm leading-relaxed text-muted-foreground">{evaluation.explanation}</p>

              {evaluation.suggested_clarification && (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-950 flex items-start gap-2.5">
                  <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold block mb-0.5">Recommended Physician Clarification</span>
                    <span>{evaluation.suggested_clarification}</span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function AuditWorkspace() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
    <div className="min-h-screen bg-background flex">
      {/* Sidebar with STAGE 1 Button */}
      <AppSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        activeStage="stage-1"
      />

      {/* Main content viewport */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="border-b bg-card/60 backdrop-blur-md sticky top-0 z-10 px-4 py-3 sm:px-8">
          <div className="mx-auto flex max-w-[1500px] items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden h-9 w-9 mr-1"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
              >
                <Menu className="h-5 w-5" />
              </Button>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground hidden sm:inline">
                  Pipeline:
                </span>
                <Badge variant="secondary" className="gap-1.5 text-xs font-semibold py-1">
                  <FileSearch className="h-3.5 w-3.5" />
                  Stage 1: Medical Gap Analyzer
                </Badge>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-700 text-xs py-1">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                FastAPI Connected
              </Badge>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1500px] w-full px-4 py-6 sm:px-8 flex-1">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,0.92fr)_minmax(520px,1.08fr)]">
            <Card className="border-border shadow-xs">
              <CardHeader className="border-b bg-muted/30 pb-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <Badge variant="secondary" className="text-[11px] font-semibold uppercase tracking-wider">
                      Case Intake
                    </Badge>
                    <CardTitle className="text-2xl font-bold tracking-tight">
                      Test the record against the rule.
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Compare physician encounter documentation against payer authorization criteria.
                    </CardDescription>
                  </div>
                  <Button variant="outline" size="sm" onClick={clearWorkspace} type="button">
                    <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
                    Clear
                  </Button>
                </div>
              </CardHeader>

              <CardContent className="space-y-5 p-5 sm:p-6">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="clinical-note" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5" /> Clinical note
                    </Label>
                    <span className="text-[11px] text-muted-foreground font-mono">{clinicalNote.length} chars</span>
                  </div>
                  <Textarea
                    id="clinical-note"
                    className="min-h-52 font-mono text-xs leading-relaxed resize-y"
                    disabled={active}
                    onChange={(event) => setClinicalNote(event.target.value)}
                    spellCheck={false}
                    value={clinicalNote}
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="policy-rubric" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <BookOpen className="h-3.5 w-3.5" /> Policy rubric
                    </Label>
                    <span className="text-[11px] text-muted-foreground font-mono">{policyRubric.length} chars</span>
                  </div>
                  <Textarea
                    id="policy-rubric"
                    className="min-h-60 font-mono text-xs leading-relaxed resize-y"
                    disabled={active}
                    onChange={(event) => setPolicyRubric(event.target.value)}
                    spellCheck={false}
                    value={policyRubric}
                  />
                </div>

                <div className="rounded-lg border bg-muted/20 p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Sliders className="h-3.5 w-3.5" /> Advanced Settings
                    </span>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="rubric-id" className="text-xs font-medium">Rubric ID</Label>
                      <Input
                        id="rubric-id"
                        className="h-8 text-xs font-mono"
                        disabled={active}
                        onChange={(event) => setRubricId(event.target.value)}
                        value={rubricId}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="temperature" className="text-xs font-medium">Temperature</Label>
                        <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0">
                          {temperature.toFixed(1)}
                        </Badge>
                      </div>
                      <input
                        className="mt-2 w-full accent-primary h-2 bg-muted rounded-lg cursor-pointer"
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
                </div>

                {formError && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription className="ml-2 text-xs font-medium">{formError}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-3 pt-2">
                  <Button
                    size="lg"
                    className="flex-1 font-semibold shadow-xs"
                    disabled={active}
                    onClick={submitAudit}
                    type="button"
                  >
                    {active ? (
                      <>
                        <Sparkles className="mr-2 h-4 w-4 animate-spin" />
                        Evaluating...
                      </>
                    ) : (
                      <>
                        <Play className="mr-2 h-4 w-4" />
                        Start clinical audit
                      </>
                    )}
                  </Button>
                  <Button
                    size="lg"
                    variant="destructive"
                    disabled={!active}
                    onClick={cancel}
                    type="button"
                  >
                    <Square className="mr-2 h-4 w-4" />
                    Stop
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border shadow-xs flex flex-col min-h-[680px]">
              <div className="grid grid-cols-2 divide-x border-b bg-muted/20 sm:grid-cols-4">
                <Metric label="State" value={state.phase} icon={<Activity className="h-3.5 w-3.5 text-muted-foreground" />} />
                <Metric label="First token" value={formatDuration(state.ttftMs)} icon={<Clock className="h-3.5 w-3.5 text-muted-foreground" />} />
                <Metric label="Elapsed" value={formatDuration(elapsedMs)} icon={<Clock className="h-3.5 w-3.5 text-muted-foreground" />} />
                <Metric label="Chunks" value={String(state.chunks)} icon={<Layers className="h-3.5 w-3.5 text-muted-foreground" />} />
              </div>

              <div className="flex items-center gap-3 border-b bg-muted/10 px-5 py-3" aria-live="polite">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    active
                      ? "animate-ping bg-amber-500"
                      : state.phase === "complete"
                      ? "bg-emerald-500"
                      : state.phase === "error"
                      ? "bg-destructive"
                      : "bg-muted-foreground/40"
                  }`}
                  aria-hidden="true"
                />
                <p className="text-xs font-semibold text-foreground">{state.statusMessage}</p>
                {state.retries > 0 && (
                  <Badge variant="outline" className="ml-auto text-[10px] font-mono">
                    Retries: {state.retries}
                  </Badge>
                )}
              </div>

              {active && (
                <div className="px-5 pt-3">
                  <Progress value={state.chunks > 0 ? Math.min(state.chunks * 3, 95) : 10} className="h-1.5" />
                </div>
              )}

              <CardContent className="p-5 sm:p-6 flex-1 flex flex-col">
                {state.phase === "idle" && (
                  <div className="m-auto text-center py-12">
                    <div className="max-w-md space-y-3">
                      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-muted border border-border/80 shadow-xs">
                        <ShieldCheck className="h-7 w-7 text-primary" />
                      </div>
                      <h2 className="text-2xl font-bold tracking-tight text-foreground">
                        Evidence before inference.
                      </h2>
                      <p className="text-sm text-muted-foreground leading-relaxed">
                        Submit the clinical encounter note to stream real-time evaluations against payer guidelines.
                        Only reports that pass complete schema validation are rendered.
                      </p>
                    </div>
                  </div>
                )}

                {(state.phase === "connecting" || state.phase === "streaming") && (
                  <div className="space-y-4 flex-1 flex flex-col">
                    <Alert className="border-primary/20 bg-primary/5">
                      <Sparkles className="h-4 w-4 text-primary animate-spin" />
                      <div className="ml-2">
                        <AlertTitle className="text-xs font-semibold uppercase tracking-wider">
                          Live Evaluation in Progress
                        </AlertTitle>
                        <AlertDescription className="text-sm font-medium">
                          {state.statusMessage}
                        </AlertDescription>
                      </div>
                    </Alert>

                    <div className="rounded-lg border bg-zinc-950 text-zinc-100 overflow-hidden shadow-sm flex-1 flex flex-col">
                      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/80 px-4 py-2.5 text-xs">
                        <span className="flex items-center gap-2 font-mono font-medium text-zinc-400">
                          <Terminal className="h-3.5 w-3.5 text-emerald-400" />
                          Raw Token Stream
                        </span>
                        <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-[10px] font-mono">
                          Streaming Active
                        </Badge>
                      </div>
                      <pre className="flex-1 max-h-[460px] overflow-auto whitespace-pre-wrap p-4 font-mono text-xs leading-relaxed text-zinc-300">
                        {state.rawText || "Connecting to LLM audit stream..."}
                        <span className="inline-block h-3.5 w-1.5 ml-1 bg-emerald-400 animate-pulse align-middle" />
                      </pre>
                    </div>
                  </div>
                )}

                {state.phase === "complete" && state.report && <ReportView report={state.report} />}

                {state.phase === "error" && (
                  <Alert variant="destructive" className="p-6">
                    <XCircle className="h-5 w-5" />
                    <div className="ml-2">
                      <AlertTitle className="text-lg font-bold">No report was accepted.</AlertTitle>
                      <AlertDescription className="mt-2 text-sm leading-relaxed text-destructive-foreground/90">
                        {state.error}
                      </AlertDescription>
                      <Button
                        variant="outline"
                        className="mt-5 border-destructive/40 hover:bg-destructive/10"
                        onClick={reset}
                        type="button"
                      >
                        Reset panel
                      </Button>
                    </div>
                  </Alert>
                )}

                {state.phase === "cancelled" && (
                  <Alert className="p-5">
                    <AlertCircle className="h-5 w-5 text-muted-foreground" />
                    <div className="ml-2">
                      <AlertTitle className="text-base font-bold">The audit was cancelled.</AlertTitle>
                      <AlertDescription className="mt-1 text-sm text-muted-foreground">
                        Partial stream text was discarded and not treated as a clinical report.
                      </AlertDescription>
                    </div>
                  </Alert>
                )}

                {state.rawText && !active && (
                  <details className="mt-6 rounded-lg border bg-muted/20 text-xs">
                    <summary className="cursor-pointer px-4 py-2.5 font-semibold text-muted-foreground hover:text-foreground">
                      Stream Diagnostics & Raw Payloads
                    </summary>
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-border bg-zinc-950 p-4 font-mono text-zinc-300">
                      {state.rawText}
                    </pre>
                  </details>
                )}
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <p className="mt-1 truncate text-lg font-bold font-mono capitalize text-foreground">{value}</p>
    </div>
  );
}
