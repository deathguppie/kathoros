# tests/smoke/test_imports.py
"""Smoke test: all packages import cleanly."""
import unittest


class TestImports(unittest.TestCase):

    def test_core_constants(self):
        from kathoros.core import constants
        self.assertEqual(constants.APP_NAME, "Kathoros")

    def test_core_enums(self):
        from kathoros.core import enums
        self.assertIsNotNone(enums.AccessMode)

    def test_core_exceptions(self):
        from kathoros.core import exceptions
        self.assertIsNotNone(exceptions.NonceError)

    def test_utils_hashing(self):
        from kathoros.utils import hashing
        self.assertTrue(callable(hashing.hash_args))

    def test_utils_paths(self):
        from kathoros.utils import paths
        self.assertTrue(callable(paths.resolve_safe_path))


if __name__ == "__main__":
    unittest.main()
