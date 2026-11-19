"""Region-bound address equivalence for the resolved member identity."""

import re
import unicodedata


def compact(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def member_address_matches(roster_address, member_address, region):
    """Allow only known administrative prefixes of the resolved roster region."""
    prefixes = {
        "울진": (("경상북도", "경북"), ("울진군",)),
        "영덕": (("경상북도", "경북"), ("영덕군",)),
        "광명": (("경기도", "경기"), ("광명시",)),
    }
    if region not in prefixes or not all(
        isinstance(v, str) and v.strip() for v in (roster_address, member_address)
    ):
        return False

    def canonical(value):
        value = unicodedata.normalize("NFKC", value).strip()
        for choices in prefixes[region]:
            value = re.sub(
                r"^(?:" + "|".join(map(re.escape, choices)) + r")\s+",
                "",
                value,
                count=1,
            )
        return compact(value)

    return bool(canonical(roster_address)) and canonical(roster_address) == canonical(
        member_address
    )
