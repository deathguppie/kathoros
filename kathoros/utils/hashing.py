# kathoros/utils/hashing.py
"""
Canonical hashing utilities.
raw_args_hash: SHA256 of sorted JSON — always 64 hex characters.
Never log raw args — only their hash.
"""
import hashlib
import json


def hash_args(args: dict) -> str:
    """
    Compute SHA256 hash of args dict (sorted keys, compact JSON).
    Returns 64-character hex string.
    Must never be called with raw API keys or secrets.
    """
    serialized = json.dumps(args, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert len(digest) == 64, f"Hash length invariant violated: {len(digest)}"
    return digest
