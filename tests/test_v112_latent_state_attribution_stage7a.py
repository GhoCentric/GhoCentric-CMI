from copy import deepcopy
import pytest
from ghost_research import v112_latent_exposure_stage7 as ex
from ghost_research import v112_latent_state_attribution_stage7a as a
from ghost_research import v112_latent_state_utility_stage7 as s7

def _overflow():
    return ex.blind_exposure(ex.canonical_levels()[1], 'full')['frozen']

def test_unknown_level_rejected():
    with pytest.raises(ValueError, match='unknown Stage-7A level'): a._level('nope')

def test_unknown_task_rejected():
    with pytest.raises(ValueError, match='unknown Stage-7A task'): a._task('nope')

def test_latest_belief_error_path():
    frozen=_overflow(); assert a._latest_belief(frozen)['subject']==ex.SUBJECT
    broken=deepcopy(frozen)
    broken['api']['epistemic']['records']=[r for r in broken['api']['epistemic']['records'] if not (r.get('kind')=='belief' and r.get('holder')==ex.AGENT and r.get('subject')==ex.SUBJECT)]
    with pytest.raises(RuntimeError, match='current belief disappeared'): a._latest_belief(broken)

def test_relationship_error_path():
    broken=deepcopy(_overflow()); broken['api']['engine']['relationships'].pop(f'{ex.AGENT}|{ex.WITNESS_A}')
    with pytest.raises(RuntimeError, match='relationship disappeared'): a._relationship(broken, ex.WITNESS_A)

@pytest.mark.parametrize('helper',[a._ablate_marker,a._ablate_relationship_a,a._ablate_evidence_links,a._ablate_revision_lineage,a._ablate_counterfactual_signals,a._ablate_duty])
def test_ablation_helpers_are_copy_safe(helper):
    frozen=_overflow(); original=deepcopy(frozen); assert helper(frozen)!=frozen; assert frozen==original

@pytest.mark.parametrize('task,expected',[
 ('early_marker_source',[2]),('relationship_event_count',[3,4,5,6,7]),('evidence_sources',[12,14,16,146]),('belief_revision_count',[12,14,16,146]),('counterfactual_without_a',[12,14,16,146]),('deeper_relationship',[3,4,5,6,7,8,9,10]),('novel_delegate_choice',[3,4,5,6,7,8,9,10])])
def test_host_steps_exact_first_overflow(task,expected):
    ledger=ex.blind_exposure(ex.canonical_levels()[1],'full')['host_ledger']; assert a._host_steps(ledger,task)==expected

def test_host_steps_unknown_rejected():
    ledger=ex.blind_exposure(ex.canonical_levels()[1],'full')['host_ledger']
    with pytest.raises(ValueError, match='no Stage-7A host-step attribution'): a._host_steps(ledger,'current_trust_sign')

@pytest.mark.parametrize('task',a._EXPECTED_TASKS)
def test_paths_cover_exact_overflow_tasks(task):
    row=a._path(task); assert row['component']; assert row['state_paths']

def test_unknown_path_rejected():
    with pytest.raises(KeyError): a._path('nope')

@pytest.mark.parametrize('task',a._EXPECTED_TASKS)
def test_counterfactual_changes_answer(task):
    row=a._counterfactual(_overflow(),task); assert row['necessary'] is True; assert row['ablated']!=row['original']

def test_delegate_value_branch_is_not_independently_necessary():
    row=a._counterfactual(_overflow(),'novel_delegate_choice'); assert row['value_only_ablation']==ex.WITNESS_A; assert row['value_necessary_on_stage7_workload'] is False

def test_unknown_counterfactual_rejected():
    with pytest.raises(ValueError, match='no Stage-7A counterfactual'): a._counterfactual(_overflow(),'current_trust_sign')

def test_trace_rejects_full_drift(monkeypatch):
    original=s7._answer
    monkeypatch.setattr(s7,'_answer',lambda frozen,task:{'status':'unsupported','answer':None} if frozen['mode']=='full' else original(frozen,task))
    with pytest.raises(RuntimeError, match='Full-Ghost anchor drifted'): a._trace('first_overflow','early_marker_source')

def test_trace_rejects_baseline_divergence_disappearing(monkeypatch):
    original=s7._answer
    def fake(frozen,task):
        return {'status':'supported','answer':ex.WITNESS_A} if frozen['mode']=='baseline' else original(frozen,task)
    monkeypatch.setattr(s7,'_answer',fake)
    with pytest.raises(RuntimeError, match='baseline divergence disappeared'): a._trace('first_overflow','early_marker_source')

def test_trace_contains_exact_path_and_overflow_state():
    row=a._trace('first_overflow','early_marker_source'); assert row['host_steps']==[2]; assert row['component']=='epistemic_observation_provenance'; assert row['perception_has_early_promise'] is False; assert row['epistemic_has_early_promise'] is True; assert row['counterfactual']['necessary'] is True

def test_run_attribution_exact_findings():
    result=a.run_attribution(); assert result['schema']==a.SCHEMA; assert result['strict_verdict']==a.VERDICT; assert result['traced_divergences']==14; assert result['causally_perturbed']==14
    assert result['component_counts']=={'epistemic_belief_lineage':2,'epistemic_evidence_graph':4,'epistemic_observation_provenance':2,'relationship_aggregate':4,'relationship_aggregate_plus_value_branch':2}
    assert result['findings']=={'all_14_have_exact_persisted_state_paths':True,'all_14_change_under_preregistered_component_ablation':True,'overflow_perception_missing_early_promise':True,'overflow_epistemic_retains_early_promise':True,'delegate_value_branch_causally_required':False}

def test_stage7_anchor_drift_rejected(monkeypatch):
    monkeypatch.setattr(s7,'run_matrix',lambda:{'totals':{}})
    with pytest.raises(RuntimeError, match='result anchor drifted'): a.run_attribution()
