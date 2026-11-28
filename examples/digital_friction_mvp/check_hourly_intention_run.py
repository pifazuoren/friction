"""Verify opportunity-mode routing against actual Plan requests, traces and SQLite outcomes."""

from collections import Counter, defaultdict
from hashlib import sha256
import json

from proto.metrics import attempt_rows_table_name
from proto.app_entry.types import _stable_hash
from proto.app_entry.intention_contract import (
    COMPACT_PLAN_V2,
    COMPACT_PLAN_VERSIONS,
    OPENING_TOKEN_VERSIONS,
    compact_repair_changed,
    compact_repair_locks,
    parse_compact_reply,
    read_compact_statement,
    changed_by_repair,
    intention_observation,
    read_stated_intent,
    stated_activity,
    stated_channels,
    validate_intent,
)
from proto.app_entry.planner import decode_compact_plan, sanitize_app_entry_plan_payload
from proto.llm_psychology import _extract_json_object


def request_payload(request):
    content = next(m["content"] for m in request["messages"] if m["role"] == "user")
    return json.loads(content[content.index("{") :])


def decode_archived_plan(output, payload):
    """Archived opportunity_v1 replies used the full nested intent and activity counts or weights."""
    count_field = (
        "app_context_weights"
        if "app_context_weights" in payload["output_schema"]["properties"]
        else "app_context_counts"
    )
    calibrated = count_field == "app_context_weights"
    constraints = payload["runtime_output_constraints"]
    plan, _ = sanitize_app_entry_plan_payload(
        {k: v for k, v in output.items() if k != "intent"},
        candidate_contexts=payload["candidate_app_contexts"],
        active_exposure_cap=(
            payload["intensity_profile"]["exposures_if_active"]
            if calibrated
            else constraints["active_exposure_maximum"]
        ),
        min_confidence=constraints["minimum_confidence"],
        calibrated=calibrated,
    )
    if plan is None or not plan["active"] and output[count_field] != {}:
        raise ValueError("raw activity failed the archived Plan contract")
    return {
        **plan,
        "intent": validate_intent(output.get("intent"), plan, payload["inputs"]),
    }


def decode_received_plan(raw, original, payload, compact):
    output = parse_compact_reply(raw) if compact else _extract_json_object(raw)
    if output is None:
        raise ValueError("no parseable Plan reply")
    if compact:
        if original is not None and compact_repair_changed(
            compact_repair_locks(read_compact_statement(original, payload), payload)[0],
            read_compact_statement(raw, payload),
        ):
            raise ValueError("repair changed a stated action, target or activity")
        return decode_compact_plan(output, payload)

    if original is not None:
        if changed_by_repair(read_stated_intent(original), read_stated_intent(raw)):
            raise ValueError("repair changed a previously stated choice")
        count_field = (
            "app_context_weights"
            if "app_context_weights" in payload["output_schema"]["properties"]
            else "app_context_counts"
        )
        for before, after in (
            (stated_activity(original), stated_activity(raw)),
            (stated_channels(original, count_field), stated_channels(raw, count_field)),
        ):
            if before is not None and after is not None and before != after:
                raise ValueError("repair changed stated phone activity")
    return decode_archived_plan(output, payload)


def check_compact_repair_request(call, original, initial_payload):
    """Check the separately transmitted correction against the decision it purports to repair."""
    repair = request_payload(call)
    before, repair_field = compact_repair_locks(
        read_compact_statement(original, initial_payload), initial_payload
    )
    if repair.get("repair_field") != repair_field:
        raise ValueError("repair prompt does not identify the permitted correction")
    locked = {
        k: before[k]
        for k in ("action", "choice", "active", "activity")
        if before[k] is not None
    }
    volume = (
        "exposures_if_active"
        if "exposures_if_active" in initial_payload
        else "exposure_cap"
    )
    constraint_keys = ["actions", "channels", volume, "minimum_confidence"]
    version = initial_payload["schema_version"]
    if version in COMPACT_PLAN_VERSIONS and version != COMPACT_PLAN_V2:
        constraint_keys.extend(("schema_version", "targets", "defer_options"))
        locked.update({key: before[key] for key in ("scores", "partial_apps", "partial_weights") if before[key]})
    if version in OPENING_TOKEN_VERSIONS:
        locked.update({key: before[key] for key in ("opened_channel", "additional_activity") if before[key] is not None})
        if before["partial_additional_apps"]:
            locked["partial_additional_apps"] = before["partial_additional_apps"]
    if repair.get("preserve") != locked or any(
        repair.get(k) != initial_payload.get(k) for k in constraint_keys
    ):
        raise ValueError(
            "repair prompt changed the available actions, activity constraints or original commitment"
        )
    if before["choice"] is None:
        if any(
            repair.get(k) != initial_payload[k] for k in ("inputs", "digital_needs")
        ):
            raise ValueError("repair prompt supplied different evidence")
    else:
        target = {
            k: initial_payload["inputs"][k]
            for k in (
                "available_opportunities",
                "current_intention",
                "monotonic_sim_hour",
                "max_defer_hours",
            )
        }
        if (
            repair.get("previous_reply") != original[:1200]
            or repair.get("target_constraints") != target
        ):
            raise ValueError(
                "repair prompt is not linked to the initial reply and its goal constraints"
            )


def check_plan_calls(rows, route):
    """Match each sender call to its own transport reply and re-validate the recorded acceptance."""
    events = [row for row in rows if row["module"] == "app_plan"]
    calls = [r for r in events if r["kind"] == "request"]
    failed = route["status"] == "technical_failure"
    if not calls:
        if events or not failed:
            raise ValueError("missing actual Plan request")
        return None
    phases = [r["phase"] for r in calls]
    if (
        phases not in (["initial"], ["initial", "repair"])
        or route["repair_count"] != len(calls) - 1
    ):
        raise ValueError("invalid initial or repair request count")
    query_id = calls[0].get("query_id")
    ids = [r.get("call_id") for r in calls]
    if not query_id or not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("missing or duplicate Plan call identities")
    transport = [r for r in events if r["kind"] in {"response", "error", "parse"}]
    if any(
        r.get("query_id") != query_id or r.get("call_id") not in ids
        for r in [*calls, *transport]
    ):
        raise ValueError("unlinked Plan response or parse")
    payload = request_payload(calls[0])
    compact = payload.get("schema_version") in COMPACT_PLAN_VERSIONS
    if not compact and not str(payload.get("schema_version", "")).endswith(
        "_with_intent_v1"
    ):
        raise ValueError("unknown opportunity Plan reply contract")
    observation = payload["inputs"]
    if route.get("visible_observation_hash") != _stable_hash(observation)[:16]:
        raise ValueError("actual Plan observation differs from routing")
    originals = []
    accepted = None
    for index, call in enumerate(calls):
        if index and compact:
            check_compact_repair_request(call, originals[0], payload)
        records = [r for r in transport if r["call_id"] == call["call_id"]]
        replies = [r for r in records if r["kind"] in {"response", "error"}]
        parses = [r for r in records if r["kind"] == "parse"]
        if len(replies) != 1 or any(r.get("phase") != call["phase"] for r in records):
            raise ValueError("missing or mismatched raw Plan response")
        if replies[0]["kind"] == "error":
            if parses or index != len(calls) - 1 or not failed:
                raise ValueError("invalid Plan transport error")
            originals.append(None)
            continue
        raw = replies[0].get("raw")
        if not isinstance(raw, str) or len(parses) != 1:
            raise ValueError("missing raw Plan response or parse")
        originals.append(raw)
        is_accepted = parses[0]["status"] in {"ok", "ok_repaired"}
        try:
            decoded = decode_received_plan(
                raw, originals[0] if index else None, payload, compact
            )
        except (ValueError, TypeError, KeyError) as exc:
            if is_accepted:
                raise ValueError(
                    f"accepted parse failed validation against the raw reply: {exc}"
                ) from exc
            if parses[0].get("parsed") is not None:
                raise ValueError("rejected parse contains a validated decision")
            continue
        if not is_accepted:
            raise ValueError("valid raw Plan was recorded as a rejected parse")
        if index != len(calls) - 1 or parses[0]["status"] != (
            "ok_repaired" if index else "ok"
        ):
            raise ValueError("invalid accepted Plan phase")
        if parses[0].get("parsed") != decoded:
            raise ValueError("accepted parse does not match the raw reply")
        accepted = decoded["intent"]
    choices = []
    for raw in originals:
        if raw is None:
            choices.append(None)
        elif compact:
            choices.append(read_compact_statement(raw, payload)["choice"])
        else:
            choices.append(read_stated_intent(raw))
    if route.get("raw_choice") != choices[0] or route.get("repaired_choice") != (
        choices[1] if len(choices) == 2 else None
    ):
        raise ValueError("raw or repaired choice differs from the recorded route")
    if failed and accepted is not None:
        raise ValueError("a validated Plan was recorded as a technical failure")
    if not failed and (accepted is None or accepted != route["accepted_choice"]):
        raise ValueError("accepted model response differs from routing")
    return observation


def check_goal_step(route, final_goal, observation, before_expected, check_previous):
    before, after = route.get("goal_state_before"), route.get("goal_state_after")
    now = (route["talkingdata_day"] - 1) * 24 + route["hour"]
    if (
        before_expected
        and before_expected.get("known_deadline_sim_hour") is not None
        and now > before_expected["known_deadline_sim_hour"]
    ):
        before_expected = None
    if check_previous and before != before_expected:
        raise ValueError("unfinished goal did not carry over from the previous hour")
    if observation is not None:
        due = (
            not before
            or before["status"] != "deferred"
            or now >= before["next_review_at_sim_hour"]
        )
        public = intention_observation(
            [], before, due, now, observation["max_defer_hours"]
        )
        if (
            observation["monotonic_sim_hour"] != now
            or observation["current_intention"] != public["current_intention"]
            or observation["goal_review_due"] != due
        ):
            raise ValueError(
                "goal observation or review hour differs from persisted state"
            )
    kind = route.get("executed_choice")
    if kind in (None, "habitual_app", "no_app"):
        if before != after:
            raise ValueError("goal changed without a goal choice")
    else:
        intent = route["accepted_choice"]
        if not after or (before and after["goal_id"] != before["goal_id"]):
            raise ValueError("missing or overwritten goal")
        oid = intent["opportunity_id"] or (before or {}).get("opportunity_id")
        if route.get("opportunity_id") != oid or after["opportunity_id"] != oid:
            raise ValueError("executed opportunity differs from chosen target")
        status = {
            "engage_goal": "engaged",
            "continue_goal": "engaged",
            "defer_goal": "deferred",
            "drop_goal": "dropped",
        }[kind]
        if (
            after["status"] != status
            or after["next_review_at_sim_hour"] != intent["next_review_at_sim_hour"]
        ):
            raise ValueError(
                "goal state differs from the selected action or review time"
            )
        if (
            before
            and before["status"] == "deferred"
            and now < before["next_review_at_sim_hour"]
        ):
            raise ValueError("deferred goal was handled before its review hour")
    return (
        final_goal
        if final_goal
        and final_goal.get("status") not in {"completed", "dropped", "expired"}
        else None
    )


def audit_hours(records, persisted, expected, error_hours, scheduled, code_hash):
    hours = defaultdict(list)
    published = {}
    visible_hours = defaultdict(set)
    by_opportunity = defaultdict(list)
    issues = []
    source_episodes = {}
    day5_memory = []
    choices = Counter()
    strategies = Counter()
    outcome_counts = Counter()
    support_status = Counter()
    last_goal_state = {}
    low_level_failures = []
    task_ids = set()
    operations = 0
    help_requests = 0
    previous_goal = previous_key = None
    for row in records:
        key = row["talkingdata_day"], row["hour"]
        if key not in expected:
            continue
        hours[key].append(row)
        if (
            row["module"] == "hourly_intention"
            and row["kind"] == "opportunity_published"
        ):
            oid = row["opportunity_id"]
            if oid in published:
                issues.append(f"opportunity published twice: {oid}")
            published[oid] = row
    for key in sorted(expected):
        rows = hours[key]
        routes = [
            r
            for r in rows
            if (r["module"], r["kind"]) == ("hourly_intention", "hourly_intention")
        ]
        if len(routes) != 1:
            issues.append(f"{key}: expected one routing decision, found {len(routes)}")
            continue
        (route,) = routes
        if (
            route.get("code_hash") != code_hash
            or route.get("hourly_intention_mode") != "opportunity_v1"
        ):
            issues.append(f"{key}: routing record disagrees with archived version")
        intent = route.get("accepted_choice") or {}
        action = route.get("executed_choice")
        starts = action in {"engage_goal", "continue_goal"}
        technical = route["status"] == "technical_failure"
        if (
            not technical
            and route["status"] != "accepted"
            or technical != (key in error_hours)
            or starts != route["task_started"]
            or (technical and (action or intent))
            or (not technical and (not action or action != intent.get("kind")))
        ):
            issues.append(f"{key}: invalid accepted/failed/executed decision")
        goals = [
            r
            for r in rows
            if (r["module"], r["kind"]) == ("hourly_intention", "goal_outcome")
        ]
        low_level_failed = (
            len(goals) == 1 and goals[0].get("status") == "technical_failure"
        )
        if low_level_failed:
            low_level_failures.append(key)
        if (
            len(goals) != int(starts)
            or len(persisted.get(key, [])) != int(starts and not low_level_failed)
            or (
                not starts
                and any(
                    r["module"] in {"strategy", "helper", "task_appraisal", "outcome"}
                    for r in rows
                )
            )
        ):
            issues.append(f"{key}: actual task outcomes disagree with routing")
        requests = [
            r
            for r in rows
            if (r["module"], r["kind"], r.get("phase"))
            == ("app_plan", "request", "initial")
        ]
        oid = route.get("opportunity_id")
        try:
            packet = check_plan_calls(rows, route)
            final_goal = (goals[0] if len(goals) == 1 else route).get(
                "goal_state_after"
            )
            previous_goal = check_goal_step(
                route, final_goal, packet, previous_goal, previous_key is not None
            )
        except (KeyError, TypeError, ValueError, StopIteration) as exc:
            issues.append(f"{key}: {exc}")
            previous_key = None
            continue
        previous_key = key
        if packet is not None:
            request = requests[0]
            visible = {
                offer["opportunity_id"]: offer
                for offer in packet["available_opportunities"]
            }
            goal = packet.get("current_intention") or {}
            if set(route["opportunity_ids"]) != set(visible):
                issues.append(
                    f"{key}: visible opportunities disagree with actual Plan input"
                )
            for offered_id in visible:
                visible_hours[offered_id].add(key)
                offer = published.get(offered_id)
                if (
                    not offer
                    or any(
                        visible[offered_id].get(k) != offer.get(k)
                        for k in (
                            "visible_from_sim_hour",
                            "required_channel",
                            "source",
                            "task_family",
                            "known_deadline_sim_hour",
                        )
                    )
                    or offer["visible_from_sim_hour"] > packet["monotonic_sim_hour"]
                    or (offer["talkingdata_day"], offer["hour"]) > key
                ):
                    issues.append(f"{key}: unavailable opportunity in observation")
            if action in {
                "engage_goal",
                "continue_goal",
                "defer_goal",
                "drop_goal",
            } and (not oid or oid not in visible and oid != goal.get("opportunity_id")):
                issues.append(
                    f"{key}: task started without an observed opportunity or goal"
                )
            if key[0] == 5 and not technical:
                episodes = {
                    ep["episode_id"]: ep
                    for ep in packet["recent_task_episodes"]
                    if ep.get("episode_id")
                }
                for episode_id in episodes.keys() & source_episodes.keys():
                    prior = source_episodes[episode_id]
                    if all(
                        episodes[episode_id].get(k) == prior.get(k)
                        for k in (
                            "task_id",
                            "outcome_type",
                            "strategy_type",
                            "support_delivery_status",
                            "requested_strategy_type",
                            "help_used",
                        )
                    ) and (
                        not prior.get("support_request_id")
                        or episodes[episode_id].get("support_request_id")
                        == prior["support_request_id"]
                    ):
                        day5_memory.append(
                            dict(
                                episode_id=episode_id,
                                call_id=request["call_id"],
                                day5_hour=key[1],
                                executed_choice=action,
                            )
                        )
        if technical:
            continue
        choices[action] += 1
        if oid:
            by_opportunity[oid].append(
                {
                    "day": key[0],
                    "hour": key[1],
                    "action": action,
                    "next_review_at_sim_hour": intent.get("next_review_at_sim_hour"),
                }
            )
            last_goal_state[oid] = (goals[0] if goals else route).get(
                "goal_state_after"
            )
        if starts and len(goals) == 1 and len(persisted.get(key, [])) == 1:
            (outcome,) = goals
            (db,) = persisted[key]
            if (
                not oid
                or outcome["opportunity_id"] != oid
                or route.get("task_id") != db["task_id"]
                or any(
                    outcome.get(k) != db.get(k)
                    for k in ("task_id", "episode_id", "outcome_type", "strategy_type")
                )
                or outcome.get("support_delivery_status")
                != db.get("support_delivery_status")
            ):
                issues.append(
                    f"{key}: routed opportunity, outcome and database disagree"
                )
            task_ids.add(db["task_id"])
            strategies[db["strategy_type"]] += 1
            outcome_counts[db["outcome_type"]] += 1
            support_status[db["support_delivery_status"]] += 1
            operations += int(db["outcome_type"] != "avoid_without_attempt")
            help_requests += int(bool(db.get("support_request_id")))
            if key[0] == 4:
                source_episodes[db["episode_id"]] = db
    if scheduled:
        offered = Counter(
            (row["talkingdata_day"], row["hour"])
            for row in published.values()
            if row.get("source") == "scheduled_login"
        )
        if offered != {(4, 9): 1, (5, 9): 1}:
            issues.append(
                "scheduled opportunities must be published exactly once at D4/D5 09:00"
            )
    if low_level_failures:
        issues.append(
            "technical failure in low-level execution; no behavioral outcome attributed"
        )
    valid = sum(choices.values())
    if not valid and error_hours >= expected:
        cross_day = "technical_failure"
    elif issues:
        cross_day = "missing_evidence"
    elif day5_memory:
        cross_day = "verified"
    elif source_episodes:
        cross_day = "missing_evidence"
        issues.append(
            "no day-four result linked to an actual day-five Plan input and action"
        )
    elif not published and not scheduled:
        cross_day = "no_natural_opportunity"
    else:
        cross_day = "no_day4_completed_task"
    return {
        "issues": issues,
        "cross_day_status": cross_day,
        "day5_memory_examples": day5_memory,
        "published_opportunities": len(published),
        "scheduled_login_opportunities": sum(row.get("source") == "scheduled_login" for row in published.values()),
        "visible_opportunities": len(visible_hours),
        "valid_intention_decisions": sum(choices.values()),
        "choices": dict(choices),
        "distinct_tasks_entered": len(task_ids),
        "low_level_decisions": sum(strategies.values()),
        "operations_started": operations,
        "help_requests": help_requests,
        "strategies": dict(strategies),
        "outcomes": dict(outcome_counts),
        "support_delivery": dict(support_status),
        "technical_failure_hours": sorted(error_hours),
        "low_level_technical_failure_hours": low_level_failures,
        "opportunities": [
            {
                "opportunity_id": oid,
                "source": row.get("source"),
                "published": [row["talkingdata_day"], row["hour"]],
                "goal_at_end": last_goal_state.get(oid),
                "visible_hours": sorted(visible_hours[oid]),
                "choices": by_opportunity[oid],
            }
            for oid, row in published.items()
        ],
    }


def audit_intention_run(
    folder, trace, conn, exp_id, agent, group, world, expected, errors, *, records=None
):
    snapshot = json.loads((folder / "resolved_config.json").read_text())
    code_hash = sha256((folder / "experiment_source.zip").read_bytes()).hexdigest()
    if (
        snapshot["source_sha256"] != code_hash
        or snapshot["runtime"]["proto_hourly_intention_mode"] != "opportunity_v1"
        or snapshot["settings"]["PROTO_HOURLY_INTENTION_MODE"] != "opportunity_v1"
    ):
        raise ValueError("source archive or mode does not match the run snapshot")
    if records is None:
        records = []
        for path in sorted(trace.glob("llm-requests-*.jsonl")):
            with path.open() as handle:
                for line in handle:
                    row = json.loads(line)
                    if (row.get("group_id"), row.get("world"), str(row.get("agent_id"))) == (group, world, agent):
                        records.append(row)
    audited_modules = {"hourly_intention", "app_plan", "strategy", "helper", "task_appraisal", "outcome"}
    records = [row for row in records if row["module"] in audited_modules]
    table = attempt_rows_table_name(exp_id)
    attempts = defaultdict(list)
    for day, tick, task, strategy, outcome, raw in conn.execute(
        f"SELECT day,t,task_id,strategy_type,outcome_type,payload_json FROM {table} WHERE agent_id=? AND day>=3",
        (agent,),
    ):
        payload = json.loads(raw)
        attempts[(day + 1, int(tick) // 3600)].append(
            dict(
                task_id=task,
                strategy_type=strategy,
                outcome_type=outcome,
                episode_id=payload["episode_id"],
                support_delivery_status=payload.get("support_delivery_status"),
                support_request_id=payload.get("support_request_id"),
                requested_strategy_type=payload.get("requested_strategy_type"),
                help_used=payload.get("outcome", {}).get("help_used"),
            )
        )
    scheduled = snapshot["runtime"]["proto_scheduled_login_hour"] is not None
    return audit_hours(records, attempts, expected, errors, scheduled, code_hash)
