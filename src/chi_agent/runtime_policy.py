"""Fixed Go CHI request timing policy, also bound into the bundle profile.

`main_read_seconds` is the per-read socket budget and `main_io_seconds` the total
wall budget for one main request. They are sized from measured evidence, not
from the transport default: provider round 17 needed 67.7s and CM round 8 needed
90.8s server-side while the client had already given up at 60s (both HTTP 200).
Raising the window only delays a real stall; it cannot turn a hung request into
a success, and a timeout still records unknown usage and stops the run.
"""
TIME_POLICY = {"connect_seconds": 30, "main_read_seconds": 300, "confirmation_read_seconds": 360,
               "write_seconds": 60, "pool_seconds": 60, "main_io_seconds": 360,
               "confirmation_io_seconds": 420, "b_admission_seconds": 180, "chi_admission_seconds": 1800,
               "b_operator_seconds": 360, "chi_operator_seconds": 1380, "operator_max_seconds": 3600}
FEE_POLICY = 'go-chi-record-incomplete-fees-v1'

# Main-agent context profiles. These constants are part of the frozen bundle
# profile: changing them requires rebuilding the bundle and a new B admission.
# The judge and patient simulator are separate processes and do not share this
# budget.
CONTEXT_PROFILES = {
    "deepseek-v4.1-flash": {
        "model": "deepseek-v4.1-flash",
        "provider_context_tokens": 1_000_000,
        "window_safety_fraction": 0.6,
        "output_reserve_tokens": 16_384,
        "bytes_per_token_floor": 3.0,
        "bytes_per_token_observed": 3.9,
        "max_context_bytes": 1_500_000,
        "max_input_tokens": 500_000,
    },
}
DEFAULT_CONTEXT_MODEL = "deepseek-v4.1-flash"


def context_profile(model):
    """Return the immutable context profile for an exact runtime model id."""
    if type(model) is not str or model not in CONTEXT_PROFILES:
        raise ValueError("chi_context_profile_invalid")
    return dict(CONTEXT_PROFILES[model])

RECOVERY_POLICY = {"version": "chi-output-recovery-v1", "default_enabled": False,
                   "max_per_chain": 1, "max_per_run": 2, "max_output_tokens": 8192,
                   "shared_max_requests": 50, "instruction_version": "chi-recovery-instruction-v1",
                   "view_version": "chi-recovery-view-v1"}

SUMMARY_POLICY = {"version": "chi-input-summary-v1", "default_enabled": False,
                  "max_per_run": 1, "max_output_tokens": 8192, "shared_max_requests": 50,
                  "trigger_numerator": 4, "trigger_denominator": 5, "retained_batches": 2,
                  "minimum_reduction_bytes": 1024}

SUMMARY_VERSIONS = ('chi-input-summary-v1', 'chi-input-summary-v2')

def summary_policy(version):
    """Return the immutable-by-version policy; never infer a version from a default."""
    if type(version) is not str or version not in SUMMARY_VERSIONS:
        raise ValueError('chi_summary_configuration_invalid')
    policy = dict(SUMMARY_POLICY)
    policy['version'] = version
    policy['max_output_tokens'] = 8192 if version == 'chi-input-summary-v1' else 32768
    return policy

def output_limit(kind, purpose, summary_version=None):
    if purpose == 'summary':
        return summary_policy(summary_version)['max_output_tokens']
    return 1024 if kind == 'coding_b' else 32768 if purpose == 'confirmation' else 8192
