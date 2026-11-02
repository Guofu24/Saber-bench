import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saber.lab.analysis_service import AnalysisQueue, create_analysis
from saber.lab.analyzers import AnalysisJob, AnalysisSettings, argv_for, execute
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger

ASSETS = Path(__file__).resolve().parents[2] / "infra/soc/analysis"


def test_sample_vault_authorization_integrity_jobs_and_restart(tmp_path, monkeypatch):
    store = Ledger(tmp_path)
    credentials = {
        "upload_token": "operator",
        "actor_capabilities": {
            "dfir": {"actor": "blue-dfir", "team": "blue", "role": "dfir"},
            "hunter": {"actor": "blue-hunter", "team": "blue", "role": "hunter"},
        },
    }
    queue = AnalysisQueue(
        store, credentials, AnalysisSettings(), ASSETS, Emitter(store, "analysis-test", "", "")
    )
    client = TestClient(create_analysis(queue))

    def auth(name):
        return {"Authorization": "Bearer " + name}

    payload = b"\x7fELF\x02\x01" + b"\0" * 32 + b"SABER_LAB_SAMPLE"
    digest = hashlib.sha256(payload).hexdigest()
    assert (
        client.post("/samples/" + digest, headers=auth("dfir"), content=payload).status_code == 403
    )
    assert (
        client.post("/samples/" + "a" * 64, headers=auth("operator"), content=payload).status_code
        == 422
    )
    assert not list((tmp_path / "samples").iterdir())
    assert client.post("/samples/" + digest, headers=auth("operator"), content=payload).json()[
        "bytes"
    ] == len(payload)
    job = {"id": str(uuid.uuid4()), "sample_id": digest, "engine": "builtin"}
    assert client.post("/jobs", headers=auth("hunter"), json=job).status_code == 403
    assert client.post("/jobs", headers=auth("dfir"), json=job).json()["state"] == "QUEUED"
    assert client.post("/jobs", headers=auth("dfir"), json=job).json()["id"] == job["id"]
    assert queue.process_one()
    result = client.get("/jobs/" + job["id"], headers=auth("dfir")).json()
    assert result["state"] == "SUCCEEDED" and result["result"]["result"]["format"] == "ELF"
    assert (
        hashlib.sha256(
            (tmp_path / "analysis" / job["id"] / "analysis.json").read_bytes()
        ).hexdigest()
        == result["result"]["report_sha256"]
    )
    assert client.get("/jobs/" + job["id"], headers=auth("hunter")).status_code == 404
    assert not queue.process_one()
    assert any(e["kind"] == "analysis.completed" for e in store.events())
    uncertain = job | {"id": str(uuid.uuid4())}
    client.post("/jobs", headers=auth("dfir"), json=uncertain)
    record = store.get("analysis-job:" + uncertain["id"])
    record["state"] = "RUNNING"
    store.put("analysis-job:" + uncertain["id"], record)
    AnalysisQueue(store, credentials, AnalysisSettings(), ASSETS, queue.emitter)
    assert store.get("analysis-job:" + uncertain["id"])["state"] == "INDETERMINATE"
    blocked = job | {"id": str(uuid.uuid4())}
    client.post("/jobs", headers=auth("dfir"), json=blocked)

    def full_disk(*args, **kwargs):
        raise OSError("Evidence budget reached")

    monkeypatch.setattr(queue.emitter, "emit", full_disk)
    assert queue.process_one()
    recorded = store.get("analysis-job:" + blocked["id"])
    assert recorded["state"] == "INDETERMINATE" and recorded["result"]["state"] == "SUCCEEDED"
    assert not queue.process_one()
    store.close()


@pytest.mark.integration
def test_actual_yara_matches_only_the_synthetic_marker(tmp_path):
    pytest.importorskip("yara")
    for i, data in enumerate((b"SABER_LAB_SAMPLE", b"ordinary harmless bytes")):
        sample = tmp_path / ("sample-" + str(i))
        sample.write_bytes(data)
        job = AnalysisJob(
            id=str(uuid.uuid4()), sample_id=hashlib.sha256(data).hexdigest(), engine="yara"
        )
        result = execute(
            job, sample, "binary", tmp_path / ("job-" + str(i)), ASSETS, AnalysisSettings()
        )
        assert result["state"] == "SUCCEEDED"
        assert result["result"]["matches"] == (["saber_synthetic_marker"] if i == 0 else [])
        assert result["pid"] > 0 and result["exit_code"] == 0


@pytest.mark.integration
def test_actual_volatility_invalid_image_is_not_a_success(tmp_path):
    pytest.importorskip("volatility3")
    sample = tmp_path / "invalid-memory"
    sample.write_bytes(b"NOT_A_MEMORY_IMAGE")
    job = AnalysisJob(
        id=str(uuid.uuid4()),
        sample_id=hashlib.sha256(sample.read_bytes()).hexdigest(),
        engine="volatility",
        profile="windows-processes",
    )
    result = execute(
        job, sample, "memory", tmp_path / "job", ASSETS, AnalysisSettings(timeout_seconds=15)
    )
    assert result["state"] == "FAILED"


def test_fixed_native_tool_arguments_and_sample_mutation_rejected(tmp_path):
    digest = "a" * 64
    job = AnalysisJob(id=str(uuid.uuid4()), sample_id=digest, engine="ghidra")
    argv = argv_for(job, tmp_path / digest, tmp_path / "job", ASSETS, AnalysisSettings())
    assert "-postScript" in argv and "ExportSummary.java" in argv and "-max-cpu" in argv
    ida = argv_for(
        job.model_copy(update={"engine": "ida"}),
        tmp_path / digest,
        tmp_path / "job",
        ASSETS,
        AnalysisSettings(),
    )
    assert "-A" in ida and any(a.endswith("ida_summary.py") for a in ida)
    with pytest.raises(ValueError):
        AnalysisJob(id=job.id, sample_id="../../keys_pool", engine="builtin")
    sample = tmp_path / "altered"
    sample.write_bytes(b"changed")
    with pytest.raises(ValueError):
        execute(
            job.model_copy(update={"engine": "builtin"}),
            sample,
            "binary",
            tmp_path / "reject",
            ASSETS,
            AnalysisSettings(),
        )


@pytest.mark.integration
def test_operator_self_test_uses_real_queue_and_native_positive_negative_controls(
    tmp_path, monkeypatch
):
    import json

    from saber.lab.analysis_cli import self_test
    from saber.lab.deployment import initialize_secrets, render
    from saber.lab.models import preset_spec

    from .test_services import served

    pytest.importorskip("yara")
    bundle = tmp_path / "bundle"
    spec = preset_spec("linux-small")
    render(spec, bundle)
    initialize_secrets(bundle, spec)
    creds = json.loads((bundle / ".secrets/analysis.json").read_text())
    store = Ledger(tmp_path / "vault")
    monkeypatch.chdir(bundle)
    queue = AnalysisQueue(
        store, creds, spec.analysis, Path("analysis"), Emitter(store, "analysis-test", "", "")
    )
    queue.thread.start()
    try:
        with served(create_analysis(queue)) as endpoint:
            receipt = self_test(bundle, endpoint, timeout=20)
            assert receipt["passed"] and len(receipt["jobs"]) == 3
            assert len([e for e in store.events() if e["kind"] == "analysis.completed"]) == 3
    finally:
        queue.close()
        store.close()
