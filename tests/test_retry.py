import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core.retry import (
    AuditEvaluationExhaustedError,
    RetryConfig,
    calculate_backoff,
    format_validation_feedback,
    is_transient_error,
)
from app.schemas.audit import ClinicalGapReport
from app.services.llm_client import GeminiAuditClient, OpenAIAuditClient


def test_calculate_backoff_growth_and_ceiling():
    config = RetryConfig(base_delay=1.0, max_delay=10.0, jitter=False)
    
    assert calculate_backoff(0, config) == 1.0   # 1 * 2^0
    assert calculate_backoff(1, config) == 2.0   # 1 * 2^1
    assert calculate_backoff(2, config) == 4.0   # 1 * 2^2
    assert calculate_backoff(3, config) == 8.0   # 1 * 2^3
    assert calculate_backoff(4, config) == 10.0  # Capped at max_delay 10.0


def test_calculate_backoff_jitter():
    config = RetryConfig(base_delay=2.0, max_delay=16.0, jitter=True)
    delays = [calculate_backoff(1, config) for _ in range(10)]
    
    # Base calculation is 4.0, with jitter [0.8, 1.2] => range [3.2, 4.8]
    for d in delays:
        assert 3.1 <= d <= 4.9
    # Ensure there is randomness
    assert len(set(delays)) > 1


def test_format_validation_feedback():
    sample_errors = [
        {"loc": ["evaluations", 0, "evidence"], "msg": "Evidence must be null when status is 'missing'."},
        {"loc": ["rubric_id"], "msg": "Field required"},
    ]
    feedback = format_validation_feedback(sample_errors)
    
    assert "evaluations -> 0 -> evidence" in feedback
    assert "Evidence must be null when status is 'missing'." in feedback
    assert "rubric_id" in feedback
    assert "Please correct the violations and output ONLY the valid JSON" in feedback


def test_is_transient_error_detection():
    # Transient by status_code
    class CustomStatusError(Exception):
        status_code = 503

    class CustomClientError(Exception):
        status_code = 400

    assert is_transient_error(CustomStatusError("Service Unavailable")) is True
    assert is_transient_error(CustomClientError("Bad Request")) is False

    # Transient by error message keywords
    assert is_transient_error(Exception("429 Too Many Requests")) is True
    assert is_transient_error(Exception("Spikes in demand / high demand")) is True
    assert is_transient_error(Exception("Resource exhausted")) is True
    assert is_transient_error(Exception("Connection timed out")) is True

    # Non-transient
    assert is_transient_error(Exception("Invalid API key provided")) is False
    assert is_transient_error(ValueError("Field required")) is False


def test_gemini_transient_retry_recovers():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")
    
    mock_success_response = MagicMock()
    mock_success_response.text = json.dumps({
        "rubric_id": "MRI_PA_001",
        "evaluations": [],
        "missing_or_unclear_summary": []
    })

    # Fail on 1st call with 503, succeed on 2nd call
    transient_exc = Exception("503 Service Unavailable")
    client.client.models.generate_content = MagicMock(
        side_effect=[transient_exc, mock_success_response]
    )

    fast_retry = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.02, jitter=False)
    
    report = client.evaluate_audit(
        clinical_note="Some note",
        policy_rubric="Some rubric",
        retry_config=fast_retry,
    )

    assert isinstance(report, ClinicalGapReport)
    assert report.rubric_id == "MRI_PA_001"
    assert client.client.models.generate_content.call_count == 2


def test_gemini_validation_feedback_loop_recovers():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")

    # 1st call returns invalid json missing rubric_id
    mock_invalid_response = MagicMock()
    mock_invalid_response.text = json.dumps({
        "evaluations": [],
        "missing_or_unclear_summary": []
    })

    # 2nd call returns valid json after feedback
    mock_valid_response = MagicMock()
    mock_valid_response.text = json.dumps({
        "rubric_id": "CORRECTED_RUBRIC",
        "evaluations": [],
        "missing_or_unclear_summary": []
    })

    client.client.models.generate_content = MagicMock(
        side_effect=[mock_invalid_response, mock_valid_response]
    )

    fast_retry = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.02, jitter=False)

    report = client.evaluate_audit(
        clinical_note="Some note",
        policy_rubric="Some rubric",
        retry_config=fast_retry,
    )

    assert isinstance(report, ClinicalGapReport)
    assert report.rubric_id == "CORRECTED_RUBRIC"
    assert client.client.models.generate_content.call_count == 2

    # Check that 2nd call received multi-turn content with feedback
    second_call_contents = client.client.models.generate_content.call_args_list[1].kwargs["contents"]
    assert len(second_call_contents) == 3
    assert second_call_contents[0].role == "user"
    assert second_call_contents[1].role == "model"
    assert second_call_contents[2].role == "user"
    assert "failed schema validation" in second_call_contents[2].parts[0].text


def test_gemini_retries_exhausted_raises_custom_error():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")
    
    # Always returns invalid json
    mock_invalid_response = MagicMock()
    mock_invalid_response.text = json.dumps({"invalid_key": "val"})

    client.client.models.generate_content = MagicMock(return_value=mock_invalid_response)

    fast_retry = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.02, jitter=False)

    with pytest.raises(AuditEvaluationExhaustedError) as exc_info:
        client.evaluate_audit(
            clinical_note="Some note",
            policy_rubric="Some rubric",
            retry_config=fast_retry,
        )

    assert "Failed to produce a valid ClinicalGapReport after 3 attempts" in str(exc_info.value)
    assert client.client.models.generate_content.call_count == 3

