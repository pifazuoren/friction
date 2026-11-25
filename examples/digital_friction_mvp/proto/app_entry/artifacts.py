from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CALIBRATION_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_MAPPING_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_TASK_OCCURRENCE_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}


def _artifact_hash(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return ""
    try:
        return hashlib.sha256(Path(normalized).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def _load_json_artifact(path: str, *, cache: dict[str, tuple[str, dict[str, Any]]]) -> tuple[dict[str, Any], str]:
    normalized = str(path or "").strip()
    if not normalized:
        return {}, ""
    if "validation" in normalized.lower():
        raise ValueError(
            "mobile-intention runtime cannot read validation artifacts; "
            "use elder_reference May1-May3 calibration artifacts only"
        )
    artifact_path = Path(normalized)
    if not artifact_path.exists():
        raise FileNotFoundError(f"mobile-intention artifact not found: {artifact_path}")
    digest = _artifact_hash(normalized)
    cached = cache.get(normalized)
    if cached is not None and cached[0] == digest:
        return cached[1], digest
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"mobile-intention artifact must be a JSON object: {artifact_path}")
    if bool(payload.get("uses_validation_data", False)):
        raise ValueError(
            "mobile-intention runtime cannot read artifacts marked "
            "uses_validation_data=true"
        )
    cache[normalized] = (digest, payload)
    return payload, digest
