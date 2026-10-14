"""Reception registration shows patient contact fields, not staff HR fields."""

from __future__ import annotations

import unittest
import registration_patient as arrival


class RegistrationContactAttributes(unittest.TestCase):
    def test_keeps_phone_and_other_phone(self) -> None:
        self.assertTrue(arrival.is_registration_contact_attribute("phoneNumber"))
        self.assertTrue(arrival.is_registration_contact_attribute("alternatePhoneNumber"))
        self.assertTrue(arrival.is_registration_contact_attribute("email"))

    def test_hides_staff_hr_fields_from_reception(self) -> None:
        for name in (
            "abikan.staffCategory",
            "abikan.employmentType",
            "abikan.address",
            "abikan.phone",
            "abikan.nin",
            "abikan.bankAccount",
            "abikan.bankName",
            "abikan.accountName",
            "abikan.qualification",
        ):
            self.assertFalse(arrival.is_registration_contact_attribute(name), name)


class RegistrationLifeStatus(unittest.TestCase):
    def test_new_patient_is_alive_and_ignores_life_status_in_body(self) -> None:
        body = {
            "givenName": "Adaeze",
            "familyName": "Okafor",
            "gender": "F",
            "birthdate": "1990-01-15",
            "alive": False,
            "dead": True,
            "deathDate": "2026-01-01",
        }
        person = arrival._person_payload(body, [])
        self.assertFalse(person["dead"])
        self.assertNotIn("deathDate", person)
        self.assertNotIn("alive", person)

    def test_patient_edit_does_not_send_life_status(self) -> None:
        body = {
            "givenName": "Adaeze",
            "familyName": "Okafor",
            "gender": "F",
            "birthdate": "1990-01-15",
            "alive": False,
            "dead": True,
            "deathDate": "2026-01-01",
        }
        person = arrival._person_payload(body, [], existing_attributes=[])
        self.assertNotIn("dead", person)
        self.assertNotIn("deathDate", person)
        self.assertNotIn("alive", person)


if __name__ == "__main__":
    unittest.main()
