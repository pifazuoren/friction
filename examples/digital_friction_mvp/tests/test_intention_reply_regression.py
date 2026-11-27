"""Synthetic fixture for the structure of historical, failed opportunity-mode traces."""

import asyncio
from hashlib import sha256
import json

import pytest

from check_intention_reply_regression import ArchiveError, check_archive, replay_members
from probe_hourly_intention import HOUR, NEEDS, SIM_HOUR, load_history, login_offer
from proto.app_entry.habit_memory import build_rollout_intensity_profile
from proto.app_entry.rollout import build_rollout_input_packet


def write_failed_fixture(folder):
    ledger, offer = login_offer()[1:]
    history = load_history(None)
    intensity = build_rollout_intensity_profile(history.habits, hour=HOUR, absolute_cap=8)
    cap = intensity["active_exposure_cap"]
    inputs = build_rollout_input_packet(
        simulation_day=4,
        talkingdata_day=5,
        hour=HOUR,
        stable_profile={},
        habit_memory=history.habits,
        recent_rollout_rows=[],
        recent_task_episodes=[],
        latest_reflection={},
        helplessness=50,
        trust=50,
        avoidance=50,
        environment={},
        intensity_profile=intensity,
        hourly_intention_mode="opportunity_v1",
        available_opportunities=ledger.visible(SIM_HOUR),
        goal_review_due=True,
    )
    context = {
        "digital_needs": NEEDS.to_dict(include_audit=False),
        "candidate_app_contexts": {"communication_social_context": 1.0, offer["required_channel"]: 0.0},
        "intensity_profile": intensity,
        "inputs": inputs,
        "prompt_version": "app_entry_plan_v3",
        "runtime_output_constraints": {"minimum_confidence": 0.5, "active_exposure_maximum": cap},
    }
    messages = [
        {"role": "system", "content": "Archived instructions"},
        {"role": "user", "content": "Return JSON.\n" + json.dumps(context)},
    ]
    initial = '{"inputs":{"simulation_day":4'
    repair = json.dumps(
        {
            "active": True,
            "app_context_counts": {"communication_social_context": cap + 1},
            "attitude": 0.5,
            "subjective_norm": 0.5,
            "perceived_control": 0.5,
            "confidence": 0.8,
            "reasoning": "fixture",
            "intent": {
                "kind": "engage_goal",
                "opportunity_id": offer["opportunity_id"],
                "goal_id": None,
                "next_review_at_sim_hour": None,
                "reason": "fixture",
            },
        }
    )
    member = {"mode": "opportunity_v1", "pair_id": "contrast-01", "member": "A", "condition": "success"}
    hashes = [sha256(value.encode()).hexdigest()[:16] for value in (initial, repair)]
    decision = {
        **member,
        "plan_valid": False,
        "technical_failure": f"last_raw_response_hash={hashes[0]}; last_repair_response_hash={hashes[1]}",
        "task_admitted": False,
        "policy_choice": None,
        "choice_source": "technical_failure",
        "requests": 2,
        "repairs": 1,
        "transport_errors": [],
    }
    (folder / "experiment_source.zip").write_bytes(b"source fixture")
    (folder / "design.json").write_text(
        json.dumps({"source_archive_sha256": sha256(b"source fixture").hexdigest()})
    )
    (folder / "summary.json").write_text(
        json.dumps(
            {
                "conditions": {
                    "opportunity_v1": {"planned": 1, "recorded": 1, "valid": 0, "technical_failures": 1}
                }
            }
        )
    )
    (folder / "request_manifest.json").write_text(json.dumps([member]))
    (folder / "decisions.jsonl").write_text(json.dumps(decision) + "\n")
    (folder / "stimuli.json").write_text(
        json.dumps({"opportunity_v1": {"success": {"messages": messages}}})
    )
    (folder / "trace").mkdir()
    rows = []
    for phase, raw in (("initial", initial), ("repair", repair)):
        head = {
            **member,
            "kind": "contrast",
            "module": "app_plan",
            "call_id": phase + "-id",
            "query_id": "same-query",
            "phase": phase,
        }
        rows.extend(
            (
                {**head, "messages": messages},
                {**head, "raw": raw},
                {**head, "parsed": None, "status": "invalid_schema"},
            )
        )
    trace = folder / "trace/llm-requests-1.jsonl"
    trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return trace


def test_offline_checker_replays_both_invalid_responses_and_valid_boundary_controls(tmp_path):
    write_failed_fixture(tmp_path)
    result = asyncio.run(check_archive(tmp_path, expected=1))
    assert (
        result["rejected_archived_initial_repair_pairs"]
        == result["rejected_historical_repairs_replayed_individually"]
        == 1
    )
    assert result["online_requests"] == result["new_model_choices_measured"] == 0


def test_truncated_or_tampered_raw_response_is_not_counted_as_a_passing_regression(tmp_path):
    trace = write_failed_fixture(tmp_path)
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    rows[1]["raw"] += "altered"
    trace.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ArchiveError, match="digest mismatch"):
        list(replay_members(tmp_path, 1))
    rows.pop(1)
    trace.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ArchiveError, match="Incomplete call"):
        list(replay_members(tmp_path, 1))
