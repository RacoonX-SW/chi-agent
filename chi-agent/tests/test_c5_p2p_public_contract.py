"""Synthetic tests of the pinned public P2P service contract; no world fixtures."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from chi_bench.core.enums import CaseStatus, IntakeStatus, MdReviewDecision, PayerRole, PeerToPeerOutcome, PeerToPeerStatus
from chi_bench.core.errors import InvalidCaseActionError
from chi_bench.core.models import DirectoryContact, MdCaseDecision, P2PSessionRecord, PayerPeerToPeerRequest, PriorAuthCase
from chi_bench.services.determination import DeterminationService
from chi_bench.services.p2p import P2PService
from chi_bench.services.review import ReviewService

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CASE = 'CASE-SYNTHETIC'
REQUEST = 'P2P-SYNTHETIC'


class MemoryStore:
    def __init__(self): self.rows = {}
    def save_resource(self, domain, kind, key, value):
        self.rows[(domain, kind, key)] = deepcopy(value)
    def get_resource(self, domain, kind, key):
        return deepcopy(self.rows[(domain, kind, key)])
    def list_models(self, domain, kind, model):
        return [model.model_validate(deepcopy(value)) for (d, k, _), value in self.rows.items()
                if d == domain and k == kind]


class SyntheticContext:
    """Only supplies external store/world interfaces; service logic remains real."""
    def __init__(self):
        self.store = MemoryStore()
        self.now = NOW
        self.case = PriorAuthCase(id=CASE, external_case_id='EXTERNAL-SYNTHETIC', patient_id='PATIENT-SYNTHETIC',
            service_request_id='ORDER-SYNTHETIC', status=CaseStatus.UNDER_REVIEW, urgency='standard',
            requested_by='PROVIDER-SYNTHETIC', assigned_to='REVIEWER-SYNTHETIC',
            created_at=NOW, updated_at=NOW, decision_due_at=NOW)
        self.contact = DirectoryContact(id='REVIEWER-SYNTHETIC', name='Synthetic reviewer', role='physician',
            email='synthetic@example.invalid', phone='000', organization_id='ORG-SYNTHETIC', escalation_role='none')
        self.session = None
        self.intake = SimpleNamespace(get_intake_case=lambda _: {'id':'INTAKE-SYNTHETIC'})
        self.p2p = SimpleNamespace(initialize_workflow_request=lambda _: None)
        self.review = ReviewService(self)
        self.determination = DeterminationService(self)
        self.artifacts = []
    def ensure_payer_mode_enabled(self): pass
    def active_review_task_for_case(self, _): return None
    def stage_trace(self, *args, **kwargs): pass
    def audit(self, *args, **kwargs): pass
    def get_case(self, case_id):
        assert case_id == CASE
        return self.case
    def intake_case_for_case(self, case_id):
        assert case_id == CASE
        return SimpleNamespace(id='INTAKE-SYNTHETIC', status=IntakeStatus.COMPLETE, decision_member_eligible=True)
    def create_peer_to_peer_request_internal(self, case_id, actor):
        item=PayerPeerToPeerRequest(id=REQUEST,case_id=case_id,created_at=NOW,updated_at=NOW)
        self.save_peer_to_peer_request(item)
        return {'p2p_request':item.model_dump(mode='json')}
    def save_peer_to_peer_request(self, item):
        self.store.save_resource('payer','payer_peer_to_peer_requests',item.id,item.model_dump(mode='json'))
    def get_peer_to_peer_request(self, request_id):
        return PayerPeerToPeerRequest.model_validate(self.store.get_resource('payer','payer_peer_to_peer_requests',request_id))
    def get_p2p_session_for_request(self, request_id): return self.session
    def publish_shared_peer_to_peer_artifact(self, **kwargs):
        self.artifacts.append(kwargs); return SimpleNamespace()
    def persist_workspace_artifact(self, **kwargs):
        self.artifacts.append(kwargs); return SimpleNamespace()
    def peer_to_peer_thread_id(self, request_id): return 'THREAD-SYNTHETIC'
    def payer_reviewer_contacts(self): return [self.contact]
    def payer_role_for_contact(self, contact): return PayerRole.PHYSICIAN_REVIEWER
    def ensure_reviewer_role(self, actor, allowed_roles): return self.contact, PayerRole.PHYSICIAN_REVIEWER
    def get_policy(self, case_id): raise KeyError(case_id)


def start_p2p(ctx):
    result=ctx.review.submit_md_case_decision(CASE,'p2p_review',clinical_notes='Synthetic reason',
                                               reviewer_id=ctx.contact.id,signed_off=False)
    assert result['case_decision']['decision']=='p2p_review'
    assert result['case_decision']['signed_off'] is False
    assert result['case_decision']['p2p_request_id'] is None
    assert result['p2p_request']['id']==REQUEST
    stored=ctx.review._load_md_case_decision(CASE)
    assert stored.p2p_request_id==REQUEST
    return stored


def preflight(ctx, decision, *, overridden=False, reason=''):
    return ctx.determination._preflight_finalization(case_id=CASE,decision=decision,
             overridden=overridden,override_reason=reason,actor=ctx.contact.id)


def test_unsigned_p2p_accepted_but_unsigned_deny_and_amend_rejected():
    ctx=SyntheticContext()
    with pytest.raises(ValueError,match='sign-off'):
        ctx.review.submit_md_case_decision(CASE,'deny',denial_rationale='Synthetic',signed_off=False)
    assert ctx.store.list_models('payer','payer_md_case_decisions',MdCaseDecision)==[]
    md=start_p2p(ctx)
    assert md.decision==MdReviewDecision.P2P_REVIEW and md.signed_off is False
    with pytest.raises(InvalidCaseActionError,match='already been submitted'):
        ctx.review.submit_md_case_decision(CASE,'deny',denial_rationale='Synthetic',signed_off=True)


@pytest.mark.parametrize('status',[None,'requested','slots_offered','slot_selected','scheduled','event_open'])
def test_unfinished_or_missing_request_blocks_override(status):
    ctx=SyntheticContext();md=start_p2p(ctx)
    key=('payer','payer_peer_to_peer_requests',REQUEST)
    if status is None: del ctx.store.rows[key]
    else: ctx.store.rows[key]['status']=status
    assert ctx.determination._resolve_p2p_status(md)=={'pending':True,'outcome':None}
    state=ctx.determination._resolve_source_state(CASE)
    assert state['blocking_reason']=='peer_to_peer_pending'
    before=deepcopy(ctx.store.rows)
    with pytest.raises(InvalidCaseActionError,match='peer-to-peer review is still in progress'):
        preflight(ctx,'approved',overridden=True,reason='Synthetic override')
    assert ctx.store.rows==before


@pytest.mark.parametrize('outcome,recommendation,decision',[
    ('uphold_intended_adverse_decision','deny','denied'),
    ('overturn_to_approval','approve','approved'),
])
def test_completed_outcome_resolves_original_without_amending_md(outcome,recommendation,decision):
    ctx=SyntheticContext();start_p2p(ctx)
    item=ctx.get_peer_to_peer_request(REQUEST);item.status=PeerToPeerStatus.COMPLETED;item.outcome=PeerToPeerOutcome(outcome)
    ctx.save_peer_to_peer_request(item)
    state=ctx.determination._resolve_source_state(CASE)
    assert state['recommendation']==state['original_recommendation']==recommendation
    assert state['md_decision'].decision==MdReviewDecision.P2P_REVIEW and state['md_decision'].signed_off is False
    before=deepcopy(ctx.store.rows)
    plan=preflight(ctx,decision)
    assert plan.record.original_recommendation==recommendation and plan.record.final_decision.value==decision
    other='approved' if decision=='denied' else 'denied'
    with pytest.raises(ValueError,match='Override metadata'): preflight(ctx,other)
    with pytest.raises(ValueError,match='Override reason'): preflight(ctx,other,overridden=True)
    override=preflight(ctx,other,overridden=True,reason='Synthetic override')
    assert override.record.overridden is True and override.record.override_reason=='Synthetic override'
    assert ctx.review._load_md_case_decision(CASE).decision==MdReviewDecision.P2P_REVIEW
    assert ctx.store.rows==before


@pytest.mark.parametrize('bad',[None,'invented',42])
def test_completed_missing_or_invalid_outcome_never_defaults(bad):
    ctx=SyntheticContext();start_p2p(ctx)
    row=ctx.store.rows[('payer','payer_peer_to_peer_requests',REQUEST)]
    row['status']='completed';row['outcome']=bad
    with pytest.raises(ValueError,match='Unsupported completed peer-to-peer outcome'):
        ctx.determination._resolve_source_state(CASE)


@pytest.mark.parametrize('initial',['requested','event_open'])
@pytest.mark.parametrize('outcome,recommendation', [('uphold_intended_adverse_decision','deny'),('overturn_to_approval','approve')])
def test_record_outcome_closes_request_once_including_earlier_status(initial,outcome,recommendation):
    ctx=SyntheticContext();md=start_p2p(ctx)
    row=ctx.store.rows[('payer','payer_peer_to_peer_requests',REQUEST)];row['status']=initial
    ctx.session=P2PSessionRecord(id='SESSION-SYNTHETIC',request_id=REQUEST,case_id=CASE,
        benchmark_side='payer',finalized=True,created_at=NOW,updated_at=NOW)
    assert ctx.determination._resolve_p2p_status(md)['pending'] is True
    p2p=P2PService(ctx)
    result=p2p.record_p2p_outcome(REQUEST,payer_contact_id=ctx.contact.id,
                                   outcome=outcome,note='Synthetic')
    assert result['p2p_request']['status']=='completed'
    assert result['p2p_request']['outcome']==outcome
    assert ctx.determination._resolve_source_state(CASE)['recommendation']==recommendation
    assert len(ctx.artifacts)==2
    with pytest.raises(InvalidCaseActionError,match='already completed'):
        p2p.record_p2p_outcome(REQUEST,outcome='uphold_intended_adverse_decision')


def test_md_without_p2p_request_id_is_pending():
    ctx=SyntheticContext();md=start_p2p(ctx)
    md.p2p_request_id=None
    assert ctx.determination._resolve_p2p_status(md)=={'pending':True,'outcome':None}


@pytest.mark.parametrize('status',['missing','unrecognized'])
def test_invalid_request_status_is_not_treated_as_completed(status):
    ctx=SyntheticContext();md=start_p2p(ctx)
    row=ctx.store.rows[('payer','payer_peer_to_peer_requests',REQUEST)]
    if status=='missing': del row['status']
    else: row['status']='invented'
    with pytest.raises(ValueError): ctx.determination._resolve_p2p_status(md)
