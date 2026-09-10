from __future__ import annotations

import unittest

from app.application import (
    ApplicationValidationError,
    IdempotentCommandExecutor,
    normalize_idempotency_key,
    request_fingerprint,
)


class FakeIdempotencyPort:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def replay_or_execute(
        self,
        *,
        scope: str,
        key: str,
        request_fingerprint: str,
        action,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "scope": scope,
                "key": key,
                "request_fingerprint": request_fingerprint,
            }
        )
        return action()


class CommandIdempotencyPolicyTests(unittest.TestCase):
    def test_fingerprint_is_stable_for_equivalent_mapping_order(self) -> None:
        first = request_fingerprint({"b": 2, "a": 1})
        second = request_fingerprint({"a": 1, "b": 2})

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_key_is_trimmed_and_bounded(self) -> None:
        self.assertEqual(normalize_idempotency_key("  retry-42  "), "retry-42")
        self.assertIsNone(normalize_idempotency_key(None))

        with self.assertRaises(ApplicationValidationError) as empty:
            normalize_idempotency_key("   ")
        self.assertEqual(empty.exception.code, "idempotency_key_invalid")

        with self.assertRaises(ApplicationValidationError) as too_long:
            normalize_idempotency_key("x" * 129)
        self.assertEqual(too_long.exception.code, "idempotency_key_invalid")

    def test_missing_key_executes_directly_without_touching_port(self) -> None:
        port = FakeIdempotencyPort()
        executor = IdempotentCommandExecutor(port)
        calls = 0

        def action() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"ok": True}

        result = executor.execute(
            scope="demand.create",
            key=None,
            request_payload={"project_number": "P-1"},
            action=action,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, 1)
        self.assertEqual(port.calls, [])

    def test_keyed_execution_delegates_normalized_key_and_fingerprint(self) -> None:
        port = FakeIdempotencyPort()
        executor = IdempotentCommandExecutor(port)
        payload = {"project_number": "P-1", "desired_start": "2026-08-24"}

        result = executor.execute(
            scope="demand.create",
            key="  key-1  ",
            request_payload=payload,
            action=lambda: {"demand_number": "DMO-2026-0001"},
        )

        self.assertEqual(result["demand_number"], "DMO-2026-0001")
        self.assertEqual(len(port.calls), 1)
        self.assertEqual(port.calls[0]["scope"], "demand.create")
        self.assertEqual(port.calls[0]["key"], "key-1")
        self.assertEqual(
            port.calls[0]["request_fingerprint"],
            request_fingerprint(payload),
        )


if __name__ == "__main__":
    unittest.main()
