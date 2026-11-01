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

    def test_capabilities_defaults_and_accepts_off(self):
        self.assertNotIn("capabilities", self.check(dict(self.base)))
        value = dict(self.base); value["capabilities"] = "off"
        self.assertEqual(self.check(value)["capabilities"], "off")
        value["capabilities"] = "f0-f3-v1"
        self.assertEqual(self.check(value)["capabilities"], "f0-f3-v1")

    def test_capabilities_rejects_unknown_mode(self):
        for mode in ("f0-f6-v1", "", None, 0, True):
            with self.subTest(mode=mode):
                value = dict(self.base); value["capabilities"] = mode
                with self.assertRaises(ValueError):
                    self.check(value)

    def test_local_rejects_state_relative(self):
        value = dict(self.base); value["history_mode"] = "local"
        value["state_relative"] = "runs/external-state"
        with self.assertRaises(ValueError):
            self.check(value)


if __name__ == "__main__":
    unittest.main()
