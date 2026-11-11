import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HAS_OPERATOR_DEPS = (importlib.util.find_spec("docker.types") is not None
                     and importlib.util.find_spec("chi_bench") is not None)
if HAS_OPERATOR_DEPS:
    import role_operator


@unittest.skipUnless(HAS_OPERATOR_DEPS, "role operator dependencies are only in the controller image")
class RoleOperatorConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = {
            "schema": "chi-role-operator-v1", "run_id": "run-1", "evaluation_id": "eval-1",
            "task_id": "pa_t011_t011_o003_p01_intake_payer", "attempt_id": "attempt-1",
            "role": "payer", "bundle_relative": "runs/release/package", "bundle_sha256": "a" * 64,
            "runtime_identity": "b" * 64, "runner_image_id": "sha256:" + "c" * 64,
            "world_image_id": "sha256:" + "d" * 64,
            "dataset_relative": "runs/dataset", "manifest_relative": "runs/payer.json",
            "manifest_sha256": "e" * 64, "output_relative": "runs/operator-1",
            "dev_sha256": {name: "f" * 64 for name in role_operator.DEV_FILES},
            "operator_timeout_seconds": 2040,
        }

    def tearDown(self):
        self.temp.cleanup()

    def check(self, value):
        path = self.root / "config.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return role_operator._config(path, digest)

    def test_local_default_and_explicit(self):
        self.assertEqual(self.check(dict(self.base))["role"], "payer")
        value = dict(self.base); value["history_mode"] = "local"
        value["local_q_root"] = "runs/prior-go"
        self.assertEqual(self.check(value)["local_q_root"], "runs/prior-go")

    def test_external_requires_state_and_rejects_qroot(self):
        value = dict(self.base); value["history_mode"] = "external"
        with self.assertRaises(ValueError):
            self.check(value)
        value["state_relative"] = "runs/external-state"
        self.assertEqual(self.check(value)["state_relative"], "runs/external-state")
        value["local_q_root"] = "runs/prior-go"
        with self.assertRaises(ValueError):
            self.check(value)

    def test_validation_toggles_default_and_accept_exact_versions(self):
        self.assertEqual(role_operator._validation_flags(self.check(dict(self.base))), [])
        for field, version in (("input_summary", "chi-input-summary-v1"),
                               ("input_summary", "chi-input-summary-v2"),
                               ("output_recovery", "chi-output-recovery-v1")):
            with self.subTest(field=field):
                value = dict(self.base); value[field] = version
                config = self.check(value)
                self.assertEqual(role_operator._validation_flags(config), ["--" + field.replace("_", "-"), version])

    def test_validation_toggles_reject_invalid_values_and_both(self):
        for field in ("input_summary", "output_recovery"):
            for bad in (None, True, 1, [], "", "chi-other-v1", "CHI-INPUT-SUMMARY-V1"):
                with self.subTest(field=field, bad=bad):
                    value = dict(self.base); value[field] = bad
                    with self.assertRaises(ValueError):
                        self.check(value)
        both = dict(self.base)
        both["input_summary"] = "chi-input-summary-v1"
        both["output_recovery"] = "chi-output-recovery-v1"
        with self.assertRaises(ValueError):
            self.check(both)

    def test_context_cap_override(self):
        value = dict(self.base)
        value["context_max_estimated_tokens"] = 2_000_000
        config = self.check(value)
        self.assertEqual(role_operator._validation_flags(config),
                         ["--context-max-estimated-tokens", "2000000"])
        for bad in (None, True, 0, -1, 3_500_001, "2000000", 1.5):
            with self.subTest(bad=bad):
                value = dict(self.base)
                value["context_max_estimated_tokens"] = bad
                with self.assertRaises(ValueError):
                    self.check(value)

    def test_context_input_token_override(self):
        value = dict(self.base)
        value["context_max_input_tokens"] = 500_000
        config = self.check(value)
        self.assertEqual(role_operator._validation_flags(config),
                         ["--context-max-input-tokens", "500000"])
        for bad in (None, True, 0, -1, 1_000_001, "500000", 1.5):
            with self.subTest(bad=bad):
                value = dict(self.base)
                value["context_max_input_tokens"] = bad
                with self.assertRaises(ValueError):
                    self.check(value)
        both = dict(self.base)
        both["context_max_estimated_tokens"] = 1_500_000
        both["context_max_input_tokens"] = 500_000
        with self.assertRaises(ValueError):
            self.check(both)

    def test_recovery_view_policy_requires_output_recovery(self):
        value = dict(self.base)
        value["output_recovery"] = "chi-output-recovery-v1"
        value["recovery_view_policy"] = "canonical-v1"
        config = self.check(value)
        self.assertEqual(role_operator._validation_flags(config),
                         ["--output-recovery", "chi-output-recovery-v1",
                          "--recovery-view-policy", "canonical-v1"])
        for bad in (None, "other", True):
            with self.subTest(bad=bad):
                value = dict(self.base)
                value["output_recovery"] = "chi-output-recovery-v1"
                value["recovery_view_policy"] = bad
                with self.assertRaises(ValueError):
                    self.check(value)
        value = dict(self.base)
        value["recovery_view_policy"] = "canonical-v1"
        with self.assertRaises(ValueError):
            self.check(value)

    def test_main_max_tokens_override(self):
        value = dict(self.base)
        value["main_max_tokens"] = 16384
        config = self.check(value)
        self.assertEqual(role_operator._validation_flags(config),
                         ["--main-max-tokens", "16384"])
        for bad in (None, True, 0, 1023, 32769, "16384", 1.5):
            with self.subTest(bad=bad):
                value = dict(self.base)
                value["main_max_tokens"] = bad
                with self.assertRaises(ValueError):
                    self.check(value)

    def test_output_recovery_and_context_cap_can_combine(self):
        value = dict(self.base)
        value["output_recovery"] = "chi-output-recovery-v1"
        value["context_max_estimated_tokens"] = 2_000_000
        config = self.check(value)
        self.assertEqual(role_operator._validation_flags(config),
                         ["--output-recovery", "chi-output-recovery-v1",
                          "--context-max-estimated-tokens", "2000000"])

    def test_requirements_exact_and_mutual_exclusion(self):
        value = dict(self.base)
        value["requirements"] = "chi-requirements-v1"
        config = self.check(value)
        self.assertEqual(role_operator._validation_flags(config),
                         ["--requirements", "chi-requirements-v1"])
        for bad in (None, True, 1, [], "", "chi-other-v1", "CHI-REQUIREMENTS-V1"):
            with self.subTest(bad=bad):
                value = dict(self.base)
                value["requirements"] = bad
                with self.assertRaises(ValueError):
                    self.check(value)
        for field, version in (("input_summary", "chi-input-summary-v1"),
                               ("output_recovery", "chi-output-recovery-v1")):
            with self.subTest(field=field):
                value = dict(self.base)
                value["requirements"] = "chi-requirements-v1"
                value[field] = version
                with self.assertRaises(ValueError):
                    self.check(value)

    def test_local_rejects_state_relative(self):
        value = dict(self.base); value["history_mode"] = "local"
        value["state_relative"] = "runs/external-state"
        with self.assertRaises(ValueError):
            self.check(value)


if __name__ == "__main__":
    unittest.main()
