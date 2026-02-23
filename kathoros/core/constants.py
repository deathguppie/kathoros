# kathoros/core/constants.py
"""
Project-wide constants.
Do not import from router or ui here — this is a leaf module.
"""

APP_NAME = "Kathoros"
APP_VERSION = "0.1.0"
LICENSE = "GPL-3.0"

# Security
DEFAULT_ACCESS_MODE = "REQUEST_FIRST"
DEFAULT_TRUST_LEVEL = "MONITORED"
MAX_SNAPSHOT_SIZE_BYTES = 1_048_576  # 1MB hard cap
MAX_RUN_ID_LENGTH = 64
MIN_RUN_ID_LENGTH = 8
RUN_ID_PATTERN = r"^[a-zA-Z0-9_\-]{8,64}$"
RAW_ARGS_HASH_LENGTH = 64  # SHA256 hex digest

# Paths (relative to project root — never absolute)
ARTIFACTS_DIR = "artifacts"
OVERSIZED_DIR = "artifacts/oversized"
MANIFESTS_DIR = "manifests"
DOCS_DIR = "docs"
EXPORTS_DIR = "exports"

# DB
GLOBAL_DB_NAME = "global.db"
PROJECT_DB_NAME = "project.db"
