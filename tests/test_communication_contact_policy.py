from __future__ import annotations

import unittest

from app.domain.communication_contact_policy import partition_unavailable_recipients


class CommunicationContactPolicyTests(unittest.TestCase):
    def test_inactive_missing_recipient_becomes_warning_not_blocker(self) -> None:
        blockers, suppressed = partition_unavailable_recipients(
            ["active-missing", "former-employee"],
            ["former-employee"],
        )
        self.assertEqual(blockers, ("active-missing",))
        self.assertEqual(suppressed, ("former-employee",))

    def test_inactive_recipient_not_targeted_produces_no_warning(self) -> None:
        blockers, suppressed = partition_unavailable_recipients(
            ["active-missing"],
            ["former-employee"],
        )
        self.assertEqual(blockers, ("active-missing",))
        self.assertEqual(suppressed, ())

    def test_duplicates_are_normalized(self) -> None:
        blockers, suppressed = partition_unavailable_recipients(
            ["former-employee", "former-employee"],
            ["former-employee"],
        )
        self.assertEqual(blockers, ())
        self.assertEqual(suppressed, ("former-employee",))


if __name__ == "__main__":
    unittest.main()
