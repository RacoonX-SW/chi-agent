"""Offline checks against the frozen pre-extraction function and exported bundle."""
import __future__
import ast
import hashlib
import itertools
import inspect
import json
import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import budget_evaluation
import go_chi_bundle
import run_baseline

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'tests/fixtures/c3_budget_reference.py.txt'


def baseline_function():
    raw = REFERENCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '915043ffa34227e63b8c563d5cf704c232b6f851539f4e7c36c49dabab23ee6c'
    tree = ast.parse(raw, filename='frozen_origin_main_budget')
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
    namespace = {'Decimal': Decimal, 'InvalidOperation': InvalidOperation}
    exec(compile(tree, 'frozen_origin_main_budget', 'exec',
                 flags=__future__.annotations.compiler_flag, dont_inherit=True), namespace)
    return namespace['evaluate_budget']


def test_old_and_extracted_function_ast_and_behavior_are_equivalent():
    old = baseline_function()
    pure = budget_evaluation.evaluate_budget
    source = ast.parse((ROOT/'scripts/budget_evaluation.py').read_text())
    extracted = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'evaluate_budget')
    assert ast.dump(extracted, include_attributes=False) == ast.dump(ast.parse(REFERENCE.read_bytes()).body[0], include_attributes=False)
    assert run_baseline.evaluate_budget is pure
    assert pure.__annotations__ == old.__annotations__
    assert inspect.signature(pure) == inspect.signature(old)
    base = {'budget_cny': 5.0, 'max_rounds': 30, 'max_tokens_per_request': 1000,
            'rounds_used': 4, 'cumulative_cost_cny': 4.0, 'input_price_usd_per_million': 100.0,
            'output_price_usd_per_million': 100.0, 'max_input_tokens_per_request': 1000,
            'usd_to_cny': 2.0, 'pricing_version': 'test', 'fx_rate_source': 'test'}
    assert pure(**base)[0] == 'within_budget'
    for changes, expected in [({'cumulative_cost_cny': 4.8}, 'stopped_insufficient_budget'),
                              ({'cumulative_cost_cny': 5.1}, 'stopped_budget_exhausted'),
                              ({'rounds_used': 30}, 'stopped_round_limit'),
                              ({'cumulative_cost_cny': None}, 'unverified_unknown_usage'),
                              ({'input_price_usd_per_million': None}, 'unverified_unknown_pricing'),
                              ({'usd_to_cny': None}, 'unverified_unknown_conversion')]:
        values = {**base, **changes}
        assert pure(**values) == old(**values)
        assert pure(**values)[0] == expected
    invalid = (None, True, False, -1, 0, 1, 1.5, float('nan'), float('inf'), '1')
    for key, value in itertools.product(base, invalid):
        values = {**base, key: value}
        try:
            expected = old(**values)
        except Exception as exc:
            try: pure(**values)
            except Exception as actual: assert type(actual) is type(exc)
            else: raise AssertionError('extracted function did not raise')
        else:
            assert pure(**values) == expected


def test_real_exported_package_budget_path_in_isolated_process(tmp_path):
    target = tmp_path/'bundle'
    identity = go_chi_bundle.build_bundle(target, source_root=ROOT)
    assert go_chi_bundle.validate_bundle(target).manifest_sha256 == identity.manifest_sha256
    assert (target/'scripts/budget_evaluation.py').is_file()
    assert not (target/'scripts/run_baseline.py').exists()
    code = r'''
import pathlib, sys
import budget_evaluation as budget, model_runner_adapter as a
root=pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(a.__file__).resolve().is_relative_to(root)
assert pathlib.Path(budget.__file__).resolve().is_relative_to(root)
body={'model':a.CANDIDATE_PROFILE['model'],'max_tokens':128,'messages':[{'role':'user','content':'synthetic closure probe'}]}
assert a._budget_check(a.Ledger('success'), body)>0
checks=[(a.Ledger('over',initial_cost_cny=4.99),body,'budget_exhausted'),
        (a.Ledger('round',rounds=a.MAX_ROUNDS),body,'round_limit'),
        (a.Ledger('unknown',usage_complete=False),body,'usage_unknown'),
        (a.Ledger('bad',known_input_tokens=True),body,'accounting_state_invalid'),
        (a.Ledger('bool'),dict(body,max_tokens=True),'output_limit'),
        (a.Ledger('oversize'),dict(body,max_tokens=129),'output_limit')]
for ledger, request, code in checks:
    try: a._budget_check(ledger,request)
    except a.IntegrationFailure as exc: assert exc.code==code,(code,exc.code)
    else: raise AssertionError(code)
    assert ledger.transport_calls==0
print('isolated_budget_closure=passed; provider_calls=0')
'''
    env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': f'{target}/scripts:/model-deps:/pdf-deps:/vendor/src:/workspace/vendor/chi-bench/src',
           'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-c', code, str(target)], cwd=tmp_path, env=env,
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'provider_calls=0' in result.stdout


def test_actual_identity_calculations_bind_budget_module():
    import b_live_preflight
    import evaluation_entry
    import live_development
    import opencode_go_provider
    expected = hashlib.sha256((ROOT/'scripts/budget_evaluation.py').read_bytes()).hexdigest()
    name = 'scripts/budget_evaluation.py'
    assert opencode_go_provider.source_identity()['files_sha256'][name] == expected
    assert b_live_preflight._source_and_sdk()[0]['application_sources_sha256'][name] == expected
    evaluation = evaluation_entry._runtime_identity()
    assert evaluation['status'] == 'verified_for_offline_integration'
    assert evaluation['source']['application_sources_sha256'][name] == expected
    assert live_development._execution_identity()['application_files_sha256'][name] == expected
