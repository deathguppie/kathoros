"""
KeyStore — secure API key storage.
Keys stored as individual files in ~/.kathoros/config/api_keys/
Directory: chmod 700. Files: chmod 600.
Keys never logged, never stored in DB, never in snapshots.
"""
import logging
import os
import re
import stat
from pathlib import Path

_log = logging.getLogger("kathoros.config.key_store")

_KEYS_DIR = Path.home() / ".kathoros" / "config" / "api_keys"
_SAFE_PROVIDER = re.compile(r"^[\w\-]+$")


def _ensure_dir() -> None:
    _KEYS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(_KEYS_DIR, stat.S_IRWXU)  # 700


def _safe_path(provider: str) -> Path:
    """Return validated key file path. Raises ValueError on bad provider name."""
    if not _SAFE_PROVIDER.match(provider):
        raise ValueError(f"Invalid provider name: {provider!r}")
    path = (_KEYS_DIR / f"{provider}.key").resolve()
    if not str(path).startswith(str(_KEYS_DIR.resolve())):
        raise ValueError(f"Path traversal blocked for provider: {provider!r}")
    return path


def save_key(provider: str, key: str) -> None:
    """Save API key for provider. File permissions set to 600."""
    _ensure_dir()
    path = _safe_path(provider)
    path.write_text(key.strip())
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
    _log.info("key saved for provider: %s", provider)


def load_key(provider: str) -> str | None:
    """Load API key for provider. Returns None if not found."""
    try:
        path = _safe_path(provider)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        return path.read_text().strip() or None
    except Exception as exc:
        _log.warning("failed to read key for %s: %s", provider, exc)
        return None


def delete_key(provider: str) -> None:
    """Delete stored key for provider."""
    try:
        path = _safe_path(provider)
    except ValueError:
        return
    if path.exists():
        path.unlink()
        _log.info("key deleted for provider: %s", provider)


def key_exists(provider: str) -> bool:
    """Return True if a key file exists and is non-empty."""
    return load_key(provider) is not None


def masked(provider: str) -> str:
    """Return masked display string e.g. 'sk-...xxxx' or 'Not set'."""
    key = load_key(provider)
    if not key:
        return "Not set"
    return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"
