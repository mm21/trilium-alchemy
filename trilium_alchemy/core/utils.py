"""
Common utilities.
"""

import hashlib

__all__ = [
    "base_n_hash",
]


# TODO: consider using this for id_hash() as it gives a true "base62"
# which preserves entropy of SHA-256 digest
# - base_n_hash(seed.encode("utf-8"), string.ascii_letters + string.digits)
def base_n_hash(data: bytes, digits: str) -> str:
    """
    Hash data using SHA-256 and encode as a base-N string, where N is
    len(digits).
    """
    assert len(digits)

    # get hash value as a large integer
    hex_digest = hashlib.sha256(data).hexdigest()
    int_digest = int(hex_digest, 16)
    max_digest = (1 << 256) - 1

    # consume hash value and generate result
    result = ""
    while int_digest:
        int_digest, index = divmod(int_digest, len(digits))
        result += digits[index]

    # get max possible length of result for this base
    max_len = 0
    while max_digest:
        max_digest = max_digest // len(digits)
        max_len += 1

    # pad result to max length
    return result.ljust(max_len, "0")
