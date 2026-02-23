# kathoros/epistemic — Epistemic graph integrity checker
# Enforces: premise gate, TOY_MODEL labeling, cycle detection,
# ontology prediction ban, framework linkage, validation scope.
from kathoros.epistemic.checker import (
    EpistemicChecker, CheckResult, Violation, Severity,
)

__all__ = ["EpistemicChecker", "CheckResult", "Violation", "Severity"]
