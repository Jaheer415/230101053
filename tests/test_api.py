"""Unit tests for FastAPI Service Endpoints & Headers."""
import os
import json
from unittest.mock import MagicMock
import pytest
import torch
from fastapi.testclient import TestClient

os.environ["MODEL_URI"] = "models/v1"
os.environ["MODEL_VERSION"] = "v1"
os.environ["SCHEMA_PATH"] = "data/schema.json"
os.environ["FAULT_INJECT"] = "0"

from service.app import app
import service.app as app_module


@pytest.fixture
def client():
    app_module.is_ready = True
    return TestClient(app)


def test_healthz_endpoint(client):
    """GET /healthz must return HTTP 200 OK."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_readyz_endpoint_states():
    """GET /readyz returns 503 when not ready and 200 when ready."""
    client = TestClient(app)
    app_module.is_ready = False
    resp_not_ready = client.get("/readyz")
    assert resp_not_ready.status_code == 503

    app_module.is_ready = True
    resp_ready = client.get("/readyz")
    assert resp_ready.status_code == 200


def test_response_headers_present(client, monkeypatch):
    """POST /parse must include X-Model-Version and X-Served-By headers."""
    fake_json = json.dumps({
        "intent": "alarm_set",
        "date": "tomorrow",
        "time": "7 am",
        "place": None
    })

    mock_tok = MagicMock()
    mock_inputs = MagicMock()
    mock_inputs.input_ids = torch.tensor([[1, 2]])
    mock_inputs.items.return_value = [("input_ids", torch.tensor([[1, 2]]))]
    mock_inputs.__getitem__.side_effect = lambda k: torch.tensor([[1, 2]]) if k == "input_ids" else None
    mock_tok.return_value = {"input_ids": torch.tensor([[1, 2]])}
    mock_tok.pad_token_id = 0
    mock_tok.eos_token_id = 2
    mock_tok.decode.return_value = fake_json

    mock_mod = MagicMock()
    mock_mod.generate.return_value = torch.tensor([[1, 2, 3, 4]])

    monkeypatch.setattr(app_module, "tokenizer", mock_tok)
    monkeypatch.setattr(app_module, "model", mock_mod)

    resp = client.post("/parse", json={"text": "set alarm for tomorrow 7 am"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Model-Version") == "v1"
    assert "X-Served-By" in resp.headers
    assert resp.json()["intent"] == "alarm_set"
