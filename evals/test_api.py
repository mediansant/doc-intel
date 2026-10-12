"""API tests: Docling, OpenAI and the real DuckDB file are all replaced, so they run offline for free."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from doc_intel import api
from doc_intel.schema import ContractRecord
from doc_intel.store import init_db

PDF = b"%PDF-1.4 fake contract bytes"


def make_record(**overrides) -> ContractRecord:
    fields = dict(
        governing_law="Delaware", governing_law_evidence="Governed by Delaware law.",
        parties=["Acme Inc", "Beta LLC"], parties_evidence="Between Acme Inc and Beta LLC.",
        agreement_date="2020-01-02", agreement_date_evidence="Dated January 2, 2020.",
        renewal_term=None, renewal_term_evidence=None,
        cap_on_liability=False, cap_on_liability_evidence=None,
        non_compete=False, non_compete_evidence=None,
    )
    return ContractRecord(**{**fields, **overrides})


@pytest.fixture
def mock_extract(monkeypatch):
    mock = MagicMock(return_value=make_record())
    monkeypatch.setattr(api, "extract", mock)
    return mock


@pytest.fixture
def client(tmp_path, monkeypatch, mock_extract):
    fake_converter = MagicMock()
    fake_converter.convert.return_value = SimpleNamespace(
        document=SimpleNamespace(export_to_markdown=lambda: "# Contract text")
    )
    monkeypatch.setattr(api, "DocumentConverter", lambda: fake_converter)
    monkeypatch.setattr(api, "init_db", lambda: init_db(tmp_path / "test.duckdb"))
    with TestClient(api.app) as c:
        c.fake_converter = fake_converter
        yield c


def post(client, data=PDF, name="c.pdf", ctype="application/pdf"):
    return client.post("/extract", files={"file": (name, data, ctype)})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_successful_extraction(client, mock_extract):
    r = post(client)
    assert r.status_code == 200
    body = r.json()
    assert body["cached"] is False
    assert body["run_id"] == api.RUN_ID
    assert len(body["doc_id"]) == 64
    assert body["record"]["governing_law"] == "Delaware"
    assert body["record"]["parties"] == ["Acme Inc", "Beta LLC"]
    mock_extract.assert_called_once()
    assert mock_extract.call_args.args[0] == "# Contract text"


def test_same_file_twice_is_cached_and_model_called_once(client, mock_extract):
    first, second = post(client), post(client)
    assert first.json()["cached"] is False
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert second.json()["doc_id"] == first.json()["doc_id"]
    assert second.json()["record"] == first.json()["record"]
    assert mock_extract.call_count == 1
    assert client.fake_converter.convert.call_count == 1  # cache hit skips parsing too


def test_different_files_both_hit_the_model(client, mock_extract):
    post(client, PDF)
    post(client, PDF + b" different")
    assert mock_extract.call_count == 2


def test_non_pdf_rejected(client, mock_extract):
    r = post(client, b"just some text", "c.txt", "text/plain")
    assert r.status_code == 415
    mock_extract.assert_not_called()


def test_oversized_upload_rejected(client, monkeypatch, mock_extract):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    assert post(client).status_code == 413
    mock_extract.assert_not_called()


def test_unparsable_pdf_is_422(client, mock_extract):
    client.fake_converter.convert.side_effect = RuntimeError("corrupt")
    r = post(client)
    assert r.status_code == 422
    mock_extract.assert_not_called()


def test_empty_text_is_422(client, mock_extract):
    client.fake_converter.convert.return_value.document.export_to_markdown = lambda: "  \n"
    assert post(client).status_code == 422
    mock_extract.assert_not_called()


def test_model_failure_is_502_and_not_cached(client, mock_extract):
    mock_extract.side_effect = RuntimeError("openai down")
    r = post(client)
    assert r.status_code == 502
    assert "openai down" in r.json()["detail"]

    # a failure must not poison the cache: the retry calls the model again
    mock_extract.side_effect = None
    mock_extract.return_value = make_record()
    retry = post(client)
    assert retry.status_code == 200 and retry.json()["cached"] is False


def test_model_returns_none_is_502(client, mock_extract):
    mock_extract.return_value = None  # refusal / unparsable output
    assert post(client).status_code == 502
