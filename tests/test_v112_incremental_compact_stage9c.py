from copy import deepcopy
import pytest

from ghost_research import v112_incremental_compact_stage9c as s9c
from ghost_research import v112_incremental_compact_codec_stage9c as inc
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_utility_stage7 as s7


def _obs(seq=1, **overrides):
    row={"id":f"epistemic_{seq:06d}","kind":"observation","observation_kind":"social","observer":"guard_00","provenance":{"token":f"t{seq}","source":"world","host_step":seq},"reliability":1.0,"sequence":seq,"subject":"visitor_00","tick":0,"visible_features":["x",f"t{seq}"]}
    row.update(overrides); return row


def test_json_bytes_canonical():
    assert inc.json_bytes({"b":2,"a":1}) == len(b'{"a":1,"b":2}')

@pytest.mark.parametrize(("value","tag"),[(True,"b"),(None,"n"),(2,"i"),(2.5,"f"),("x","s")])
def test_primitive_tags(value,tag):
    assert inc._primitive_tag(value)==tag

def test_primitive_tag_rejects_nested():
    with pytest.raises(TypeError,match="unsupported provenance"):
        inc._primitive_tag({"x":1})

def test_incremental_codec_roundtrip_and_nonderived_id():
    c=inc.IncrementalObservationCodec(); rows=[_obs(),_obs(2,id="custom")]
    for row in rows: c.append(row)
    assert [c.decode(i) for i in range(2)]==rows
    restored=inc.IncrementalObservationCodec(c.snapshot())
    assert [restored.decode(i) for i in range(2)]==rows

def test_incremental_codec_rejects_schema_and_visible_type():
    c=inc.IncrementalObservationCodec(); bad=_obs(); bad.pop("observer")
    with pytest.raises(ValueError,match="unexpected"): c.append(bad)
    with pytest.raises(TypeError,match="visible_features"): c.append(_obs(visible_features=[3]))

def test_codec_snapshot_rejects_wrong_schema():
    with pytest.raises(ValueError,match="schema mismatch"):
        inc.IncrementalObservationCodec({"schema":"wrong"})

def test_sidecar_rejects_bad_record_order_and_duplicate():
    s=inc.IncrementalCompactSidecar(); s.ingest_record(_obs())
    with pytest.raises(ValueError,match="duplicate"): s.ingest_record(_obs())
    with pytest.raises(ValueError,match="increasing"): s.ingest_record(_obs(1,id="other"))

def test_sidecar_rejects_missing_id():
    s=inc.IncrementalCompactSidecar(); row=_obs(); row["id"]=""
    with pytest.raises(ValueError,match="id missing"): s.ingest_record(row)

def test_sidecar_snapshot_restart_preserves_answers():
    live=s9c.LiveExposure({"id":"events_224","ambient_events":224}).run(restart_points={50,150})
    side=s9c.LiveExposureAnswer.sidecar(live)
    restarted=inc.IncrementalCompactSidecar(side.snapshot())
    for task in s7.reveal_tasks():
        assert restarted.answer(task)==s7._ground_truth(live["host_ledger"],task)

def test_expand_rejects_wrong_schema():
    live=s9c.LiveExposure({"id":"events_224","ambient_events":224}).run()
    bad=deepcopy(live["compact"]); bad["api"]["epistemic"]["records_codec"]["schema"]="wrong"
    with pytest.raises(ValueError,match="schema mismatch"):
        inc.IncrementalCompactSidecar.expand_full_snapshot(bad)

def test_live_exposure_matches_frozen_reference_exactly():
    live=s9c.LiveExposure({"id":"events_224","ambient_events":224}).run(restart_points={50,150})
    ref=ex.blind_exposure({"id":"events_224","ambient_events":224},"full")
    assert live["host_ledger"]==ref["host_ledger"]
    assert live["frozen"]==ref["frozen"]
    assert inc.IncrementalCompactSidecar.expand_full_snapshot(live["compact"])==ref["frozen"]

def test_live_writer_task_blind_surface():
    names=set(s9c.LiveExposure.__dict__)|set(inc.IncrementalCompactSidecar.__dict__)
    assert "reveal_tasks" not in names

def test_marker_latest_token_update_without_rebuild():
    side=inc.IncrementalCompactSidecar()
    side.ingest_record(_obs(1,provenance={"token":"same","source":"a","host_step":1}))
    side.ingest_record(_obs(2,provenance={"token":"same","source":"b","host_step":2}))
    assert side._marker({"token":"same"})=="b"

def test_relationship_and_values_incremental_updates():
    side=inc.IncrementalCompactSidecar(); packet={"trust":0.5,"maturity":0.05}
    side.update_relationship(ex.AGENT,ex.WITNESS_A,packet); side.set_agent_values(ex.AGENT,{"duty":0.8})
    assert side._relationship(ex.AGENT,ex.WITNESS_A)==packet
    assert side.agent_values[ex.AGENT]["duty"]==0.8

def test_profile_level_without_timing():
    r=s9c._profile_level({"id":"events_224","ambient_events":224},timing=False,samples=1)
    assert r["exact_reference_match"] is True and r["exact_roundtrip"] is True and r["all_correct"] is True
    assert r["write_work"]["no_full_rebuilds"] is True
    assert r["timing"] is None

def test_profile_level_with_timing():
    r=s9c._profile_level({"id":"events_224","ambient_events":224},timing=True,samples=1)
    assert r["timing"]["samples"]==1
    assert r["timing"]["incremental_query_battery_us"]>=0

def test_profile_detects_reference_drift(monkeypatch):
    original=s9c.ex.blind_exposure
    def drift(level,mode):
        value=original(level,mode); value["host_ledger"]=value["host_ledger"]+[{"drift":True}]; return value
    monkeypatch.setattr(s9c.ex,"blind_exposure",drift)
    with pytest.raises(RuntimeError,match="drifted"):
        s9c._profile_level({"id":"events_224","ambient_events":224},timing=False,samples=1)

def test_profile_detects_roundtrip_drift(monkeypatch):
    monkeypatch.setattr(inc.IncrementalCompactSidecar,"expand_full_snapshot",staticmethod(lambda compact:{"drift":True}))
    with pytest.raises(RuntimeError,match="full-snapshot reconstruction"):
        s9c._profile_level({"id":"events_224","ambient_events":224},timing=False,samples=1)

@pytest.mark.parametrize("bad",[True,0,1.5])
def test_run_rejects_bad_samples(bad):
    with pytest.raises(ValueError,match="positive integer"):
        s9c.run_experiment(timing_samples=bad)

def test_canonical_level_matrix():
    assert [x["ambient_events"] for x in s9c._LEVELS] == [224, 1024, 2048, 4096]

def test_run_structural_determinism(monkeypatch):
    monkeypatch.setattr(s9c, "_LEVELS", ({"id":"events_224","ambient_events":224},))
    left=s9c.run_experiment(timing=False,timing_samples=1); right=s9c.run_experiment(timing=False,timing_samples=1)
    assert left==right
    assert left["all_correct"] and left["all_exact_reference_matches"] and left["all_exact_roundtrips"]

def test_claim_boundary_keeps_production_open(monkeypatch):
    monkeypatch.setattr(s9c, "_LEVELS", ({"id":"events_224","ambient_events":224},))
    r=s9c.run_experiment(timing=False,timing_samples=1)
    assert r["constraints"]["research_only"] is True
    assert r["constraints"]["full_ghost_restart_continuation_not_tested"] is True
    assert r["constraints"]["no_periodic_full_rebuilds"] is True

def test_codec_sid_rejects_non_string():
    c=inc.IncrementalObservationCodec()
    with pytest.raises(TypeError,match="string value"):
        c._sid(3)

def test_sidecar_snapshot_rejects_wrong_schema():
    with pytest.raises(ValueError,match="sidecar schema mismatch"):
        inc.IncrementalCompactSidecar({"schema":"wrong"})

def test_sidecar_tokenless_observation_and_restart_branch():
    side=inc.IncrementalCompactSidecar()
    side.ingest_record(_obs(1,provenance={"source":"world","host_step":1}))
    restarted=inc.IncrementalCompactSidecar(side.snapshot())
    assert restarted.latest_observation_position_by_token=={}

def test_sidecar_missing_belief_evidence_is_empty():
    assert inc.IncrementalCompactSidecar()._evidence("missing") == []
