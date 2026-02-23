# tests/unit/test_paths.py
import unittest
from pathlib import Path
import tempfile
from kathoros.utils.paths import resolve_safe_path
from kathoros.core.exceptions import AbsolutePathError, TraversalError


class TestResolveSafePath(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.docs = self.root / "docs"
        self.docs.mkdir()

    def test_valid_path(self):
        (self.docs / "paper.pdf").touch()
        result = resolve_safe_path("docs/paper.pdf", self.root, [self.docs])
        self.assertTrue(result.is_absolute())

    def test_absolute_path_rejected(self):
        with self.assertRaises(AbsolutePathError) as ctx:
            resolve_safe_path("/etc/passwd", self.root, [self.docs])
        self.assertIn("absolute", str(ctx.exception))

    def test_traversal_rejected(self):
        with self.assertRaises(TraversalError) as ctx:
            resolve_safe_path("../../etc/passwd", self.root, [self.docs])
        self.assertIn("traversal", str(ctx.exception))

    def test_prefix_bypass_rejected(self):
        # docs_evil should not be allowed even though it starts with "docs"
        evil = self.root / "docs_evil"
        evil.mkdir()
        (evil / "secret.txt").touch()
        with self.assertRaises(TraversalError):
            resolve_safe_path("docs_evil/secret.txt", self.root, [self.docs])

    def test_not_in_allowed_roots(self):
        staging = self.root / "staging"
        staging.mkdir()
        (staging / "file.txt").touch()
        with self.assertRaises(TraversalError):
            resolve_safe_path("staging/file.txt", self.root, [self.docs])


if __name__ == "__main__":
    unittest.main()
