"""
AgentDialog — Add or edit a Proxenos agent in the global registry.
No DB access — returns result_data dict to caller.
"""
from __future__ import annotations

import json
import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("kathoros.ui.dialogs.agent_dialog")


class AgentDialog(QDialog):
    """
    Add or edit a Proxenos agent.
    Pass agent_data=None for a new agent, or a dict for editing.
    After accept(), read .result_data for the field values.
    """

    def __init__(self, agent_data: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._editing = agent_data is not None
        self.result_data: dict | None = None
        self.setWindowTitle("Edit Agent" if self._editing else "Add Agent")
        self.setMinimumSize(560, 660)
        self._build_ui()
        if self._editing:
            self._populate(agent_data)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        form = QFormLayout()
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Basic identity
        self._name = QLineEdit()
        self._name.setPlaceholderText("Required")
        self._alias = QLineEdit()
        self._alias.setPlaceholderText("Short nickname (optional)")
        form.addRow("Name *", self._name)
        form.addRow("Alias", self._alias)

        # Type & provider
        self._type = QComboBox()
        self._type.addItems(["local", "api"])
        self._provider = QComboBox()
        self._provider.addItems(["ollama", "anthropic", "openai", "gemini", "other"])
        self._provider.setEditable(True)
        form.addRow("Type", self._type)
        form.addRow("Provider", self._provider)

        # Connection
        self._endpoint = QLineEdit()
        self._endpoint.setPlaceholderText("http://localhost:11434  (leave empty for API providers)")
        self._model_string = QLineEdit()
        self._model_string.setPlaceholderText("e.g. deepseek-r1, claude-sonnet-4-6")
        form.addRow("Endpoint", self._endpoint)
        form.addRow("Model String", self._model_string)

        # Capabilities & cost
        self._capability_tags = QLineEdit()
        self._capability_tags.setPlaceholderText("math, logic, writing  (comma-separated)")
        self._cost_tier = QComboBox()
        self._cost_tier.addItems(["free", "low", "medium", "high"])
        self._context_window = QSpinBox()
        self._context_window.setRange(0, 2_000_000)
        self._context_window.setSingleStep(1000)
        self._context_window.setSpecialValueText("(unset)")
        form.addRow("Capability Tags", self._capability_tags)
        form.addRow("Cost Tier", self._cost_tier)
        form.addRow("Context Window", self._context_window)

        # Trust & approval
        self._trust_level = QComboBox()
        self._trust_level.addItems(["monitored", "trusted", "untrusted"])
        self._require_tool_approval = QCheckBox("Require approval for tool calls")
        self._require_tool_approval.setChecked(True)
        self._require_write_approval = QCheckBox("Require approval for write operations")
        self._require_write_approval.setChecked(True)
        self._is_active = QCheckBox("Active (shown in agent selector)")
        self._is_active.setChecked(True)
        form.addRow("Trust Level", self._trust_level)
        form.addRow("", self._require_tool_approval)
        form.addRow("", self._require_write_approval)
        form.addRow("", self._is_active)

        # Notes & prompts
        self._user_notes = QPlainTextEdit()
        self._user_notes.setPlaceholderText("Researcher notes about this agent...")
        self._user_notes.setMaximumHeight(72)
        self._research_prompt = QPlainTextEdit()
        self._research_prompt.setPlaceholderText("System prompt used for research conversations...")
        self._research_prompt.setMaximumHeight(120)
        self._audit_prompt = QPlainTextEdit()
        self._audit_prompt.setPlaceholderText("System prompt used for audit sessions...")
        self._audit_prompt.setMaximumHeight(120)
        form.addRow("Notes", self._user_notes)
        form.addRow("Research Prompt", self._research_prompt)
        form.addRow("Audit Prompt", self._audit_prompt)

        form_widget = QWidget()
        form_widget.setLayout(form)

        scroll = QScrollArea()
        scroll.setWidget(form_widget)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        outer.addWidget(scroll)

        # Buttons
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Populate for edit mode
    # ------------------------------------------------------------------

    def _populate(self, d: dict) -> None:
        self._name.setText(d.get("name") or "")
        self._alias.setText(d.get("alias") or "")
        self._set_combo(self._type, d.get("type") or "local")
        self._set_combo(self._provider, d.get("provider") or "")
        self._endpoint.setText(d.get("endpoint") or "")
        self._model_string.setText(d.get("model_string") or "")
        # capability_tags may be a JSON string or a list
        tags = d.get("capability_tags") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [t.strip() for t in tags.split(",") if t.strip()]
        self._capability_tags.setText(", ".join(tags))
        self._set_combo(self._cost_tier, d.get("cost_tier") or "free")
        self._context_window.setValue(int(d.get("context_window") or 0))
        self._set_combo(self._trust_level, d.get("trust_level") or "monitored")
        rta = d.get("require_tool_approval")
        self._require_tool_approval.setChecked(bool(rta) if rta is not None else True)
        rwa = d.get("require_write_approval")
        self._require_write_approval.setChecked(bool(rwa) if rwa is not None else True)
        self._is_active.setChecked(bool(d.get("is_active", True)))
        self._user_notes.setPlainText(d.get("user_notes") or "")
        self._research_prompt.setPlainText(d.get("default_research_prompt") or "")
        self._audit_prompt.setPlainText(d.get("default_audit_prompt") or "")

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.isEditable():
            combo.setCurrentText(value)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Agent name cannot be empty.")
            return

        raw_tags = self._capability_tags.text()
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

        self.result_data = {
            "name":                    name,
            "alias":                   self._alias.text().strip() or None,
            "type":                    self._type.currentText(),
            "provider":                self._provider.currentText().strip() or None,
            "endpoint":                self._endpoint.text().strip() or None,
            "model_string":            self._model_string.text().strip() or None,
            "capability_tags":         tags,
            "cost_tier":               self._cost_tier.currentText(),
            "context_window":          self._context_window.value() or None,
            "trust_level":             self._trust_level.currentText(),
            "require_tool_approval":   int(self._require_tool_approval.isChecked()),
            "require_write_approval":  int(self._require_write_approval.isChecked()),
            "is_active":               int(self._is_active.isChecked()),
            "user_notes":              self._user_notes.toPlainText().strip() or None,
            "default_research_prompt": self._research_prompt.toPlainText().strip() or None,
            "default_audit_prompt":    self._audit_prompt.toPlainText().strip() or None,
        }
        self.accept()
