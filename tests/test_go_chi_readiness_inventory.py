import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "readiness_inventory", Path(__file__).parents[1] / "scripts/tools/inspect_readiness.py")
inv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inv)


def completion(version, claim=None):
    result = {"schema": f"chi-completion-v{version}", "verification": "mechanical_pass",
              "business_effect": "observed", "reason": None,
              "target": {"case_id": "case", "patient_id": None}, "claim": claim,
              "last_mutation_call_id": None, "latest_business_status": None,
              "open_unknowns": [], "claim_violation": False, "stagnation": None,
              "note": "mechanical only"}
    if version >= 2:
        result.update(claim_policy="optional_final_text", last_business_mutation=None,
                      last_file_mutation=None, required_readback=None, remaining_limitations=[])
    if version == 3:
        result["unresolved_file_deliveries"] = []
    return result


CLAIM = {"version": 1, "target": {"case_id": "case", "patient_id": None},
         "verified_status_call_id": None, "at_utc_ms": 1, "kind": "model_claim"}
REFERENCE = {"call_id": "c", "tool": "t", "seq": 1, "event": "returned"}
STATUS = {"text": "ready", "source_call_id": "c", "source_seq": 1,
          "source_tool": "t", "source_kind": "business_status", "source_scope": "s",
          "source_event": "returned"}


class CompletionTests(unittest.TestCase):
    def test_versions_and_claim_tristate(self):
        for version in (1, 2, 3):
            for claim, expected in ((None, False), (CLAIM, True)):
                with self.subTest(version=version, claim=claim):
                    self.assertEqual(inv._completion_state(completion(version, claim)),
                                     ("present", "mechanical_pass", None, expected))
            missing = completion(version)
            del missing["claim"]
            self.assertEqual(inv._completion_state(missing), ("incomplete", None, None, None))
            invalid = completion(version, 17)
            self.assertEqual(inv._completion_state(invalid), ("invalid", None, None, None))
        self.assertEqual(inv._completion_state({}), ("invalid", None, None, None))
        self.assertEqual(inv._completion_state(None), ("missing", None, None, None))

    def test_schema_types(self):
        for schema in ([], {}, None, True, 17, "other"):
            with self.subTest(schema=schema):
                self.assertEqual(inv._completion_state({"schema": schema}),
                                 ("invalid", None, None, None))

    def test_versioned_status_shape(self):
        old_status = {"text": "ready", "source_call_id": "c", "source_seq": 1}
        for version, status in ((1, old_status), (2, STATUS), (3, STATUS)):
            with self.subTest(version=version):
                candidate = completion(version)
                candidate["latest_business_status"] = status
                self.assertEqual(inv._completion_state(candidate)[0], "present")
                for bad in ({**status, "source_seq": "1"}, {**status, "extra": "x"}):
                    candidate["latest_business_status"] = bad
                    self.assertEqual(inv._completion_state(candidate),
                                     ("invalid", None, None, None))
        candidate = completion(1)
        candidate["latest_business_status"] = STATUS
        self.assertEqual(inv._completion_state(candidate)[0], "invalid")
        candidate = completion(2)
        candidate["latest_business_status"] = old_status
        self.assertEqual(inv._completion_state(candidate)[0], "invalid")

    def test_unresolved_resource_none(self):
        candidate = completion(3)
        candidate["unresolved_file_deliveries"] = [{"call_id": "c", "tool": "t",
                                                    "resource": None, "event": "failed"}]
        self.assertEqual(inv._completion_state(candidate)[0], "present")
        candidate["unresolved_file_deliveries"][0]["resource"] = 17
        self.assertEqual(inv._completion_state(candidate), ("invalid", None, None, None))

    def test_nested_valid_and_invalid(self):
        valid = completion(3, CLAIM)
        valid.update(last_mutation_call_id="c", last_business_mutation=REFERENCE,
                     last_file_mutation=REFERENCE, latest_business_status=STATUS,
                     stagnation={"tool": "t", "count": 1, "call_id": None, "effect": "x"},
                     unresolved_file_deliveries=[{"call_id": "c", "tool": "t",
                                                  "resource": "r", "event": "failed"}])
        self.assertEqual(inv._completion_state(valid)[0], "present")
        bad_values = {"last_mutation_call_id": [17, {}, True],
                      "last_business_mutation": [{"unexpected": "synthetic"},
                                                 {**REFERENCE, "event": []},
                                                 {**REFERENCE, "seq": True}],
                      "latest_business_status": [{}, {**STATUS, "source_kind": {}},
                                                 {**STATUS, "source_event": []}],
                      "stagnation": [{}, {"tool": "t", "count": [], "call_id": None, "effect": "x"}],
                      "unresolved_file_deliveries": [[{}], [{"call_id": "c", "tool": "t",
                                                                "resource": "r", "event": []}]],
                      "target": [{}, {"case_id": [], "patient_id": None}],
                      "claim": [{}, {**CLAIM, "target": []}],
                      "required_readback": [[], {}], "open_unknowns": [[{}]],
                      "remaining_limitations": [[{}]]}
        for key, values in bad_values.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    candidate = copy.deepcopy(valid)
                    candidate[key] = value
                    self.assertEqual(inv._completion_state(candidate), ("invalid", None, None, None))


class InventoryTests(unittest.TestCase):
    def test_trace_completeness(self):
        for rows in ([{}], [{"role": "tool"}], [{"role": [], "content": ""}]):
            self.assertEqual(inv._trace_counts(rows, "present"), (None, None, None, "invalid"))
        self.assertEqual(inv._trace_counts([{"role": "assistant", "content": "ok"}], "present"),
                         (0, 0, 0, "present"))
        self.assertEqual(inv._trace_counts([], "empty"), (None, None, None, "empty"))

    def test_snapshot_and_bad_records_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = root / "run/runner-logs/result"
            result.mkdir(parents=True)
            item = {"candidate": "synthetic", "role": "provider", "task": "t",
                    "simulator": "none", "root": "run"}
            (result / "run_log.txt").write_text(json.dumps({"completion": {"schema": []},
                                                            "official_reward": {}}))
            (result / "trace.jsonl").write_text('{"role":"tool"}\n')
            with patch.object(inv, "ROOT", root):
                row = inv.inventory(item)
            self.assertEqual(row["completion_status"], "invalid")
            self.assertIsNone(row["claim_present"])
            self.assertEqual(row["trace_status"], "invalid")
            self.assertIsNone(row["trace_errors"])
            self.assertIsNone(row["official_reward"])
            self.assertEqual(row["run_result_status"], "missing")
            self.assertEqual(len(row["source_hashes"]["run_log.txt"]["sha256"]), 64)
            with patch.object(inv, "ROOT", root), patch.object(inv, "_snapshot", return_value=(
                    {name: {"status": "present", "bytes": 1, "sha256": "x"} for name in inv.FILES}, False)):
                changed = inv.inventory(item)
            self.assertEqual(changed["snapshot_status"], "changed_during_read")
            self.assertIsNone(changed["claim_present"])

    def test_missing_empty_invalid_and_truncated(self):
        self.assertEqual(inv._jsonl({"status": "missing"}), (None, "missing"))
        self.assertEqual(inv._jsonl({"status": "present", "data": b""}), ([], "empty"))
        self.assertEqual(inv._jsonl({"status": "present", "data": b"{"}), (None, "invalid"))
        with patch.object(inv, "MAX_LINES", 1):
            self.assertEqual(inv._jsonl({"status": "present", "data": b'{}\n{}\n'}),
                             (None, "truncated"))
        self.assertEqual(inv._json({"status": "present", "data": b""}), (None, "invalid"))

    def test_actual_changed_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = {"status": "present", "bytes": 1, "sha256": "a", "data": b"a"}
            second = {**first, "sha256": "b", "data": b"b"}
            with patch.object(inv, "_read_raw", side_effect=[first] * 5 + [second] * 5):
                snapshot, stable = inv._snapshot(Path(tmp))
            self.assertFalse(stable)
            self.assertEqual(snapshot["run_log.txt"]["sha256"], "a")


if __name__ == "__main__":
    unittest.main()
