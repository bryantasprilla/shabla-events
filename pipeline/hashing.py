"""Content hashing for change detection (Milestone 5)."""
import hashlib


def content_hash(title: str, body: str) -> str:
    normalized = (title or "").strip().lower() + "\n" + (body or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
