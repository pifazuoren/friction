"""Read structured model replies, including commitments in incomplete JSON."""

import json
import re


def response_fields(text: str) -> tuple[dict, dict, bool]:
    """Find top-level fields even after malformed scalars. Skip all nested evidence."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    fields, partial = {}, {}
    if start < 0:
        return fields, partial, False
    depth = 1
    want_key = True
    seen = set()
    index = start + 1
    while index < len(text) and depth:
        char = text[index]
        if char == '"':
            try:
                token, end = decoder.raw_decode(text, index)
            except ValueError:
                break
            if depth == 1 and want_key:
                rest = text[end:].lstrip()
                if rest.startswith(":"):
                    if token in seen:
                        return fields, partial, True
                    seen.add(token)
                    rest = rest[1:].lstrip()
                    try:
                        fields[token], _ = decoder.raw_decode(rest)
                    except ValueError:
                        partial[token] = rest
                    want_key = False
            index = end
            continue
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 1:
            want_key = True
        index += 1
    return fields, partial, False


def parse_compact_reply(text: str) -> dict | None:
    """Accept one complete object, allowing an outer Markdown fence but no duplicate fields."""
    content = text.strip()
    fence = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE
    )
    if fence:
        content = fence[1]

    def unique_fields(pairs):
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("duplicate JSON object field")
        return fields

    try:
        obj = json.loads(content, object_pairs_hook=unique_fields)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None
