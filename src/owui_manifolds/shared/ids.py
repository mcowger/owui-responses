"""Stable short IDs used for hidden Open WebUI persistence references."""

from __future__ import annotations

import secrets

ULID_LENGTH = 16
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(ULID_LENGTH))


__all__ = ["CROCKFORD_ALPHABET", "ULID_LENGTH", "generate_ulid"]

