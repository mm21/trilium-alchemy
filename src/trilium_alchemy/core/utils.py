"""
Common utilities.
"""

import hashlib
from functools import cache

__all__ = [
    "TEMPLATE_RELATIONS",
    "INHERIT_RELATIONS",
    "base_n_hash",
]

TEMPLATE_RELATIONS = [
    "template",
    "workspaceTemplate",
]
"""
List of relations defining templates.
"""

INHERIT_RELATIONS = TEMPLATE_RELATIONS + ["inherit"]
"""
List of relations entailing inheritance.
"""


def base_n_hash(data: bytes, chars: str) -> str:
    """
    Hash data using SHAKE-128 and encode as a base-N string, where N is
    len(chars).
    """
    assert len(chars)

    # get hash value as a large integer
    digest = hashlib.shake_128(data).digest(16)
    int_digest = int.from_bytes(digest)

    # consume hash value and generate result
    result = ""
    while int_digest:
        int_digest, index = divmod(int_digest, len(chars))
        result += chars[index]

    # get max possible length of result for this base
    max_len = _get_max_len(128, len(chars))

    # pad result to max length
    return result.ljust(max_len, "0")


@cache
def _get_max_len(bit_count: int, char_count: int) -> int:
    """
    Get max length of the resulting hash for the given # bits and # characters
    used to represent it.
    """
    max_digest = (1 << bit_count) - 1
    max_len = 0
    while max_digest:
        max_digest = max_digest // char_count
        max_len += 1
    return max_len
