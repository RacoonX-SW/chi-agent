import unittest
import role_runner

class CapabilityModeTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(role_runner.capability_mode(None), "f0-f3-v1")
        self.assertEqual(role_runner.capability_mode(""), "f0-f3-v1")
        self.assertEqual(role_runner.capability_mode("f0-f3-v1"), "f0-f3-v1")
        self.assertIsNone(role_runner.capability_mode("off"))

    def test_unknown_rejected(self):
        for value in ("f0-f6-v1", "ON", 1):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    role_runner.capability_mode(value)

if __name__ == "__main__":
    unittest.main()
