"""
SettingsPanel — global settings editor.
No DB calls — receives settings dict, emits changes via signal.
Caller (main window) reads/writes DB via ProjectManager.
"""
import logging
from kathoros.config.key_store import save_key, masked, key_exists
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QCheckBox, QLineEdit, QPushButton, QScrollArea
)
from PyQt6.QtCore import pyqtSignal

_log = logging.getLogger("kathoros.ui.panels.settings_panel")


class SettingsPanel(QWidget):
    # Emits (settings_dict, scope) where scope is "global" or "project"
    settings_changed = pyqtSignal(dict, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_loaded: dict = {}

        header = QLabel("Settings")
        header.setStyleSheet("font-weight: bold; padding: 4px;")

        # Widgets
        self._access_mode = QComboBox()
        self._access_mode.addItems(["REQUEST_FIRST", "FULL_ACCESS", "NO_ACCESS"])

        self._trust_level = QComboBox()
        self._trust_level.addItems(["MONITORED", "TRUSTED", "UNTRUSTED"])

        self._write_approval = QCheckBox()
        self._tool_approval = QCheckBox()
        self._git_confirm = QCheckBox()
        self._security_scan = QCheckBox()
        self._snapshot_size = QLineEdit()
        self._snapshot_size.setPlaceholderText("bytes")
        self._audit_append = QCheckBox()

        form = QFormLayout()
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(10)
        form.addRow("Default Access Mode",    self._access_mode)
        form.addRow("Default Trust Level",    self._trust_level)
        form.addRow("Require Write Approval", self._write_approval)
        form.addRow("Require Tool Approval",  self._tool_approval)
        form.addRow("Require Git Confirm",    self._git_confirm)
        form.addRow("Require Security Scan",  self._security_scan)
        form.addRow("Max Snapshot Size",      self._snapshot_size)
        form.addRow("Audit Log Append Only",  self._audit_append)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._on_reset)

        self._scope = QComboBox()
        self._scope.addItems(["Global", "Project"])
        self._scope.setToolTip(
            "Global: save as default for all projects\n"
            "Project: override for current project only"
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Save to:"))
        toolbar.addWidget(self._scope)
        toolbar.addStretch()
        toolbar.addWidget(reset_btn)
        toolbar.addWidget(save_btn)

        form_widget = QWidget()
        form_widget.setLayout(form)

        self._api_key_section = self._build_api_key_section()
        scroll = QScrollArea()
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addWidget(form_widget)
        container_layout.addWidget(self._api_key_section)
        container_layout.addStretch()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(header)
        main_layout.addWidget(scroll)
        main_layout.addLayout(toolbar)

    def load_settings(self, settings: dict) -> None:
        self._last_loaded = dict(settings)
        self._access_mode.setCurrentText(settings.get("default_access_mode", "REQUEST_FIRST"))
        self._trust_level.setCurrentText(settings.get("default_trust_level", "MONITORED"))
        self._write_approval.setChecked(bool(int(settings.get("require_write_approval", 1))))
        self._tool_approval.setChecked(bool(int(settings.get("require_tool_approval", 1))))
        self._git_confirm.setChecked(bool(int(settings.get("require_git_confirm", 1))))
        self._security_scan.setChecked(bool(int(settings.get("require_security_scan", 1))))
        self._snapshot_size.setText(str(settings.get("max_snapshot_size_bytes", 1048576)))
        self._audit_append.setChecked(bool(int(settings.get("audit_log_append_only", 1))))

    def get_settings(self) -> dict:
        return {
            "default_access_mode":     self._access_mode.currentText(),
            "default_trust_level":     self._trust_level.currentText(),
            "require_write_approval":  "1" if self._write_approval.isChecked() else "0",
            "require_tool_approval":   "1" if self._tool_approval.isChecked() else "0",
            "require_git_confirm":     "1" if self._git_confirm.isChecked() else "0",
            "require_security_scan":   "1" if self._security_scan.isChecked() else "0",
            "max_snapshot_size_bytes": self._snapshot_size.text().strip() or "1048576",
            "audit_log_append_only":   "1" if self._audit_append.isChecked() else "0",
        }

    def _on_save(self) -> None:
        self._last_loaded = self.get_settings()
        scope = self._scope.currentText().lower()  # "global" or "project"
        self.settings_changed.emit(self._last_loaded, scope)

    def _on_reset(self) -> None:
        if self._last_loaded:
            self.load_settings(self._last_loaded)

    def _build_api_key_section(self) -> QWidget:
        from PyQt6.QtWidgets import QGroupBox, QFormLayout, QLineEdit
        group = QGroupBox("API Keys")
        group.setStyleSheet("QGroupBox { color: #cccccc; border: 1px solid #333; margin-top: 8px; padding: 8px; }")
        form = QFormLayout(group)

        self._api_inputs = {}
        for provider, label in [("anthropic", "Anthropic"), ("openai", "OpenAI")]:
            row = QHBoxLayout()
            display = QLabel(masked(provider))
            display.setStyleSheet("color: #888888; min-width: 120px;")
            entry = QLineEdit()
            entry.setPlaceholderText(f"Paste {label} API key...")
            entry.setEchoMode(QLineEdit.EchoMode.Password)
            entry.setStyleSheet("QLineEdit { background: #2d2d2d; color: #cccccc; border: 1px solid #333; padding: 4px; }")
            save_btn = QPushButton("Save")
            save_btn.clicked.connect(lambda _, p=provider, e=entry, d=display: self._save_api_key(p, e, d))
            row.addWidget(entry)
            row.addWidget(save_btn)
            row.addWidget(display)
            w = QWidget()
            w.setLayout(row)
            form.addRow(f"{label}:", w)
            self._api_inputs[provider] = (entry, display)

        return group

    def _save_api_key(self, provider: str, entry, display) -> None:
        key = entry.text().strip()
        if not key:
            return
        save_key(provider, key)
        entry.clear()
        display.setText(masked(provider))
        import logging
        logging.getLogger("kathoros.ui.panels.settings_panel").info(
            "API key saved for provider: %s", provider
        )
