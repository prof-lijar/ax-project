"""Find appended transcript text without interpreting pixels or replaying old history."""

from app.models import AgentError


def appended_text(before, after):
    if after == before:
        return ""
    if after.startswith(before):
        return after[len(before) :].strip()
    if before.endswith(after):
        return ""  # Only older text was trimmed from the accessible view.
    old, new = before.splitlines(), after.splitlines()
    # Accessible views can drop older lines as new messages arrive.
    for count in range(min(len(old), len(new)), 0, -1):
        if old[-count:] == new[:count]:
            return "\n".join(new[count:]).strip()
    raise AgentError(
        "Conversation text changed without a verifiable append; keep the latest messages visible and restart Run Agent (auto)"
    )
