"""
PygmentsHighlighter — QSyntaxHighlighter using pygments for token-based highlighting.
Supports python, markdown, latex, text.
Plugs into any QPlainTextEdit or QTextEdit document.
"""
import logging
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt
from pygments import lex
from pygments.token import Token
from pygments.lexers import PythonLexer, MarkdownLexer, TexLexer, TextLexer

_log = logging.getLogger("kathoros.ui.panels.syntax_highlighter")


def _fmt(color: str, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if italic:
        f.setFontItalic(True)
    return f


_FORMATS = {
    Token.Keyword:              _fmt("#cc99cd"),
    Token.Keyword.Constant:     _fmt("#cc99cd"),
    Token.Keyword.Declaration:  _fmt("#cc99cd"),
    Token.Keyword.Type:         _fmt("#cc99cd"),
    Token.Name.Function:        _fmt("#6fb3d2"),
    Token.Name.Class:           _fmt("#6fb3d2"),
    Token.Name.Builtin:         _fmt("#6fb3d2"),
    Token.Name.Decorator:       _fmt("#f08d49"),
    Token.String:               _fmt("#7ec699"),
    Token.String.Doc:           _fmt("#7ec699", italic=True),
    Token.Comment:              _fmt("#999999", italic=True),
    Token.Comment.Single:       _fmt("#999999", italic=True),
    Token.Number:               _fmt("#f08d49"),
    Token.Operator:             _fmt("#cccccc"),
    Token.Punctuation:          _fmt("#cccccc"),
}

_DEFAULT_FMT = _fmt("#cccccc")

_LEXERS = {
    "python":   PythonLexer,
    "markdown": MarkdownLexer,
    "latex":    TexLexer,
    "text":     TextLexer,
}


class PygmentsHighlighter(QSyntaxHighlighter):
    def __init__(self, document, language: str = "text") -> None:
        super().__init__(document)
        self._lexer = _LEXERS.get(language.lower(), TextLexer)()

    def set_language(self, language: str) -> None:
        self._lexer = _LEXERS.get(language.lower(), TextLexer)()
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        offset = 0
        try:
            for token_type, value in lex(text, self._lexer):
                length = len(value)
                fmt = self._token_format(token_type)
                self.setFormat(offset, length, fmt)
                offset += length
        except Exception as exc:
            _log.debug("highlight error: %s", exc)

    def _token_format(self, token_type) -> QTextCharFormat:
        # Walk up token hierarchy to find best match
        t = token_type
        while t:
            if t in _FORMATS:
                return _FORMATS[t]
            t = t.parent if hasattr(t, "parent") else None
        return _DEFAULT_FMT
