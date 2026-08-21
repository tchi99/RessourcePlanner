from __future__ import annotations

from contextvars import Context
import unittest

from app.ui_context import ScopedNiceGUI


class _FakeUI:
    def select(self, *args, **kwargs):
        return ("base-select", args, kwargs)

    def scroll_area(self, *args, **kwargs):
        return ("base-scroll", args, kwargs)


class ScopedNiceGUITests(unittest.TestCase):
    def test_unmodified_factory_delegates_to_base_ui(self) -> None:
        base = _FakeUI()
        facade = ScopedNiceGUI(base, scope_name="test", scoped_factories=("select",))
        self.assertEqual(facade.select(["A"])[0], "base-select")

    def test_legacy_assign_restore_is_scoped_in_current_context(self) -> None:
        base = _FakeUI()
        facade = ScopedNiceGUI(base, scope_name="test", scoped_factories=("select",))
        original = facade.select

        def proxy(*args, **kwargs):
            return ("proxy", args, kwargs)

        facade.select = proxy
        self.assertEqual(facade.select(["A"])[0], "proxy")

        # A fresh Context does not inherit the temporary assignment.
        self.assertEqual(Context().run(lambda: facade.select(["A"])[0]), "base-select")

        facade.select = original
        self.assertEqual(facade.select(["A"])[0], "base-select")

    def test_context_manager_resets_override_even_after_exception(self) -> None:
        base = _FakeUI()
        facade = ScopedNiceGUI(base, scope_name="test", scoped_factories=("select",))

        def proxy(*args, **kwargs):
            return ("proxy", args, kwargs)

        with self.assertRaises(RuntimeError):
            with facade.override_factory("select", proxy):
                self.assertEqual(facade.select()[0], "proxy")
                raise RuntimeError("stop")

        self.assertEqual(facade.select()[0], "base-select")

    def test_static_override_does_not_touch_delegate(self) -> None:
        base = _FakeUI()

        def horizontal(*args, **kwargs):
            return ("horizontal", args, kwargs)

        facade = ScopedNiceGUI(
            base,
            scope_name="test",
            scoped_factories=("select",),
            static_overrides={"scroll_area": horizontal},
        )
        self.assertEqual(facade.scroll_area()[0], "horizontal")
        self.assertEqual(base.scroll_area()[0], "base-scroll")


if __name__ == "__main__":
    unittest.main()
