"""Observation and action contracts for the single-goal hourly App plan."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from .types import APP_CONTEXT_SET


KINDS = (
    "engage_goal",
    "continue_goal",
    "defer_goal",
    "drop_goal",
    "habitual_app",
    "no_app",
)
INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "opportunity_id",
        "goal_id",
        "next_review_at_sim_hour",
        "reason",
    ],
    "properties": {
        "kind": {"enum": list(KINDS)},
        "opportunity_id": {"type": ["string", "null"]},
        "goal_id": {"type": ["string", "null"]},
        "next_review_at_sim_hour": {"type": ["integer", "null"]},
        "reason": {"type": "string", "minLength": 1, "maxLength": 240},
    },
}

INTENT_GUIDANCE = (
    "Choose one action for this hour. Consider visible opportunities, any unfinished goal, "
    "normal phone use and your prior experiences. To engage a new opportunity use its "
    "opportunity_id and null goal_id. To continue the current goal use its goal_id. "
    "To defer or drop, identify either the visible opportunity or the current goal. "
    "With an unfinished goal, do not start a different one. A deferred goal may be reconsidered "
    "only when goal_review_due is true. For defer_goal give a future integer review hour "
    "within max_defer_hours and any known deadline; otherwise use null. Engage/continue require "
    "phone activity in the target's required_channel. Defer/drop allow unrelated phone activity. "
    "habitual_app requires phone activity; no_app requires inactive with empty counts. "
    "For habitual_app and no_app use null IDs. Give a short reason."
)

_OFFER_FIELDS = (
    "opportunity_id",
    "source",
    "status",
    "task_family",
    "visible_description",
    "required_channel",
    "offered_at_sim_hour",
    "visible_from_sim_hour",
    "known_deadline_sim_hour",
)
_GOAL_FIELDS = (
    *_OFFER_FIELDS,
    "goal_id",
    "created_at_sim_hour",
    "accepted_at_sim_hour",
    "next_review_at_sim_hour",
    "decision_index",
    "operation_attempt_count",
    "last_episode_ids",
)


def intention_observation(
    offers: list[dict] | None,
    goal: dict | None,
    review_due: bool,
    now: int,
    max_defer: int,
) -> dict:
    """Expose only observable fields; environment-side templates, arm and random draws stay private."""
    if type(max_defer) is not int or max_defer < 1:
        raise ValueError("max_defer_hours must be a positive integer")
    visible = []
    for offer in offers or []:
        if offer.get("status") in {"dropped", "completed", "expired"}:
            continue
        if offer.get("visible_from_sim_hour", now) > now:
            continue
        deadline = offer.get("known_deadline_sim_hour")
        if deadline is not None and deadline < now:
            continue
        visible.append({key: offer[key] for key in _OFFER_FIELDS if key in offer})
    current = None
    if goal and goal.get("status") not in {"completed", "dropped", "expired"}:
        current = {key: goal[key] for key in _GOAL_FIELDS if key in goal}
    return {
        "available_opportunities": visible,
        "current_intention": current,
        "goal_review_due": review_due,
        "monotonic_sim_hour": now,
        "max_defer_hours": max_defer,
    }


def include_required_channels(
    candidates: dict[str, float], packet: dict
) -> dict[str, float]:
    """Keep historical weights intact. Zero denotes an allowed channel added by an explicit offer."""
    allowed = dict(candidates)
    targets = list(packet["available_opportunities"])
    goal = packet.get("current_intention")
    if goal and (
        goal.get("required_channel")
        or all(offer["opportunity_id"] != goal["opportunity_id"] for offer in targets)
    ):
        targets.append(goal)
    for target in targets:
        channel = target.get("required_channel")
        if channel not in APP_CONTEXT_SET:
            raise ValueError(
                "visible opportunity or goal has no valid required_channel"
            )
        allowed.setdefault(channel, 0.0)
    return allowed


def read_stated_intent(text: str) -> dict | None:
    """Read complete JSON fields even if the intent or outer response ends prematurely."""
    matches = list(re.finditer(r'"intent"\s*:\s*', text))
    if len(matches) != 1:
        return None
    remaining = text[matches[0].end() :].lstrip()
    if not remaining.startswith("{"):
        return None
    decoder = json.JSONDecoder()
    fields = {}
    remaining = remaining[1:].lstrip()
    while remaining:
        try:
            key, end = decoder.raw_decode(remaining)
            rest = remaining[end:].lstrip()
            if not isinstance(key, str) or not rest.startswith(":"):
                break
            rest = rest[1:].lstrip()
            value, end = decoder.raw_decode(rest)
        except ValueError:
            break
        if key in INTENT_SCHEMA["required"]:
            if key in fields:
                return None
            fields[key] = value
        remainder = rest[end:].lstrip()
        if not remainder.startswith(","):
            break
        remaining = remainder[1:].lstrip()
    return fields or None


def stated_activity(text: str) -> bool | None:
    matches = re.findall(r'"active"\s*:\s*(true|false)\b', text)
    return matches[0] == "true" if len(matches) == 1 else None


def stated_channels(text: str, field: str) -> list[str] | None:
    matches = list(re.finditer(rf'"{field}"\s*:\s*', text))
    if len(matches) != 1:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text, matches[0].end())
    except ValueError:
        return None
    if not isinstance(value, dict) or not all(
        type(n) is int and n >= 0 for n in value.values()
    ):
        return None
    return sorted(k for k, n in value.items() if n > 0)


def changed_by_repair(original: dict | None, repaired: dict | None) -> bool:
    if not original or not repaired or original.get("kind") not in KINDS:
        return False
    if original["kind"] != repaired.get("kind"):
        return True
    # A known reference or review time must never point somewhere else after reformatting.
    return any(
        original.get(key) is not None and original[key] != repaired.get(key)
        for key in ("opportunity_id", "goal_id", "next_review_at_sim_hour")
    )


def validate_intent(value: Any, plan: dict, observation: dict) -> dict:
    if not isinstance(value, dict) or set(value) != set(INTENT_SCHEMA["required"]):
        raise ValueError("intent fields do not match the schema")
    kind = value["kind"]
    if kind not in KINDS:
        raise ValueError("unknown intent kind")
    if (
        not isinstance(value["reason"], str)
        or not 1 <= len(value["reason"].strip()) <= 240
    ):
        raise ValueError("intent.reason must be 1..240 characters")
    opp_id, goal_id, review = (
        value["opportunity_id"],
        value["goal_id"],
        value["next_review_at_sim_hour"],
    )
    for ref in (opp_id, goal_id):
        if ref is not None and (not isinstance(ref, str) or not ref.strip()):
            raise ValueError("intent IDs must be nonempty strings or null")
    if kind != "defer_goal" and review is not None:
        raise ValueError("only defer_goal may set next_review_at_sim_hour")
    if kind in {"no_app", "habitual_app"}:
        if (
            opp_id is not None
            or goal_id is not None
            or plan["active"] != (kind == "habitual_app")
        ):
            raise ValueError("activity choice conflicts with target IDs or active flag")
        return dict(value)

    offers = {o["opportunity_id"]: o for o in observation["available_opportunities"]}
    current = observation.get("current_intention")
    if current:
        if (
            kind == "engage_goal"
            or goal_id != current["goal_id"]
            or opp_id not in (None, current["opportunity_id"])
        ):
            raise ValueError(
                "only the current unfinished goal can be reconsidered with its goal_id"
            )
        if not observation["goal_review_due"]:
            raise ValueError("the goal is not due for review")
        target = {**offers.get(current["opportunity_id"], {}), **current}
    else:
        if kind == "continue_goal" or goal_id is not None or opp_id not in offers:
            raise ValueError("intent must reference a visible opportunity")
        target = offers[opp_id]
    now = observation["monotonic_sim_hour"]
    deadline = target.get("known_deadline_sim_hour")
    if deadline is not None and now > deadline:
        raise ValueError("opportunity has expired")
    if kind == "defer_goal":
        last = now + observation["max_defer_hours"]
        if deadline is not None:
            last = min(last, deadline)
        if type(review) is not int or not now < review <= last:
            raise ValueError(
                "defer_goal requires a future review hour within the allowed window"
            )
    if kind in {"engage_goal", "continue_goal"}:
        if (
            not plan["active"]
            or plan["app_context_counts"].get(target.get("required_channel"), 0) <= 0
        ):
            raise ValueError(
                "selected goal must use its required_channel during an active hour"
            )
    return dict(value)


COMPACT_PLAN_V2 = "hourly_plan_compact_v2"
COMPACT_PLAN_V3 = "hourly_plan_compact_v3"
COMPACT_PLAN_VERSION = "hourly_plan_compact_v4"
COMPACT_PLAN_VERSIONS = frozenset(
    {COMPACT_PLAN_V2, COMPACT_PLAN_V3, COMPACT_PLAN_VERSION}
)
COMPACT_SCORES = ("attitude", "subjective_norm", "perceived_control", "confidence")


def compact_needs(needs: dict) -> dict:
    return {
        k: needs[k]
        for k in ("need_pressures", "dominant_need", "active_intent", "intensity_hint")
    }


def compact_observation(packet: dict) -> dict:
    """Give context frequencies as historical shares, distinct from this hour's decision."""
    habit = packet.get("day1_3_habit", {})
    history = {"same_hour_active": habit.get("same_hour_active", {})}
    profile = habit.get("intensity_profile", {})
    if "same_hour_mean_exposures" in profile:
        history["mean_exposures_at_this_hour"] = profile["same_hour_mean_exposures"]
    for key in ("same_hour", "overall"):
        counts = habit.get(key + "_context_counts", {})
        total = sum(counts.values())
        history[key + "_historical_share"] = (
            {channel: round(n / total, 4) for channel, n in counts.items() if n > 0}
            if total
            else {}
        )
    return {**packet, "day1_3_habit": history}


def _v2_actions(observation: dict) -> list[str]:
    now = observation["monotonic_sim_hour"]
    goal = observation.get("current_intention")
    offers = observation["available_opportunities"]
    actions = ["habitual_app", "no_app"]
    if goal:
        if not observation["goal_review_due"]:
            return actions
        original = next(
            (o for o in offers if o["opportunity_id"] == goal["opportunity_id"]), {}
        )
        targets = [{**original, **goal}]
    else:
        targets = offers
    for target in targets:
        deadline = target.get("known_deadline_sim_hour")
        if deadline is not None and deadline < now:
            continue
        ref = (
            "goal:" + goal["goal_id"]
            if goal
            else "opportunity:" + target["opportunity_id"]
        )
        kinds = ["continue_goal" if goal else "engage_goal", "drop_goal"]
        if deadline is None or now < deadline:
            kinds.append("defer_goal")
        actions.extend(f"{kind}:{ref}" for kind in kinds)
    return sorted(actions)


def compact_menu(observation: dict, schema_version: str = COMPACT_PLAN_VERSION) -> dict:
    """List behavior families once. Each deferred target offers its entire legal time window."""
    now = observation["monotonic_sim_hour"]
    offers = {o["opportunity_id"]: o for o in observation["available_opportunities"]}
    targets = {}
    actions = ["habitual_app", "no_app"]
    windows = {}
    current = observation.get("current_intention")
    if current:
        eligible = [
            (
                "g1",
                current["goal_id"],
                {**offers.get(current["opportunity_id"], {}), **current},
            )
        ]
        if not observation["goal_review_due"]:
            eligible = []
    else:
        eligible = [
            (f"o{i}", oid, offers[oid]) for i, oid in enumerate(sorted(offers), 1)
        ]
    for alias, target_id, target in eligible:
        deadline = target.get("known_deadline_sim_hour")
        if deadline is not None and deadline < now:
            continue
        targets[alias] = target_id
        handle = ("continue_goal@" if current else "engage_goal@") + alias
        if schema_version == COMPACT_PLAN_VERSION:
            channel = target.get("required_channel")
            if channel not in APP_CONTEXT_SET:
                raise ValueError(
                    "an actionable target must have a valid required_channel"
                )
            handle += f"@open:{channel}"
        actions.extend([handle, f"drop_goal@{alias}"])
        last = now + observation["max_defer_hours"]
        if deadline is not None:
            last = min(deadline, last)
        if last > now:
            windows[alias] = (now + 1, last)
    # Use a lossless interval representation when a large configuration would dominate the prompt.
    enumerate_hours = sum(last - first + 1 for first, last in windows.values()) <= 96
    options = {}
    for alias, (first, last) in windows.items():
        prefix = f"defer_goal@{alias}@"
        options[alias] = (
            [f"{prefix}{hour}" for hour in range(first, last + 1)]
            if enumerate_hours
            else {"prefix": prefix, "first_hour": first, "last_hour": last}
        )
    return {"actions": actions, "targets": targets, "defer_options": options}


def stated_open_channel(token: Any, body: dict) -> str | None:
    """Only an explicitly selected, listed v4 action declares an embedded App opening."""
    if (
        body["schema_version"] != COMPACT_PLAN_VERSION
        or not isinstance(token, str)
        or token not in body["actions"]
    ):
        return None
    kind, _, opening = token.partition("@")
    if kind not in {"engage_goal", "continue_goal"}:
        return None
    _, marker, channel = opening.partition("@open:")
    return channel if marker and channel in body["channels"] else None


def _v3_action_fields(token: Any, body: dict) -> dict | None:
    if not isinstance(token, str):
        return None
    kind, *parts = token.split("@")
    if kind not in KINDS:
        return None
    fields = {
        "kind": kind,
        "opportunity_id": None,
        "goal_id": None,
        "next_review_at_sim_hour": None,
    }
    if parts:
        alias = parts[0]
        if alias in body["targets"]:
            fields["goal_id" if alias.startswith("g") else "opportunity_id"] = body[
                "targets"
            ][alias]
        if (
            kind == "defer_goal"
            and len(parts) == 2
            and re.fullmatch(r"0|[1-9][0-9]*", parts[1])
        ):
            try:
                fields["next_review_at_sim_hour"] = int(parts[1])
            except ValueError:
                pass
    return fields


def _v3_intent(raw: dict, body: dict) -> dict:
    token = raw["action"]
    fields = _v3_action_fields(token, body)
    if fields is None:
        raise ValueError("action must match an available token")
    if fields["kind"] != "defer_goal":
        if token not in body["actions"]:
            raise ValueError(
                "action must match an available token with its exact target"
            )
    else:
        review = fields["next_review_at_sim_hour"]
        if review is None:
            raise ValueError(
                "defer_goal requires a complete action token containing the chosen hour"
            )
        _, alias, _ = token.split("@")
        options = body["defer_options"].get(alias)
        if isinstance(options, list):
            valid = token in options
        elif isinstance(options, dict):
            valid = (
                token == f"{options['prefix']}{review}"
                and options["first_hour"] <= review <= options["last_hour"]
            )
        else:
            valid = False
        if not valid:
            raise ValueError(
                "defer_goal hour or target is outside the available options"
            )
    return {**fields, "reason": raw["reason"]}


def _action_fields(token: Any) -> dict | None:
    if not isinstance(token, str):
        return None
    kind, *target = token.split(":", 2)
    if kind not in KINDS:
        return None
    fields = {"kind": kind, "opportunity_id": None, "goal_id": None}
    if len(target) == 2 and target[0] in {"opportunity", "goal"}:
        fields[target[0] + "_id"] = target[1]
    return fields


def compact_intent(raw: dict, body: dict) -> dict:
    if body["schema_version"] in (COMPACT_PLAN_V3, COMPACT_PLAN_VERSION):
        menu = compact_menu(body["inputs"], body["schema_version"])
        if any(body.get(key) != value for key, value in menu.items()):
            raise ValueError(
                "action menu is inconsistent with the observed targets or windows"
            )
        return _v3_intent(raw, body)
    token = raw["action"]
    if token not in body["actions"] or token not in _v2_actions(body["inputs"]):
        raise ValueError("action must match one available token with its exact target")
    return {
        **_action_fields(token),
        "next_review_at_sim_hour": raw["review"],
        "reason": raw["reason"],
    }


def _response_fields(text: str) -> tuple[dict, dict, bool]:
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


def _complete_list_items(fragment: str) -> list:
    """Recover only complete elements of a partially transmitted list."""
    if not fragment.startswith("["):
        return []
    rest = fragment[1:].lstrip()
    items = []
    decoder = json.JSONDecoder()
    while rest:
        try:
            value, end = decoder.raw_decode(rest)
        except ValueError:
            break
        items.append(value)
        rest = rest[end:].lstrip()
        if not rest.startswith(","):
            break
        rest = rest[1:].lstrip()
    return items


def _known_volumes(value: Any) -> dict | None:
    if isinstance(value, dict) and all(
        type(n) is int and n >= 0 for n in value.values()
    ):
        return {key: count for key, count in value.items() if count > 0}
    return None


def read_compact_statement(raw_text: str, request_body: dict) -> dict:
    """Recover exact stated choices and volumes without mistaking an input echo for an action."""
    fields, partial, ambiguous = _response_fields(raw_text)
    action = fields.get("action")
    v4 = request_body["schema_version"] == COMPACT_PLAN_VERSION
    v3 = request_body["schema_version"] in (COMPACT_PLAN_V3, COMPACT_PLAN_VERSION)
    choice = _v3_action_fields(action, request_body) if v3 else _action_fields(action)
    old_token = v3 and choice is None and isinstance(action, str) and ":" in action
    if old_token:
        choice = _action_fields(action)
    if choice:
        if (not v3 or old_token) and "review" in fields:
            value = fields["review"]
            choice["next_review_at_sim_hour"] = (
                value if not v3 or type(value) is int else None
            )
        if "reason" in fields:
            choice["reason"] = fields["reason"]
    elif isinstance(fields.get("intent"), dict):
        choice = fields["intent"]
    elif "intent" in partial:
        choice = read_stated_intent('{"intent":' + partial["intent"])

    # An incomplete but identifiable deferral can gain a time in a repair, never a new target.
    complete_defer_token = False
    if v3 and choice and choice.get("kind") == "defer_goal":
        for alias, full_id in request_body["targets"].items():
            field = "goal_id" if alias.startswith("g") else "opportunity_id"
            if choice.get(field) != full_id:
                continue
            legacy_target = "goal" if field == "goal_id" else "opportunity"
            complete_defer_token = action in (
                f"defer_goal@{alias}",
                f"defer_goal:{legacy_target}:{full_id}",
                None,
            )
            # Extra legacy fields never pass v3, but an explicitly stated integer still binds a repair.
            if type(fields.get("review")) is int:
                encoded_hour = choice.get("next_review_at_sim_hour")
                if encoded_hour is not None and encoded_hour != fields["review"]:
                    ambiguous = True
                else:
                    choice["next_review_at_sim_hour"] = fields["review"]

    embedded = fields.get("intent")
    if v3 and action and choice and isinstance(embedded, dict):
        ambiguous = (
            ambiguous
            or changed_by_repair(choice, embedded)
            or changed_by_repair(embedded, choice)
        )

    calibrated = "exposures_if_active" in request_body
    count_field = "app_context_weights" if calibrated else "app_context_counts"
    activity = _known_volumes(fields.get("weights" if calibrated else count_field))
    legacy_volume = _known_volumes(fields.get(count_field))
    if calibrated and activity is None:
        activity = legacy_volume
    apps = fields.get("apps")
    if (
        not calibrated
        and isinstance(apps, list)
        and all(isinstance(a, str) for a in apps)
    ):
        activity = dict(Counter(apps))
    opened = stated_open_channel(action, request_body)
    additional = fields.get("additional_apps")
    additional_activity = None
    if (
        v4
        and isinstance(additional, list)
        and all(isinstance(channel, str) for channel in additional)
    ):
        additional_activity = dict(Counter(additional))
        # Without a complete listed action, the extra openings do not specify a total.
        if isinstance(action, str) and (
            action in request_body["actions"]
            or choice
            and choice.get("kind") == "defer_goal"
        ):
            total = Counter(additional)
            if opened is not None:
                total[opened] += 1
            if activity is not None and activity != total:
                ambiguous = True
            activity = dict(total)
    if opened is not None and activity is not None and not activity.get(opened):
        ambiguous = True
    if activity is not None and legacy_volume is not None and activity != legacy_volume:
        ambiguous = True

    active = fields.get("active")
    if not isinstance(active, bool):
        active = (
            bool(activity)
            if activity is not None
            else (True if opened is not None else None)
        )
    elif opened is not None and not active:
        ambiguous = True
    elif activity is not None and active != bool(activity):
        ambiguous = True

    # A fragment ending midway through a channel name states no such channel.
    partial_apps = Counter(
        a
        for a in _complete_list_items(partial.get("apps", ""))
        if isinstance(a, str) and a in request_body["channels"]
    )
    partial_additional_apps = (
        Counter(
            a
            for a in _complete_list_items(partial.get("additional_apps", ""))
            if isinstance(a, str) and a in request_body["channels"]
        )
        if v4
        else {}
    )
    partial_weights = {}
    for label in ("weights", count_field) if calibrated else (count_field,):
        if partial.get(label, "").startswith("{"):
            volumes, _, repeated = _response_fields(partial[label])
            ambiguous = ambiguous or repeated
            partial_weights.update(
                {
                    k: n
                    for k, n in volumes.items()
                    if type(n) is int and n >= 0 and k in request_body["channels"]
                }
            )
    scores = {
        key: fields[key]
        for key in COMPACT_SCORES
        if type(fields.get(key)) in (int, float) and 0 <= fields[key] <= 1
    }
    return {
        "choice": choice,
        "action": action,
        "active": active,
        "activity": activity,
        "channels": sorted(activity) if activity is not None else None,
        "ambiguous": ambiguous,
        "partial_apps": dict(partial_apps),
        "partial_weights": partial_weights,
        "scores": scores,
        "compact_v3": v3,
        "complete_defer_token": complete_defer_token,
        "opened_channel": opened,
        "additional_activity": additional_activity,
        "partial_additional_apps": dict(partial_additional_apps),
    }


def compact_repair_changed(first: dict, repaired: dict) -> bool:
    check_fields = ["active", "activity", "additional_activity"]
    if not first["complete_defer_token"]:
        check_fields.append("action")
    if (
        first["ambiguous"]
        or repaired["ambiguous"]
        or changed_by_repair(first["choice"], repaired["choice"])
        or any(
            first[k] is not None and repaired[k] is not None and first[k] != repaired[k]
            for k in check_fields
        )
    ):
        return True
    if not first["compact_v3"]:
        return False
    extras = repaired["additional_activity"]
    if extras is not None and any(
        extras.get(k, 0) < n for k, n in first["partial_additional_apps"].items()
    ):
        return True
    activity = repaired["activity"]
    if activity is not None and (
        any(activity.get(k, 0) < n for k, n in first["partial_apps"].items())
        or any(activity.get(k, 0) != n for k, n in first["partial_weights"].items())
    ):
        return True
    return any(
        key in repaired["scores"] and repaired["scores"][key] != value
        for key, value in first["scores"].items()
    )


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
