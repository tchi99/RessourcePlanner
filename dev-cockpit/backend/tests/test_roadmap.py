import unittest

from app.roadmap import (
    agents_allow_chaining,
    extract_declared_active,
    first_unfinished,
    has_explicit_block_order,
    merge_subitems,
    pipeline_window,
    product_pipeline,
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



CURRENT_PIPELINE_ROADMAP = """
**#332 est terminé. #333 est la tranche produit active avec 333A READY.**

Ordre actif :

1. ✅ **#332 — partage et duplication atomiques**
   **Bloc terminé : 332A ✅ → 332B ✅ → 332C ✅.**

2. **#333 — extension de fenêtre contrôlée + dialogue DnD contextuel — ACTIF; 333A READY**
   - **333A — décision contextuelle + commande immédiate — READY**
   - **333B — proposition hors enveloppe**
   - **333C — dialogue React + acceptation**

### Suite produit après #333 — bloc P1 puis préparation environnementale

Chemin principal retenu :

```text
#333A → #333B → #333C
  ↓
ASTRA ciblé #291 sur main post-#333
  ↓
#291 actifs réservables
  ↓
#292 qualifications/permis des actifs
  ↓
#276 routage d'approbation par tâches
  ↓
#278 dashboard Coordonnateur consolidé
  ↓
#263 validation VM Ubuntu réelle avec SQLite, si encore à faire
  ↓
audit/fermeture des anciennes issues locales
```

**Gates et logique :**

| Étape | État / gate | Pourquoi maintenant |
|---|---|---|
| #333 | actif; 333A READY → 333B → 333C | terminer la consolidation |
| analyse ASTRA #291 | après fusion complète de #333 | vérifier le contrat générique |
| #291 | NEXT après analyse | introduire les actifs |
| #292 | après #291 | qualifications |
| #276 | après #292 dans le flux principal | approbation |
| #278 | après #292 + #276 | dashboard |
| #263 | après P1 ou en parallèle infra | valider la vraie VM Ubuntu |
"""

CURRENT_PARALLEL_PIPELINE_ROADMAP = """
La prochaine tranche active du flux principal est #292.

### Suite produit après #333 — bloc P1 puis préparation environnementale

Chemin principal retenu :

```text
#291A ✅ → #291B ✅ → #291C ✅ → #291D ✅ → #291E ✅ → #291F ✅
  ↓
#292 qualifications/permis des actifs
  ↓
#399 demande d'annulation + résolution coordonnateur
  ↓
#276 routage d'approbation par tâches
  ↓
#278 dashboard Coordonnateur consolidé

En parallèle dès maintenant : #398 UX sidebar + liste Demandes
  ↓
si les accès externes manquent encore :
analyse architecture #362
  ↓
#362 Delivery
  ↓
#363 Verification
```
"""


CURRENT_407_TABLE_ROADMAP = """
### Suite produit après #333 — bloc P1 puis préparation environnementale

Chemin principal retenu :

```text
#292 ✅ qualifications/permis des actifs — PR #406, CI #822
  ↓
#407 cohérence sauvegarde → workflow + protection des modifications non enregistrées
  ↓
#399 demande d'annulation + résolution coordonnateur
  ↓
#276 routage d'approbation par tâches
  ↓
#410 inclure les demandes du coordonnateur assigné dans Mon périmètre
  ↓
#278 dashboard Coordonnateur consolidé
```

| Étape | État / gate | Pourquoi maintenant |
|---|---|---|
| #292 | ✅ TERMINÉ — PR #406 / CI #822 | livré |
| #407 | 🟠 NEXT — #292 terminée | corriger la cohérence version/read model |
| #399 | après #407 | annulation |
| #276 | après #399 | approbation |
| #410 | avant #278 | scope coordonnateur |
| #278 | après #407 + #399 + #276 + #410 | dashboard |
"""


CURRENT_FALSE_DONE_ROADMAP = """
### Suite produit après #333 — bloc P1 puis préparation environnementale

Chemin principal retenu :

```text
#291A ✅ → #291B ✅ → #291C ✅ → #291D ✅ → #291E ✅ → #291F ✅
  ↓
#292 qualifications/permis des actifs
  ↓
#399 demande d'annulation + résolution coordonnateur
  ↓
#276 routage d'approbation par tâches
  ↓
#278 dashboard Coordonnateur consolidé

Livré en parallèle : #398 UX sidebar + liste Demandes — PR #400, CI #814
  ↓
si les accès externes manquent encore :
analyse architecture #362 ✅ — main@4fb40665
  ↓
#362A → #362B → #362C → #362D → #362E → #362F
  ↓
#363 Verification
```

#291A–#291F sont maintenant terminés; le flux principal poursuit avec
#292 → #399 → #276 → #278; #398 est livré via PR #400.
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


    def test_done_keyword_marks_subitems_completed(self):
        body = """
### #291A — contrats — DONE (PR #394, CI #801)
### #291B — catalogue — DONE
### #291C — projections — READY
"""
        items = subitems_from_text(body, 291)
        self.assertEqual([item.key for item in items], ["291A", "291B", "291C"])
        self.assertTrue(items[0].done)
        self.assertTrue(items[1].done)
        self.assertFalse(items[2].done)
        self.assertEqual(first_unfinished(items).key, "291C")

    def test_merge_preserves_secondary_in_progress_marker(self):
        primary = subitems_from_text("### #13G — contrats de lecture", 13)
        secondary = subitems_from_text("- 🟡 13G — contrats de lecture", 13)
        merged = merge_subitems(primary, secondary)
        self.assertEqual(merged[0].marker, "🟡")
        self.assertFalse(merged[0].done)


    def test_current_product_pipeline_crosses_heading_boundary(self):
        self.assertEqual(extract_declared_active(CURRENT_PIPELINE_ROADMAP), "333")
        pipeline = product_pipeline(CURRENT_PIPELINE_ROADMAP)
        self.assertEqual(
            [step.key for step in pipeline],
            ["333A", "333B", "333C", "ASTRA-291", "291", "292", "276", "278", "263"],
        )
        self.assertEqual(
            [step.kind for step in pipeline],
            [
                "WORK",
                "WORK",
                "WORK",
                "ARCHITECTURE_GATE",
                "WORK",
                "WORK",
                "WORK",
                "WORK",
                "ENVIRONMENT_GATE",
            ],
        )
        self.assertFalse(pipeline[3].done)
        self.assertFalse(pipeline[-1].done)

    def test_pipeline_after_333c_moves_to_architecture_gate(self):
        body = CURRENT_PIPELINE_ROADMAP.replace(
            "- **333A — décision contextuelle + commande immédiate — READY**",
            "- ✅ **333A — décision contextuelle + commande immédiate**",
        ).replace(
            "- **333B — proposition hors enveloppe**",
            "- ✅ **333B — proposition hors enveloppe**",
        ).replace(
            "- **333C — dialogue React + acceptation**",
            "- ✅ **333C — dialogue React + acceptation**",
        )
        window = pipeline_window(product_pipeline(body))
        self.assertEqual(window["now"]["key"], "ASTRA-291")
        self.assertEqual(window["now"]["kind"], "ARCHITECTURE_GATE")
        self.assertEqual(window["next"][0]["key"], "291")

    def test_satisfied_astra_gate_releases_next_dev_work(self):
        body = CURRENT_PIPELINE_ROADMAP.replace(
            "- **333A — décision contextuelle + commande immédiate — READY**",
            "- ✅ **333A — décision contextuelle + commande immédiate**",
        ).replace(
            "- **333B — proposition hors enveloppe**",
            "- ✅ **333B — proposition hors enveloppe**",
        ).replace(
            "- **333C — dialogue React + acceptation**",
            "- ✅ **333C — dialogue React + acceptation**",
        ).replace(
            "| analyse ASTRA #291 | après fusion complète de #333 |",
            "| analyse ASTRA #291 | ✅ terminée |",
        )
        window = pipeline_window(product_pipeline(body))
        self.assertEqual(window["now"]["key"], "291")
        self.assertEqual(window["now"]["kind"], "WORK")
        self.assertEqual(window["next"][0]["key"], "292")

    def test_current_roadmap_uses_main_lane_and_exposes_parallel_ready_work(self):
        self.assertEqual(
            extract_declared_active(CURRENT_PARALLEL_PIPELINE_ROADMAP),
            "292",
        )
        pipeline = product_pipeline(CURRENT_PARALLEL_PIPELINE_ROADMAP)
        parallel = [step for step in pipeline if step.lane == "PARALLEL"]
        self.assertEqual([step.key for step in parallel], ["398"])

        window = pipeline_window(pipeline)
        self.assertEqual(window["now"]["key"], "292")
        self.assertEqual(
            [step["key"] for step in window["parallel"]],
            ["398"],
        )
        self.assertEqual(
            [step["key"] for step in window["next"]],
            ["399", "276", "278"],
        )
        self.assertEqual(window["later"][0]["key"], "ASTRA-362")
        self.assertEqual(window["later"][0]["kind"], "ARCHITECTURE_GATE")

    def test_table_dependency_completion_does_not_complete_next_work(self):
        pipeline = product_pipeline(CURRENT_407_TABLE_ROADMAP)
        window = pipeline_window(pipeline)
        by_key = {step.key: step for step in pipeline}

        self.assertTrue(by_key["292"].done)
        self.assertFalse(by_key["407"].done)
        self.assertEqual(window["now"]["key"], "407")
        self.assertEqual(
            [step["key"] for step in window["next"]],
            ["399", "276", "410"],
        )

    def test_completion_word_on_other_work_does_not_skip_main_pipeline(self):
        pipeline = product_pipeline(CURRENT_FALSE_DONE_ROADMAP)
        window = pipeline_window(pipeline)

        self.assertEqual(window["now"]["key"], "292")
        self.assertEqual(
            [step["key"] for step in window["next"]],
            ["399", "276", "278"],
        )
        by_key = {step.key: step for step in pipeline}
        for key in ("292", "399", "276", "278"):
            self.assertFalse(by_key[key].done)

    def test_delivered_in_parallel_is_classified_as_parallel_and_done(self):
        pipeline = product_pipeline(CURRENT_FALSE_DONE_ROADMAP)
        step = next(item for item in pipeline if item.key == "398")

        self.assertEqual(step.lane, "PARALLEL")
        self.assertTrue(step.done)
        self.assertNotIn(
            "398",
            [item["key"] for item in pipeline_window(pipeline)["parallel"]],
        )

    def test_explicit_numeric_completion_still_requires_own_segment(self):
        body = """
### Suite produit

```text
#292 qualifications
  ↓
#399 annulation
```

#292 — terminé via PR #405, CI #820.
#399 dépend de #292 terminé.
"""
        pipeline = product_pipeline(body)
        by_key = {step.key: step for step in pipeline}

        self.assertTrue(by_key["292"].done)
        self.assertFalse(by_key["399"].done)

    def test_parallel_work_never_blocks_main_pipeline_progression(self):
        body = CURRENT_PARALLEL_PIPELINE_ROADMAP.replace(
            "#292 qualifications/permis des actifs",
            "#292 qualifications/permis des actifs ✅",
        )
        window = pipeline_window(product_pipeline(body))
        self.assertEqual(window["now"]["key"], "399")
        self.assertEqual([step["key"] for step in window["parallel"]], ["398"])

    def test_old_13a_roadmap_compatibility_is_preserved(self):
        self.assertEqual(extract_declared_active(ROADMAP), "13")
        self.assertEqual(product_pipeline(ROADMAP), [])
        items = subitems_from_text(ISSUE, 13)
        self.assertEqual([item.key for item in items], ["13A", "13B", "13C"])

    def test_pipeline_resolver_does_not_hardcode_product_issue_numbers(self):
        from pathlib import Path

        source = Path("app/roadmap.py").read_text(encoding="utf-8")
        for issue_number in ("333", "291", "292", "276", "278", "263"):
            self.assertNotRegex(source, rf"(?<!\\d){issue_number}(?!\\d)")

    def test_chain_permission_requires_documented_order_and_agents_rule(self):
        items = subitems_from_text(ISSUE, 13)
        agents = "## 20. Chained execution\nAutomatic chaining is allowed only when the next item belongs to the same approved work block."
        self.assertTrue(has_explicit_block_order(ISSUE, ROADMAP, items))
        self.assertTrue(agents_allow_chaining(agents))


if __name__ == "__main__":
    unittest.main()
