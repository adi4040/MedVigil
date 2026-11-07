import { z } from "zod";

export const criterionStatusSchema = z.enum(["met", "missing", "unclear"]);

export const criterionEvaluationSchema = z.object({
  criterion: z.string(),
  evidence: z.string().nullable().optional(),
  explanation: z.string(),
  status: criterionStatusSchema,
  suggested_clarification: z.string().nullable().optional(),
});

export const clinicalGapReportSchema = z.object({
  rubric_id: z.string(),
  evaluations: z.array(criterionEvaluationSchema),
  missing_or_unclear_summary: z.array(z.string()),
});

export const auditRequestSchema = z.object({
  clinical_note: z.string().trim().min(1, "Clinical note is required."),
  policy_rubric: z.string().trim().min(1, "Policy rubric is required."),
  rubric_id: z.string().trim().optional(),
  temperature: z.number().min(0).max(2).default(0),
});

export const streamChunkSchema = z.object({
  event: z.enum(["status", "token", "done", "error"]),
  message: z.string().nullable().optional(),
  text: z.string().nullable().optional(),
  report: clinicalGapReportSchema.nullable().optional(),
  error: z.string().nullable().optional(),
  retries: z.number().int().nonnegative().nullable().optional(),
  request_id: z.string().nullable().optional(),
});

export type AuditRequest = z.infer<typeof auditRequestSchema>;
export type ClinicalGapReport = z.infer<typeof clinicalGapReportSchema>;
export type CriterionEvaluation = z.infer<typeof criterionEvaluationSchema>;
export type CriterionStatus = z.infer<typeof criterionStatusSchema>;
export type StreamChunk = z.infer<typeof streamChunkSchema>;
