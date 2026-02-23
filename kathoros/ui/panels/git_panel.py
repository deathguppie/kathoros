"""
GitPanel — git log viewer + stage/commit workflow for current project repo.
No DB calls. Signals to main window for all actions.
"""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QMessageBox
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont

_log = logging.getLogger("kathoros.ui.panels.git_panel")


class GitPanel(QWidget):
    # Emitted when user clicks Refresh
    refresh_requested = pyqtSignal()
    # Emitted when user clicks Init Repo
    init_requested = pyqtSignal()
    # Emitted when user clicks Stage All
    stage_requested = pyqtSignal()
    # Emitted when user clicks Commit (carries the message text)
    commit_requested = pyqtSignal(str)
    # Emitted when user clicks Suggest to get an AI-generated message
    suggest_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._repo_path = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row: branch label + status + refresh
        header_row = QHBoxLayout()
        self._branch_label = QLabel("Branch: —")
        self._branch_label.setStyleSheet("font-weight: bold; padding: 2px 4px;")
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888888; padding: 2px 4px;")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(70)
        refresh_btn.clicked.connect(self._on_refresh)
        header_row.addWidget(self._branch_label)
        header_row.addWidget(self._status_label)
        header_row.addStretch()
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Commit log
        self._list = QListWidget()
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self._list.setFont(font)
        self._list.setStyleSheet(
            "QListWidget { background: #1e1e1e; border: 1px solid #333; }"
            "QListWidget::item { min-height: 24px; padding: 2px 4px; color: #cccccc; }"
            "QListWidget::item:selected { background: #3d3d3d; }"
        )
        layout.addWidget(self._list, stretch=1)

        # Commit message row
        msg_row = QHBoxLayout()
        self._message_input = QLineEdit()
        self._message_input.setPlaceholderText("Commit message...")
        self._message_input.returnPressed.connect(self._on_commit)
        suggest_btn = QPushButton("Suggest")
        suggest_btn.setFixedWidth(62)
        suggest_btn.setToolTip("Generate message from committed objects")
        suggest_btn.clicked.connect(self.suggest_requested)
        msg_row.addWidget(self._message_input)
        msg_row.addWidget(suggest_btn)
        layout.addLayout(msg_row)

        # Action buttons row
        btn_row = QHBoxLayout()
        self._init_btn = QPushButton("Init Repo")
        self._init_btn.setToolTip("Initialize a git repository in the project repo/ directory")
        self._init_btn.clicked.connect(self.init_requested)
        self._stage_btn = QPushButton("Stage All")
        self._stage_btn.setToolTip("Export committed objects and run git add -A")
        self._stage_btn.clicked.connect(self.stage_requested)
        self._commit_btn = QPushButton("Commit")
        self._commit_btn.setToolTip("Commit staged changes with the message above")
        self._commit_btn.clicked.connect(self._on_commit)
        self._commit_btn.setStyleSheet("QPushButton { font-weight: bold; }")

        btn_row.addWidget(self._init_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._stage_btn)
        btn_row.addWidget(self._commit_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public interface called by main_window
    # ------------------------------------------------------------------

    def load_repo(self, repo_path: str) -> None:
        self._repo_path = repo_path
        self._reload_log()

    def update_status(self, status: dict) -> None:
        """
        Refresh status display from a dict returned by GitService.get_status().
        """
        initialized = status.get("initialized", False)
        self._init_btn.setVisible(not initialized)
        self._stage_btn.setEnabled(initialized)
        self._commit_btn.setEnabled(initialized)

        if not initialized:
            self._branch_label.setText("Branch: —")
            self._status_label.setText("No repository")
            return

        branch = status.get("branch", "?")
        self._branch_label.setText(f"Branch: {branch}")

        staged = status.get("staged", 0)
        modified = status.get("modified", 0)
        untracked = status.get("untracked", 0)
        parts = []
        if staged:
            parts.append(f"{staged} staged")
        if modified:
            parts.append(f"{modified} modified")
        if untracked:
            parts.append(f"{untracked} untracked")
        self._status_label.setText(" | ".join(parts) if parts else "clean")

    def set_suggested_message(self, message: str) -> None:
        """Called by main_window after generating a suggested commit message."""
        self._message_input.setText(message)
        self._message_input.setFocus()

    def clear(self) -> None:
        self._list.clear()
        self._branch_label.setText("Branch: —")
        self._status_label.setText("")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_refresh(self) -> None:
        if self._repo_path:
            self._reload_log()
        self.refresh_requested.emit()

    def _on_commit(self) -> None:
        msg = self._message_input.text().strip()
        if not msg:
            QMessageBox.warning(self, "No Message", "Enter a commit message first.")
            return
        self.commit_requested.emit(msg)

    def _reload_log(self) -> None:
        self._list.clear()
        if not self._repo_path:
            return
        try:
            from git import Repo, InvalidGitRepositoryError
            repo = Repo(self._repo_path)
            try:
                self._branch_label.setText(f"Branch: {repo.active_branch.name}")
            except TypeError:
                self._branch_label.setText("Branch: (detached)")
            for commit in repo.iter_commits(max_count=200):
                item = QListWidgetItem(self._format_commit(commit))
                self._list.addItem(item)
            if self._list.count() == 0:
                self._list.addItem("No commits yet")
        except Exception as exc:
            self._list.addItem("No repository found")
            _log.debug("git reload: %s", exc)

    @staticmethod
    def _format_commit(commit) -> str:
        msg = commit.message.splitlines()[0][:60]
        date = commit.authored_datetime.strftime("%Y-%m-%d %H:%M")
        return f"{commit.hexsha[:7]}  {date}  {commit.author.name:<14}  {msg}"
