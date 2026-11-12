from chi_agent.context_budget import check_budget, measure_request
from chi_agent.runtime_policy import output_limit, summary_policy


def test_limits_are_version_and_purpose_specific():
    assert summary_policy('chi-input-summary-v1')['max_output_tokens'] == 8192
    assert summary_policy('chi-input-summary-v2')['max_output_tokens'] == 32768
    for version in ('chi-input-summary-v1', 'chi-input-summary-v2'):
        assert output_limit('chi', 'main', version) == 8192
        assert output_limit('chi', 'continuation', version) == 8192
        assert output_limit('chi', 'patient_simulator', version) == 8192
        assert output_limit('chi', 'confirmation', version) == 32768
        assert output_limit('coding_b', 'main', version) == 1024


def test_actual_context_boundary_reserves_new_output_limit():
    body = {'messages': [{'role': 'user', 'content': 'synthetic'}], 'max_tokens': 32768}
    metric = measure_request(body)
    budget = {'schema': 'chi-context-budget-v2', 'max_chars': 10000,
              'max_estimated_tokens': metric['estimated_tokens'] + 32768,
              'output_reserve_tokens': 8192, 'basis': 'synthetic'}
    assert check_budget(metric, budget) is None
    assert metric['effective_output_reserve_tokens'] == 32768
    budget['max_estimated_tokens'] -= 1
    assert check_budget(metric, budget) == 'chi_context_budget_exceeded'
