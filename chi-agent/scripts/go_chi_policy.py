"""Fixed Go CHI request timing policy, also bound into the bundle profile."""
TIME_POLICY = {"connect_seconds": 10, "main_read_seconds": 60, "confirmation_read_seconds": 360,
               "write_seconds": 60, "pool_seconds": 60, "main_io_seconds": 120,
               "confirmation_io_seconds": 420, "b_admission_seconds": 180, "chi_admission_seconds": 900,
               "b_operator_seconds": 360, "chi_operator_seconds": 1380, "operator_max_seconds": 3600}
