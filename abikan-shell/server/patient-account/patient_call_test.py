"""Patient-call behaviour is covered by notifications_test.PatientCallCompatTests."""

from __future__ import annotations

import unittest


class PatientCallPointer(unittest.TestCase):
    def test_compat_suite_lives_with_notifications(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
