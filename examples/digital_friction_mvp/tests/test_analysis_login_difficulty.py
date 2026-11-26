import json
import sqlite3

import pytest

from analysis_login_difficulty import _audit_day, analyze_study, daily_summary
from check_scheduled_login import FAMILY, PREFIX
from proto.llm_psychology import _sanitize_strategy_deliberation


def design():
    return {
        "seeds": [101], "profile_count": 1, "devices": [{"rank": 1, "device_id": "dev", "profile_id": "p1"}],
        "exposure_days": [4, 5, 6], "probe_day": 7, "difficulty_increment": .2, "scheduled_hour": 9,
        "arms": ["standard", "elevated"],
        "runs": [{"seed": 101, "arm": arm, "group": arm, "dir": arm} for arm in ("standard", "elevated")],
    }


def test_missing_planned_runs_do_not_report_zero_avoidance(tmp_path):
    (tmp_path / "design.json").write_text(json.dumps(design()))
    sqlite3.connect(tmp_path / "state.db").close()
    report = analyze_study(tmp_path, tmp_path / "state.db")
    assert not report["complete"] and len(report["issues"]) == 2
    probe = report["days"]["7"]
    assert probe["planned_pairs"] == 1 and probe["observed_pairs"] == 0
    assert probe["paired_metrics"]["avoid"]["planned_sample_difference"] is None
    assert probe["paired_metrics"]["avoid"]["observed_elevated_minus_standard"] is None


def _first_and_retry(conn, *, fallback=False):
    task_id = PREFIX + "first"
    weights = {"attempt_self": .3, "seek_help_then_attempt": .2, "avoid": .5}
    source = "rule_fallback_invalid_schema" if fallback else "hybrid_blended"
    status = "invalid_schema" if fallback else "ok"
    score = {"attempt_self_score": .3, "seek_help_score": .2, "avoid_score": .5, "dominant_strategy": "avoid",
             "judge_confidence": .88, "reason": "Fixture."}
    result, _ = _sanitize_strategy_deliberation(score)
    task = {"task_family": FAMILY, "task_id": task_id, "difficulty": .69}
    rows = []
    conn.execute("CREATE TABLE attempts(agent_id,day,t,task_id,strategy_type,outcome_type,payload_json)")
    for idx, action in enumerate(("avoid", "attempt_self")):
        tick = 32401 + 3600 * idx
        clock = dict(task_id=task_id, task_family=FAMILY, hour=9+idx, simulation_day=6, talkingdata_day=7,
                     tick_seconds=tick, tick_id=f"t{idx}")
        if idx == 0:
            rows.append(dict(clock, module="task_schedule", kind="scheduled_login", scheduled_hour=9,
                             nominal_difficulty_delta=0, assigned_difficulty=.69, difficulty_arm="elevated"))
        query = dict(clock, module="strategy", call_id="call", query_id="query")
        rows.append(dict(query, kind="request", phase="initial",
                         messages=[{"role": "user", "content": json.dumps({"task": task})}]))
        rows.append(dict(query, kind="response", raw="{}" if fallback else json.dumps(score)))
        rows.append(dict(query, kind="parse", status=status, parsed=None if fallback else result))
        rows.append(dict(clock, module="strategy", kind="sample", draw=.9 if idx == 0 else .1,
                         action=action, final_weights=weights))
        outcome = "avoid_without_attempt" if idx == 0 else "success_self"
        decision = dict(clock, module="task", kind="decision", action=action, outcome=outcome, episode_id=str(idx),
                        status="completed", support_delivery_status="not_requested", requested_strategy_type=action,
                        requested_weights=weights, help_used=False,
                        strategy_source=source, strategy_status=status, rule_weights=weights)
        rows.append(decision)
        saved = dict(task=task, episode_id=str(idx), requested_strategy_type=action,
                     requested_strategy={"strategy_type": action, "weights": weights}, outcome={"help_used": False}, support_delivery_status="not_requested",
                     support_request={}, support_response={}, profile_summary={"age": 70},
                     update={"helplessness_after": 51}, strategy_deliberation={
                         "source": source, "status": status, "rule_weights": weights,
                         "llm_weights": None if fallback else weights,
                     })
        conn.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?)",
                     (1, 6, tick, task_id, action, outcome, json.dumps(saved)))
    return rows


@pytest.mark.parametrize("fallback", [False, True])
def test_primary_is_first_draw_and_retries_and_missing_model_scores_stay_separate(fallback):
    d = design()
    with sqlite3.connect(":memory:") as conn:
        trace = _first_and_retry(conn, fallback=fallback)
        first = _audit_day(conn, "attempts", 1, 7, trace, {"arm": "elevated"}, d)
        assert first["action"] == "avoid" and [r["action"] for r in first["retries"]] == ["attempt_self"]
        result = daily_summary([dict(standard=first, elevated=first, same_tick=True)])
        assert result["paired_metrics"]["avoid"]["planned_sample_difference"] == 0
        assert result["paired_metrics"]["llm_p_avoid"]["paired_n"] == int(not fallback)
        assert result["arm_totals"]["elevated"]["retry_n"] == 1
        trace[0]["assigned_difficulty"] = .89
        with pytest.raises(ValueError, match="prompt"):
            _audit_day(conn, "attempts", 1, 7, trace, {"arm": "elevated"}, d)


def test_help_failure_preserves_already_sampled_primary_action():
    with sqlite3.connect(":memory:") as conn:
        rows = _first_and_retry(conn)
        decision = next(r for r in rows if r["kind"] == "decision")
        decision.update(status="technical_failure", requested_action="seek_help_then_attempt", action=None, outcome=None)
        sample = next(r for r in rows if r["kind"] == "sample")
        sample.update(draw=.4, action="seek_help_then_attempt")
        observed = _audit_day(conn, "attempts", 1, 7, rows, {"arm": "elevated"}, design())
        assert observed["avoid"] == 0 and observed["delivery"] == "technical_failure"
        assert observed["outcome"] is None
