import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import go_chi_delivery as delivery
from go_chi_bundle import build_bundle

ROOT = Path(__file__).parents[1]


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = build_bundle(self.root / "bundle", source_root=ROOT)
        (self.root / "model" / "agents").mkdir(parents=True)
        (self.root / "pdf" / "pypdf").mkdir(parents=True)
        (self.root / "vendor" / "src" / "chi_bench").mkdir(parents=True)
        (self.root / "handbook").mkdir()
        (self.root / "instruction.md").write_text("public instruction", encoding="utf-8")
        (self.root / "tool_reference.md").write_text("public tool reference", encoding="utf-8")
        (self.root / "state").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        return {
            "schema": "chi-go-delivery-plan-v1",
            "role": "provider",
            "bundle": {"root": str(self.bundle.root), "sha256": self.bundle.manifest_sha256},
            "dependencies": {"model_root": str(self.root / "model"),
                              "pdf_root": str(self.root / "pdf")},
            "vendor": {"root": str(self.root / "vendor"), "commit": "4" * 40},
            "resources": {"instruction": str(self.root / "instruction.md"),
                          "handbook_root": str(self.root / "handbook"),
                          "tool_references": [str(self.root / "tool_reference.md")]},
            "mcp": {"url": "http://world:8020/mcp", "role": "provider"},
            "state": {"output_root": str(self.root / "state"),
                       "logs_dir": str(self.root / "logs")},
            "history": {"mode": "external", "q_root": None},
            "credentials": {"model_env": "OPENCODE_API_KEY",
                            "forbidden_env": sorted(delivery.FORBIDDEN_ENV)},
        }

    def test_valid_plan_checks_without_network_install(self):
        report = delivery.check_plan(self.plan())
        self.assertEqual(report["status"], "valid")
        self.assertFalse(report["network_install"])
        self.assertEqual(report["credential_names"], ["OPENCODE_API_KEY"])
        self.assertRegex(report["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["bundle_manifest_sha256"], self.bundle.manifest_sha256)

    def test_missing_bundle_dependencies_and_vendor(self):
        plan = self.plan()
        plan["bundle"]["root"] = str(self.root / "absent")
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_bundle_missing")
        plan = self.plan()
        plan["dependencies"]["model_root"] = str(self.root / "absent")
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_dependencies_missing")
        plan = self.plan()
        plan["vendor"]["root"] = str(self.root / "absent")
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_vendor_missing")

    def test_bundle_identity_mismatch_is_rejected(self):
        plan = self.plan()
        plan["bundle"]["sha256"] = "f" * 64
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_bundle_identity_invalid")

    def test_role_mcp_port_mismatch_is_rejected(self):
        plan = self.plan()
        plan["mcp"]["role"] = "payer"
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.validate_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_mcp_invalid")
        plan = self.plan()
        plan["mcp"]["url"] = "http://world:8100/mcp"
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.validate_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_mcp_invalid")

    def test_logs_must_be_new_and_state_parent_present(self):
        plan = self.plan()
        (self.root / "logs").mkdir()
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_logs_exist")
        plan = self.plan()
        plan["state"]["output_root"] = str(self.root / "absent" / "state")
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_state_invalid")

    def test_instruction_symlink_and_blocked_path_are_rejected(self):
        target = self.root / "outside.md"
        target.write_text("outside", encoding="utf-8")
        (self.root / "link.md").symlink_to(target)
        plan = self.plan()
        plan["resources"]["instruction"] = str(self.root / "link.md")
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_instruction_invalid")
        plan = self.plan()
        blocked = self.root / "fixtures" / "instruction.md"
        blocked.parent.mkdir()
        blocked.write_text("bad", encoding="utf-8")
        plan["resources"]["instruction"] = str(blocked)
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_instruction_invalid")

    def test_credentials_are_restricted_to_the_model_key(self):
        plan = self.plan()
        plan["credentials"]["model_env"] = "DEEPSEEK_API_KEY"
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.validate_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_credentials_invalid")
        plan = self.plan()
        plan["credentials"]["forbidden_env"] = ["ANTHROPIC_API_KEY"]
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.validate_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_credentials_invalid")

    def test_local_history_must_match_existing_q_root(self):
        qroot = self.root / "prior-go"
        qroot.mkdir()
        plan = self.plan()
        plan["history"] = {"mode": "local", "q_root": str(qroot)}
        plan["state"]["output_root"] = str(qroot / "chi-evaluation")
        self.assertEqual(delivery.check_plan(plan)["status"], "valid")
        plan = self.plan()
        plan["history"] = {"mode": "local", "q_root": str(qroot)}
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.check_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_history_invalid")
        plan = self.plan()
        plan["history"] = {"mode": "external", "q_root": str(qroot)}
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.validate_plan(plan)
        self.assertEqual(caught.exception.code, "delivery_history_invalid")

    def test_cli_valid_and_plan_sha_mismatch(self):
        path = self.root / "plan.json"
        path.write_text(json.dumps(self.plan()), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(delivery.main(["check", "--plan", str(path)]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "valid")
            output.seek(0)
            output.truncate(0)
            self.assertEqual(delivery.main([
                "check", "--plan", str(path), "--plan-sha256", "0" * 64]), 1)
            self.assertEqual(json.loads(output.getvalue())["code"],
                             "delivery_plan_sha256_mismatch")


if __name__ == "__main__":
    unittest.main()
