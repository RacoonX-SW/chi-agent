import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from chi_agent.journal import ChiJournal
from chi_agent.patient_identity_binding import PatientBinding, Refusal
from chi_agent.runtime import run_chi


class MemoryJournal:
    def __init__(self): self.run_doc = {}
    def _persist(self): pass


def result(value):
    return SimpleNamespace(isError=False, structuredContent=value, content=[],
                           model_dump=lambda **_: {"structuredContent": value, "content": [], "isError": False})


def sample():
    patients = [{"id": f"P{i}", "patient_name": ("名\\\"" * 45) + str(i),
                 "sex": "male" if i == 0 else "female", "dob": "1970-01-01"} for i in range(65)]
    roster = {"items": patients, "total": len(patients)}
    chart = {"patient": patients[0], "orders": [{"id": "O1", "patient_id": "P0",
                                                   "procedure_code": "12345", "site_of_service": "22"}],
             "notes": "90 day treatment trial " + ('中文\\\"\n' * 3000)}
    return roster, chart


def test_page_coverage_requires_exact_current_source_and_no_gaps():
    roster, chart = sample()
    binding = PatientBinding("90 day treatment trial", MemoryJournal())
    binding.observe("r", "chart.search_patients", {}, result(roster))
    binding.observe("c", "chart.get_patient_chart_by_patient", {"patient_id": "P0"}, result(chart))
    roster_pages, chart_pages = [], []
    for pages, read, tool in ((roster_pages, lambda off: binding.read_roster(__import__('hashlib').sha256(binding.roster['text'].encode()).hexdigest(), off), "local-read-patient-roster"),
                              (chart_pages, lambda off: binding.read_observation("P0", off), "local-read-patient-observation")):
        offset = 0
        while offset is not None:
            raw = read(offset); page = json.loads(raw)
            assert len(raw) <= 8192 and len(raw.encode()) <= 32768
            pages.append({"call_id": "r" if tool.endswith('roster') and offset == 0 else f"{tool}{offset}", "tool": tool, "result": raw})
            offset = page['next_offset']
    assert len(roster_pages) > 1 and len(chart_pages) > 1
    assert len(json.loads(binding.confirmation_input("P0", roster_pages + chart_pages))["required_candidate_ids"]) == 65
    for history, reason in ((roster_pages[:-1] + chart_pages, "roster_not_observed"),
                            (roster_pages + chart_pages[1:], "candidate_observations_incomplete")):
        with pytest.raises(Refusal, match=reason): binding.confirmation_input("P0", history)
    bad = [dict(x) for x in chart_pages]; page = json.loads(bad[0]['result']); page['content'] += 'x'; bad[0]['result'] = json.dumps(page)
    with pytest.raises(Refusal, match="candidate_observations_incomplete"): binding.confirmation_input("P0", roster_pages + bad)
    updated = dict(chart, notes=chart['notes'] + 'changed')
    binding.observe("new", "chart.get_patient_chart_by_patient", {"patient_id": "P0"}, result(updated))
    with pytest.raises(Refusal, match="candidate_observations_incomplete"): binding.confirmation_input("P0", roster_pages + chart_pages)
    with pytest.raises(Refusal, match="version_mismatch"): binding.read_observation("P0", 0, json.loads(chart_pages[0]['result'])['sha256'])
    roster2 = dict(roster, items=list(reversed(roster['items'])))
    binding.observe("r2", "chart.search_patients", {}, result(roster2))
    with pytest.raises(Refusal, match="roster_not_observed"): binding.confirmation_input("P0", roster_pages + chart_pages)


@pytest.mark.parametrize("v3", [False, True])
def test_actual_go_transport_delivers_pages_and_guards_mutations(tmp_path, v3):
    asyncio.run(_exercise_transport(tmp_path, v3))


async def _exercise_transport(tmp_path, v3):
    roster, chart = sample()
    class Server:
        def __init__(self): self.calls = []
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def list_tools(self):
            def tool(name, props, required):
                return SimpleNamespace(name=name, description="synthetic", inputSchema={"type":"object", "properties":props, "required":required, "additionalProperties":False})
            return [tool("chart.search_patients", {}, []), tool("chart.get_patient_chart_by_patient", {"patient_id":{"type":"string"}}, ["patient_id"]),
                    tool("cases.create_from_order", {key: {"type": "string"} for key in
                          ("patient_id", "source_order_id", "procedure_code", "site_of_service")},
                         ["patient_id", "source_order_id"])]
        async def call_tool(self, name, args):
            self.calls.append((name, args))
            if name == 'chart.search_patients': return result(roster)
            if name == 'chart.get_patient_chart_by_patient': return result(chart)
            return result({"case":{"id":"C1", "patient_id":"P0", "service_request_id":"O1"}, "patient":{"id":"P0"}, "service_request":{"id":"O1", "patient_id":"P0"}})
    server = Server(); requests = []; confirm_wire = []; steps = []; delivered_pages = {}
    location_quote = '"site_of_service": "22"'
    location_page = None
    async def wire(request):
        nonlocal location_page
        body = json.loads(request.content); requests.append(body)
        if 'response_format' in body:
            confirm_wire.append(body)
            verdict = {"status":"unique_match", "selected_patient_id":"P0", "matches":["P0"], "mismatches":[f"P{i}" for i in range(1,65)], "unknown":[], "evidence":[{"instruction_quote":"90 day treatment trial", "chart_quote":"90 day treatment trial"}]}
            message = {"role":"assistant", "content":json.dumps(verdict)}; finish = 'stop'
        else:
            n = len(steps)
            if n == 0: name, args = 'chart__search_patients', {}
            elif n == 1: name, args = 'chart__get_patient_chart_by_patient', {'patient_id':'P0'}
            else:
                tool_messages = [m for m in body['messages'] if m['role'] == 'tool']
                pages = []
                for m in tool_messages:
                    try: pages.append((m['tool_call_id'], json.loads(m['content'])))
                    except (ValueError, TypeError): pass
                for call_id, page in pages:
                    if page.get('kind') == 'patient_roster_page':
                        delivered_pages[('roster', page['offset'])] = page
                    elif page.get('patient_id') == 'P0' and 'next_offset' in page and 'content' in page:
                        delivered_pages[('chart', page['offset'])] = page
                        if location_quote in page['content']:
                            location_page = call_id
                roster_pages = [page for (kind, _), page in delivered_pages.items() if kind == 'roster']
                chart_pages = [page for (kind, _), page in delivered_pages.items() if kind == 'chart']
                if roster_pages[-1]['next_offset'] is not None:
                    p = roster_pages[-1]; name, args = 'local-read-patient-roster', {'sha256':p['sha256'], 'offset':p['next_offset']}
                elif not chart_pages or chart_pages[-1]['next_offset'] is not None:
                    name, args = 'local-read-patient-observation', {'patient_id':'P0', 'offset':chart_pages[-1]['next_offset'] if chart_pages else 0}
                elif not any(s[0] == 'local-confirm-patient' for s in steps):
                    name, args = 'local-confirm-patient', {'patient_id':'P0', 'instruction_quote':'90 day treatment trial', 'chart_quote':'90 day treatment trial'}
                elif v3 and not any(s[0] == 'local-state-update' for s in steps):
                    assert location_page is not None
                    name, args = 'local-state-update', {'provider_location': {'site_of_service': 'outpatient_hospital',
                                                                              'source_call_id': location_page, 'quote': location_quote}}
                elif not any(s[0] == 'cases__create_from_order' and s[1]['patient_id'] == 'P1' for s in steps):
                    name, args = 'cases__create_from_order', {'patient_id':'P1', 'source_order_id':'O1'}
                elif not any(s[0] == 'cases__create_from_order' and s[1]['patient_id'] == 'P0' for s in steps):
                    name, args = 'cases__create_from_order', {'patient_id':'P0', 'source_order_id':'O1'}
                    if v3:
                        args.update(procedure_code='12345', site_of_service='outpatient_hospital')
                elif v3 and not any(s[0] == 'local-claim_done' for s in steps):
                    name, args = 'local-claim_done', {}
                else: name = None
            if name:
                steps.append((name,args)); message = {'role':'assistant','content':None,'reasoning_content':'reason','tool_calls':[{'id':f'call_{len(steps)}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}; finish = 'tool_calls'
            else: message = {'role':'assistant','content':'done'}; finish = 'stop'
        return httpx.Response(200, request=request, json={'id':'synthetic','object':'chat.completion','created':0,'model':'deepseek-v4.1-flash','choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5,'cost':0,'opencode':{'billing_source':'go','list_cost':0.1,'allowance':0.1}}})
    instruction = tmp_path/'instruction'; instruction.write_text('90 day treatment trial')
    handbook = tmp_path/'handbook'; handbook.mkdir(); workspace = tmp_path/'workspace'; workspace.mkdir()
    launch = {'context_policy': 'chi-context-v3', 'source_evidence_policy': 'canonical-v1', 'role': 'provider'} if v3 else {}
    journal = ChiJournal(tmp_path/'state', identity='a'*64, evaluation='eval', task='provider', attempt='a', run='run', launch=launch)
    from chi_agent.context_budget import budget_from_input_tokens, DEFAULT_BUDGET
    budget = budget_from_input_tokens(45000) if v3 else DEFAULT_BUDGET
    try:
        async def run():
            return await run_chi(journal, 'synthetic-secret', role='provider', instruction='90 day treatment trial', mcp_url='http://synthetic.invalid/mcp', instruction_path=instruction, logs_dir=tmp_path/'logs', workspace_root=workspace, handbook_root=handbook, tool_references=[], lower=httpx.MockTransport(wire), server_factory=lambda _: server, capabilities="f0-f3-v1" if v3 else None, context_budget=budget)
        if v3:
            from chi_agent.opencode_go_provider import GoFailure
            # The synthetic workflow intentionally stops before terminal authorization;
            # production completion rules correctly prevent its claim.
            with pytest.raises(GoFailure, match='chi_claim_required'):
                await run()
        else:
            await run()
        assert len(confirm_wire) == 1
        payload = json.loads(confirm_wire[0]['messages'][-1]['content'])['public_observations']
        assert len(payload['required_candidate_ids']) == 65 and payload['charts']['P0'] == chart
        assert [args['patient_id'] for name,args in server.calls if name == 'cases.create_from_order'] == ['P0']
        assert any('REFUSED:' in str(m['content']) for body in requests for m in body['messages'] if m.get('role') == 'tool' and m.get('tool_call_id') == f'call_{next(i for i,s in enumerate(steps,1) if s[0] == "cases__create_from_order" and s[1]["patient_id"] == "P1")}')
        if v3:
            before_confirm = next(i for i, body in enumerate(requests) if 'response_format' in body) - 1
            main_wire = requests[before_confirm]
            prior = [m for m in main_wire['messages'] if m.get('role') == 'tool' and 'chi-tool-result-ref-v1' in str(m.get('content'))]
            assert prior, 'expected earlier delivered pages to be projected from the confirmation-triggering request'
            projected_ids = {m['tool_call_id'] for m in prior}
            page_calls = {f'call_{i}' for i, (name, _) in enumerate(steps, 1) if name in {'chart__search_patients', 'local-read-patient-roster', 'local-read-patient-observation'}}
            assert projected_ids & page_calls
            assert any(m.get('tool_call_id') in projected_ids and 'patient_roster_page' in str(m.get('content')) for body in requests[:before_confirm] for m in body['messages'] if m.get('role') == 'tool')
        journal.finish('failed' if v3 else 'complete', error='chi_claim_required' if v3 else None)
        if v3:
            journal._validate('a' * 64)
    finally: journal.close()
    if v3:
        from chi_agent.journal import inspect_history
        import hashlib
        raw = (tmp_path/'state'/'chi-accounting.json').read_bytes()
        assert inspect_history(tmp_path/'state', 'a'*64, hashlib.sha256(raw).hexdigest())['status'] == 'inspected'


def test_legacy_fixed_pages_remain_valid():
    roster, chart = sample()
    binding = PatientBinding('90 day treatment trial', MemoryJournal())
    binding.observe('r', 'chart.search_patients', {}, result(roster))
    binding.observe('c', 'chart.get_patient_chart_by_patient', {'patient_id': 'P0'}, result(chart))
    import hashlib
    text = binding.charts['P0']['text']
    history = [{'call_id':'r', 'result':json.dumps(roster, ensure_ascii=False)}]
    for offset in range(0, len(text), 12000):
        page = {'patient_id':'P0', 'offset':offset, 'total':len(text),
                'sha256':hashlib.sha256(text.encode()).hexdigest(), 'content':text[offset:offset+12000]}
        history.append({'tool':'local-read-patient-observation', 'result':json.dumps(page, ensure_ascii=False)})
    assert json.loads(binding.confirmation_input('P0', history))['expected_count'] == 65


def test_partial_and_filtered_results_do_not_establish_roster():
    roster, _ = sample()
    binding = PatientBinding('instruction', MemoryJournal())
    binding.observe('filtered', 'chart.search_patients', {'query':'P'}, result(roster))
    assert binding.roster is None
    binding.observe('partial', 'chart.search_patients', {}, result({'items':roster['items'][:10], 'total':65}))
    assert binding.roster is None


def test_summary_verifies_roster_page_against_original_evidence(tmp_path):
    import hashlib
    from chi_agent.evidence import write_tool
    from chi_agent.input_summary import verify_tool_actions
    roster, _ = sample()
    binding = PatientBinding('instruction', MemoryJournal())
    binding.observe('call_0', 'chart.search_patients', {}, result(roster))
    raw = json.dumps(roster, ensure_ascii=False)
    page = binding.read_roster(hashlib.sha256(raw.encode()).hexdigest(), 0)
    evidence = write_tool(tmp_path, 'run', 'call_0', raw, ())
    digest = hashlib.sha256(raw.encode()).hexdigest()
    events = [{'call_id':'call_0', 'tool':'chart.search_patients', 'event':'started', 'arguments_sha256':hashlib.sha256(b'{}').hexdigest()},
              {'call_id':'call_0', 'tool':'chart.search_patients', 'event':'returned', 'result_sha256':digest, 'result_evidence_sha256':evidence}]
    records = [{'id':'call_0', 'name':'search', 'arguments':{}, 'result':page}]
    mapping = {'search':'chart.search_patients'}
    assert verify_tool_actions(records, events, mapping, root=tmp_path, run='run')[0]['result_sha256'] == digest
    changed = json.loads(page); changed['items'][0]['id'] = 'forged'; records[0]['result'] = json.dumps(changed, ensure_ascii=False)
    with pytest.raises(ValueError): verify_tool_actions(records, events, mapping, root=tmp_path, run='run')
