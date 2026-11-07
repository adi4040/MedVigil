import { describe, expect, it } from "vitest";

import { auditReducer, initialAuditState } from "./audit-reducer";

const report = {
  rubric_id: "MRI_TEST",
  evaluations: [
    {
      criterion: "Symptoms and Duration",
      evidence: "Back pain for eight weeks",
      explanation: "The duration is documented.",
      status: "met" as const,
      suggested_clarification: null,
    },
  ],
  missing_or_unclear_summary: [],
};

describe("auditReducer", () => {
  it("tracks status, first-token timing, and a validated report", () => {
    const connecting = auditReducer(initialAuditState, { type: "start" });
    const status = auditReducer(connecting, {
      type: "status",
      message: "Evaluating clinical note against rubric...",
    });
    const streaming = auditReducer(status, {
      type: "token",
      text: '{"rubric_id":',
      ttftMs: 325,
    });
    const complete = auditReducer(streaming, { type: "done", report });

    expect(status.statusMessage).toContain("Evaluating");
    expect(streaming.phase).toBe("streaming");
    expect(streaming.ttftMs).toBe(325);
    expect(streaming.chunks).toBe(1);
    expect(complete.phase).toBe("complete");
    expect(complete.report).toEqual(report);
  });

  it("never keeps a previous report after a new failure", () => {
    const complete = auditReducer(initialAuditState, { type: "done", report });
    const restarted = auditReducer(complete, { type: "start" });
    const failed = auditReducer(restarted, { type: "error", message: "Provider unavailable" });

    expect(restarted.report).toBeNull();
    expect(failed.report).toBeNull();
    expect(failed.phase).toBe("error");
  });

  it("marks cancellation without treating partial JSON as a report", () => {
    const streaming = auditReducer(
      auditReducer(initialAuditState, { type: "start" }),
      { type: "token", text: "partial" },
    );
    const cancelled = auditReducer(streaming, { type: "cancel" });

    expect(cancelled.phase).toBe("cancelled");
    expect(cancelled.report).toBeNull();
    expect(cancelled.rawText).toBe("partial");
  });
});
