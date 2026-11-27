"""Opt-in common environment random streams for matched decisions across policies."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PairedRandomProvider:
    pair_seed: int

    def rng(
        self, profile_id: int | str, opportunity_id: str, decision_index: int, mechanism: str
    ) -> random.Random:
        if not str(profile_id).strip() or not opportunity_id or not mechanism:
            raise ValueError("A paired stream requires a profile, opportunity and mechanism")
        if type(decision_index) is not int or decision_index < 1:
            raise ValueError("decision_index starts at one and includes low-level avoid decisions")
        key = json.dumps(
            [str(profile_id), opportunity_id, decision_index, mechanism, self.pair_seed],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))
