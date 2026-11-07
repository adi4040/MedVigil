import type { ClinicalGapReport } from "@medv/api-client";

export type AuditPhase =
  | "idle"
  | "connecting"
  | "streaming"
  | "complete"
  | "error"
  | "cancelled";

export interface AuditState {
  phase: AuditPhase;
  statusMessage: string;
  rawText: string;
  report: ClinicalGapReport | null;
  error: string | null;
  chunks: number;
  retries: number;
  ttftMs: number | null;
}

export const initialAuditState: AuditState = {
  phase: "idle",
  statusMessage: "Ready for review",
  rawText: "",
  report: null,
  error: null,
  chunks: 0,
  retries: 0,
  ttftMs: null,
};

export type AuditAction =
  | { type: "start" }
  | { type: "status"; message: string; retries?: number }
  | { type: "token"; text: string; ttftMs?: number }
  | { type: "done"; report: ClinicalGapReport; retries?: number }
  | { type: "error"; message: string }
  | { type: "cancel" }
  | { type: "reset" };

export function auditReducer(state: AuditState, action: AuditAction): AuditState {
  switch (action.type) {
    case "start":
      return {
        ...initialAuditState,
        phase: "connecting",
        statusMessage: "Connecting to the audit service",
      };
    case "status":
      return {
        ...state,
        statusMessage: action.message,
        retries: Math.max(state.retries, action.retries ?? 0),
      };
    case "token":
      return {
        ...state,
        phase: "streaming",
        statusMessage: "Receiving structured analysis",
        rawText: state.rawText + action.text,
        chunks: state.chunks + 1,
        ttftMs: state.ttftMs ?? action.ttftMs ?? null,
      };
    case "done":
      return {
        ...state,
        phase: "complete",
        statusMessage: "Audit complete",
        report: action.report,
        error: null,
        retries: Math.max(state.retries, action.retries ?? 0),
      };
    case "error":
      return {
        ...state,
        phase: "error",
        statusMessage: "Audit could not be completed",
        report: null,
        error: action.message,
      };
    case "cancel":
      return {
        ...state,
        phase: "cancelled",
        statusMessage: "Audit cancelled",
        report: null,
        error: null,
      };
    case "reset":
      return initialAuditState;
    default:
      return state;
  }
}
