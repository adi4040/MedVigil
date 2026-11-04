import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core.retry import AuditEvaluationExhaustedError, RetryConfig
from app.schemas.audit import (
    AuditStreamAccumulator,
    ClinicalGapReport,
    StreamChunk,
    StreamEventType,
)
from app.services.llm_client import (
    GeminiAuditClient,
    MockAuditClient,
    OpenAIAuditClient,
)


@pytest.mark.asyncio
async def test_mock_client_streaming_tokens_and_done():
    client = MockAuditClient(chunk_size=15)
    note = "Patient has severe lower-back pain for eight weeks. Neurological exam not included."
    rubric = "RUBRIC ID: MRI_PA_001\n1. Symptoms and Duration"

    chunks = []
    async for chunk in client.stream_audit(note, rubric):
        chunks.append(chunk)

    # Verify stream structure
    assert len(chunks) > 1
    token_chunks = [c for c in chunks if c.event == StreamEventType.TOKEN]
    done_chunks = [c for c in chunks if c.event == StreamEventType.DONE]

    assert len(token_chunks) >= 1
    assert len(done_chunks) == 1
    assert done_chunks[0].report is not None
    assert isinstance(done_chunks[0].report, ClinicalGapReport)
    assert done_chunks[0].report.rubric_id == "MRI_PA_001"

    # Reconstructed text must match report JSON
    accumulated = "".join(c.text for c in token_chunks if c.text)
    validated = ClinicalGapReport.model_validate_json(accumulated)
    assert validated.rubric_id == "MRI_PA_001"


@pytest.mark.asyncio
async def test_audit_stream_accumulator():
    client = MockAuditClient(chunk_size=25)
    note = "Patient reports persistent lower-back pain for 8 weeks."
    rubric = "RUBRIC ID: MRI_TEST"

    acc = await AuditStreamAccumulator().consume(client.stream_audit(note, rubric))

    assert len(acc.tokens) > 0
    assert acc.final_report is not None
    assert acc.final_report.rubric_id == "MRI_TEST"
    assert acc.error is None
    assert len(acc.accumulated_text) > 0


@pytest.mark.asyncio
async def test_gemini_streaming_success():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")

    sample_report_dict = {
        "rubric_id": "MRI_STREAM_001",
        "evaluations": [
            {
                "criterion": "Symptoms and Duration",
                "status": "met",
                "evidence": "Back pain 8 weeks",
                "explanation": "Clearly documented",
                "suggested_clarification": None,
            }
        ],
        "missing_or_unclear_summary": [],
    }
    raw_json = json.dumps(sample_report_dict)

    # Create mock chunks
    chunk1 = MagicMock()
    chunk1.text = raw_json[:30]
    chunk2 = MagicMock()
    chunk2.text = raw_json[30:]

    async def fake_stream():
        yield chunk1
        yield chunk2

    client.client.aio.models.generate_content_stream = AsyncMock(
        return_value=fake_stream()
    )

    acc = await AuditStreamAccumulator().consume(
        client.stream_audit("Some note", "Some rubric")
    )

    assert acc.error is None
    assert acc.final_report is not None
    assert acc.final_report.rubric_id == "MRI_STREAM_001"
    assert acc.accumulated_text == raw_json
    assert len(acc.tokens) == 2


@pytest.mark.asyncio
async def test_gemini_streaming_pre_stream_transient_retry():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")

    sample_report_dict = {
        "rubric_id": "MRI_RETRY_001",
        "evaluations": [],
        "missing_or_unclear_summary": [],
    }
    raw_json = json.dumps(sample_report_dict)

    chunk = MagicMock()
    chunk.text = raw_json

    async def fake_success_stream():
        yield chunk

    transient_exc = Exception("503 Service Temporarily Unavailable")
    client.client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[transient_exc, fake_success_stream()]
    )

    fast_retry = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.02, jitter=False)

    acc = await AuditStreamAccumulator().consume(
        client.stream_audit("note", "rubric", retry_config=fast_retry)
    )

    assert acc.final_report is not None
    assert acc.final_report.rubric_id == "MRI_RETRY_001"
    assert client.client.aio.models.generate_content_stream.call_count == 2


@pytest.mark.asyncio
async def test_gemini_streaming_pre_stream_retries_exhausted():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")

    transient_exc = Exception("429 Rate limit reached")
    client.client.aio.models.generate_content_stream = AsyncMock(
        side_effect=transient_exc
    )

    fast_retry = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.02, jitter=False)

    with pytest.raises(AuditEvaluationExhaustedError) as exc_info:
        async for _ in client.stream_audit("note", "rubric", retry_config=fast_retry):
            pass

    assert "Exhausted 3 stream attempts due to transient errors" in str(exc_info.value)
    assert client.client.aio.models.generate_content_stream.call_count == 3


@pytest.mark.asyncio
async def test_gemini_streaming_mid_stream_failure_yields_error_chunk():
    client = GeminiAuditClient(api_key="test-key", model="gemini-3.5-flash")

    chunk1 = MagicMock()
    chunk1.text = '{"rubric_id": "PARTIAL"'

    async def failing_stream():
        yield chunk1
        raise ConnectionResetError("Connection severed mid-stream")

    client.client.aio.models.generate_content_stream = AsyncMock(
        return_value=failing_stream()
    )

    chunks = []
    async for chunk in client.stream_audit("note", "rubric"):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].event == StreamEventType.TOKEN
    assert chunks[0].text == '{"rubric_id": "PARTIAL"'
    assert chunks[1].event == StreamEventType.ERROR
    assert "Connection severed mid-stream" in chunks[1].error


@pytest.mark.asyncio
async def test_openai_streaming_success():
    client = OpenAIAuditClient(api_key="test-key", model="gpt-4o")

    sample_report = ClinicalGapReport(
        rubric_id="MRI_OPENAI_STREAM",
        evaluations=[],
        missing_or_unclear_summary=[],
    )

    event1 = MagicMock()
    event1.type = "content.delta"
    event1.delta = '{"rubric_id": '

    event2 = MagicMock()
    event2.type = "content.delta"
    event2.delta = '"MRI_OPENAI_STREAM", "evaluations": [], "missing_or_unclear_summary": []}'

    class FakeStream:
        def __aiter__(self):
            return self._iter()

        async def _iter(self):
            yield event1
            yield event2

        async def get_final_completion(self):
            return MagicMock(
                choices=[MagicMock(message=MagicMock(parsed=sample_report))]
            )

    stream_obj = FakeStream()
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=stream_obj)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    client.async_client.beta.chat.completions.stream = MagicMock(
        return_value=mock_stream_ctx
    )

    acc = await AuditStreamAccumulator().consume(
        client.stream_audit("note", "rubric")
    )

    assert acc.error is None
    assert acc.final_report is not None
    assert acc.final_report.rubric_id == "MRI_OPENAI_STREAM"
    assert acc.tokens == ['{"rubric_id": ', '"MRI_OPENAI_STREAM", "evaluations": [], "missing_or_unclear_summary": []}']


@pytest.mark.asyncio
async def test_stream_chunk_json_serialization_for_sse():
    token_chunk = StreamChunk.token_chunk("hello")
    dumped = token_chunk.model_dump_json()
    assert '"event":"token"' in dumped
    assert '"text":"hello"' in dumped

    report = ClinicalGapReport(
        rubric_id="RUBRIC_1",
        evaluations=[],
        missing_or_unclear_summary=[],
    )
    done_chunk = StreamChunk.done_chunk(report)
    dumped_done = done_chunk.model_dump_json()
    assert '"event":"done"' in dumped_done
    assert '"rubric_id":"RUBRIC_1"' in dumped_done

    error_chunk = StreamChunk.error_chunk("Service unavailable")
    dumped_err = error_chunk.model_dump_json()
    assert '"event":"error"' in dumped_err
    assert '"error":"Service unavailable"' in dumped_err


def test_sse_endpoint_stream_success(client):
    from app.main import app
    from app.services.llm_client import MockAuditClient, get_llm_client

    app.dependency_overrides[get_llm_client] = lambda: MockAuditClient(chunk_size=30)
    payload = {
        "clinical_note": "Patient presents with persistent lower-back pain for eight weeks.",
        "policy_rubric": "RUBRIC ID: MRI_PA_001\n1. Symptoms and Duration",
        "rubric_id": "MRI_PA_001",
    }

    with client.stream("POST", "/api/v1/audit/evaluate/stream", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers["cache-control"] == "no-cache"

        raw_text = response.read().decode("utf-8")

    app.dependency_overrides.clear()

    # Verify SSE formatting
    assert "event: token" in raw_text
    assert "event: done" in raw_text
    assert "data: {" in raw_text
    assert '"rubric_id":"MRI_PA_001"' in raw_text


def test_sse_endpoint_validation_error(client):
    # Missing required 'policy_rubric'
    payload = {"clinical_note": "Missing rubric"}
    response = client.post("/api/v1/audit/evaluate/stream", json=payload)
    assert response.status_code == 422


def test_sse_endpoint_runtime_error_yields_error_event(client):
    from app.main import app
    from app.services.llm_client import BaseLLMClient, get_llm_client

    class FailingStreamClient(BaseLLMClient):
        def evaluate_audit(self, *args, **kwargs):
            raise NotImplementedError()

        async def stream_audit(self, *args, **kwargs):
            yield StreamChunk.token_chunk("partial text")
            raise RuntimeError("Mid-stream connection dropped")

    app.dependency_overrides[get_llm_client] = lambda: FailingStreamClient()
    payload = {
        "clinical_note": "Some note",
        "policy_rubric": "Some rubric",
    }

    with client.stream("POST", "/api/v1/audit/evaluate/stream", json=payload) as response:
        assert response.status_code == 200
        raw_text = response.read().decode("utf-8")

    app.dependency_overrides.clear()

    assert "event: token" in raw_text
    assert "event: error" in raw_text
    assert "Mid-stream connection dropped" in raw_text

