# tests/unit/epistemic/test_checker.py
"""
Tests for EpistemicChecker — covers all six checks + scenario tests
from the epistemic spec including the "Conspiracy Drift Attack" scenario.
"""
import unittest
from kathoros.epistemic.checker import (
    EpistemicChecker, ObjectNode, Edge, Severity,
)

checker = EpistemicChecker()


def obj(
    id, *,
    object_type="toy_model",
    epistemic_status="draft",
    claim_level="definition",
    narrative_label="N/A",
    falsifiable="unknown",
    falsification_criteria="",
    validation_scope="internal",
    attached_artifact_hash=None,
):
    return ObjectNode(
        id=id,
        object_type=object_type,
        epistemic_status=epistemic_status,
        claim_level=claim_level,
        narrative_label=narrative_label,
        falsifiable=falsifiable,
        falsification_criteria=falsification_criteria,
        validation_scope=validation_scope,
        attached_artifact_hash=attached_artifact_hash,
    )


def dep(src, tgt):
    return Edge(source_id=src, target_id=tgt, reference_type="depends_on")


def sup(src, tgt):
    return Edge(source_id=src, target_id=tgt, reference_type="supports")


# ---------------------------------------------------------------------------
# EP001 — Premise gate
# ---------------------------------------------------------------------------

class TestEP001PremiseGate(unittest.TestCase):

    def test_blocks_validation_with_unvalidated_dep(self):
        A = obj(1, epistemic_status="proposed")
        B = obj(2, epistemic_status="proposed")    # not validated
        result = checker.check(A, [A, B], [dep(1, 2)], proposed_status="validated")
        self.assertFalse(result.ok)
        codes = [v.code for v in result.violations]
        self.assertIn("EP001", codes)
        block = next(v for v in result.violations if v.code == "EP001")
        self.assertEqual(block.severity, Severity.BLOCK)

    def test_allows_validation_when_dep_is_validated(self):
        A = obj(1, epistemic_status="proposed")
        B = obj(2, epistemic_status="validated")
        result = checker.check(A, [A, B], [dep(1, 2)], proposed_status="validated")
        ep001 = [v for v in result.violations if v.code == "EP001"]
        self.assertEqual(ep001, [])

    def test_no_deps_allows_validation(self):
        A = obj(1, epistemic_status="proposed")
        result = checker.check(A, [A], [], proposed_status="validated")
        ep001 = [v for v in result.violations if v.code == "EP001"]
        self.assertEqual(ep001, [])

    def test_missing_dep_node_blocks(self):
        """Dependency references a node not in scope — must block."""
        A = obj(1, epistemic_status="proposed")
        result = checker.check(A, [A], [dep(1, 99)], proposed_status="validated")
        codes = [v.code for v in result.violations]
        self.assertIn("EP001", codes)

    def test_non_validated_target_status_skipped(self):
        """EP001 only fires when proposed_status=validated."""
        A = obj(1, epistemic_status="proposed")
        B = obj(2, epistemic_status="draft")
        result = checker.check(A, [A, B], [dep(1, 2)], proposed_status="proposed")
        ep001 = [v for v in result.violations if v.code == "EP001"]
        self.assertEqual(ep001, [])

    def test_no_upstream_validation_flow(self):
        """
        Validating C that depends_on B depends_on A must NOT change A or B status.
        Checker is read-only — it never mutates nodes.
        """
        A = obj(1, epistemic_status="validated")
        B = obj(2, epistemic_status="validated")
        C = obj(3, epistemic_status="proposed")
        result = checker.check(C, [A, B, C], [dep(3, 2), dep(2, 1)], proposed_status="validated")
        # C should pass — A and B are validated
        ep001 = [v for v in result.violations if v.code == "EP001"]
        self.assertEqual(ep001, [])
        # Checker must not have mutated A or B
        self.assertEqual(A.epistemic_status, "validated")
        self.assertEqual(B.epistemic_status, "validated")


# ---------------------------------------------------------------------------
# EP002 — TOY_MODEL labeling
# ---------------------------------------------------------------------------

class TestEP002ToyModelLabel(unittest.TestCase):

    def test_blocks_interpretation_without_toy_model_label(self):
        A = obj(1, claim_level="interpretation", narrative_label="N/A")
        result = checker.check(A, [A], [])
        codes = [v.code for v in result.violations]
        self.assertIn("EP002", codes)

    def test_allows_interpretation_with_toy_model_label(self):
        A = obj(1, claim_level="interpretation", narrative_label="TOY_MODEL")
        result = checker.check(A, [A], [])
        ep002 = [v for v in result.violations if v.code == "EP002"]
        self.assertEqual(ep002, [])

    def test_validated_interpretation_exempt(self):
        """Validated objects are exempt from EP002 — they earned it."""
        A = obj(1, claim_level="interpretation", narrative_label="N/A",
                epistemic_status="validated")
        result = checker.check(A, [A], [], proposed_status="validated")
        ep002 = [v for v in result.violations if v.code == "EP002"]
        self.assertEqual(ep002, [])

    def test_non_interpretation_not_affected(self):
        A = obj(1, claim_level="definition", narrative_label="N/A")
        result = checker.check(A, [A], [])
        ep002 = [v for v in result.violations if v.code == "EP002"]
        self.assertEqual(ep002, [])


# ---------------------------------------------------------------------------
# EP003 — Ontology prediction ban
# ---------------------------------------------------------------------------

class TestEP003OntologyPrediction(unittest.TestCase):

    def test_blocks_ontology_with_prediction(self):
        A = obj(1, object_type="speculative_ontology", claim_level="prediction")
        result = checker.check(A, [A], [])
        codes = [v.code for v in result.violations]
        self.assertIn("EP003", codes)
        block = next(v for v in result.violations if v.code == "EP003")
        self.assertEqual(block.severity, Severity.BLOCK)

    def test_toy_model_with_prediction_allowed(self):
        A = obj(1, object_type="toy_model", claim_level="prediction")
        result = checker.check(A, [A], [])
        ep003 = [v for v in result.violations if v.code == "EP003"]
        self.assertEqual(ep003, [])

    def test_ontology_non_prediction_allowed(self):
        A = obj(1, object_type="speculative_ontology", claim_level="definition")
        result = checker.check(A, [A], [])
        ep003 = [v for v in result.violations if v.code == "EP003"]
        self.assertEqual(ep003, [])


# ---------------------------------------------------------------------------
# EP004 — Framework ontology linkage
# ---------------------------------------------------------------------------

class TestEP004FrameworkOntologyLink(unittest.TestCase):

    def test_warns_framework_interpretation_without_ontology_dep(self):
        A = obj(1, object_type="abstract_framework", claim_level="interpretation",
                narrative_label="TOY_MODEL")
        result = checker.check(A, [A], [])
        codes = [v.code for v in result.violations]
        self.assertIn("EP004", codes)
        warn = next(v for v in result.violations if v.code == "EP004")
        self.assertEqual(warn.severity, Severity.WARN)

    def test_framework_with_ontology_dep_passes(self):
        F = obj(1, object_type="abstract_framework", claim_level="interpretation",
                narrative_label="TOY_MODEL")
        O = obj(2, object_type="speculative_ontology", epistemic_status="proposed")
        result = checker.check(F, [F, O], [dep(1, 2)])
        ep004 = [v for v in result.violations if v.code == "EP004"]
        self.assertEqual(ep004, [])

    def test_framework_derivation_not_affected(self):
        """EP004 only fires for interpretation or definition claim levels."""
        F = obj(1, object_type="abstract_framework", claim_level="derivation")
        result = checker.check(F, [F], [])
        ep004 = [v for v in result.violations if v.code == "EP004"]
        self.assertEqual(ep004, [])

    def test_toy_model_not_affected(self):
        A = obj(1, object_type="toy_model", claim_level="interpretation",
                narrative_label="TOY_MODEL")
        result = checker.check(A, [A], [])
        ep004 = [v for v in result.violations if v.code == "EP004"]
        self.assertEqual(ep004, [])


# ---------------------------------------------------------------------------
# EP005 — Cycle detection
# ---------------------------------------------------------------------------

class TestEP005Cycles(unittest.TestCase):

    def test_direct_cycle_blocked(self):
        """A depends_on B, B depends_on A."""
        A = obj(1, epistemic_status="proposed")
        B = obj(2, epistemic_status="proposed")
        edges = [dep(1, 2), dep(2, 1)]
        result = checker.check(A, [A, B], edges, proposed_status="validated")
        codes = [v.code for v in result.violations]
        self.assertIn("EP005", codes)
        block = next(v for v in result.violations if v.code == "EP005")
        self.assertEqual(block.severity, Severity.BLOCK)

    def test_three_node_cycle_blocked(self):
        """A→B→C→A."""
        A, B, C = obj(1), obj(2), obj(3)
        edges = [dep(1, 2), dep(2, 3), dep(3, 1)]
        result = checker.check(A, [A, B, C], edges)
        codes = [v.code for v in result.violations]
        self.assertIn("EP005", codes)

    def test_self_loop_blocked(self):
        """A depends_on itself."""
        A = obj(1)
        result = checker.check(A, [A], [dep(1, 1)])
        codes = [v.code for v in result.violations]
        self.assertIn("EP005", codes)

    def test_linear_chain_allowed(self):
        """A→B→C with no cycle."""
        A, B, C = obj(1), obj(2), obj(3)
        edges = [dep(1, 2), dep(2, 3)]
        result = checker.check(A, [A, B, C], edges)
        ep005 = [v for v in result.violations if v.code == "EP005"]
        self.assertEqual(ep005, [])

    def test_cycle_blocks_further_checks(self):
        """When EP005 fires, checker stops — no EP001 etc added."""
        A = obj(1, epistemic_status="proposed")
        B = obj(2, epistemic_status="draft")
        edges = [dep(1, 2), dep(2, 1)]
        result = checker.check(A, [A, B], edges, proposed_status="validated")
        # EP005 present
        self.assertTrue(any(v.code == "EP005" for v in result.violations))
        # EP001 should NOT be present (cycle short-circuits)
        self.assertFalse(any(v.code == "EP001" for v in result.violations))


# ---------------------------------------------------------------------------
# EP006 — Validation scope
# ---------------------------------------------------------------------------

class TestEP006ValidationScope(unittest.TestCase):

    def test_warns_external_scope_without_evidence(self):
        A = obj(1, validation_scope="external")
        result = checker.check(A, [A], [])
        codes = [v.code for v in result.violations]
        self.assertIn("EP006", codes)
        warn = next(v for v in result.violations if v.code == "EP006")
        self.assertEqual(warn.severity, Severity.WARN)

    def test_external_with_artifact_hash_passes(self):
        A = obj(1, validation_scope="external", attached_artifact_hash="abc123")
        result = checker.check(A, [A], [])
        ep006 = [v for v in result.violations if v.code == "EP006"]
        self.assertEqual(ep006, [])

    def test_external_with_evidence_support_passes(self):
        A = obj(1, validation_scope="external")
        E = obj(2, object_type="evidence")  # evidence object
        result = checker.check(A, [A, E], [sup(2, 1)])  # E supports A
        ep006 = [v for v in result.violations if v.code == "EP006"]
        self.assertEqual(ep006, [])

    def test_internal_scope_not_affected(self):
        A = obj(1, validation_scope="internal")
        result = checker.check(A, [A], [])
        ep006 = [v for v in result.violations if v.code == "EP006"]
        self.assertEqual(ep006, [])


# ---------------------------------------------------------------------------
# Scenario: "Conspiracy Drift Attack"
# Cannot launder ontology into validated physics via internal coherence.
# ---------------------------------------------------------------------------

class TestConspiracyDriftScenario(unittest.TestCase):
    """
    Build the chain from spec F2:
      O1: speculative_ontology (proposed) — metaphysical narrative
      F1: abstract_framework (proposed) — implicitly assumes O1, no link
      M1: toy_model (proposed) — derived from F1
      E1: evidence (validated) — supports M1

    Attempt sequence:
      1) Validate M1 without O1/F1 validated → EP001 blocks
      2) Validate F1 without linking O1 → EP004 warns
      3) Validate O1 as external with no evidence → EP006 warns
    """

    def setUp(self):
        self.O1 = obj(1, object_type="speculative_ontology", epistemic_status="proposed",
                      claim_level="interpretation", narrative_label="TOY_MODEL")
        self.F1 = obj(2, object_type="abstract_framework", epistemic_status="proposed",
                      claim_level="interpretation", narrative_label="TOY_MODEL")
        self.M1 = obj(3, object_type="toy_model", epistemic_status="proposed",
                      claim_level="derivation")
        self.E1 = obj(4, object_type="evidence", epistemic_status="validated",
                      claim_level="prediction")

        # F1 implicitly assumes O1 but doesn't link it
        # M1 depends_on F1
        # E1 supports M1
        self.edges = [
            dep(3, 2),    # M1 depends_on F1
            sup(4, 3),    # E1 supports M1
        ]
        self.all_nodes = [self.O1, self.F1, self.M1, self.E1]

    def test_cannot_validate_M1_without_F1_validated(self):
        """Step 1: validate M1 → EP001 blocks (F1 is proposed)."""
        result = checker.check(
            self.M1, self.all_nodes, self.edges, proposed_status="validated"
        )
        self.assertFalse(result.ok)
        self.assertTrue(any(v.code == "EP001" for v in result.violations))

    def test_cannot_validate_F1_without_O1_linked(self):
        """Step 2: F1 has no depends_on O1 → EP004 warns."""
        # F1 by itself, no edges to O1
        result = checker.check(
            self.F1, self.all_nodes, [], proposed_status="validated"
        )
        # EP004 should warn (framework interp without ontology dep)
        self.assertTrue(any(v.code == "EP004" for v in result.violations))

    def test_cannot_validate_O1_as_external_without_evidence(self):
        """Step 3: O1 external scope, no evidence → EP006 warns."""
        O1_ext = obj(1, object_type="speculative_ontology", epistemic_status="proposed",
                     claim_level="interpretation", narrative_label="TOY_MODEL",
                     validation_scope="external")
        result = checker.check(O1_ext, [O1_ext], [], proposed_status="validated")
        self.assertTrue(any(v.code == "EP006" for v in result.violations))

    def test_full_valid_chain_requires_all_validated(self):
        """
        Even if E1 supports M1, you cannot validate M1 without
        validating its premises (F1) first. Evidence support does not
        substitute for premise validation.
        """
        result = checker.check(
            self.M1, self.all_nodes, self.edges, proposed_status="validated"
        )
        self.assertFalse(result.ok)
        # Block must be EP001, not EP006
        blocks = [v for v in result.violations if v.severity == Severity.BLOCK]
        self.assertTrue(any(v.code == "EP001" for v in blocks))


# ---------------------------------------------------------------------------
# CheckResult helpers
# ---------------------------------------------------------------------------

class TestCheckResult(unittest.TestCase):

    def test_ok_true_when_no_blocks(self):
        A = obj(1, validation_scope="external")   # EP006 warn only
        result = checker.check(A, [A], [])
        self.assertTrue(result.ok)    # WARN doesn't set ok=False
        self.assertEqual(len(result.warns), 1)
        self.assertEqual(len(result.blocks), 0)

    def test_ok_false_when_block_present(self):
        A = obj(1, object_type="speculative_ontology", claim_level="prediction")
        result = checker.check(A, [A], [])
        self.assertFalse(result.ok)
        self.assertEqual(len(result.blocks), 1)

    def test_multiple_violations_accumulated(self):
        """Multiple independent violations all reported."""
        # EP003 + EP006 both fire
        A = obj(1, object_type="speculative_ontology", claim_level="prediction",
                validation_scope="external")
        result = checker.check(A, [A], [])
        codes = {v.code for v in result.violations}
        self.assertIn("EP003", codes)
        self.assertIn("EP006", codes)


if __name__ == "__main__":
    unittest.main()
