# kathoros/epistemic — Epistemic graph integrity checker
# Enforces: premise gate, TOY_MODEL labeling, cycle detection,
# ontology prediction ban, framework linkage, validation scope.
from kathoros.epistemic.checker import (
    CheckResult,
    EpistemicChecker,
    Severity,
    Violation,
)

__all__ = ["EpistemicChecker", "CheckResult", "Violation", "Severity"]
