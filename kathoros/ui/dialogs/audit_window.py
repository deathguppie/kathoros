"""
AuditWindow — modal dialog for running a structured audit on a research object.
Linear mode only. Researcher-driven conflict recording.
No tool execution. No router calls. No direct DB access (uses SessionService only).
"""
from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kathoros.agents.dispatcher import AgentDispatcher
from kathoros.agents.prompts import AUDIT_SYSTEM_PROMPT

_log = logging.getLogger("kathoros.ui.dialogs.audit_window")

_DARK_STYLE = """
QDialog { background: #1e1e1e; color: #cccccc; }
QLabel { color: #cccccc; }
QCheckBox { color: #cccccc; }
QPushButton {
    background: #2d2d2d; color: #cccccc; border: 1px solid #555;
    padding: 4px 10px; border-radius: 3px;
}
QPushButton:hover { background: #3d3d3d; }
QPushButton:disabled { background: #252525; color: #666; }
QPlainTextEdit {
    background: #141414; color: #cccccc; border: 1px solid #333;
    font-family: monospace; font-size: 11pt;
}
QListWidget {
    background: #1a1a1a; color: #cccccc; border: 1px solid #333;
}
QTabWidget::pane { border: 1px solid #333; }
QTabBar::tab {
    background: #2d2d2d; color: #aaa; padding: 4px 10px;
    border: 1px solid #444; border-bottom: none;
}
QTabBar::tab:selected { background: #1e1e1e; color: #eee; }
QFrame[frameShape="4"] { color: #444; }
"""


class AuditWindow(QDialog):
    def __init__(self, object_data: dict, session_service, global_service,
                 session_nonce: str, parent=None) -> None:
        super().__init__(parent)
        self._object_data = object_data
        self._session_service = session_service
        self._global_service = global_service
        self._session_nonce = session_nonce

        self._audit_session_id: int | None = None
        self._agent_queue: list[int] = []
        self._agent_outputs: dict[int, QPlainTextEdit] = {}
        self._dispatchers: list[AgentDispatcher] = []
        self._audit_message = self._build_audit_message(object_data)

        self.setWindowTitle(
            f"Audit: {object_data.get('name', '?')}  ({object_data.get('type', '?')})"
        )
        self.setMinimumSize(800, 650)
        self.setStyleSheet(_DARK_STYLE)
        self.setModal(True)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Title bar
        title = QLabel(
            f"<b>Audit:</b> {self._object_data.get('name', '?')} "
            f"<span style='color:#888'>({self._object_data.get('type', '?')})</span>"
        )
        title.setStyleSheet("font-size: 13pt; padding: 4px;")
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Config pane — agent checkboxes + Start button
        self._config_pane = self._build_config_pane()
        root.addWidget(self._config_pane)

        # Output tabs — hidden until audit starts
        self._output_tabs = QTabWidget()
        self._output_tabs.setVisible(False)
        root.addWidget(self._output_tabs, stretch=3)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        # Conflicts section
        root.addWidget(self._build_conflicts_section())

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep3)

        # Researcher notes
        notes_label = QLabel("Researcher Notes:")
        root.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setFixedHeight(80)
        self._notes_edit.setPlaceholderText("Optional notes for this audit session...")
        root.addWidget(self._notes_edit)

        sep4 = QFrame(); sep4.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep4)

        # Action buttons
        root.addLayout(self._build_action_buttons())

    def _build_config_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Select Agents:"))

        agents = self._global_service.list_agents()
        self._agent_checkboxes: dict[int, QCheckBox] = {}

        for agent in agents:
            agent_id = agent.get("id")
            name = agent.get("name", "?")
            provider = agent.get("provider", "")
            cost_tier = agent.get("cost_tier", "")
            label = f"{name} ({provider})"
            if cost_tier:
                label += f"  [{cost_tier}]"
            cb = QCheckBox(label)
            cb.stateChanged.connect(self._update_start_button)
            self._agent_checkboxes[agent_id] = cb
            layout.addWidget(cb)

        if not agents:
            layout.addWidget(QLabel("<i>No active agents configured.</i>"))

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start Audit")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return pane

    def _build_conflicts_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Conflicts:"))
        header_row.addStretch()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._on_add_conflict)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        self._conflict_list = QListWidget()
        self._conflict_list.setFixedHeight(80)
        layout.addWidget(self._conflict_list)

        return widget

    def _build_action_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()

        self._save_btn = QPushButton("Save Log")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_log)

        self._reject_btn = QPushButton("Reject")
        self._reject_btn.setEnabled(False)
        self._reject_btn.setStyleSheet(
            "QPushButton { color: #f04040; } QPushButton:disabled { color: #555; }"
        )
        self._reject_btn.clicked.connect(self._on_reject)

        self._commit_btn = QPushButton("Commit \u2713")
        self._commit_btn.setEnabled(False)
        self._commit_btn.setStyleSheet(
            "QPushButton { color: #40c040; } QPushButton:disabled { color: #555; }"
        )
        self._commit_btn.clicked.connect(self._on_commit)

        row.addWidget(self._save_btn)
        row.addWidget(self._reject_btn)
        row.addWidget(self._commit_btn)
        return row

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_audit_message(self, obj: dict) -> str:
        parts = ["Research Object Audit Request", "=" * 40]
        parts.append(f"Name: {obj.get('name', 'Unknown')}")
        parts.append(f"Type: {obj.get('type', 'unknown')}")
        parts.append(f"Status: {obj.get('status', 'pending')}")
        if obj.get("content"):
            parts.append(f"\nContent:\n{obj['content']}")
        if obj.get("math_expression"):
            parts.append(f"\nMath Expression:\n{obj['math_expression']}")
        if obj.get("researcher_notes"):
            parts.append(f"\nResearcher Notes:\n{obj['researcher_notes']}")
        return "\n".join(parts)

    def _update_start_button(self) -> None:
        any_checked = any(cb.isChecked() for cb in self._agent_checkboxes.values())
        self._start_btn.setEnabled(any_checked)

    def _get_tab_for_agent(self, agent_id: int, agent_name: str) -> QPlainTextEdit:
        if agent_id in self._agent_outputs:
            return self._agent_outputs[agent_id]
        text_widget = QPlainTextEdit()
        text_widget.setReadOnly(True)
        self._output_tabs.addTab(text_widget, agent_name)
        self._agent_outputs[agent_id] = text_widget
        return text_widget

    # ------------------------------------------------------------------
    # Audit flow
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        selected_ids = [
            aid for aid, cb in self._agent_checkboxes.items() if cb.isChecked()
        ]
        if not selected_ids:
            return

        obj_id = self._object_data.get("id", 0)
        obj_type = self._object_data.get("type", "unknown")

        self._audit_session_id = self._session_service.create_audit_session(
            artifact_id=obj_id,
            artifact_type=obj_type,
            execution_mode="linear",
            agent_ids=selected_ids,
            scope="current",
        )

        # Pre-create output tabs in selection order
        for aid in selected_ids:
            agent = self._global_service.get_agent(aid)
            name = agent.get("name", f"Agent {aid}") if agent else f"Agent {aid}"
            self._get_tab_for_agent(aid, name)

        self._agent_queue = list(selected_ids)

        self._config_pane.setVisible(False)
        self._output_tabs.setVisible(True)

        self._dispatch_next()

    def _dispatch_next(self) -> None:
        if not self._agent_queue:
            self._show_resolution()
            return

        agent_id = self._agent_queue.pop(0)
        agent = self._global_service.get_agent(agent_id)
        if agent is None:
            _log.warning("agent %d not found, skipping", agent_id)
            self._dispatch_next()
            return

        result_id = self._session_service.start_audit_result(
            self._audit_session_id, agent_id
        )
        text_widget = self._agent_outputs[agent_id]
        # Switch to this agent's tab
        idx = self._output_tabs.indexOf(text_widget)
        if idx >= 0:
            self._output_tabs.setCurrentIndex(idx)

        accumulated: list[str] = [""]

        def on_chunk(chunk: str) -> None:
            accumulated[0] += chunk
            text_widget.insertPlainText(chunk)
            text_widget.ensureCursorVisible()

        def on_done() -> None:
            self._session_service.finish_audit_result(result_id, accumulated[0])
            self._dispatch_next()

        def on_error(msg: str) -> None:
            text_widget.insertPlainText(f"\n[ERROR: {msg}]")
            self._session_service.finish_audit_result(result_id, accumulated[0])
            self._dispatch_next()

        dispatcher = AgentDispatcher()
        dispatcher.dispatch(
            message=self._audit_message,
            agent=agent,
            access_mode="REQUEST_FIRST",
            session_nonce=self._session_nonce,
            system_prompt=AUDIT_SYSTEM_PROMPT,
            on_chunk=on_chunk,
            on_done=on_done,
            on_error=on_error,
        )
        self._dispatchers.append(dispatcher)

    def _show_resolution(self) -> None:
        self._save_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        self._commit_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Conflict recording
    # ------------------------------------------------------------------

    def _on_add_conflict(self) -> None:
        if self._audit_session_id is None:
            return
        text, ok = QInputDialog.getText(
            self, "Add Conflict", "Describe the conflict:"
        )
        if not ok or not text.strip():
            return
        self._session_service.add_conflict(self._audit_session_id, text.strip())
        idx = self._conflict_list.count() + 1
        self._conflict_list.addItem(QListWidgetItem(f"{idx}. {text.strip()}"))

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    def _on_save_log(self) -> None:
        self._finalize_audit(decision=None)
        self.accept()

    def _on_reject(self) -> None:
        self._finalize_audit(decision="rejected")
        obj_id = self._object_data.get("id")
        if obj_id is not None:
            self._session_service.set_object_status(obj_id, "flagged")
        self.accept()

    def _on_commit(self) -> None:
        self._finalize_audit(decision="approved")
        obj_id = self._object_data.get("id")
        if obj_id is not None:
            self._session_service.commit_object(obj_id)
        self.accept()

    def reject(self) -> None:
        """Stop all dispatchers before closing to prevent callbacks on dead widgets."""
        for d in self._dispatchers:
            d.stop()
        self._dispatchers.clear()
        super().reject()

    def _finalize_audit(self, decision) -> None:
        if self._audit_session_id is None:
            return
        for d in self._dispatchers:
            d.stop()
        self._dispatchers.clear()
        notes = self._notes_edit.toPlainText().strip()
        self._session_service.complete_audit(self._audit_session_id, decision, notes)
