"""
ToolApprovalDialog — modal approval dialog for agent tool requests.
Shows tool name, args summary, access mode.
Optional collapsible JSON editor for args inspection/modification.
Approve / Deny buttons. Never executes tools — only returns decision.
"""
import json
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

_log = logging.getLogger("kathoros.ui.dialogs.tool_approval_dialog")


class ToolApprovalDialog(QDialog):
    def __init__(self, tool_name: str, args: dict,
                 access_mode: str = "REQUEST_FIRST",
                 agent_name: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self._args = dict(args)
        self._approved = False

        self.setWindowTitle("Tool Request — Approval Required")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: #1e1e1e; color: #cccccc; }")

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)

        # Header
        header = QLabel("⚠  Tool Request")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #f0c040; padding: 4px;")

        # Info rows
        agent_row = self._info_row("Agent:", agent_name or "unknown")
        tool_row = self._info_row("Tool:", tool_name)
        mode_color = {
            "FULL_ACCESS": "#40c040",
            "REQUEST_FIRST": "#f0c040",
            "NO_ACCESS": "#f04040",
        }.get(access_mode, "#888888")
        mode_row = self._info_row("Access Mode:", access_mode, mode_color)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")

        # Args summary
        args_summary = QLabel("Arguments:")
        args_summary.setStyleSheet("color: #888888; padding: 2px 0;")

        # Collapsible JSON editor
        self._toggle_btn = QPushButton("▶  View / Edit JSON")
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: #2d2d2d; color: #4090f0; "
            "border: 1px solid #333; padding: 4px 8px; text-align: left; }"
            "QPushButton:hover { background: #3d3d3d; }"
        )
        self._toggle_btn.clicked.connect(self._toggle_json)

        self._json_edit = QPlainTextEdit()
        self._json_edit.setFont(font)
        self._json_edit.setFixedHeight(160)
        self._json_edit.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #cccccc; border: 1px solid #444; }"
        )
        self._json_edit.setPlainText(json.dumps(args, indent=2))
        self._json_edit.setVisible(False)

        self._json_warning = QLabel("⚠  Editing args may cause unexpected behavior.")
        self._json_warning.setStyleSheet("color: #f0c040; font-size: 10px; padding: 2px 4px;")
        self._json_warning.setVisible(False)

        # Buttons
        deny_btn = QPushButton("Deny")
        deny_btn.setStyleSheet(
            "QPushButton { background: #3d1a1a; color: #f04040; "
            "border: 1px solid #f04040; padding: 6px 20px; }"
            "QPushButton:hover { background: #4d2a2a; }"
        )
        deny_btn.clicked.connect(self._on_deny)

        approve_btn = QPushButton("Approve")
        approve_btn.setStyleSheet(
            "QPushButton { background: #1a3d1a; color: #40c040; "
            "border: 1px solid #40c040; padding: 6px 20px; }"
            "QPushButton:hover { background: #2a4d2a; }"
        )
        approve_btn.clicked.connect(self._on_approve)
        approve_btn.setDefault(True)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(deny_btn)
        btn_row.addWidget(approve_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(header)
        layout.addLayout(agent_row)
        layout.addLayout(tool_row)
        layout.addLayout(mode_row)
        layout.addWidget(sep)
        layout.addWidget(args_summary)
        layout.addWidget(self._toggle_btn)
        layout.addWidget(self._json_edit)
        layout.addWidget(self._json_warning)
        layout.addStretch()
        layout.addLayout(btn_row)

    def _info_row(self, label: str, value: str, value_color: str = "#cccccc"):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #888888; min-width: 100px;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {value_color}; font-weight: bold;")
        row.addWidget(lbl)
        row.addWidget(val)
        row.addStretch()
        return row

    def _toggle_json(self) -> None:
        visible = not self._json_edit.isVisible()
        self._json_edit.setVisible(visible)
        self._json_warning.setVisible(visible)
        self._toggle_btn.setText("▼  View / Edit JSON" if visible else "▶  View / Edit JSON")
        self.adjustSize()

    def _on_approve(self) -> None:
        # Parse edited JSON if visible
        if self._json_edit.isVisible():
            try:
                self._args = json.loads(self._json_edit.toPlainText())
            except json.JSONDecodeError as exc:
                self._json_edit.setStyleSheet(
                    "QPlainTextEdit { background: #1a1a1a; color: #f04040; border: 1px solid #f04040; }"
                )
                _log.warning("invalid JSON in approval dialog: %s", exc)
                return
        self._approved = True
        self.accept()

    def _on_deny(self) -> None:
        self._approved = False
        self.reject()

    @property
    def approved(self) -> bool:
        return self._approved

    @property
    def args(self) -> dict:
        return self._args


def request_approval(tool_name: str, args: dict,
                     access_mode: str = "REQUEST_FIRST",
                     agent_name: str = "",
                     parent=None) -> tuple[bool, dict]:
    """
    Convenience function. Shows dialog, returns (approved, args).
    args may be modified by researcher via JSON editor.
    """
    dialog = ToolApprovalDialog(
        tool_name=tool_name,
        args=args,
        access_mode=access_mode,
        agent_name=agent_name,
        parent=parent,
    )
    dialog.exec()
    return dialog.approved, dialog.args
