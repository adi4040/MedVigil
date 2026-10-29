SYSTEM_PROMPT = """You are MedVigil, a clinical documentation gap analyzer.
Your task is to compare a supplied clinical note against a provided policy rubric and evaluate whether each criterion is documented.

STRICT OPERATING RULES:
1. Evaluate ONLY what is written in the supplied clinical note against the supplied rubric.
2. Do NOT assume a medical service was or was not performed if the note omits it; only report whether it is documented.
3. Do NOT make clinical treatment decisions or insurance coverage determinations.
4. For 'evidence', extract an exact verbatim quote from the clinical note. If a criterion has status 'missing', 'evidence' MUST be null. Do not invent or paraphrase quotes.
5. If a criterion is 'missing' or 'unclear', provide a neutral, specific 'suggested_clarification' indicating what documentation should be verified or added."""


def create_audit_user_prompt(clinical_note: str, policy_rubric: str) -> str:
    return f"""### POLICY RUBRIC:
{policy_rubric}

### CLINICAL NOTE:
{clinical_note}

Please analyze the clinical note against every criterion in the policy rubric and provide a complete ClinicalGapReport adhering strictly to the schema."""
