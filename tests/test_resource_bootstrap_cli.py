from __future__ import annotations

import unittest

from app.application.resource_bootstrap import ResourceBootstrapResult
from tools.import_resources import _result_text


class ResourceBootstrapCliTests(unittest.TestCase):
    def test_report_exposes_operator_counts(self) -> None:
        report = _result_text(
            ResourceBootstrapResult(
                received=5, created=2, updated=1, unchanged=2, invalid=0,
                schedules_created=2, schedules_unchanged=1,
                schedules_preserved=1, without_schedule=1,
            ),
            preview=True,
        )
        for label in (
            "Ressources lues : 5", "À créer : 2", "À mettre à jour : 1",
            "Sans changement : 2", "Lignes invalides : 0",
            "Horaires standards à créer : 2", "Horaires déjà identiques : 1",
            "Horaires existants conservés : 1", "Sans horaire fourni : 1",
        ):
            self.assertIn(label, report)


if __name__ == "__main__":
    unittest.main()
