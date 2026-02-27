"""Tests for import_panel helper functions and copy logic."""
import shutil
import tempfile
import unittest
from pathlib import Path

from kathoros.ui.panels.import_panel import (
    _copy_file_to_docs,
    _fmt_size,
    _target_subfolder,
)


class TestFmtSize(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(_fmt_size(0), "0B")
        self.assertEqual(_fmt_size(512), "512B")
        self.assertEqual(_fmt_size(1023), "1023B")

    def test_kilobytes(self):
        self.assertEqual(_fmt_size(1024), "1KB")
        self.assertEqual(_fmt_size(2048), "2KB")
        self.assertEqual(_fmt_size(1024 * 1024 - 1), "1023KB")

    def test_megabytes(self):
        self.assertEqual(_fmt_size(1024 * 1024), "1MB")
        self.assertEqual(_fmt_size(5 * 1024 * 1024), "5MB")


class TestTargetSubfolder(unittest.TestCase):
    def test_pdf(self):
        self.assertEqual(_target_subfolder(".pdf"), "pdf")

    def test_markdown_extensions(self):
        self.assertEqual(_target_subfolder(".md"), "markdown")
        self.assertEqual(_target_subfolder(".txt"), "markdown")
        self.assertEqual(_target_subfolder(".text"), "markdown")

    def test_latex(self):
        self.assertEqual(_target_subfolder(".tex"), "latex")

    def test_python(self):
        self.assertEqual(_target_subfolder(".py"), "python")

    def test_json(self):
        self.assertEqual(_target_subfolder(".json"), "json")

    def test_unknown_returns_other(self):
        self.assertEqual(_target_subfolder(".xyz"), "other")
        self.assertEqual(_target_subfolder(".docx"), "other")

    def test_case_insensitive(self):
        self.assertEqual(_target_subfolder(".PDF"), "pdf")
        self.assertEqual(_target_subfolder(".Md"), "markdown")


class TestCopyFileToDocs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.docs_root = self.tmp / "docs"
        self.docs_root.mkdir()
        self.src_dir = self.tmp / "source"
        self.src_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_src(self, name: str, content: str = "hello") -> Path:
        p = self.src_dir / name
        p.write_text(content)
        return p

    def test_copies_to_correct_subfolder(self):
        src = self._make_src("notes.md")
        dest = _copy_file_to_docs(src, self.docs_root)
        self.assertEqual(dest.parent.name, "markdown")
        self.assertEqual(dest.name, "notes.md")
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "hello")

    def test_pdf_subfolder(self):
        src = self._make_src("paper.pdf", content="fake-pdf")
        dest = _copy_file_to_docs(src, self.docs_root)
        self.assertEqual(dest.parent.name, "pdf")

    def test_creates_subfolder_if_missing(self):
        src = self._make_src("code.py")
        dest = _copy_file_to_docs(src, self.docs_root)
        self.assertTrue((self.docs_root / "python").is_dir())
        self.assertEqual(dest, self.docs_root / "python" / "code.py")

    def test_collision_adds_suffix(self):
        src = self._make_src("notes.md", "first")
        _copy_file_to_docs(src, self.docs_root)

        src2 = self._make_src("notes.md", "second")
        dest2 = _copy_file_to_docs(src2, self.docs_root)
        self.assertEqual(dest2.name, "notes_1.md")
        self.assertEqual(dest2.read_text(), "second")

    def test_multiple_collisions(self):
        src = self._make_src("data.json", "v1")
        _copy_file_to_docs(src, self.docs_root)

        src2 = self._make_src("data.json", "v2")
        _copy_file_to_docs(src2, self.docs_root)

        src3 = self._make_src("data.json", "v3")
        dest3 = _copy_file_to_docs(src3, self.docs_root)
        self.assertEqual(dest3.name, "data_2.json")
        self.assertEqual(dest3.read_text(), "v3")

    def test_preserves_file_content(self):
        content = "line1\nline2\nline3"
        src = self._make_src("test.txt", content)
        dest = _copy_file_to_docs(src, self.docs_root)
        self.assertEqual(dest.read_text(), content)


if __name__ == "__main__":
    unittest.main()
