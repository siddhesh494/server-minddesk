"""Shared helpers for tenant identifiers, phones, and log-safe masking."""

from __future__ import annotations

import hashlib
import re
from uuid import UUID


PHONE_DIGITS_RE = re.compile(r"\D+")


def normalize_phone_number(phone: str) -> str:
    """Keep digits only so +91 9876543210 and 919876543210 share a thread."""
    return PHONE_DIGITS_RE.sub("", phone or "")


def build_thread_id(phone: str, business_uuid: str) -> str:
    """Conversation memory key: normalized phone + business UUID.

    The same customer talking to two businesses must never share history.
    """
    return f"{normalize_phone_number(phone)}:{business_uuid}"


def build_namespace(business_uuid: str, version: int) -> str:
    """Pinecone-safe namespace for a business version.

    Logical form in the product spec is '{uuid}::v{version}'. Pinecone
    namespace names do not allow colons, so the stored namespace uses '--'.
    """
    return f"{business_uuid}--v{version}"


def build_vector_id(business_uuid: str, version: int, chunk_index: int) -> str:
    return f"{business_uuid}:v{version}:chunk:{chunk_index}"


def parse_uuid(value: str) -> str:
    return str(UUID(str(value)))


def mask_phone_number(phone: str) -> str:
    digits = normalize_phone_number(phone)
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def normalize_business_text(text: str) -> str:
    collapsed = re.sub(r"[ \t]+", " ", text or "")
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()
