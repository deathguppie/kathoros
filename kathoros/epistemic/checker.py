# kathoros/epistemic/checker.py
"""
Epistemic Graph Integrity Checker — v0

Enforces six deterministic rules against an in-memory object graph.
Purely functional — no DB access, no I/O. All inputs passed explicitly.

Checks (v0):
  EP001  Premise gate           — cannot validate if any dependency is not validated (BLOCK)
  EP002  TOY_MODEL labeling     — interpretation objects must be labeled TOY_MODEL (BLOCK)
  EP003  Ontology prediction ban — speculative_ontology cannot have claim_level=prediction (BLOCK)
  EP004  Framework ontology link — abstract_framework with interp/def claims must depend_on ontology (WARN)
  EP005  Cycle detection        — depends_on graph must be acyclic (BLOCK)
  EP006  Validation scope       — external scope requires evidence support or artifact (WARN)

Design:
  - Inputs: ObjectNode dataclass + list of Edge tuples
  - Output: CheckResult(ok, violations)
  - No NLP — enforcement is structural/metadata-driven
  - Stateless: safe to call repeatedly with same or different graphs
  - Upstream validation is never inferred (C1 invariant — explicit)

Security note:
  Checker is read-only. It never mutates object state.
  Status changes are the caller's responsibility after passing checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    BLOCK = "block"
    WARN  = "warn"


@dataclass(frozen=True)
class Violation:
    code:          str            # EP001 .. EP006
    severity:      Severity
    message:       str
    nodes_involved: tuple[int, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    ok:         bool              # True only if zero BLOCK violations
    violations: tuple[Violation, ...]

    @property
    def blocks(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == Severity.BLOCK]

    @property
    def warns(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == Severity.WARN]


# ---------------------------------------------------------------------------
# Input graph types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObjectNode:
    """
    Minimal metadata required by the checker.
    Caller fills from DB row or in-memory object.
    All string fields must match enum values exactly (lowercase).
    """
    id:                  int
    object_type:         str   # toy_model | abstract_framework | speculative_ontology
    epistemic_status:    str   # draft | proposed | audited | validated | rejected
    claim_level:         str   # question | definition | derivation | prediction |
                               # interpretation | implementation_detail
    narrative_label:     str   # TOY_MODEL | N/A
    falsifiable:         str   # yes | no | unknown
    falsification_criteria: str = ""
    validation_scope:    str = "internal"   # internal | external
    attached_artifact_hash: Optional[str] = None


@dataclass(frozen=True)
class Edge:
    """A directed dependency edge: source depends_on / supports / etc target."""
    source_id:      int
    target_id:      int
    reference_type: str   # depends_on | supports | contradicts | extends


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

class EpistemicChecker:
    """
    Stateless checker. Instantiate once; call check() as many times as needed.

    Usage:
        checker = EpistemicChecker()
        result = checker.check(target, all_nodes, all_edges)
        if not result.ok:
            # handle blocks
    """

    def check(
        self,
        target: ObjectNode,
        all_nodes: list[ObjectNode],
        all_edges: list[Edge],
        proposed_status: Optional[str] = None,
    ) -> CheckResult:
        """
        Run all six checks against target in the context of the full graph.

        target:          the object being saved or promoted
        all_nodes:       every object in the relevant scope (current project minimum)
        all_edges:       every edge in scope (cross_references rows)
        proposed_status: if caller is attempting a status change, pass the new
                         value here — checker will evaluate it against current graph
        """
        node_map = {n.id: n for n in all_nodes}
        # Include target in map (may have updated fields from caller)
        node_map[target.id] = target

        effective_status = proposed_status or target.epistemic_status
        violations: list[Violation] = []

        # EP005 first — cycles make other checks unsafe
        _check_ep005_cycles(target.id, all_edges, violations)
        if any(v.code == "EP005" for v in violations):
            # Cannot reason about the graph if cyclic
            return CheckResult(ok=False, violations=tuple(violations))

        # Run remaining checks in spec order
        _check_ep001_premise_gate(target, effective_status, all_edges, node_map, violations)
        _check_ep002_toy_model_label(target, effective_status, violations)
        _check_ep003_ontology_prediction(target, violations)
        _check_ep004_framework_ontology_link(target, all_edges, node_map, violations)
        _check_ep006_validation_scope(target, all_edges, node_map, violations)

        has_blocks = any(v.severity == Severity.BLOCK for v in violations)
        return CheckResult(ok=not has_blocks, violations=tuple(violations))


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_ep001_premise_gate(
    target: ObjectNode,
    proposed_status: str,
    edges: list[Edge],
    node_map: dict[int, ObjectNode],
    violations: list[Violation],
) -> None:
    """
    EP001: Premise gate.
    If attempting to set status=validated, every depends_on target must
    already be validated. No exceptions in v0.
    Validation never flows upstream (C1 invariant — not enforced here,
    but the directional rule means caller must explicitly validate dependencies first).
    """
    if proposed_status != "validated":
        return

    dep_ids = [
        e.target_id for e in edges
        if e.source_id == target.id and e.reference_type == "depends_on"
    ]

    for dep_id in dep_ids:
        dep = node_map.get(dep_id)
        if dep is None:
            violations.append(Violation(
                code="EP001",
                severity=Severity.BLOCK,
                message=f"Dependency object {dep_id} not found in graph scope — "
                        f"cannot validate without resolving all premises.",
                nodes_involved=(target.id, dep_id),
            ))
        elif dep.epistemic_status != "validated":
            violations.append(Violation(
                code="EP001",
                severity=Severity.BLOCK,
                message=(
                    f"Cannot validate object {target.id}: dependency {dep_id} "
                    f"has status '{dep.epistemic_status}', must be 'validated'. "
                    f"Validation does not flow upstream."
                ),
                nodes_involved=(target.id, dep_id),
            ))


def _check_ep002_toy_model_label(
    target: ObjectNode,
    proposed_status: str,
    violations: list[Violation],
) -> None:
    """
    EP002: TOY_MODEL labeling invariant.
    Any object with claim_level=interpretation must have narrative_label=TOY_MODEL
    unless it is already validated.
    """
    if proposed_status == "validated":
        return  # validated objects are exempt — label was required to get here
    if target.claim_level == "interpretation" and target.narrative_label != "TOY_MODEL":
        violations.append(Violation(
            code="EP002",
            severity=Severity.BLOCK,
            message=(
                f"Object {target.id} has claim_level='interpretation' but "
                f"narrative_label='{target.narrative_label}'. "
                f"All unvalidated interpretive claims must be labeled 'TOY_MODEL'."
            ),
            nodes_involved=(target.id,),
        ))


def _check_ep003_ontology_prediction(
    target: ObjectNode,
    violations: list[Violation],
) -> None:
    """
    EP003: Ontology cannot produce predictions directly.
    speculative_ontology + claim_level=prediction is always blocked.
    A toy_model must be instantiated first.
    """
    if (
        target.object_type == "speculative_ontology"
        and target.claim_level == "prediction"
    ):
        violations.append(Violation(
            code="EP003",
            severity=Severity.BLOCK,
            message=(
                f"Object {target.id} is a speculative_ontology with "
                f"claim_level='prediction'. Ontologies cannot make predictions "
                f"directly — instantiate a toy_model first."
            ),
            nodes_involved=(target.id,),
        ))


def _check_ep004_framework_ontology_link(
    target: ObjectNode,
    edges: list[Edge],
    node_map: dict[int, ObjectNode],
    violations: list[Violation],
) -> None:
    """
    EP004: abstract_framework with interpretive/definitional claims must
    explicitly depend_on at least one speculative_ontology.
    WARN (not block) in v0 — surfaces the gap without hard-stopping.
    """
    if target.object_type != "abstract_framework":
        return
    if target.claim_level not in ("interpretation", "definition"):
        return

    dep_ids = [
        e.target_id for e in edges
        if e.source_id == target.id and e.reference_type == "depends_on"
    ]
    has_ontology_dep = any(
        node_map.get(did, ObjectNode(
            id=did, object_type="", epistemic_status="", claim_level="",
            narrative_label="", falsifiable=""
        )).object_type == "speculative_ontology"
        for did in dep_ids
    )
    if not has_ontology_dep:
        violations.append(Violation(
            code="EP004",
            severity=Severity.WARN,
            message=(
                f"Object {target.id} is an abstract_framework with "
                f"claim_level='{target.claim_level}' but does not depend_on "
                f"any speculative_ontology. Implicit ontological assumptions "
                f"must be made explicit."
            ),
            nodes_involved=(target.id,),
        ))


def _check_ep005_cycles(
    target_id: int,
    edges: list[Edge],
    violations: list[Violation],
) -> None:
    """
    EP005: Cycle detection in depends_on graph.
    Uses DFS from target_id following depends_on edges.
    Any path back to target_id is a cycle.
    """
    dep_edges = {
        e.source_id: [] for e in edges if e.reference_type == "depends_on"
    }
    for e in edges:
        if e.reference_type == "depends_on":
            dep_edges.setdefault(e.source_id, []).append(e.target_id)

    visited: set[int] = set()
    path: list[int] = []
    cycle_nodes: list[int] = []

    def dfs(node_id: int) -> bool:
        if node_id in path:
            cycle_nodes.extend(path[path.index(node_id):])
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        path.append(node_id)
        for neighbor in dep_edges.get(node_id, []):
            if dfs(neighbor):
                return True
        path.pop()
        return False

    if dfs(target_id):
        violations.append(Violation(
            code="EP005",
            severity=Severity.BLOCK,
            message=(
                f"Cycle detected in depends_on graph involving object {target_id}. "
                f"Cycle path: {' → '.join(str(n) for n in cycle_nodes)} → {cycle_nodes[0]}. "
                f"Circular justification is not permitted."
            ),
            nodes_involved=tuple(set(cycle_nodes)),
        ))


def _check_ep006_validation_scope(
    target: ObjectNode,
    edges: list[Edge],
    node_map: dict[int, ObjectNode],
    violations: list[Violation],
) -> None:
    """
    EP006: External validation scope requires evidence support.
    If validation_scope='external', target must have either:
      - at least one 'supports' edge from an evidence/prediction object
      - OR an attached_artifact_hash
    WARN in v0.
    """
    if target.validation_scope != "external":
        return

    has_artifact = bool(target.attached_artifact_hash)

    support_ids = [
        e.source_id for e in edges
        if e.target_id == target.id and e.reference_type == "supports"
    ]
    evidence_types = {"evidence", "prediction"}
    has_evidence_support = any(
        node_map.get(sid, ObjectNode(
            id=sid, object_type="", epistemic_status="", claim_level="",
            narrative_label="", falsifiable=""
        )).object_type in evidence_types
        for sid in support_ids
    )

    if not has_artifact and not has_evidence_support:
        violations.append(Violation(
            code="EP006",
            severity=Severity.WARN,
            message=(
                f"Object {target.id} has validation_scope='external' but "
                f"has no supporting evidence object and no attached artifact hash. "
                f"External validation requires traceable evidence."
            ),
            nodes_involved=(target.id,),
        ))
