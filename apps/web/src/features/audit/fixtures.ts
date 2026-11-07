export const sampleClinicalNote = `Chief Complaint:
Patient reports lower-back pain for eight weeks.

Clinical Findings:
Persistent pain reported. Detailed neurological examination findings are not included.

Previous Treatment:
Treatment history is not documented.

Plan:
MRI of the lumbar spine requested.`;

export const samplePolicyRubric = `RUBRIC ID: MRI_PA_001
PROCEDURE: MRI Lumbar Spine (Without Contrast)
PURPOSE: Evaluate whether the clinical note documents the required evidence for medical-necessity review.

CRITERIA TO EVALUATE:

1. Symptoms and Duration
- Requirement: The note must document the patient's primary lumbar/back symptoms AND the specific duration of those symptoms.
- Unclear condition: Symptoms are mentioned without a measurable timeframe.

2. Physical Examination Findings
- Requirement: The note must document objective physical or neurological findings relevant to the lumbar spine.
- Unclear condition: An examination is referenced without specific findings.

3. Previous Diagnostic Testing
- Requirement: The note must document lumbar X-ray results or a clinical reason prior imaging is unnecessary.
- Unclear condition: Prior imaging is referenced but its findings are unavailable.

4. Conservative Treatment History
- Requirement: Document at least 6 weeks of provider-directed conservative therapy and response, or an acute clinical exception.
- Unclear condition: Therapy is mentioned without duration, adherence, or outcome.

5. Clinical Indication and Medical Necessity
- Requirement: State the diagnostic reason or suspected pathology for the lumbar MRI.
- Unclear condition: The note only states that an MRI was requested.`;
