import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.audit import (
    ClinicalGapReport,
    CriterionEvaluation,
    CriterionStatus,
)
from app.services.llm_client import (
    MockAuditClient,
    get_configured_llm_client,
    get_llm_client,
)


def test_criterion_evaluation_valid_met():
    eval_item = CriterionEvaluation(
        criterion="Symptoms and Duration",
        status=CriterionStatus.MET,
        evidence="Back pain for 6 weeks",
        explanation="Duration and symptoms are clearly documented.",
        suggested_clarification=None,
    )
    assert eval_item.status == CriterionStatus.MET
    assert eval_item.evidence == "Back pain for 6 weeks"
    assert eval_item.suggested_clarification is None


def test_criterion_evaluation_missing_sanitizes_evidence():
    eval_item = CriterionEvaluation(
        criterion="Previous Diagnostic Testing",
        status=CriterionStatus.MISSING,
        evidence="Some quote stating not performed",
        explanation="Not documented",
        suggested_clarification="Order X-ray",
    )
    assert eval_item.evidence is None


def test_criterion_evaluation_met_sanitizes_clarification():
    eval_item = CriterionEvaluation(
        criterion="Physical Examination Findings",
        status=CriterionStatus.MET,
        evidence="Exam normal",
        explanation="Documented fully",
        suggested_clarification="Unnecessary clarification",
    )
    assert eval_item.suggested_clarification is None


def test_mock_llm_client_generates_valid_report():
    client = MockAuditClient()
    note = "Patient presents with persistent lower-back pain for eight weeks. Examination completed."
    rubric = "RUBRIC ID: MRI_PA_001\n1. Symptoms and Duration"

    report = client.evaluate_audit(note, rubric)
    assert isinstance(report, ClinicalGapReport)
    assert report.rubric_id == "MRI_PA_001"
    assert len(report.evaluations) > 0
    assert len(report.missing_or_unclear_summary) > 0


def test_get_llm_client_factory_mock():
    client = get_llm_client("mock")
    assert isinstance(client, MockAuditClient)


def test_get_llm_client_invalid_provider():
    with pytest.raises(ValueError) as exc:
        get_llm_client("invalid_provider")
    assert "Unsupported LLM provider" in str(exc.value)


def test_provider_selection_is_not_exposed_in_openapi():
    operation = app.openapi()["paths"]["/api/v1/audit/evaluate/stream"]["post"]
    parameter_names = {parameter["name"] for parameter in operation.get("parameters", [])}
    assert "provider" not in parameter_names


def test_audit_evaluate_endpoint_success(client: TestClient):
    app.dependency_overrides[get_configured_llm_client] = lambda: MockAuditClient()

    payload = {
        "clinical_note": "Patient presents with lower-back pain for eight weeks. Neurological exam not included.",
        "policy_rubric": "RUBRIC ID: MRI_PA_001\nCRITERIA TO EVALUATE:\n1. Symptoms and Duration",
        "rubric_id": "MRI_PA_001",
    }
    response = client.post("/api/v1/audit/evaluate", json=payload)
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["rubric_id"] == "MRI_PA_001"
    assert isinstance(data["evaluations"], list)
    assert len(data["evaluations"]) > 0
    assert "missing_or_unclear_summary" in data


def test_audit_evaluate_endpoint_validation_error(client: TestClient):
    # Missing required 'policy_rubric'
    payload = {
        "clinical_note": "Just a note without rubric",
    }
    response = client.post("/api/v1/audit/evaluate", json=payload)
    assert response.status_code == 422


def test_audit_evaluate_endpoint_runtime_error_mapping(client: TestClient):
    class ErrorLLMClient:
        def evaluate_audit(self, *args, **kwargs):
            raise RuntimeError("LLM rate limit reached")

    app.dependency_overrides[get_configured_llm_client] = lambda: ErrorLLMClient()
    payload = {
        "clinical_note": "Some note",
        "policy_rubric": "Some rubric",
    }
    response = client.post("/api/v1/audit/evaluate", json=payload)
    app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "LLM provider error" in response.json()["detail"]


def test_audit_evaluate_endpoint_missing_api_key_returns_503(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LLM_API_KEY", None)
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", None)
    app.dependency_overrides.clear()
    payload = {
        "clinical_note": "Some note",
        "policy_rubric": "Some rubric",
    }
    response = client.post("/api/v1/audit/evaluate", json=payload)
    assert response.status_code == 503
    assert "API Key is required" in response.json()["detail"]
