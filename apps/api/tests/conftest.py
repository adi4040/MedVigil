import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_client import MockAuditClient, get_configured_llm_client


@pytest.fixture
def client():
    # By default, use MockAuditClient during automated tests
    app.dependency_overrides[get_configured_llm_client] = lambda: MockAuditClient()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
