import json
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import patch
from pathlib import Path

from scripts.development.capture_resources import capture_resources


class World:
    client = object()
    def exec_run(self, command, demux=False):
        if command[-1] == "payer":
            return 1, b"error"
        return 0, json.dumps([{"resource_type": "patient", "resource_id": "one", "payload": "{}"}]).encode()


class SnapshotTests(unittest.TestCase):
    def test_partial_failure_is_not_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.development.capture_resources._api_timeout', return_value=nullcontext()):
                result = capture_resources(World(), Path(directory), "before")
            self.assertEqual(result["provider"]["count"], 1)
            self.assertEqual(result["payer"]["status"], "unavailable")
            self.assertFalse((Path(directory) / "before-payer-resources.json").exists())
            self.assertEqual(json.loads((Path(directory) / "before-provider-resources.json").read_text())[0]["payload"], "{}")
