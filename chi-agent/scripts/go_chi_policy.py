"""Fixed Go CHI request timing policy, also bound into the bundle profile.

`main_read_seconds` is the per-read socket budget and `main_io_seconds` the total
wall budget for one main request. They are sized from measured evidence, not
from the transport default: provider round 17 needed 67.7s and CM round 8 needed
90.8s server-side while the client had already given up at 60s (both HTTP 200).
Raising the window only delays a real stall; it cannot turn a hung request into
a success, and a timeout still records unknown usage and stops the run.
"""
TIME_POLICY = {"connect_seconds": 10, "main_read_seconds": 240, "confirmation_read_seconds": 360,
               "write_seconds": 60, "pool_seconds": 60, "main_io_seconds": 300,
               "confirmation_io_seconds": 420, "b_admission_seconds": 180, "chi_admission_seconds": 900,
               "b_operator_seconds": 360, "chi_operator_seconds": 1380, "operator_max_seconds": 3600}
FEE_POLICY = 'go-chi-record-incomplete-fees-v1'

RECOVERY_POLICY = {"version": "chi-output-recovery-v1", "default_enabled": False,
                   "max_per_chain": 1, "max_per_run": 2, "max_output_tokens": 8192,
                   "shared_max_requests": 50, "instruction_version": "chi-recovery-instruction-v1",
                   "view_version": "chi-recovery-view-v1"}
