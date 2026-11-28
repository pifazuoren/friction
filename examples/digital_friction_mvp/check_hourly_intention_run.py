"""Verify opportunity-mode routing against actual Plan requests, traces and SQLite outcomes."""

from collections import Counter, defaultdict
from hashlib import sha256
import json

from check_hourly_choice_evidence import check_phone_choice, check_retry_review, request_payload
from proto.app_entry import PHONE_USE_NEEDS_V5, RESIDENT_DECISION_PLAN_VERSION
from proto.app_entry.needs import PHONE_USE_NEEDS_VERSION
from proto.retry_review import RETRY_REVIEW_VERSIONS
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


_REQUEST_FACTS = ("requested_support_style", "requested_support_style_source")
_RESPONSE_FACTS = ("support_style", "instruction_quality", "autonomy_preservation", "proxy_completion_level")


def support_exchange_facts(payload):
    """Read measured preferences and helper actions from the original exchange in SQLite."""
    request = payload.get("support_request") or {}
    response = payload.get("support_response") or {}
    if not any(request.get(key) is not None for key in _REQUEST_FACTS):
        if any(payload.get(key) is not None for key in _REQUEST_FACTS):
            raise ValueError("support preference lacks its recorded request")
        return {}  # Older runs did not ask the resident for a support preference.
    return {
        **{key: request.get(key) for key in _REQUEST_FACTS},
        **{key: response.get(key) for key in _RESPONSE_FACTS},
    }


def support_exchange_matches(prior, recalled):
    # Unmeasured legacy events have no exchange fields. A measured missing value
    # must stay absent or null, so a failed model judgment cannot become a preference.
    return all(recalled.get(k) == prior[k] for k in (*_REQUEST_FACTS, *_RESPONSE_FACTS) if k in prior)


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
        if (failed and len(events) == 1 and events[0]["kind"] == "channel_unavailable"
                and route.get("retry_review_version") in RETRY_REVIEW_VERSIONS):
            return None  # The upstream phone decision and the failure marker are checked together.
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


def memory_window(source_day, target_day, persisted, valid_plans):
    """Compare a completed SQLite episode with the actual input to an accepted Plan."""
    source = {r["episode_id"]: r for (day, _), entries in persisted.items() if day == source_day
              for r in entries}
    matches = []
    issues = []
    for hour, call_id, action, episodes in valid_plans:
        for recalled in episodes:
            eid = recalled.get("episode_id")
            prior = source.get(eid)
            if prior is None:
                continue
            if not support_exchange_matches(prior, recalled):
                issues.append(f"day {target_day} hour {hour}: recalled support exchange differs from SQLite for {eid}")
                continue
            facts = ("task_id", "outcome_type", "strategy_type", "support_delivery_status",
                     "requested_strategy_type", "help_used")
            if (any(recalled.get(k) != prior.get(k) for k in facts)
                    or (recalled.get("support_request_id") or None) != (prior.get("support_request_id") or None)):
                issues.append(f"day {target_day} hour {hour}: recalled task facts differ from SQLite for {eid}")
                continue
            matches.append({"episode_id": eid, "call_id": call_id, "target_hour": hour, "executed_choice": action})
    if issues:
        status = "mismatch"
    elif not source:
        status = "no_source_task"
    elif not valid_plans:
        status = "no_valid_plan"
    elif matches:
        status = "verified"
    else:
        status = "not_observed"
    return {"status": status, "source_completed_tasks": len(source), "valid_target_plans": len(valid_plans),
            "matched_episode_ids": sorted({r["episode_id"] for r in matches}),
            "first_evidence": next(iter(matches), None)}, matches, issues


def audit_hours(records, persisted, expected, error_hours, scheduled, code_hash, *,
                login_hour=9, login_days=(4, 5), require_strategy=False, require_resident_choices=False,
                phone_use_needs_version=None, replay_habit=None, paired_environment_seed=None):
    hours = defaultdict(list)
    published = {}
    visible_hours = defaultdict(set)
    by_opportunity = defaultdict(list)
    issues = [f"{key}: persisted task outside the expected window" for key in persisted if key not in expected]
    valid_plans = defaultdict(list)
    choices = Counter()
    strategies = Counter()
    outcome_counts = Counter()
    support_status = Counter()
    phone_choices, retry_reviews = Counter(), Counter()
    phone_recommendations, resolved_phone_choices, executed_phone_choices = Counter(), Counter(), Counter()
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
            if require_resident_choices or route.get("retry_review_version") is not None:
                if route.get("retry_review_version") not in RETRY_REVIEW_VERSIONS:
                    raise ValueError("missing or unknown resident retry review version")
                phone, resolution = check_phone_choice(
                    rows, route, requests[0] if requests else None, expected_version=phone_use_needs_version,
                    replay_habit=replay_habit, paired_environment_seed=paired_environment_seed,
                )
                if phone is not None:
                    phone_choices[phone] += 1
                    if resolution is not None:
                        phone_recommendations[resolution["llm_recommendation"]] += 1
                        resolved_phone_choices[resolution["final_choice"]] += 1
                        execution = action if not technical else (
                            phone if phone == "use_phone_channel_unavailable" else "plan_technical_failure"
                        )
                        executed_phone_choices[execution] += 1
                    elif phone_use_needs_version == PHONE_USE_NEEDS_V5:
                        executed_phone_choices["needs_unmeasured"] += 1
                retry = check_retry_review(rows, route, goals, persisted.get(key, []), packet)
                if retry is not None:
                    retry_reviews[retry] += 1
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
            if not technical:
                valid_plans[key[0]].append((key[1], request["call_id"], action, packet["recent_task_episodes"]))
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
            if require_strategy and not any((r["module"], r["kind"], r.get("phase")) == ("strategy", "request", "initial")
                                            for r in rows):
                issues.append(f"{key}: completed task missing actual strategy request")
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
    if scheduled:
        offered = Counter(
            (row["talkingdata_day"], row["hour"])
            for row in published.values()
            if row.get("source") == "scheduled_login"
        )
        scheduled_slots = {(day, login_hour): 1 for day in login_days if (day, login_hour) in expected}
        if offered != scheduled_slots:
            issues.append(f"scheduled opportunities must be published exactly once at {sorted(scheduled_slots)}")
    if low_level_failures:
        issues.append(
            "technical failure in low-level execution; no behavioral outcome attributed"
        )
    target_days = {day for day, _ in expected}
    transitions = {}
    earlier_day7 = {}
    day5_memory = []
    for target in sorted(target_days):
        if target < 5:
            continue
        sources = [target - 1] if target != 7 else [target - 1, 4, 5]
        for source in sources:
            window, matches, mismatches = memory_window(source, target, persisted, valid_plans[target])
            window["source_low_level_technical_failure_hours"] = sorted(h for d, h in low_level_failures if d == source)
            window["target_technical_failure_hours"] = sorted(h for d, h in error_hours if d == target)
            if window["status"] == "no_source_task" and window["source_low_level_technical_failure_hours"]:
                window["status"] = "source_technical_failure"
            issues.extend(mismatches)
            collection = transitions if source == target - 1 else earlier_day7
            collection[f"D{source}->D{target}"] = window
            if target == 5:
                day5_memory = [{"episode_id": r["episode_id"], "call_id": r["call_id"],
                                "day5_hour": r["target_hour"], "executed_choice": r["executed_choice"]} for r in matches]
    valid = sum(choices.values())
    if not valid and error_hours >= expected:
        cross_day = "technical_failure"
    elif issues:
        cross_day = "missing_evidence"
    elif day5_memory:
        cross_day = "verified"
    elif transitions.get("D4->D5", {}).get("source_completed_tasks"):
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
        "memory_transitions": transitions,
        "day7_earlier_memory": earlier_day7,
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
        **({"phone_use_decision_counts": dict(phone_choices), "retry_review_counts": dict(retry_reviews)}
           if require_resident_choices or phone_choices or retry_reviews else {}),
        **({"phone_use_llm_recommendation_counts": dict(phone_recommendations),
            "phone_use_resolved_counts": dict(resolved_phone_choices),
            "free_hour_execution_counts": dict(executed_phone_choices)}
           if phone_use_needs_version == PHONE_USE_NEEDS_V5 or phone_recommendations else {}),
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
    audited_modules = {"hourly_intention", "app_plan", "strategy", "helper", "task_appraisal", "outcome",
                       "app_needs", "retry_review"}
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
                **({"retry_review": payload["retry_review"]} if "retry_review" in payload else {}),
                **support_exchange_facts(payload),
            )
        )
    runtime = snapshot["runtime"]
    phone_version = runtime.get("proto_app_entry_phone_use_needs_version")
    replay_habit = None
    if (phone_version in (PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V5)
            and runtime.get("proto_app_entry_plan_prompt_version") == RESIDENT_DECISION_PLAN_VERSION):
        status_table = f"as_{exp_id.replace('-', '_')}_mvp_status"
        handoff = conn.execute(f"SELECT status_json FROM {status_table} WHERE agent_id=? AND day=3 ORDER BY t DESC LIMIT 1",
                               (agent,)).fetchone()
        if not handoff:
            raise ValueError("missing day-3 handoff for the device history comparison")
        replay_habit = json.loads(handoff[0])["proto_day4_replay_snapshot"]["app_entry_habit_memory"]
    login_hour = runtime["proto_scheduled_login_hour"]
    login_days = (4, 5, 6, 7) if runtime.get("proto_login_difficulty_arm") else (4, 5)
    return audit_hours(records, attempts, expected, errors, login_hour is not None, code_hash,
                       login_hour=login_hour, login_days=login_days,
                       phone_use_needs_version=phone_version, replay_habit=replay_habit,
                       paired_environment_seed=runtime.get("proto_paired_environment_seed"),
                       require_resident_choices=runtime.get("proto_app_entry_plan_prompt_version") == RESIDENT_DECISION_PLAN_VERSION,
                       require_strategy=bool(runtime.get("proto_llm_strategy_deliberation_enabled")))
