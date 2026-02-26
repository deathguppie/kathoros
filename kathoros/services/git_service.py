"""
GitService — GitPython wrapper for project repo operations.
Owns nothing outside the repo/ directory.
No DB access — caller provides objects as plain dicts.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

_log = logging.getLogger("kathoros.services.git_service")

_SAFE_NAME_RE = re.compile(r"[^\w\-]")


def _safe_fname(name: str, max_len: int = 48) -> str:
    return _SAFE_NAME_RE.sub("_", name)[:max_len].strip("_") or "object"


class GitService:
    """
    Wraps GitPython for project git operations.
    All paths are constrained to repo_path.
    """

    def __init__(self, repo_path: Path) -> None:
        self._repo_path = repo_path

    # ------------------------------------------------------------------
    # Repo lifecycle
    # ------------------------------------------------------------------

    def is_initialized(self) -> bool:
        return (self._repo_path / ".git").exists()

    def ensure_repo(self) -> None:
        """Initialize git repo if not already present."""
        if self.is_initialized():
            return
        self._repo_path.mkdir(parents=True, exist_ok=True)
        from git import Repo
        Repo.init(str(self._repo_path))
        _log.info("git repo initialized at %s", self._repo_path)

    def _get_repo(self):
        from git import InvalidGitRepositoryError, Repo
        try:
            return Repo(str(self._repo_path))
        except InvalidGitRepositoryError:
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """
        Return a status dict suitable for display.
        Returns {"initialized": False} if no repo.
        """
        repo = self._get_repo()
        if repo is None:
            return {"initialized": False, "branch": "—", "modified": 0,
                    "untracked": 0, "staged": 0}

        try:
            branch = repo.active_branch.name
        except TypeError:
            branch = "(detached)"

        # Staged count: diffs against HEAD (or all index entries if empty)
        try:
            staged = len(repo.index.diff("HEAD"))
        except Exception:
            staged = len(list(repo.index.entries))

        modified = len(repo.index.diff(None))
        untracked = len(repo.untracked_files)

        return {
            "initialized": True,
            "branch": branch,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "is_dirty": repo.is_dirty(untracked_files=True),
        }

    # ------------------------------------------------------------------
    # Object export
    # ------------------------------------------------------------------

    def export_objects(self, objects: list[dict]) -> list[str]:
        """
        Write committed objects as JSON files to repo/objects/.
        Returns list of relative paths written.
        Objects with large content fields have them truncated to keep
        git diffs readable.
        """
        if not objects:
            return []
        objects_dir = self._repo_path / "objects"
        objects_dir.mkdir(exist_ok=True)

        written = []
        for obj in objects:
            obj_id = obj.get("id", 0)
            name = _safe_fname(obj.get("name") or "object")
            fname = f"{obj_id:06d}_{name}.json"
            fpath = objects_dir / fname

            # Exclude source_conversation_ref (can be very long)
            record = {k: v for k, v in obj.items() if k != "source_conversation_ref"}
            fpath.write_text(
                json.dumps(record, indent=2, default=str), encoding="utf-8"
            )
            rel = str(fpath.relative_to(self._repo_path))
            written.append(rel)

        _log.info("exported %d objects to %s", len(written), objects_dir)
        return written

    # ------------------------------------------------------------------
    # Staging and commit
    # ------------------------------------------------------------------

    def stage_all(self) -> int:
        """
        git add -A inside repo_path.
        Returns number of staged changes.
        """
        repo = self._get_repo()
        if repo is None:
            raise RuntimeError("No git repository — call ensure_repo() first.")
        repo.git.add(A=True)
        try:
            count = len(repo.index.diff("HEAD"))
        except Exception:
            count = len(list(repo.index.entries))
        _log.info("staged %d item(s)", count)
        return count

    def commit(self, message: str) -> str:
        """
        git commit with message.
        Returns the short SHA (7 chars) of the new commit.
        """
        repo = self._get_repo()
        if repo is None:
            raise RuntimeError("No git repository — call ensure_repo() first.")

        # Resolve author from git config with fallback
        try:
            author_name = repo.config_reader().get_value("user", "name", "Kathoros Researcher")
            author_email = repo.config_reader().get_value("user", "email", "researcher@kathoros.local")
        except Exception:
            author_name = "Kathoros Researcher"
            author_email = "researcher@kathoros.local"

        from git import Actor
        author = Actor(author_name, author_email)
        c = repo.index.commit(message, author=author, committer=author)
        sha = c.hexsha[:7]
        _log.info("committed: %s — %s", sha, message[:60])
        return sha

    # ------------------------------------------------------------------
    # Message suggestion
    # ------------------------------------------------------------------

    def suggest_message(self, objects: list[dict]) -> str:
        """Generate a commit message from committed object names."""
        if not objects:
            return "Update project"
        names = [o.get("name") or "object" for o in objects[:5]]
        suffix = f", and {len(objects) - 5} more" if len(objects) > 5 else ""
        label = "objects" if len(objects) != 1 else "object"
        return f"Commit {len(objects)} {label}: {', '.join(names)}{suffix}"
