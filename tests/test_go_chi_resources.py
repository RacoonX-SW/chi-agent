import tempfile
import unittest
from pathlib import Path

from chi_agent.tools.workspace_paths import workspace_path


class ResourcesTests(unittest.TestCase):
    def test_role_boundary_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "case" / "provider").mkdir(parents=True)
            (root / "case" / "payer").mkdir()
            (root / "case" / "shared").mkdir()
            provider = str(root / "case" / "provider" / "file")
            shared = str(root / "case" / "shared" / "file")
            self.assertIsNotNone(workspace_path(root, provider, "provider"))
            self.assertIsNone(workspace_path(root, provider, "payer"))
            self.assertIsNone(workspace_path(root, provider, "cm"))
            self.assertIsNotNone(workspace_path(root, shared, "payer"))
            (root / "case" / "payer" / "link").symlink_to(root / "case" / "provider", target_is_directory=True)
            self.assertIsNone(workspace_path(root, str(root / "case" / "payer" / "link" / "file"), "payer"))
            self.assertIsNone(workspace_path(root, str(root / "case" / "payer" / ".." / "provider" / "file"), "payer"))


if __name__ == "__main__":
    unittest.main()
