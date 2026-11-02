import uuid

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from saber.lab.collector import create_collector, flush_index
from saber.lab.ledger import Ledger, now

from .test_services import served


def test_indexer_http_contract_persists_ack_and_queries_actual_sources(tmp_path):
    """A protocol server, explicitly not an OpenSearch runtime acceptance test."""
    ledger = Ledger(tmp_path)
    event = {
        "id": str(uuid.uuid4()),
        "ts": now(),
        "host": "app-test",
        "kind": "file.write",
        "sensor": "test",
        "data": {"bytes": 42},
    }
    ledger.append(event)
    backend, documents, mappings = FastAPI(), {}, []

    @backend.put("/saber-test")
    def create(body: dict):
        mappings.append(body)
        return {"acknowledged": True}

    @backend.put("/saber-test/_doc/{eid}")
    def index(eid: str, body: dict):
        documents[eid] = body
        return JSONResponse(status_code=201, content={"result": "created"})

    @backend.post("/saber-test/_search")
    def search(body: dict):
        assert body["query"]["bool"]["filter"][0]["range"]["ts"]["lte"]
        assert body["size"] == 100 and body["sort"] == [{"ts": "desc"}, {"id": "desc"}]
        return {
            "timed_out": False,
            "_shards": {"failed": 0},
            "hits": {"hits": [{"_source": e} for e in documents.values()]},
        }

    with served(backend) as url:
        assert flush_index(ledger, url, "saber-test") == 1
        assert not ledger.events(pending=True)
        assert mappings[0]["mappings"]["properties"]["data"] == {"type": "object", "enabled": False}
        assert documents[event["id"]] == event
        gateway = TestClient(
            create_collector(ledger, {"sources": {}, "read_token": "reader"}, url, "saber-test")
        )
        result = gateway.post("/siem/search", headers={"Authorization": "Bearer reader"}, json={})
        assert result.json()["events"] == [event]
        assert result.json()["source"] == "opensearch"
    ledger.close()


def test_indexer_rejection_retains_raw_outbox_and_no_success_timestamp(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.append(
        {"id": str(uuid.uuid4()), "ts": now(), "host": "app", "kind": "file.write", "data": {}}
    )
    backend = FastAPI()

    @backend.put("/saber-test")
    def reject(body: dict):
        return JSONResponse(
            status_code=400, content={"error": {"type": "mapper_parsing_exception"}}
        )

    with served(backend) as url:
        with pytest.raises(ConnectionError):
            flush_index(ledger, url, "saber-test")
        assert len(ledger.events(pending=True)) == 1
        assert ledger.get("indexer_last_success") is None
    ledger.close()
