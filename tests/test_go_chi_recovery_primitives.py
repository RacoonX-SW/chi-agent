from copy import deepcopy

import pytest

from chi_agent.context.output_recovery import PARTIAL, REGENERATE, classify, derive_view, mode_and_fragment
from chi_agent.accounting.request_budget import feedback


def parent():
    return {'model': 'deepseek-v4.1-flash', 'max_tokens': 8192, 'messages': [
        {'role': 'system', 'content': 'system' + feedback(0, False)[0]},
        {'role': 'user', 'content': 'work'}], 'tools': []}


def response(message):
    return {'model': 'deepseek-v4.1-flash', 'choices': [{'finish_reason': 'length', 'message': message}]}


def test_partial_and_regenerate_views():
    original = parent()
    partial = response({'role': 'assistant', 'content': 'part', 'reasoning_content': 'think'})
    a = derive_view(original, partial, old_used=0, claimed=False)
    assert a['messages'][-2:] == [{'role': 'assistant', 'content': 'part', 'reasoning_content': 'think'},
                                  {'role': 'user', 'content': PARTIAL}]
    batch = response({'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'unfinished', 'type': 'function', 'function': {'name': 'tool', 'arguments': '{'}}]})
    b = derive_view(original, batch, old_used=0, claimed=False)
    assert b['messages'][-1] == {'role': 'user', 'content': REGENERATE}
    assert all(msg.get('tool_calls') is None for msg in b['messages'])
    assert original == parent()


def test_invalid_history_and_classification_fail_closed():
    bad = parent()
    bad['messages'].append({'role': 'assistant', 'tool_calls': [{'id': 'x'}]})
    with pytest.raises(ValueError):
        derive_view(bad, response({'role': 'assistant', 'content': 'part'}), old_used=0, claimed=False)
    assert classify('inbox.list_messages') == 'mutation'
    with pytest.raises(ValueError): classify('unknown.tool')
    bad_response = response({'role': 'assistant', 'content': 'part', 'audio': {'hidden': True}})
    with pytest.raises(ValueError): mode_and_fragment(bad_response)


@pytest.mark.parametrize('call', [
    {'id': 'x'},
    {'id': 'x', 'unexpected': 1},
    {'id': 'x', 'function': []},
    {'id': 'x', 'function': {'arguments': 0}},
    {'id': 'x', 'index': True},
])
def test_malformed_tool_call_cannot_be_regenerated(call):
    with pytest.raises(ValueError):
        mode_and_fragment(response({'role': 'assistant', 'tool_calls': [call]}))
