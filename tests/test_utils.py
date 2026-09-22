from app.core.utils import build_namespace, build_thread_id, mask_phone_number, normalize_phone_number
from app.rag.prompts import DEFAULT_SYSTEM_PROMPT, resolve_system_prompt


def test_build_thread_id_normalizes_phone_and_keeps_business_uuid() -> None:
    assert build_thread_id("+91 9876543210", "abc") == "919876543210:abc"


def test_build_thread_id_separates_businesses() -> None:
    phone = "+919876543210"
    assert build_thread_id(phone, "businessA") != build_thread_id(phone, "businessB")


def test_normalize_phone_number_strips_non_digits() -> None:
    assert normalize_phone_number("+91-98765-43210") == "919876543210"


def test_mask_phone_number_hides_prefix() -> None:
    assert mask_phone_number("+919876543210") == "***3210"


def test_build_namespace_is_pinecone_safe() -> None:
    namespace = build_namespace("550e8400-e29b-41d4-a716-446655440000", 3)
    assert namespace == "550e8400-e29b-41d4-a716-446655440000--v3"
    assert ":" not in namespace


def test_resolve_system_prompt_uses_custom_or_default() -> None:
    assert resolve_system_prompt("  Be a concise shop assistant.  ") == "Be a concise shop assistant."
    assert resolve_system_prompt("") == DEFAULT_SYSTEM_PROMPT
    assert resolve_system_prompt(None) == DEFAULT_SYSTEM_PROMPT
