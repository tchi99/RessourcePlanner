import unittest

from app.roadmap import (
    agents_allow_chaining,
    extract_declared_active,
    first_unfinished,
    has_explicit_block_order,
    merge_subitems,
    subitems_from_text,
    top_level_items,
)


ROADMAP = """
**#331 est terminé. #13 est maintenant la tranche active.**

Ordre actif :

1. **#331 — séparation des ressources**
   **Bloc terminé : 331A ✅ → 331E ✅.** #331 est désormais complétée.

2. **#13 — périodes + enveloppe approuvée commune**
   - **13A — contrat et politique pure**
   - **13B — révisions approuvées immuables**
   - **13C — préparation commune**

   Ordre : **13A → 13B → 13C**.

3. **#328 — identité demandeur**
"""

ISSUE = """
# #13 — périodes + enveloppe approuvée commune

## Découpage d'implémentation

Ordre obligatoire :

### #13A — contrat et politique pure
### #13B — capture des révisions approuvées
### #13C — préparation commune et protection des verrous
"""


class RoadmapTests(unittest.TestCase):
    def test_extracts_active_parent_and_first_subitem(self):
        self.assertEqual(extract_declared_active(ROADMAP), "13")
        top = top_level_items(ROADMAP)
        self.assertTrue(top[0].done)
        issue_items = subitems_from_text(ISSUE, 13)
        roadmap_items = subitems_from_text(ROADMAP, 13)
        merged = merge_subitems(issue_items, roadmap_items)
        self.assertEqual([item.key for item in merged], ["13A", "13B", "13C"])
        self.assertEqual(first_unfinished(merged).key, "13A")

    def test_explicit_checkmark_marks_only_that_subitem_done(self):
        body = """
### ✅ #13A — contrat et politique pure
### #13B — capture des révisions
"""
        items = subitems_from_text(body, 13)
        self.assertTrue(items[0].done)
        self.assertFalse(items[1].done)
        self.assertEqual(first_unfinished(items).key, "13B")

    def test_merge_preserves_secondary_in_progress_marker(self):
        primary = subitems_from_text("### #13G — contrats de lecture", 13)
        secondary = subitems_from_text("- 🟡 13G — contrats de lecture", 13)
        merged = merge_subitems(primary, secondary)
        self.assertEqual(merged[0].marker, "🟡")
        self.assertFalse(merged[0].done)

    def test_chain_permission_requires_documented_order_and_agents_rule(self):
        items = subitems_from_text(ISSUE, 13)
        agents = "## 20. Chained execution\nAutomatic chaining is allowed only when the next item belongs to the same approved work block."
        self.assertTrue(has_explicit_block_order(ISSUE, ROADMAP, items))
        self.assertTrue(agents_allow_chaining(agents))


if __name__ == "__main__":
    unittest.main()
