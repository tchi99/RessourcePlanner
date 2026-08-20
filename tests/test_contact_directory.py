from __future__ import annotations

import unittest

from app.domain.contact_directory import (
    BOTH_TYPE,
    PROJECT_MANAGER_TYPE,
    TECHNICIAN_TYPE,
    build_contact_candidates,
    default_display_name,
    missing_contact_candidates,
)


def synthetic_email(local: str) -> str:
    return local + chr(64) + "invalid.test"


class ContactDirectoryTests(unittest.TestCase):
    def test_display_name_uses_first_name_from_normal_name(self) -> None:
        self.assertEqual(default_display_name("Jean Tremblay"), "Jean")

    def test_display_name_handles_last_comma_first_format(self) -> None:
        self.assertEqual(default_display_name("Tremblay, Jean Pierre"), "Jean")

    def test_candidates_include_technicians_and_project_managers(self) -> None:
        candidates = build_contact_candidates(
            [{"name": "Tech A"}, {"name": "Tech B"}],
            [{"ChargeProjet": "PM A"}, {"ChargeProjet": "PM B"}],
        )
        by_id = {candidate.person_id: candidate for candidate in candidates}
        self.assertEqual(by_id["Tech A"].person_type, TECHNICIAN_TYPE)
        self.assertEqual(by_id["PM A"].person_type, PROJECT_MANAGER_TYPE)
        self.assertEqual(set(by_id), {"Tech A", "Tech B", "PM A", "PM B"})

    def test_same_key_in_both_roles_is_kept_once(self) -> None:
        candidates = build_contact_candidates(
            [{"name": "Personne A"}],
            [{"ChargeProjet": "Personne A"}, {"ChargeProjet": "Personne A"}],
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].person_type, BOTH_TYPE)

    def test_missing_candidates_never_overwrite_existing_contact(self) -> None:
        candidates = build_contact_candidates(
            [{"name": "Tech A"}, {"name": "Tech B"}],
            [{"ChargeProjet": "PM A"}],
        )
        missing = missing_contact_candidates(
            candidates,
            [
                {
                    "PersonneCle": "Tech A",
                    "Courriel": synthetic_email("existing"),
                    "NomAffiche": "Nom personnalisé",
                }
            ],
        )
        self.assertEqual(
            {candidate.person_id for candidate in missing},
            {"Tech B", "PM A"},
        )


if __name__ == "__main__":
    unittest.main()
