import json
import sqlite3

import pytest

from check_scheduled_login import FAMILY, PREFIX, recalled_login_attempts, verify_day
from proto.llm_psychology import _sanitize_strategy_deliberation
from proto.memory.packet import compact_recent_episodes


def test_recalled_login_can_be_deferred_retry_in_bounded_prompt():
    first = dict(episode_id="09", day=3, tick_seconds=32401, task_id=PREFIX + "day4", task_family=FAMILY,
                 strategy_type="avoid", outcome_type="avoid_without_attempt", help_used=False)
    retry = dict(first, episode_id="10", tick_seconds=36001, strategy_type="seek_help_then_attempt",
                 outcome_type="success_with_help", help_used=True)
    later = [dict(first, episode_id=str(hour), task_id="another-login", tick_seconds=3600 * hour + 1)
             for hour in range(11, 15)]
    episodes = {r["episode_id"]: r for r in (first, retry, *later)}
    visible = compact_recent_episodes(list(episodes.values()))
    assert first["episode_id"] not in [r["episode_id"] for r in visible]
    assert recalled_login_attempts(first, episodes, visible) == [retry]
    assert recalled_login_attempts(first, episodes, [retry, first]) == [first, retry]
    with pytest.raises(ValueError, match="no matching"):
        recalled_login_attempts(first, episodes, later)
    with pytest.raises(ValueError, match="disagrees"):
        recalled_login_attempts(first, episodes, [first, dict(retry, help_used=False)])


@pytest.mark.parametrize("inconsistent", [None, "database_score", "model_reply", "unsupported_help"])
def test_scheduled_login_verifies_actual_judgment_and_sample(inconsistent):
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE attempts (day INTEGER, agent_id INTEGER, t REAL, task_id TEXT, payload_json TEXT)")
        task_id = PREFIX + "4"
        action = "seek_help_then_attempt" if inconsistent == "unsupported_help" else "attempt_self"
        episode = dict(episode_id="episode", task_id=task_id, tick_seconds=36001., task_family=FAMILY,
                       day=4, strategy_type="attempt_self", requested_strategy_type=action, help_used=False,
                       support_delivery_status="not_requested", outcome_type="failure_after_attempt")
        output = dict(attempt_self_score=.6, seek_help_score=.3, avoid_score=.1,
                      dominant_strategy="attempt_self", judge_confidence=.9, reason="Try this task.")
        parsed, _ = _sanitize_strategy_deliberation(output)
        weights = dict(attempt_self=.55, seek_help_then_attempt=.30, avoid=.15)
        payload = dict(strategy_deliberation={**parsed, "source": "hybrid_blended"},
                       requested_strategy={"weights": weights}, support_request={}, support_response={})
        if inconsistent == "database_score":
            payload["strategy_deliberation"]["attempt_self_score"] = .8
        conn.execute("INSERT INTO attempts VALUES (4,1,36001,?,?)", (task_id, json.dumps(payload)))
        task = {"task_id": task_id, "task_family": FAMILY}
        clock = dict(simulation_day=4, talkingdata_day=5, hour=10, tick_seconds=36001., tick_id="tick", **task)
        memory = [{"episode_id": "record from yesterday"}]
        packet = {"task": task, "task_relevant_memory": {"recent_task_episodes": memory}}
        trace = [
            dict(**clock, module="task_schedule", kind="scheduled_login", scheduled_hour=9),
            dict(**clock, module="task", kind="decision", status="completed", episode_id="episode", action="attempt_self",
                 outcome="failure_after_attempt", help_used=False, requested_strategy_type=action,
                 support_delivery_status="not_requested", strategy_source="hybrid_blended"),
            dict(**clock, module="strategy", kind="sample", final_weights=weights, draw=.3, action=action),
            dict(**clock, module="strategy", kind="request", query_id="query", call_id="first", phase="initial",
                 messages=[{"role": "user", "content": json.dumps(packet)}]),
            dict(**clock, module="strategy", kind="parse", query_id="query", call_id="second", status="ok_repaired",
                 parsed=parsed),
            dict(**clock, module="strategy", kind="response", query_id="query", call_id="second",
                 raw=json.dumps({**output, "attempt_self_score": .8} if inconsistent == "model_reply" else output)),
        ]
        if inconsistent:
            with pytest.raises(ValueError):
                verify_day(5, conn, "attempts", 1, {"episode": episode}, trace)
        else:
            report, recalled = verify_day(5, conn, "attempts", 1, {"episode": episode}, trace)
            assert recalled == memory
            assert report["model_scores"]["attempt_self"] == .6 and report["sampled_weights"]["attempt_self"] == .55
            assert (report["initial_call_id"], report["accepted_call_id"]) == ("first", "second")
            assert (report["scheduled_hour"], report["executed_hour"]) == (9, 10)
