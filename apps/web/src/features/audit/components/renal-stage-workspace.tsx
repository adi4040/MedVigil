"use client";

import { useState, type FormEvent } from "react";

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
  Label,
  Textarea,
} from "@medv/ui";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  Play,
  RotateCcw,
  Terminal,
  XCircle,
} from "lucide-react";

type RenalSafetyVerdict = "safe" | "dose_adjustment_required" | "insufficient_data";

interface RenalAuditReport {
  patient_id: string;
  medication_name: string;
  prescribed_daily_dose_mg: number | null;
  required_renal_metric: "crcl" | "egfr" | null;
  renal_metric_value: number | null;
  verdict: RenalSafetyVerdict;
  lab_warning: string | null;
  rationale: string;
  tool_trace: string[];
}

const SAMPLE_GABAPENTIN_JSON = JSON.stringify(
  {
    patient_id: "patient-001",
    medication_name: "Gabapentin",
    prescribed_daily_dose_mg: 1800,
    regimen: "600 mg PO TID",
  },
  null,
  2,
);

const SAMPLE_METFORMIN_JSON = JSON.stringify(
  {
    patient_id: "patient-001",
    medication_name: "Metformin",
    prescribed_daily_dose_mg: 2000,
    regimen: "1000 mg PO BID",
  },
  null,
  2,
);

function getVerdictStyle(verdict: RenalSafetyVerdict) {
  switch (verdict) {
    case "safe":
      return {
        label: "Safe",
        badgeClass: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700",
        Icon: CheckCircle2,
      };
    case "dose_adjustment_required":
      return {
        label: "Dose Adjustment Required",
        badgeClass: "border-rose-500/30 bg-rose-500/15 text-rose-700",
        Icon: XCircle,
      };
    case "insufficient_data":
    default:
      return {
        label: "Insufficient Data",
        badgeClass: "border-amber-500/30 bg-amber-500/15 text-amber-700",
        Icon: AlertTriangle,
      };
  }
}

export function RenalStageWorkspace() {
  const [dischargeJson, setDischargeJson] = useState(SAMPLE_GABAPENTIN_JSON);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<RenalAuditReport | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = dischargeJson.trim();
    if (!trimmed) {
      setError("Please provide a discharge JSON payload.");
      return;
    }

    try {
      JSON.parse(trimmed);
    } catch {
      setError("Discharge input must be valid JSON.");
      return;
    }

    setError(null);
    setLoading(true);
    setReport(null);

    try {
      const response = await fetch("/api/v1/renal/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ discharge_json: trimmed }),
      });

      if (!response.ok) {
        const errBody = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errBody?.detail ?? `Request failed with status ${response.status}`);
      }

      const data = (await response.json()) as RenalAuditReport;
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run renal safety audit.");
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setDischargeJson("");
    setError(null);
    setReport(null);
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.92fr)_minmax(520px,1.08fr)]">
      {/* Left: Inputs */}
      <Card className="border-border shadow-xs">
        <CardHeader className="border-b bg-muted/30 pb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-1">
              <Badge variant="secondary" className="text-[11px] font-semibold uppercase tracking-wider">
                Pharmacokinetic Intake
              </Badge>
              <CardTitle className="text-2xl font-bold tracking-tight">
                Verify renal dosing safety.
              </CardTitle>
              <CardDescription className="text-xs">
                Submit discharge medication JSON to run the Stage 2 Gemini tool-calling agent.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={handleClear} type="button" disabled={loading}>
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
              Clear
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-5 sm:p-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">Load sample:</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                disabled={loading}
                onClick={() => {
                  setDischargeJson(SAMPLE_GABAPENTIN_JSON);
                  setError(null);
                }}
              >
                Gabapentin (CrCl)
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                disabled={loading}
                onClick={() => {
                  setDischargeJson(SAMPLE_METFORMIN_JSON);
                  setError(null);
                }}
              >
                Metformin (eGFR)
              </Button>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label
                  htmlFor="discharge-json"
                  className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5"
                >
                  <FlaskConical className="h-3.5 w-3.5" /> Discharge JSON
                </Label>
                <span className="text-[11px] text-muted-foreground font-mono">
                  {dischargeJson.length} chars
                </span>
              </div>
              <Textarea
                id="discharge-json"
                className="min-h-64 font-mono text-xs leading-relaxed resize-y"
                disabled={loading}
                onChange={(event) => setDischargeJson(event.target.value)}
                spellCheck={false}
                value={dischargeJson}
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle className="text-xs font-semibold">Validation / API Error</AlertTitle>
                <AlertDescription className="text-xs">{error}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              <Play className="h-4 w-4 mr-2" />
              {loading ? "Running Renal Safety Audit..." : "Run Renal Safety Audit"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Right: Outputs */}
      <Card className="border-border shadow-xs">
        <CardHeader className="border-b bg-muted/30 pb-4">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Badge variant="outline" className="text-[11px] font-semibold uppercase tracking-wider">
                Agent Output
              </Badge>
              <CardTitle className="text-xl font-bold tracking-tight">
                Renal Audit Report
              </CardTitle>
              <CardDescription className="text-xs">
                Deterministic Cockcroft-Gault / eGFR verification &amp; guideline check.
              </CardDescription>
            </div>
            {report && (
              <Badge variant="outline" className={`px-3 py-1 text-xs font-semibold ${getVerdictStyle(report.verdict).badgeClass}`}>
                {getVerdictStyle(report.verdict).label}
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="p-5 sm:p-6">
          {!report && !loading && (
            <div className="rounded-xl border border-dashed border-border bg-muted/20 p-8 text-center space-y-2">
              <FlaskConical className="h-8 w-8 mx-auto text-muted-foreground/70" />
              <p className="text-sm font-semibold text-foreground">
                Ready for Stage 2 Renal Verification
              </p>
              <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
                Submit a discharge JSON payload to inspect the medication&apos;s required renal metric,
                fetch patient labs, compute Cockcroft-Gault CrCl when needed, and verify dose safety.
              </p>
            </div>
          )}

          {loading && (
            <div className="rounded-xl border border-border bg-muted/20 p-8 text-center space-y-2">
              <p className="text-sm font-semibold text-foreground animate-pulse">
                Executing Stage 2 Tool-Calling Loop...
              </p>
              <p className="text-xs text-muted-foreground">
                Querying guidelines, patient labs, and renal clearance calculations.
              </p>
            </div>
          )}

          {report && (
            <div className="space-y-5" data-testid="renal-report">
              {report.lab_warning && (
                <Alert variant="warning" className="border-amber-500/30 bg-amber-500/10 text-amber-900">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <AlertTitle className="text-xs font-semibold">Lab Warning</AlertTitle>
                  <AlertDescription className="text-xs">{report.lab_warning}</AlertDescription>
                </Alert>
              )}

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-lg border bg-muted/20 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Patient ID
                  </p>
                  <p className="mt-1 text-xs font-mono font-semibold text-foreground truncate">
                    {report.patient_id}
                  </p>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Medication
                  </p>
                  <p className="mt-1 text-xs font-semibold text-foreground truncate">
                    {report.medication_name}
                  </p>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Daily Dose
                  </p>
                  <p className="mt-1 text-xs font-mono font-semibold text-foreground">
                    {report.prescribed_daily_dose_mg !== null ? `${report.prescribed_daily_dose_mg} mg` : "--"}
                  </p>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Required Metric
                  </p>
                  <p className="mt-1 text-xs font-mono uppercase font-semibold text-foreground">
                    {report.required_renal_metric ?? "--"}
                  </p>
                </div>
                <div className="rounded-lg border bg-muted/20 p-3 col-span-2 sm:col-span-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Verified Metric Value
                  </p>
                  <p className="mt-1 text-xs font-mono font-semibold text-foreground">
                    {report.renal_metric_value !== null ? `${report.renal_metric_value} mL/min` : "--"}
                  </p>
                </div>
              </div>

              <div className="rounded-lg border bg-card p-4 space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Clinical Rationale
                </p>
                <p className="text-sm text-foreground leading-relaxed">{report.rationale}</p>
              </div>

              <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Terminal className="h-3.5 w-3.5" /> Tool Execution Trace ({report.tool_trace.length})
                </p>
                {report.tool_trace.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No tool calls recorded.</p>
                ) : (
                  <ol className="space-y-1 text-xs font-mono text-foreground">
                    {report.tool_trace.map((step, idx) => (
                      <li key={`${idx}-${step}`} className="flex items-start gap-2">
                        <span className="text-muted-foreground">{idx + 1}.</span>
                        <span className="break-all">{step}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
