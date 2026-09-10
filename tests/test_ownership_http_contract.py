from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.server.schemas import DemandCreateRequest, DemandUpdateRequest


class OwnershipHttpContractTests(unittest.TestCase):
    def test_project_manager_is_not_writable_through_demand_http_contract(self) -> None:
        with self.assertRaises(ValidationError):
            DemandCreateRequest.model_validate(
                {
                    "project_number": "P-1",
                    "desired_start": "2026-08-24",
                    "project_manager": "Do not copy this value",
                }
            )
        with self.assertRaises(ValidationError):
            DemandUpdateRequest.model_validate(
                {"project_manager": "Do not copy this value"}
            )

    def test_requester_remains_an_explicit_writable_operational_field(self) -> None:
        created = DemandCreateRequest.model_validate(
            {
                "project_number": "P-1",
                "desired_start": "2026-08-24",
                "requester": "Marie",
            }
        )
        updated = DemandUpdateRequest.model_validate({"requester": "Alex"})

        self.assertEqual(created.requester, "Marie")
        self.assertEqual(updated.requester, "Alex")


if __name__ == "__main__":
    unittest.main()
