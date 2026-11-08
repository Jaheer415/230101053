"""Unit tests for Schema Validation and FAULT_INJECT."""
import os
import json
import pytest
from fastapi.testclient import TestClient

os.environ["MODEL_URI"] = "models/v1"
os.environ["MODEL_VERSION"] = "v1"
os.environ["SCHEMA_PATH"] = "data/schema.json"

from service.app import app
import service.app as app_module


@pytest.fixture
def client():
    app_module.is_ready = True
    return TestClient(app)


def test_fault_inject_returns_500(client, monkeypatch):
    """When FAULT_INJECT=1, /parse must return HTTP 500 with {"error": "invalid_model_output"}."""
    monkeypatch.setenv("FAULT_INJECT", "1")
    monkeypatch.setattr(app_module, "FAULT_INJECT", "1")

    resp = client.post("/parse", json={"text": "what is the weather today"})
    assert resp.status_code == 500
    assert resp.json() == {"error": "invalid_model_output"}
    assert "X-Model-Version" in resp.headers
    assert "X-Served-By" in resp.headers


def test_schema_valid_and_invalid_payloads():
    """Verify JSON schema catches missing keys, invalid types, and invalid intents."""
    import jsonschema
    with open("data/schema.json", "r", encoding="utf-8") as f:
        schema = json.load(f)["json_schema"]

    valid_payload = {
        "intent": "weather_query",
        "date": "today",
        "time": None,
        "place": "london"
    }
    # Should not raise
    jsonschema.validate(instance=valid_payload, schema=schema)

    # Missing key
    invalid_missing = {"intent": "weather_query", "date": "today", "time": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_missing, schema=schema)

    # Invalid intent
    invalid_intent = {
        "intent": "buy_groceries",
        "date": None,
        "time": None,
        "place": None
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_intent, schema=schema)
