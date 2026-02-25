"""
Kathoros main application window.
Layout and wiring only — no business logic, no tool execution.
UI components may request approval but must never execute tools directly (INV-1).
"""
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QVBoxLayout,
    QWidget, QLabel, QTabWidget
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QFont
import sys
import logging
from kathoros.ui.panels.objects_panel import ObjectsPanel as _RealObjectsPanel
from kathoros.ui.panels.audit_log_panel import AuditLogPanel
from kathoros.ui.panels.reader_panel import ReaderPanel
from kathoros.ui.panels.import_panel import ImportPanel
from kathoros.ui.panels.sagemath_panel import SageMathPanel
from kathoros.ui.panels.latex_panel import LaTeXPanel
from kathoros.ui.panels.matplot_panel import MatPlotPanel
from kathoros.ui.panels.graph_panel import GraphPanel
from kathoros.ui.panels.editor_panel import EditorPanel
from kathoros.ui.panels.git_panel import GitPanel
from kathoros.ui.panels.shell_panel import ShellPanel
from kathoros.ui.panels.notes_panel import NotesPanel
from kathoros.ui.panels.results_panel import ResultsPanel
from kathoros.ui.panels.settings_panel import SettingsPanel
from kathoros.ui.panels.agent_manager_panel import AgentManagerPanel
from kathoros.ui.panels.sqlite_explorer_panel import SQLiteExplorerPanel
from kathoros.ui.panels.cross_project_search_panel import CrossProjectSearchPanel
from kathoros.ui.panels.ai_output_panel import AIOutputPanel as _RealAIOutputPanel
from kathoros.ui.panels.ai_input_panel import AIInputPanel as _RealAIInputPanel
from kathoros.core.constants import APP_NAME, APP_VERSION
from kathoros.core.enums import AccessMode, TrustLevel, Decision
from kathoros.agents.dispatcher import AgentDispatcher
from kathoros.services.tool_service import ToolService
from kathoros.services.git_service import GitService
from kathoros.ui.dialogs.tool_approval_dialog import request_approval
from kathoros.ui.dialogs.import_approval_dialog import ImportApprovalDialog
from kathoros.agents.import_parser import parse_object_suggestions
from kathoros.agents.prompts import IMPORT_SYSTEM_PROMPT, RESEARCH_SYSTEM_PROMPT

_log = logging.getLogger("kathoros.ui.main_window")


def _build_export_body(notes: list[dict], fmt: str) -> str:
    parts = []
    for n in notes:
        title   = n.get("title") or "Untitled"
        content = n.get("content") or ""
        if fmt == "markdown":
            parts.append(f"## {title}\n\n{content}\n")
        elif fmt == "latex":
            safe = title.replace("_", r"\_").replace("&", r"\&")
            parts.append(f"\\section{{{safe}}}\n\n{content}\n")
        else:
            parts.append(f"=== {title} ===\n\n{content}\n")
    if fmt == "latex":
        sep = "\n\n"
        header = "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\begin{document}\n\n"
        return header + sep.join(parts) + "\n\\end{document}\n"
    sep = "\n---\n\n" if fmt == "markdown" else "\n\n"
    return sep.join(parts)


def _read_file_text(path: str, max_chars: int = 12000) -> str:
    """Read text content from a file. Handles PDF via fitz, others as plain text."""
    from pathlib import Path
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        import fitz
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text[:max_chars]
    return Path(path).read_text(encoding="utf-8", errors="replace")[:max_chars]


class DocumentsTabGroup(QTabWidget):
    def __init__(self):
        super().__init__()
        self._reader_panel = ReaderPanel()
        self._editor_panel = EditorPanel()
        self._latex_panel = LaTeXPanel()
        self.addTab(self._reader_panel, "Reader")
        self.addTab(self._editor_panel, "Editor")
        self.addTab(self._latex_panel, "LaTeX")
        self._audit_log = AuditLogPanel()
        self.addTab(self._audit_log, "Audit Log")
        self._import_panel = ImportPanel()
        self.addTab(self._import_panel, "Import")
        self._notes_panel = NotesPanel()
        self.addTab(self._notes_panel, "Notes")


class MathematicsTabGroup(QTabWidget):
    def __init__(self):
        super().__init__()
        self._sagematch_panel = SageMathPanel()
        self._graph_panel = GraphPanel()
        self._matplot_panel = MatPlotPanel()
        self.addTab(self._sagematch_panel, "SageMath")
        self.addTab(self._graph_panel, "Graph")
        self.addTab(self._matplot_panel, "MatPlot")


class DataTabGroup(QTabWidget):
    def __init__(self):
        super().__init__()
        self._sqlite_explorer = SQLiteExplorerPanel()
        self.addTab(self._sqlite_explorer, "SQLite Explorer")
        self._results_panel = ResultsPanel()
        self.addTab(self._results_panel, "Results")
        self._search_panel = CrossProjectSearchPanel()
        self.addTab(self._search_panel, "Search")


class SystemTabGroup(QTabWidget):
    def __init__(self):
        super().__init__()
        self._shell_panel = ShellPanel()
        self.addTab(self._shell_panel, "Shell")
        self._git_panel = GitPanel()
        self.addTab(self._git_panel, "Git")
        self._agent_manager = AgentManagerPanel()
        self.addTab(self._agent_manager, "Agent Manager")
        self._settings_panel = SettingsPanel()
        self.addTab(self._settings_panel, "Settings")


class RightPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._tab_widget = QTabWidget()
        self._docs_tab_group = DocumentsTabGroup()
        self._math_tab_group = MathematicsTabGroup()
        self._data_tab_group = DataTabGroup()
        self._system_tab_group = SystemTabGroup()
        self._tab_widget.addTab(self._docs_tab_group, "Documents")
        self._tab_widget.addTab(self._math_tab_group, "Mathematics")
        self._tab_widget.addTab(self._data_tab_group, "Data")
        self._tab_widget.addTab(self._system_tab_group, "System")
        layout.addWidget(self._tab_widget)


class KathorosMainWindow(QMainWindow):
    def __init__(self, project_manager=None):
        super().__init__()
        _log.info("INIT self id=%s", id(self))
        self._pm = project_manager
        self._dispatcher = AgentDispatcher()
        self._pending_import_paths: list = []
        self._import_mode: bool = False
        self._tool_service: ToolService | None = None
        self._git_service: GitService | None = None
        self._selected_objects: list[dict] = []  # objects highlighted in objects panel
        self.setWindowTitle(f"{APP_NAME} — {APP_VERSION}")
        self.setMinimumSize(1200, 800)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        self._left_panel = QSplitter(Qt.Orientation.Vertical)
        self._ai_output_panel = _RealAIOutputPanel()
        self._ai_input_panel = _RealAIInputPanel()
        self._objects_panel = _RealObjectsPanel()
        self._objects_panel.refresh_requested.connect(lambda: self._load_objects())
        self._objects_panel.object_selected.connect(self._on_object_selected)
        self._objects_panel.audit_requested.connect(self._on_audit_requested)
        self._objects_panel.object_edit_requested.connect(self._on_object_edit_requested)
        self._objects_panel.status_change_requested.connect(self._on_status_change_requested)
        self._objects_panel.open_source_requested.connect(self._on_open_source_requested)
        self._ai_input_panel.message_submitted.connect(self._on_message_submitted)
        self._ai_input_panel.stop_requested.connect(self._on_stop_requested)
        self._left_panel.addWidget(self._ai_output_panel)
        self._left_panel.addWidget(self._ai_input_panel)
        self._left_panel.addWidget(self._objects_panel)

        self._right_panel = RightPanel()

        self._splitter.addWidget(self._left_panel)
        self._splitter.addWidget(self._right_panel)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 7)
        self.setCentralWidget(self._splitter)
        self._build_menu_bar()

        settings = QSettings("Kathoros", "Kathoros")
        if settings.contains("splitterState"):
            self._splitter.restoreState(settings.value("splitterState"))

        # Wire right panel signals
        sys_tab = self._right_panel.findChild(SystemTabGroup)
        if sys_tab:
            sys_tab._agent_manager.refresh_requested.connect(self._load_agents)
            sys_tab._agent_manager.add_agent_requested.connect(self._on_add_agent)
            sys_tab._agent_manager.edit_agent_requested.connect(self._on_edit_agent)
            sys_tab._agent_manager.delete_requested.connect(self._on_delete_agent)
            sys_tab._settings_panel.settings_changed.connect(self._on_settings_changed)
            self._agent_manager = sys_tab._agent_manager
            self._settings_panel = sys_tab._settings_panel

        # Wire LaTeX panel pdf_ready → open in reader
        latex_panel = self._right_panel._docs_tab_group._latex_panel
        latex_panel.pdf_ready.connect(self._on_latex_pdf_ready)

        # Startup loads
        self._load_objects()
        self._load_agents()
        self._load_settings()          # seeds access mode from settings
        self._load_agents_into_input()
        self._wire_sqlite_explorer()
        self._wire_search_panel()
        self._wire_git_panel()
        self._wire_import_panel()
        self._wire_notes_panel()
        self._wire_shell_panel()
        self._restore_session_snapshot()   # may override access mode from saved session
        self._init_tool_service()          # reads final access mode from panel
        if self._pm and self._pm.project_name:
            self.setWindowTitle(f"{APP_NAME} — {APP_VERSION} — {self._pm.project_name}")
        self._restore_conversation_history()

    def _build_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        switch_action = QAction("Switch Project...", self)
        switch_action.setShortcut("Ctrl+Shift+O")
        switch_action.triggered.connect(self._on_switch_project)
        file_menu.addAction(switch_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(quit_action)

        notes_menu = self.menuBar().addMenu("Notes")
        for label, fmt in [
            ("Export Selected as Markdown…", "markdown"),
            ("Export Selected as LaTeX…",    "latex"),
            ("Export Selected as Plain Text…", "text"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda checked, f=fmt: self._on_export_notes(f))
            notes_menu.addAction(action)

    def _on_switch_project(self) -> None:
        from kathoros.ui.dialogs.project_dialog import ProjectDialog
        self._save_session_snapshot()
        dialog = ProjectDialog(self._pm, parent=self)
        if dialog.exec() != ProjectDialog.DialogCode.Accepted:
            return
        self._reinitialize_for_new_project()

    def _reinitialize_for_new_project(self) -> None:
        # Disconnect import signal before rewire (lambda can't be disconnected by ref)
        if hasattr(self, "_import_panel") and self._import_panel is not None:
            try:
                self._import_panel.import_requested.disconnect()
            except RuntimeError:
                pass
        # Reset session-scoped state
        self._pending_import_paths = []
        self._import_mode = False
        self._dispatcher._history.clear()
        # Clear UI
        self._ai_output_panel.clear()
        # Reload all panels
        self._load_objects()
        self._load_agents()
        self._load_settings()
        self._load_agents_into_input()
        self._wire_sqlite_explorer()
        self._wire_search_panel()
        self._wire_git_panel()
        self._wire_import_panel()
        notes_panel = self.findChild(NotesPanel)
        if notes_panel:
            notes_panel.clear()
        self._wire_notes_panel()
        self._wire_shell_panel()
        self._restore_session_snapshot()   # may override access mode from saved session
        self._init_tool_service()          # reads final access mode from panel
        self._restore_conversation_history()
        if self._pm and self._pm.project_name:
            self.setWindowTitle(f"{APP_NAME} — {APP_VERSION} — {self._pm.project_name}")
        _log.info("reinitialized for project: %s", self._pm.project_name)

    def closeEvent(self, event):
        self._save_session_snapshot()
        settings = QSettings("Kathoros", "Kathoros")
        settings.setValue("splitterState", self.centralWidget().saveState())

    def _on_audit_requested(self, object_id: int) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        obj = self._pm.session_service.get_object(object_id)
        if obj is None:
            return
        nonce = self._pm.session_service.session_nonce
        from kathoros.ui.dialogs.audit_window import AuditWindow
        window = AuditWindow(
            object_data=obj,
            session_service=self._pm.session_service,
            global_service=self._pm.global_service,
            session_nonce=nonce,
            parent=self,
        )
        window.exec()
        self._load_objects()

    def _on_object_selected(self, object_id: int) -> None:
        """Left-click: show object content in the appropriate panel and track selection."""
        if self._pm is None or self._pm.session_service is None:
            return
        obj = self._pm.session_service.get_object(object_id)
        if obj is None:
            return
        # Track for context injection — keep at most 5 selected objects
        self._selected_objects = [
            o for o in self._selected_objects if o.get("id") != obj.get("id")
        ]
        self._selected_objects.insert(0, obj)
        self._selected_objects = self._selected_objects[:5]

        # Switch right panel to Documents tab first
        outer = self._right_panel._tab_widget
        outer.setCurrentIndex(0)
        docs = self._right_panel._docs_tab_group

        latex = (obj.get("latex") or "").strip()
        source_file = (obj.get("source_file") or "")
        is_latex = bool(latex) or source_file.lower().endswith(".tex")
        _log.info("object_selected id=%s latex_len=%d source_file=%s is_latex=%s",
                  object_id, len(latex), source_file, is_latex)

        if is_latex:
            content_for_latex = latex or (obj.get("content") or "").strip()
            self._right_panel._docs_tab_group._latex_panel.load_content(content_for_latex)
            docs.setCurrentIndex(2)  # LaTeX is tab 2
        else:
            editor = self._right_panel.findChild(EditorPanel)
            if editor:
                editor.load_object(obj)
            docs.setCurrentIndex(1)  # Editor is tab 1

    def _on_object_edit_requested(self, object_id: int) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        obj = self._pm.session_service.get_object(object_id)
        if obj is None:
            return
        from kathoros.ui.dialogs.object_detail_dialog import ObjectDetailDialog
        all_objects = self._objects_panel._objects if hasattr(self._objects_panel, "_objects") else []
        docs_path = str(self._pm.project_root / "docs") if self._pm and self._pm.project_root else None
        dlg = ObjectDetailDialog(obj, self._pm.session_service, all_objects=all_objects,
                                 docs_path=docs_path, parent=self)
        dlg.open_in_reader.connect(self._open_file_in_reader)
        dlg.exec()
        self._load_objects()

    def _on_open_source_requested(self, object_id: int) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        obj = self._pm.session_service.get_object(object_id)
        if obj is None:
            return
        source_file = obj.get("source_file") or ""
        if not source_file:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Source File",
                                    "This object has no source file set.\n"
                                    "Open the object (double-click) and fill in the Source field.")
            return
        from pathlib import Path
        candidate = Path(source_file)
        if not (candidate.is_absolute() and candidate.exists()):
            docs_dir = self._pm.project_root / "docs" if self._pm.project_root else None
            if docs_dir:
                candidate = docs_dir / source_file
        if candidate.exists():
            self._open_file_in_reader(str(candidate))
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "File Not Found",
                                    f"Could not locate '{source_file}' in the project docs/ folder.")

    def _on_latex_pdf_ready(self, pdf_path: str) -> None:
        """Open a freshly compiled LaTeX PDF in the reader panel."""
        import os
        _log.info("pdf_ready received: path=%s exists=%s", pdf_path, os.path.exists(pdf_path))
        self._open_file_in_reader(pdf_path)

    def _open_file_in_reader(self, path: str) -> None:
        from pathlib import Path
        from kathoros.ui.panels.reader_panel import ReaderPanel
        from kathoros.ui.panels.editor_panel import EditorPanel

        docs_group = self._right_panel.findChild(DocumentsTabGroup)

        def _switch_docs(tab_index: int) -> None:
            if docs_group:
                outer = docs_group.parent()
                while outer and not isinstance(outer, QTabWidget):
                    outer = outer.parent()
                if outer:
                    for i in range(outer.count()):
                        if outer.tabText(i) == "Documents":
                            outer.setCurrentIndex(i)
                            break
                docs_group.setCurrentIndex(tab_index)

        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            reader = self.findChild(ReaderPanel)
            _log.info("opening PDF in reader: reader=%s path=%s", reader, path)
            if reader:
                reader.load_pdf(path)
                _switch_docs(0)   # Reader is tab 0
        else:
            editor = self.findChild(EditorPanel)
            if editor:
                try:
                    content = Path(path).read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    _log.warning("could not read %s: %s", path, exc)
                    return
                editor.load_content(content, filename=Path(path).name)
                _switch_docs(1)   # Editor is tab 1

    def _on_status_change_requested(self, object_id: int, new_status: str) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        result = self._pm.session_service.set_object_status(object_id, new_status)
        if not result["ok"]:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Status Change Failed",
                                result.get("error", "Unknown error"))
        self._load_objects()

    def _load_interactions(self) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        try:
            interactions = self._pm.session_service.get_interactions()
            panel = self.findChild(AuditLogPanel)
            if panel:
                panel.load_interactions(interactions)
        except Exception as exc:
            _log.warning("failed to load interactions: %s", exc)

    def _load_objects(self, panel=None) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        target = panel or self._objects_panel
        try:
            objects = self._pm.session_service.list_objects()
            target.load_objects(objects)
        except Exception as exc:
            _log.warning("failed to load objects: %s", exc)

    def _load_agents(self) -> None:
        if self._pm is None or self._pm.global_service is None:
            return
        try:
            agents = self._pm.global_service.list_agents()
            if hasattr(self, "_agent_manager"):
                self._agent_manager.load_agents(agents)
        except Exception as exc:
            _log.warning("failed to load agents: %s", exc)

    def _load_settings(self) -> None:
        if self._pm is None:
            return
        try:
            effective = self._pm.get_effective_settings()
            if hasattr(self, "_settings_panel"):
                self._settings_panel.load_settings(effective)
            # Seed the AI input panel access mode from settings (snapshot restores may override)
            mode = effective.get("default_access_mode", "REQUEST_FIRST")
            if hasattr(self, "_ai_input_panel"):
                self._ai_input_panel.set_access_mode(mode)
        except Exception as exc:
            _log.warning("failed to load settings: %s", exc)

    def _on_add_agent(self) -> None:
        from kathoros.ui.dialogs.agent_dialog import AgentDialog
        from PyQt6.QtWidgets import QMessageBox
        if self._pm is None or self._pm.global_service is None:
            return
        dialog = AgentDialog(parent=self)
        if dialog.exec() != AgentDialog.DialogCode.Accepted:
            return
        try:
            self._pm.global_service.insert_agent(**dialog.result_data)
            self._load_agents()
            self._load_agents_into_input()
        except Exception as exc:
            _log.error("failed to add agent: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _on_edit_agent(self, agent_id: int) -> None:
        from kathoros.ui.dialogs.agent_dialog import AgentDialog
        from PyQt6.QtWidgets import QMessageBox
        if self._pm is None or self._pm.global_service is None:
            return
        agent = self._pm.global_service.get_agent(agent_id)
        if agent is None:
            return
        dialog = AgentDialog(agent_data=agent, parent=self)
        if dialog.exec() != AgentDialog.DialogCode.Accepted:
            return
        try:
            self._pm.global_service.update_agent(agent_id, **dialog.result_data)
            self._load_agents()
            self._load_agents_into_input()
        except Exception as exc:
            _log.error("failed to update agent: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _on_delete_agent(self, agent_id: int) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if self._pm is None or self._pm.global_service is None:
            return
        agent = self._pm.global_service.get_agent(agent_id)
        if agent is None:
            return
        answer = QMessageBox.warning(
            self, "Delete Agent",
            f"Delete agent '{agent.get('name', agent_id)}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._pm.global_service.delete_agent(agent_id)
            self._load_agents()
            self._load_agents_into_input()
        except Exception as exc:
            _log.error("failed to delete agent: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _on_settings_changed(self, settings: dict, scope: str = "global") -> None:
        if self._pm is None:
            return
        try:
            if scope == "project":
                self._pm.set_project_settings(settings)
                _log.info("project settings saved")
            else:
                if self._pm.global_service:
                    self._pm.global_service.apply_settings(settings)
                _log.info("global settings saved")
            # Apply new access mode to AI panel and reinit tool service immediately
            mode = settings.get("default_access_mode")
            if mode and hasattr(self, "_ai_input_panel"):
                self._ai_input_panel.set_access_mode(mode)
            self._init_tool_service()
        except Exception as exc:
            _log.warning("failed to save settings: %s", exc)

    def _load_agents_into_input(self) -> None:
        if self._pm is None or self._pm.global_service is None:
            return
        try:
            agents = self._pm.global_service.list_agents()
            self._ai_input_panel.load_agents(agents)
        except Exception as exc:
            _log.warning("failed to load agents into input: %s", exc)

    def _wire_sqlite_explorer(self) -> None:
        if self._pm is None:
            return
        panel = self.findChild(SQLiteExplorerPanel)
        if panel is None:
            return
        if self._pm._project_conn is not None:
            panel.set_connection("project", self._pm._project_conn)
        if self._pm._global_conn is not None:
            panel.set_connection("global", self._pm._global_conn)

    def _wire_search_panel(self) -> None:
        if self._pm is None:
            return
        panel = self.findChild(CrossProjectSearchPanel)
        if panel is None:
            return
        panel.set_project_manager(self._pm)

    def _wire_git_panel(self) -> None:
        if self._pm is None or self._pm.project_root is None:
            return
        panel = self.findChild(GitPanel)
        if panel is None:
            return
        repo_path = self._pm.project_root / "repo"
        self._git_service = GitService(repo_path)

        # Disconnect any previous connections (safe on first call)
        try:
            panel.init_requested.disconnect()
            panel.stage_requested.disconnect()
            panel.commit_requested.disconnect()
            panel.suggest_requested.disconnect()
        except (RuntimeError, TypeError):
            pass

        panel.init_requested.connect(self._on_git_init)
        panel.stage_requested.connect(self._on_git_stage)
        panel.commit_requested.connect(self._on_git_commit)
        panel.suggest_requested.connect(self._on_git_suggest)
        panel.load_repo(str(repo_path))
        panel.update_status(self._git_service.get_status())

    def _wire_notes_panel(self) -> None:
        panel = self.findChild(NotesPanel)
        if panel is None or self._pm is None:
            return
        try:
            panel.note_create_requested.disconnect()
            panel.note_delete_requested.disconnect()
            panel.note_save_requested.disconnect()
        except (RuntimeError, TypeError):
            pass
        panel.note_create_requested.connect(self._on_note_create)
        panel.note_delete_requested.connect(self._on_note_delete)
        panel.note_save_requested.connect(self._on_note_save)
        panel.load_notes(self._pm.list_notes())

    def _wire_shell_panel(self) -> None:
        if self._pm is None or self._pm.project_root is None:
            return
        panel = self.findChild(ShellPanel)
        if panel:
            panel.set_cwd(str(self._pm.project_root))

    def _on_note_create(self) -> None:
        note = self._pm.create_note()
        panel = self.findChild(NotesPanel)
        if panel:
            panel.load_notes(self._pm.list_notes())
            panel.set_current_note(note)

    def _on_note_delete(self, ids: list) -> None:
        for nid in ids:
            self._pm.delete_note(nid)
        panel = self.findChild(NotesPanel)
        if panel:
            panel.load_notes(self._pm.list_notes())

    def _on_note_save(self, note_id: int, title: str, content: str, fmt: str) -> None:
        self._pm.save_note(note_id, title, content, fmt)
        panel = self.findChild(NotesPanel)
        if panel:
            panel.load_notes(self._pm.list_notes())
            # Load content for the currently displayed note if it changed
            cur_id = panel._current_note_id
            if cur_id is not None and cur_id != note_id and self._pm._project_conn is not None:
                row = self._pm._project_conn.execute(
                    "SELECT id, title, content, format FROM notes WHERE id = ?", (cur_id,)
                ).fetchone()
                if row:
                    panel.set_current_note(dict(row))

    def _on_export_notes(self, fmt: str) -> None:
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        panel = self.findChild(NotesPanel)
        if panel is None:
            return
        ids = panel.selected_note_ids()
        if not ids:
            QMessageBox.information(self, "No Selection", "Select one or more notes to export.")
            return
        notes = []
        for nid in ids:
            if self._pm._project_conn is None:
                continue
            row = self._pm._project_conn.execute(
                "SELECT id, title, content, format FROM notes WHERE id = ?", (nid,)
            ).fetchone()
            if row:
                notes.append(dict(row))
        ext = {"markdown": "md", "latex": "tex", "text": "txt"}[fmt]
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export Notes as {fmt.title()}", "", f"*.{ext}"
        )
        if not path:
            return
        Path(path).write_text(_build_export_body(notes, fmt), encoding="utf-8")
        _log.info("exported %d note(s) to %s", len(notes), path)

    def _on_message_submitted(self, text: str, agent_id: str, access_mode: str) -> None:
        _log.info("message submitted: agent=%s mode=%s", agent_id, access_mode)
        orig_text = text  # save before possible augmentation with file context
        self._ai_output_panel._in_stream = False
        if self._import_mode:
            names = ", ".join(p.split("/")[-1] for p in self._pending_import_paths)
            self._ai_output_panel.append_text(f"You: Analyze files: {names}", role="user")
        else:
            self._ai_output_panel.append_text(f"You: {text}", role="user")
        self._ai_output_panel._in_stream = False
        if self._pm is None or self._pm.global_service is None:
            return
        agent = self._pm.global_service.get_agent(int(agent_id))
        if agent is None:
            self._ai_output_panel.append_text("No agent found.", role="system")
            return
        # Persist user interaction to DB (skip import mode — file context is too large)
        if not self._import_mode and self._pm.session_service:
            try:
                self._pm.session_service.log_interaction(
                    int(agent_id) if agent_id else None, "user", orig_text
                )
            except Exception as exc:
                _log.warning("failed to log user interaction: %s", exc)
        # Inject pending import file contents if any
        pending = getattr(self, '_pending_import_paths', [])
        if not pending and hasattr(self, '_import_panel') and self._import_panel:
            pending = getattr(self._import_panel, '_pending_paths', [])
        _log.info("self id=%s pending paths: %s", id(self), pending)
        if pending:
            context = self._build_import_context(pending)
            _log.info("context length: %d chars", len(context))
            text = f"{context}\n\n{text}"
            self._pending_import_paths = []
            if hasattr(self, '_import_panel') and self._import_panel:
                self._import_panel._pending_paths = []
        nonce = self._pm.session_service.session_nonce if self._pm.session_service else ""
        self._ai_input_panel.set_busy(True)
        # Build dispatch context (import mode uses compact prompt, research uses rich context)
        if self._import_mode:
            dispatch_context = {"import_mode": True}
        else:
            ss = self._pm.session_service
            tool_desc = (
                self._tool_service.get_tool_descriptions()
                if self._tool_service else ""
            )
            # Fallback: use recent objects when researcher hasn't clicked anything
            recent_objects: list[dict] = []
            if not self._selected_objects and ss:
                try:
                    recent_objects = ss.list_objects(limit=5)
                except Exception:
                    pass
            dispatch_context = {
                "project_id":        self._pm._current_project_id,
                "project_name":      self._pm.project_name or "",
                "session_id":        ss._session_id if ss else "",
                "user_goal":         self._pm.get_effective_settings().get("user_goal", ""),
                "selected_objects":  self._selected_objects,
                "recent_objects":    recent_objects,
                "enforce_epistemic": True,
                "session_nonce":     nonce,
                "tool_descriptions": tool_desc,
            }
        self._dispatcher.dispatch(
            message=text,
            agent=agent,
            access_mode=access_mode,
            session_nonce=nonce,
            context=dispatch_context,
            on_chunk=lambda chunk: None if self._import_mode else self._ai_output_panel.append_text(chunk, role="assistant"),
            on_tool_request=self._on_tool_request,
            on_error=lambda msg: self._ai_output_panel.append_text(f"Error: {msg}", role="system"),
            on_done=lambda: self._on_agent_done(),
        )

    def _on_stop_requested(self) -> None:
        self._dispatcher.stop()
        self._ai_input_panel.set_busy(False)
        self._ai_output_panel.append_text("[stopped]", role="system")

    def _init_tool_service(self) -> None:
        if self._pm is None:
            return
        ss = self._pm.session_service
        nonce = ss.session_nonce if ss else ""
        mode = AccessMode[self._ai_input_panel.get_access_mode()]
        self._tool_service = ToolService(
            project_root=self._pm.project_root,
            session_nonce=nonce,
            session_id=str(ss._session_id if ss else ""),
            access_mode=mode,
            approval_callback=self._router_approval_callback,
        )
        _log.info("ToolService initialized")

    def _get_agent_effective_settings(self, agent_id: str) -> dict:
        """
        Return merged settings for a specific agent.
        Priority: global defaults → project overrides → per-agent fields.
        """
        effective = self._pm.get_effective_settings() if self._pm else {}
        if self._pm and self._pm.global_service and agent_id:
            try:
                agent = self._pm.global_service.get_agent(int(agent_id))
                if agent:
                    for key in ("require_tool_approval", "require_write_approval"):
                        val = agent.get(key)
                        if val is not None:
                            effective[key] = str(int(val))
            except (ValueError, TypeError):
                pass
        return effective

    def _router_approval_callback(self, req, tool) -> bool:
        """
        Called by the router at approval step (step 8).
        Consults per-agent safety toggles before showing the UI dialog.
        Auto-approves when the relevant toggle is off.
        """
        effective = self._get_agent_effective_settings(req.agent_id)

        if tool.write_capable:
            if effective.get("require_write_approval", "1") == "0":
                _log.info(
                    "auto-approved write tool %s for agent %s (require_write_approval=0)",
                    tool.name, req.agent_name,
                )
                return True
        else:
            if effective.get("require_tool_approval", "1") == "0":
                _log.info(
                    "auto-approved tool %s for agent %s (require_tool_approval=0)",
                    tool.name, req.agent_name,
                )
                return True

        access_mode = self._ai_input_panel.get_access_mode()
        approved, _ = request_approval(
            tool_name=tool.name,
            args=req.args,
            access_mode=access_mode,
            agent_name=req.agent_name,
            parent=self,
        )
        return approved

    def _wire_import_panel(self) -> None:
        if self._pm is None or self._pm.project_root is None:
            return
        panel = self._right_panel._docs_tab_group._import_panel
        if panel is None:
            _log.warning("import panel not found")
            return
        self._import_panel = panel
        docs_path = str(self._pm.project_root / "docs")
        panel.set_docs_path(docs_path)
        panel.import_requested.connect(lambda p: self._on_import_requested(p))
        _log.info("import panel wired id=%s", id(panel))


    def _on_git_init(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if self._git_service is None:
            return
        try:
            self._git_service.ensure_repo()
            panel = self.findChild(GitPanel)
            if panel:
                panel.load_repo(str(self._pm.project_root / "repo"))
                panel.update_status(self._git_service.get_status())
        except Exception as exc:
            _log.error("git init failed: %s", exc)
            QMessageBox.critical(self, "Git Init Failed", str(exc))

    def _on_git_stage(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if self._git_service is None or self._pm is None:
            return
        try:
            # Export all committed objects before staging
            objects = self._pm.list_committed_objects()
            self._git_service.export_objects(objects)
            count = self._git_service.stage_all()
            panel = self.findChild(GitPanel)
            if panel:
                panel.update_status(self._git_service.get_status())
            _log.info("staged %d item(s)", count)
        except Exception as exc:
            _log.error("git stage failed: %s", exc)
            QMessageBox.critical(self, "Stage Failed", str(exc))

    def _on_git_commit(self, message: str) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if self._git_service is None:
            return
        # Respect require_git_confirm setting
        effective = self._pm.get_effective_settings() if self._pm else {}
        if effective.get("require_git_confirm", "1") == "1":
            answer = QMessageBox.question(
                self, "Confirm Commit",
                f"Commit with message:\n\n\"{message}\"",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            sha = self._git_service.commit(message)
            panel = self.findChild(GitPanel)
            if panel:
                panel.load_repo(str(self._pm.project_root / "repo"))
                panel.update_status(self._git_service.get_status())
                panel.set_suggested_message("")
            self._ai_output_panel.append_text(
                f"[git] committed {sha} — {message}", role="system"
            )
        except Exception as exc:
            _log.error("git commit failed: %s", exc)
            QMessageBox.critical(self, "Commit Failed", str(exc))

    def _on_git_suggest(self) -> None:
        if self._git_service is None or self._pm is None:
            return
        try:
            objects = self._pm.list_committed_objects()
            message = self._git_service.suggest_message(objects)
            panel = self.findChild(GitPanel)
            if panel:
                panel.set_suggested_message(message)
        except Exception as exc:
            _log.warning("suggest message failed: %s", exc)

    def _build_import_context(self, paths: list) -> str:
        sections = []
        for p in paths:
            try:
                content = open(p).read(8192)
                name = p.split('/')[-1]
                sections.append(f'--- {name} ---\n{content}')
            except Exception as exc:
                sections.append(f'--- {p} --- (unreadable: {exc})')
        return '\n\n'.join(sections)

    def _on_import_requested(self, paths: list) -> None:
        _log.info("ON_IMPORT self id=%s paths=%s", id(self), paths)
        if not paths:
            return
        self._pending_import_paths = paths

        from pathlib import Path
        json_paths    = [p for p in paths if Path(p).suffix.lower() == ".json"]
        content_paths = [p for p in paths if Path(p).suffix.lower() != ".json"]

        # JSON files are already in import format — skip AI, go straight to approval
        if json_paths and not content_paths:
            self._import_json_directly(json_paths)
            return

        # Content files (pdf, md, tex, py) — read text and send to AI
        self._import_mode = True
        blocks = []
        for p in content_paths:
            try:
                text = _read_file_text(p)
                blocks.append(f"=== {Path(p).name} ===\n{text}")
            except Exception as exc:
                _log.warning("could not read %s: %s", p, exc)

        if blocks:
            prompt = (
                "Extract and structure research objects from the following content.\n"
                "Respond with ONLY a valid JSON array. Each element must include:\n"
                "  name         — short title of the concept, theorem, or result\n"
                "  type         — one of: concept, definition, derivation, prediction, evidence, open_question, data\n"
                "  description  — plain-text summary (1-3 sentences)\n"
                "  latex        — verbatim LaTeX source for the primary equation, theorem, or formula (copy exactly from source; empty string if none)\n"
                "  math_expression — ASCII/Unicode representation of the key formula (empty string if none)\n"
                "  researcher_notes — caveats, open questions, or context (empty string if none)\n"
                "  tags         — list of keyword strings\n"
                "  depends_on   — list of names of other objects in this batch that this one logically depends on\n"
                "  source_file  — original filename\n\n"
                "For .tex files: always populate the latex field by copying the relevant equation or theorem environment verbatim.\n"
                "For .py files: extract simulation models, algorithms, and numerical results as data/evidence/derivation objects; include key formulas or parameter definitions in math_expression.\n"
                "For .txt files: extract claims, observations, and conclusions as concept/evidence/open_question objects.\n\n"
                + "\n\n".join(blocks)
            )
        else:
            names = ", ".join(Path(p).name for p in paths)
            prompt = f"Analyze and suggest research objects for: {names}"

        self._ai_input_panel._input.setPlainText(prompt)
        self._ai_input_panel._input.setFocus()

    def _import_json_directly(self, paths: list) -> None:
        """Parse pre-formatted JSON import files without going through the AI."""
        from pathlib import Path
        from kathoros.agents.import_parser import parse_object_suggestions
        suggestions = []
        for p in paths:
            try:
                text = Path(p).read_text(encoding="utf-8")
                parsed = parse_object_suggestions(text)
                fname = Path(p).name
                for obj in parsed:
                    if not obj.get("source_file"):
                        obj["source_file"] = fname
                suggestions.extend(parsed)
                _log.info("parsed %d objects from %s", len(parsed), fname)
            except Exception as exc:
                _log.warning("failed to parse JSON import %s: %s", p, exc)

        if not suggestions:
            self._ai_output_panel.append_text(
                "[No valid objects found in selected JSON files]", role="system"
            )
            return

        dialog = ImportApprovalDialog(suggestions, parent=self)
        if dialog.exec() != ImportApprovalDialog.DialogCode.Accepted:
            return
        approved = dialog.results
        if approved:
            self._write_objects_to_db(approved)

    def _on_tool_request(self, req: dict) -> None:
        if self._import_mode:
            return
        if self._tool_service is None:
            _log.warning("tool request received but ToolService not initialized")
            return
        tool_name = req.get("tool_name", "?")
        args = req.get("args", {})
        detected_via = req.get("detected_via", "none")
        enveloped = req.get("enveloped", False)

        self._ai_output_panel.append_tool_request(tool_name, str(args))

        # Resolve agent context from current selection
        agent_id_str = self._ai_input_panel.get_selected_agent_id() or ""
        agent_name = ""
        trust_level = TrustLevel.MONITORED
        if self._pm and self._pm.global_service and agent_id_str:
            agent = self._pm.global_service.get_agent(int(agent_id_str))
            if agent:
                agent_name = agent.get("name", "")
                trust_level = TrustLevel[agent.get("trust_level", "MONITORED").upper()]
        nonce = self._pm.session_service.session_nonce if (
            self._pm and self._pm.session_service
        ) else ""

        # Router handles validation + approval (callback) + execution
        result = self._tool_service.handle(
            tool_name=tool_name,
            args=args,
            agent_id=agent_id_str,
            agent_name=agent_name,
            trust_level=trust_level,
            nonce=nonce,
            detected_via=detected_via,
            enveloped=enveloped,
        )

        if result.decision == Decision.APPROVED:
            _log.info("tool executed: %s", tool_name)
            self._ai_output_panel.append_text(
                f"[tool result] {tool_name}: {result.output}", role="system"
            )
        else:
            _log.info("tool rejected: %s errors=%s", tool_name, result.validation_errors)
            self._ai_output_panel.append_text(
                f"[tool rejected] {tool_name}: {'; '.join(result.validation_errors)}",
                role="system",
            )

    def _on_agent_done(self) -> None:
        _log.info("agent done import_mode=%s", self._import_mode)
        self._ai_input_panel.set_busy(False)
        self._save_session_snapshot()
        # Persist assistant response to DB (skip import mode — handled by import flow)
        if not self._import_mode and self._pm and self._pm.session_service:
            history = self._dispatcher._history
            if history and history[-1].get("role") == "assistant":
                content = history[-1].get("content", "")
                agent_id_str = self._ai_input_panel.get_selected_agent_id() or ""
                if content:
                    try:
                        self._pm.session_service.log_interaction(
                            int(agent_id_str) if agent_id_str else None,
                            "assistant", content,
                        )
                    except Exception as exc:
                        _log.warning("failed to log assistant interaction: %s", exc)
            return
        _log.info("checking history len=%d", len(self._dispatcher._history))
        for i, h in enumerate(self._dispatcher._history):
            _log.info("history[%d] role=%s len=%d", i, h.get('role'), len(h.get('content','')))
        self._import_mode = False
        # Get full response from dispatcher history
        history = self._dispatcher._history
        if not history:
            return
        last = history[-1]
        if last.get("role") != "assistant":
            return
        content = last.get("content", "")
        _log.info("last role=%s content_len=%d preview=%s", last.get('role'), len(content), repr(content[:100]))
        suggestions = parse_object_suggestions(content)
        _log.info("parsed %d suggestions", len(suggestions))
        if not suggestions:
            self._ai_output_panel.append_text(
                "[No structured objects found in response]", role="system"
            )
            return
        # Backfill source_file for objects that didn't get one from the AI
        import_names = [p.split("/")[-1] for p in (self._pending_import_paths or [])]
        fallback_source = ", ".join(import_names) if import_names else ""
        for s in suggestions:
            if not s.get("source_file") and fallback_source:
                s["source_file"] = fallback_source
        dialog = ImportApprovalDialog(suggestions, parent=self)
        if dialog.exec() != ImportApprovalDialog.DialogCode.Accepted:
            return
        approved = dialog.results
        if not approved:
            return
        self._write_objects_to_db(approved)

    def _write_objects_to_db(self, objects: list[dict]) -> None:
        ss = self._pm.session_service if self._pm else None
        if ss is None:
            _log.warning("no session service — cannot write objects")
            return
        try:
            count = ss.insert_objects(objects)
        except ValueError as exc:
            # Circular dependency — surface the full explanation to the researcher
            _log.error("import rejected: %s", exc)
            self._ai_output_panel.append_text(str(exc), role="system")
            return
        self._ai_output_panel.append_text(
            f"[{count} objects written to project DB]", role="system"
        )
        _log.info("wrote %d objects to DB", count)
        self._save_session_snapshot()
        self._load_objects()

    def _build_snapshot(self) -> dict:
        snap: dict = {"version": 1}
        snap["agent"] = {
            "selected_agent_id": self._ai_input_panel.get_selected_agent_id(),
            "access_mode": self._ai_input_panel.get_access_mode(),
        }
        right_tab = self._right_panel.findChild(QTabWidget)
        docs_tab = self._right_panel.findChild(DocumentsTabGroup)
        snap["ui"] = {
            "right_tab": right_tab.currentIndex() if right_tab else 0,
            "documents_tab": docs_tab.currentIndex() if docs_tab else 0,
        }
        return snap

    def _save_session_snapshot(self) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        try:
            self._pm.save_state(self._build_snapshot())
        except Exception as exc:
            _log.warning("failed to save session snapshot: %s", exc)

    def _restore_session_snapshot(self) -> None:
        if self._pm is None or self._pm.session_service is None:
            return
        snap = self._pm.session_service.get_snapshot()
        if not snap:
            return
        agent_snap = snap.get("agent", {})
        if agent_snap.get("selected_agent_id") is not None:
            self._ai_input_panel.set_selected_agent_id(agent_snap["selected_agent_id"])
        if agent_snap.get("access_mode"):
            self._ai_input_panel.set_access_mode(agent_snap["access_mode"])
        ui_snap = snap.get("ui", {})
        right_tab = self._right_panel.findChild(QTabWidget)
        if right_tab and "right_tab" in ui_snap:
            right_tab.setCurrentIndex(ui_snap["right_tab"])
        docs_tab = self._right_panel.findChild(DocumentsTabGroup)
        if docs_tab and "documents_tab" in ui_snap:
            docs_tab.setCurrentIndex(ui_snap["documents_tab"])

    def _restore_conversation_history(self) -> None:
        """Replay persisted interactions into output panel and dispatcher history."""
        if self._pm is None or self._pm.session_service is None:
            return
        try:
            interactions = self._pm.session_service.get_interactions(limit=100)
        except Exception as exc:
            _log.warning("failed to load interactions for restore: %s", exc)
            return
        if not interactions:
            return
        self._ai_output_panel.clear()
        for row in interactions:
            role = row.get("role", "assistant")
            content = row.get("content", "")
            self._ai_output_panel._in_stream = False
            self._ai_output_panel.append_text(content, role=role)
            self._dispatcher._history.append({"role": role, "content": content})
