# tests/unit/test_hashing.py
import unittest
from kathoros.utils.hashing import hash_args


class TestHashArgs(unittest.TestCase):

    def test_returns_64_chars(self):
        result = hash_args({"tool": "file_analyze", "path": "docs/paper.pdf"})
        self.assertEqual(len(result), 64)

    def test_deterministic(self):
        args = {"b": 2, "a": 1}
        self.assertEqual(hash_args(args), hash_args(args))

    def test_key_order_invariant(self):
        a = hash_args({"a": 1, "b": 2})
        b = hash_args({"b": 2, "a": 1})
        self.assertEqual(a, b)

    def test_different_args_different_hash(self):
        a = hash_args({"path": "docs/a.pdf"})
        b = hash_args({"path": "docs/b.pdf"})
        self.assertNotEqual(a, b)

    def test_empty_dict(self):
        result = hash_args({})
        self.assertEqual(len(result), 64)


if __name__ == "__main__":
    unittest.main()
