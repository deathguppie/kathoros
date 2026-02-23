# tests/unit/test_enums.py
import unittest
from kathoros.core.enums import AccessMode, TrustLevel, Decision


class TestEnums(unittest.TestCase):

    def test_access_mode_values(self):
        self.assertEqual(AccessMode.NO_ACCESS, "NO_ACCESS")
        self.assertEqual(AccessMode.REQUEST_FIRST, "REQUEST_FIRST")
        self.assertEqual(AccessMode.FULL_ACCESS, "FULL_ACCESS")

    def test_default_access_mode(self):
        from kathoros.core.constants import DEFAULT_ACCESS_MODE
        self.assertEqual(DEFAULT_ACCESS_MODE, AccessMode.REQUEST_FIRST)

    def test_trust_levels(self):
        self.assertEqual(TrustLevel.UNTRUSTED, "UNTRUSTED")
        self.assertEqual(TrustLevel.MONITORED, "MONITORED")
        self.assertEqual(TrustLevel.TRUSTED, "TRUSTED")

    def test_decision_values(self):
        self.assertEqual(Decision.APPROVED, "APPROVED")
        self.assertEqual(Decision.REJECTED, "REJECTED")


if __name__ == "__main__":
    unittest.main()
