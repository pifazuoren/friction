"""Verify the two resident choices introduced in the fourth App entry policy."""

import json

from proto.app_entry.wire import parse_compact_reply
from proto.app_entry import PHONE_USE_NEEDS_V5
from proto.app_entry.intention_contract import COMPACT_PLAN_V9
from proto.app_entry.phone_policy import replay_activity_counts, resolve_phone_use
from proto.app_entry.needs import (
    DIGITAL_NEED_LABELS, HABIT_KEY, OBSERVED_HABIT_KEY, PHONE_RECOMMENDATIONS, PHONE_USE_OPTIONS,
    PHONE_USE_NEEDS_V1, PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_VERSIONS,
    sanitize_phone_needs, stated_phone_use_decision,
)
from proto.app_entry.rollout import phone_use_habit_fact
from proto.retry_review import RETRY_REVIEW_VERSIONS, parse_review_time


def request_payload(request):
    content = next(m["content"] for m in request["messages"] if m["role"] == "user")
    return json.loads(content[content.index("{"):])


def exchanges(rows, module, route):
    """Require one ordered transport reply per call, sharing the resident tick and query."""
    events = [r for r in rows if r["module"] == module and r["kind"] in {"request", "response", "error", "parse"}]
    calls = [r for r in events if r["kind"] == "request"]
    if not calls:
        if events:
            raise ValueError(f"{module} response without request")
        return []
    ids = [r.get("call_id") for r in calls]
    if (not all(ids) or len(set(ids)) != len(ids) or not calls[0].get("query_id")
            or any(r.get("query_id") != calls[0]["query_id"] or r.get("call_id") not in ids
                   or r.get("tick_id") != route.get("tick_id") for r in events)):
        raise ValueError(f"unlinked {module} request or response")
    replies = []
    ordered = []
    for call in calls:
        linked = [r for r in events if r["call_id"] == call["call_id"]]
        kinds = [r["kind"] for r in linked]
        if (kinds not in (["request", "response", "parse"], ["request", "error"])
                or any(r.get("phase") != call["phase"] for r in linked)):
            raise ValueError(f"incomplete {module} call evidence")
        ordered.extend(linked)
        replies.append((call, linked[1], linked[2] if len(linked) == 3 else None))
    if ordered != events:
        raise ValueError(f"overlapping {module} responses")
    return replies


def check_phone_choice(rows, route, plan, *, expected_version=None, replay_habit=None,
                       paired_environment_seed=None):
    # A queued opportunity is not actionable while the current goal awaits its appointment.
    before = route.get("goal_state_before")
    now = (route["talkingdata_day"] - 1) * 24 + route["hour"]
    free = (before["status"] == "deferred" and now < before["next_review_at_sim_hour"]
            if before else not route["opportunity_ids"])
    calls = exchanges(rows, "app_needs", route)
    if not calls:
        raise ValueError("missing actual Needs request")
    first = request_payload(calls[0][0])
    needs_version = first.get("schema_version")
    resolutions = [r for r in rows if (r["module"], r["kind"]) == ("app_needs", "phone_use_resolution")]
    if resolutions and needs_version != PHONE_USE_NEEDS_V5:
        raise ValueError("unexpected phone-use resolution outside a V5 free hour")
    if free != (needs_version in PHONE_USE_NEEDS_VERSIONS):
        raise ValueError("phone choice scope disagrees with the resident's available goal")
    body = request_payload(plan) if plan is not None else None
    if body and body.get("schema_version") != COMPACT_PLAN_V9:
        raise ValueError("unexpected wire version in fourth-policy Plan")
    if not free:
        if body and any(body["digital_needs"].get(k) is not None for k in ("phone_use_decision", "phone_use_resolution")):
            raise ValueError("task Plan was constrained by an unscheduled phone choice")
        return None, None

    inputs = first["inputs"]
    if expected_version is not None and needs_version != expected_version:
        raise ValueError("free-hour Needs version differs from the run configuration")
    if needs_version in (PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V5):
        habit = inputs["day1_3_habit"]
        if not isinstance(habit.get("device_history_fact"), str) or not habit["device_history_fact"]:
            raise ValueError("missing same-hour device history fact")
        if replay_habit is not None:
            hour = route["hour"]
            activity = replay_habit["active_by_hour"].get(str(hour), {})
            counts = replay_habit["context_by_hour"].get(str(hour), {})
            if (habit["same_hour_active"] != activity or habit["replay_days"] != replay_habit["replay_days"]
                    or habit["device_history_fact"] != phone_use_habit_fact(hour, activity, counts)):
                raise ValueError("same-hour device history differs from the replay handoff")
    context = {"task_opportunity": "none_actionable"}
    if before:
        review = before["next_review_at_sim_hour"]
        context.update(next_review_at_sim_hour=review, hours_until_review=review - now)
    accepts_observed_alias = needs_version != PHONE_USE_NEEDS_V1
    keys = {"schema_version", "inputs"}
    allow_follow_habit = (needs_version == PHONE_USE_NEEDS_V5
                          and replay_activity_counts(inputs["day1_3_habit"].get("same_hour_active")) is not None)
    if needs_version == PHONE_USE_NEEDS_V5:
        keys.add("recommendation_options")
        if first.get("recommendation_options") != list(PHONE_RECOMMENDATIONS if allow_follow_habit else PHONE_USE_OPTIONS):
            raise ValueError("phone-use recommendations differ from the available same-hour history")
    if accepts_observed_alias:
        keys.add("pressure_keys")
        if first.get("pressure_keys") != list(DIGITAL_NEED_LABELS):
            raise ValueError("phone choice lacks the canonical pressure field names")
    if (set(first) != keys or set(inputs) & {"actions", "channels", "targets"}
            or inputs.get("phone_use_context") != context
            or inputs.get("talkingdata_day") != route["talkingdata_day"] or inputs.get("hour") != route["hour"]
            or [c["phase"] for c, _, _ in calls] not in (["initial"], ["initial", "repair"])):
        raise ValueError("invalid free-hour Needs request")
    accepted_needs = None
    choice = locked = None
    normalization = None
    for index, (call, reply, parsed) in enumerate(calls):
        if index and request_payload(call) != first:
            raise ValueError("phone-choice repair changed the resident observation")
        if parsed is None:
            if index + 1 != len(calls):
                raise ValueError("unexpected repair after a phone-choice transport error")
            continue
        raw = reply.get("raw", "")
        stated = stated_phone_use_decision(raw, allow_follow_habit=allow_follow_habit)
        if index == 0:
            locked = stated
        payload = parse_compact_reply(raw)
        decoded, _ = sanitize_phone_needs(payload, needs_version, allow_follow_habit=allow_follow_habit)
        if decoded and locked not in (None, decoded["phone_use_decision"]):
            decoded = None
        if decoded is None:
            if parsed["status"] in ("ok", "ok_repaired") or parsed.get("parsed") is not None:
                raise ValueError("invalid phone preference accepted as a decision")
            continue
        if (parsed.get("parsed") != decoded or parsed["status"] != ("ok_repaired" if index else "ok")
                or index + 1 != len(calls)):
            raise ValueError("accepted phone choice differs from the raw Needs reply")
        if accepts_observed_alias and OBSERVED_HABIT_KEY in payload["need_pressures"]:
            normalization = (call["phase"], rows.index(reply), rows.index(parsed))
        accepted_needs = decoded
        choice = decoded["phone_use_decision"]

    markers = [r for r in rows if (r["module"], r["kind"]) == ("app_needs", "pressure_key_normalized")]
    if len(markers) != int(normalization is not None):
        raise ValueError("phone choice lacks matching evidence of pressure key normalization")
    if normalization:
        phase, start, end = normalization
        marker, = markers
        if (marker.get("tick_id") != route.get("tick_id") or marker.get("phase") != phase
                or not start < rows.index(marker) < end or marker.get("from_key") != OBSERVED_HABIT_KEY
                or marker.get("to_key") != HABIT_KEY):
            raise ValueError("pressure key normalization differs from the actual reply")

    unavailable = [r for r in rows if (r["module"], r["kind"]) == ("app_plan", "channel_unavailable")]
    resolution = None
    if needs_version == PHONE_USE_NEEDS_V5:
        if len(resolutions) != int(choice is not None):
            raise ValueError("phone-use resolution count differs from the number of accepted Needs decisions")
        if resolutions:
            marker, = resolutions
            resolution = resolve_phone_use(
                same_hour_active=inputs["day1_3_habit"]["same_hour_active"], recommendation=choice,
                agent_id=route["agent_id"], talkingdata_day=route["talkingdata_day"], hour=route["hour"],
                paired_environment_seed=paired_environment_seed,
            )
            following = plan or next(iter(unavailable), route)
            if (marker.get("resolution") != resolution
                    or any(marker.get(key) != route[key] for key in ("tick_id", "agent_id", "talkingdata_day", "hour"))
                    or not rows.index(calls[-1][2]) < rows.index(marker) < rows.index(following)):
                raise ValueError("phone-use resolution differs from replay history, model reply, clock or seed")
            choice = resolution["final_choice"]
            accepted_needs = {**accepted_needs, "phone_use_decision": choice}
    if body is None:
        if choice == "use_phone" and len(unavailable) == 1:
            marker = unavailable[0]
            if (marker.get("phone_use_decision") == choice and marker.get("candidate_app_contexts") == {}
                    and marker["status"] == route["status"] == "technical_failure"):
                return "use_phone_channel_unavailable", resolution
        if choice is None and not unavailable and route["status"] == "technical_failure":
            return "unmeasured", None
        raise ValueError("phone choice lacks its downstream Plan or channel-failure receipt")

    if (not accepted_needs or unavailable
            or any(k not in body["digital_needs"] or body["digital_needs"][k] != accepted_needs[k]
                   for k in ("phone_use_decision", "intensity_hint", "active_intent", "need_pressures"))
            or rows.index(calls[-1][2]) >= rows.index(plan)):
        raise ValueError("Plan did not receive the preceding accepted phone choice")
    if resolution is not None:
        private_fields = ("phone_use_resolution", "seed", "sample_u", "odds_multiplier",
                          "prior_use_probability", "use_probability", "llm_recommendation")
        plan_wire = json.dumps(body, separators=(",", ":"))
        if any(f'"{field}":' in plan_wire for field in private_fields):
            raise ValueError("Plan prompt exposed internal phone-use resolution fields")
    plan_inputs = body["inputs"]
    if (inputs["day1_3_habit"].get("same_hour_active") != plan_inputs["day1_3_habit"].get("same_hour_active")
            or inputs["recent_simulated_bundles"] != plan_inputs["recent_simulated_bundles"]):
        raise ValueError("phone choice and Plan received different observed or simulated activity histories")
    channels = body["channels"]
    permitted = [f"habitual_app@open:{ch}" for ch in sorted(channels)] if choice == "use_phone" else ["no_app"]
    if ((choice == "leave_phone" and channels) or not permitted or body["actions"] != permitted
            or body["targets"] or body["defer_options"]):
        raise ValueError("free-hour Plan menu can override the resident phone choice")
    action = {"leave_phone": "no_app", "use_phone": "habitual_app"}[choice]
    if route["status"] == "accepted" and route.get("executed_choice") != action:
        raise ValueError("execution differs from the resident phone choice")
    return choice, resolution


def _slot(stamp):
    if not isinstance(stamp, dict) or type(stamp.get("day")) is not int or type(stamp.get("hour")) is not int:
        raise ValueError("invalid retry date or time")
    if stamp["day"] < 1 or not 0 <= stamp["hour"] < 24:
        raise ValueError("retry date or time outside the simulation clock")
    return (stamp["day"] - 1) * 24 + stamp["hour"]


def check_retry_review(rows, route, goal_outcomes, attempts, observation):
    calls = exchanges(rows, "retry_review", route)
    if not attempts:
        if calls or any(r.get("retry_review") for r in goal_outcomes):
            raise ValueError("retry review without a settled task")
        return None
    if len(goal_outcomes) != 1 or len(attempts) != 1 or observation is None:
        raise ValueError("missing settled goal or Plan for retry review")
    outcome, attempt = goal_outcomes[0], attempts[0]
    record = outcome.get("retry_review")
    version = route.get("retry_review_version")
    if (version not in RETRY_REVIEW_VERSIONS or not isinstance(record, dict) or record.get("version") != version
            or record != attempt.get("retry_review")):
        raise ValueError("retry review differs between goal outcome and SQLite")
    before = route["goal_state_after"]
    after = outcome["goal_state_after"]
    operated = attempt["outcome_type"] != "avoid_without_attempt"
    if (after["operation_attempt_count"] != before["operation_attempt_count"] + int(operated)
            or outcome.get("operation_started") is not operated
            or after["decision_index"] != before["decision_index"]
            or after["last_episode_ids"] != before["last_episode_ids"] + [attempt["episode_id"]]):
        raise ValueError("retry goal counters or episodes disagree with the settled operation")
    now = observation["monotonic_sim_hour"]
    latest = now + observation["max_defer_hours"]
    deadline = before["known_deadline_sim_hour"]
    if deadline is not None:
        latest = min(latest, deadline)
    success = attempt["outcome_type"] in {"success_self", "success_with_help"}
    choice = None
    if success or latest <= now:
        if calls:
            raise ValueError("retry request after success or outside the available window")
        status = "not_needed" if success else "no_future_hour"
    elif not calls:
        status = "missing_llm"
    else:
        if len(calls) != 1 or calls[0][0]["phase"] != "initial":
            raise ValueError("unexpected retry review request count")
        call, reply, parsed = calls[0]
        body = request_payload(call)
        task = body["task"]
        facts = body["outcome"]
        if (rows.index(reply if parsed is None else parsed) >= rows.index(outcome)
                or body.get("schema_version") != version
                or (_slot(body["now"]), _slot(body["earliest"]), _slot(body["latest"])) != (now, now + 1, latest)
                or task.get("goal_id") != before["goal_id"] or task.get("task_id") != attempt["task_id"]
                or task.get("known_deadline_sim_hour") != deadline
                or task.get("description") != before["visible_description"]
                or task.get("decision_count") != before["decision_index"]
                or task.get("operation_count") != after["operation_attempt_count"]
                or any(facts.get(k) != attempt[k] for k in ("episode_id", "outcome_type", "strategy_type", "help_used"))
                or facts.get("operation_started") != outcome.get("operation_started")):
            raise ValueError("retry prompt does not describe the settled task and review window")
        if parsed is None:
            status = "request_error"
        else:
            decision = parse_review_time(reply.get("raw"), now + 1, latest, version=version)
            if decision is None:
                if parsed.get("parsed") is not None or parsed["status"] != "invalid_response":
                    raise ValueError("invalid retry time accepted as a decision")
                status = "invalid_response"
            else:
                raw, choice = decision
                if parsed.get("parsed") != raw or parsed["status"] != "ok":
                    raise ValueError("accepted retry time differs from model reply")
                status = "scheduled"
    final_status = "completed" if success else ("deferred" if choice is not None else "needs_review")
    if (record.get("status") != status or "next_review_at_sim_hour" not in record
            or record["next_review_at_sim_hour"] != choice or after["status"] != final_status
            or after["next_review_at_sim_hour"] != choice or after["goal_id"] != before["goal_id"]):
        raise ValueError("saved goal or retry review differs from the resident decision")
    return status
