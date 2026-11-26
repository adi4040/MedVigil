from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db.session import get_db
from app.main import app
from app.schemas.renal import RenalAuditReport


async def _override_get_db():
    yield MagicMock()


def test_renal_evaluate_rejects_invalid_json_with_422():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/renal/evaluate", json={"discharge_json": "{not-json"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_renal_evaluate_missing_gemini_config_returns_503_without_leak():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        with patch(
            "app.api.v1.renal.RenalAgentRunner",
            side_effect=ValueError("Gemini API Key is required. Secret details."),
        ):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/renal/evaluate",
                    json={"discharge_json": '{"patient_id": "p1"}'},
                )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Renal safety service is not configured."
        assert "Secret" not in resp.text
    finally:
        app.dependency_overrides.clear()


def test_renal_evaluate_invalid_model_output_returns_502_not_400():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        try:
            RenalAuditReport.model_validate_json('{"bad": "schema"}')
        except ValidationError as validation_err:
            runner_instance = MagicMock()
            runner_instance.run = AsyncMock(side_effect=validation_err)

            with patch("app.api.v1.renal.RenalAgentRunner", return_value=runner_instance):
                with TestClient(app) as client:
                    resp = client.post(
                        "/api/v1/renal/evaluate",
                        json={"discharge_json": '{"patient_id": "p1"}'},
                    )
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Upstream model returned an invalid renal audit report."
    finally:
        app.dependency_overrides.clear()


def test_renal_evaluate_internal_error_returns_500_without_db_leak():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        runner_instance = MagicMock()
        runner_instance.run = AsyncMock(
            side_effect=RuntimeError("psycopg: connection to postgresql://medv_user:secret@localhost failed")
        )
        with patch("app.api.v1.renal.RenalAgentRunner", return_value=runner_instance):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/renal/evaluate",
                    json={"discharge_json": '{"patient_id": "p1"}'},
                )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Renal safety evaluation failed due to an internal error."
        assert "postgresql://" not in resp.text
        assert "secret" not in resp.text
    finally:
        app.dependency_overrides.clear()


def test_renal_evaluate_returns_report_without_internal_telemetry():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        report = RenalAuditReport(
            patient_id="p1",
            medication_name="Gabapentin",
            prescribed_daily_dose_mg=1800.0,
            required_renal_metric="crcl",
            renal_metric_value=95.0,
            verdict="safe",
            rationale="Within guidelines.",
            tool_trace=["get_renal_metric({'medication_name': 'Gabapentin'})"],
        )
        runner_instance = MagicMock()
        runner_instance.run = AsyncMock(
            return_value={
                "report": report,
                "tools_called": ["get_renal_metric", "fetch_patient_crcl", "calculate_crcl"],
                "steps": 4,
                "input_tokens": 500,
                "output_tokens": 120,
            }
        )
        with patch("app.api.v1.renal.RenalAgentRunner", return_value=runner_instance):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/renal/evaluate",
                    json={"discharge_json": '{"patient_id": "p1", "medication_name": "Gabapentin"}'},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "safe"
        assert "steps" not in body
        assert "input_tokens" not in body
        assert "output_tokens" not in body
        assert "tools_called" not in body
    finally:
        app.dependency_overrides.clear()
