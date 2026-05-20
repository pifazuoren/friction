from collections import Counter

from proto.task_assignment import (
    TASK_LIBRARY,
    evaluate_mobile_entry_for_agent,
    is_task_window_tick,
    select_task_for_agent,
    skipped_mobile_entry_decision,
)


TASK_WINDOW_MORNING = 9 * 60 * 60
TASK_WINDOW_AFTERNOON = 14 * 60 * 60
TASK_WINDOW_EVENING = 19 * 60 * 60
NON_WINDOW_TICK = 8 * 60 * 60


def test_task_assignment_only_uses_fixed_pool(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    task = select_task_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=float(TASK_WINDOW_MORNING),
        env={"friction_level": 1, "complexity_level": 1, "risk_level": 1},
    )
    assert task is not None
    families = {item["task_family"] for item in TASK_LIBRARY}
    assert task.task_family in families
    assert task.friction_type in {
        "verification",
        "form_complexity",
        "payment_risk_popup",
        "information_overload",
    }

def test_task_assignment_returns_none_outside_windows(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    task = select_task_for_agent(
        agent_id=3,
        day=1,
        tick_seconds=float(NON_WINDOW_TICK),
        env={},
    )
    assert task is None


def test_is_task_window_tick_matches_fixed_windows() -> None:
    assert is_task_window_tick(float(TASK_WINDOW_MORNING)) is True
    assert is_task_window_tick(float(TASK_WINDOW_MORNING + 1)) is True
    assert is_task_window_tick(float(TASK_WINDOW_AFTERNOON + 120)) is True
    assert is_task_window_tick(float(TASK_WINDOW_AFTERNOON)) is True
    assert is_task_window_tick(float(TASK_WINDOW_EVENING)) is True
    assert is_task_window_tick(float(TASK_WINDOW_EVENING - 119)) is True
    assert is_task_window_tick(float(NON_WINDOW_TICK)) is False
    assert is_task_window_tick(float(TASK_WINDOW_MORNING + 121)) is False


def test_task_assignment_accepts_runtime_tick_offset_within_tolerance(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    exact_task = select_task_for_agent(
        agent_id=3,
        day=0,
        tick_seconds=float(TASK_WINDOW_MORNING),
        env={},
    )
    offset_task = select_task_for_agent(
        agent_id=3,
        day=0,
        tick_seconds=float(TASK_WINDOW_MORNING + 1),
        env={},
    )
    assert exact_task is not None
    assert offset_task is not None
    assert offset_task.task_id == exact_task.task_id
    assert offset_task.task_family == exact_task.task_family


def test_task_assignment_is_deterministic_for_same_window(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    task_a = select_task_for_agent(
        agent_id=3,
        day=1,
        tick_seconds=float(TASK_WINDOW_MORNING),
        env={},
    )
    task_b = select_task_for_agent(
        agent_id=3,
        day=1,
        tick_seconds=float(TASK_WINDOW_MORNING),
        env={},
    )
    assert task_a is not None
    assert task_b is not None
    assert task_a.task_id == task_b.task_id


def test_task_assignment_is_shared_across_worlds(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    low_friction_task = select_task_for_agent(
        agent_id=4,
        day=2,
        tick_seconds=float(TASK_WINDOW_AFTERNOON),
        env={
            "friction_level": 1,
            "malicious_friction_level": 1,
            "complexity_level": 1,
            "risk_level": 1,
            "accessibility_level": 1,
        },
    )
    high_friction_task = select_task_for_agent(
        agent_id=4,
        day=2,
        tick_seconds=float(TASK_WINDOW_AFTERNOON),
        env={
            "friction_level": 3,
            "malicious_friction_level": 3,
            "complexity_level": 3,
            "risk_level": 3,
            "accessibility_level": 0,
        },
    )
    assert low_friction_task is not None
    assert high_friction_task is not None
    assert low_friction_task.task_family == high_friction_task.task_family
    assert low_friction_task.friction_type == high_friction_task.friction_type
    assert high_friction_task.difficulty > low_friction_task.difficulty


def test_task_assignment_cycles_evenly_over_four_days(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    counts: Counter[str] = Counter()
    for day in range(4):
        for tick_seconds in (
            TASK_WINDOW_MORNING,
            TASK_WINDOW_AFTERNOON,
            TASK_WINDOW_EVENING,
        ):
            task = select_task_for_agent(
                agent_id=2,
                day=day,
                tick_seconds=float(tick_seconds),
                env={},
            )
            assert task is not None
            counts[task.task_family] += 1
    assert set(counts) == {str(template["task_family"]) for template in TASK_LIBRARY}


def test_mobile_entry_decision_distinguishes_skipped_eval() -> None:
    decision = skipped_mobile_entry_decision(
        agent_id=1,
        day=0,
        tick_seconds=123.0,
        entry_mode="mobile_intention_rule",
    )
    assert decision.entry_evaluated is False
    assert decision.entry_status == "skipped_eval"
    assert decision.task is None
    assert decision.audit["is_avoidance"] is False


def test_mobile_entry_no_mobile_action_is_noop(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"no_mobile_action":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    decision = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
        confidence_threshold=0.70,
    )
    assert decision.entry_evaluated is True
    assert decision.entry_status == "no_mobile_action_noop"
    assert decision.task is None
    assert decision.task_generated is False
    assert decision.audit["is_avoidance"] is False
    assert decision.audit["does_not_update_psychology"] is True


def test_mobile_entry_communicate_is_not_help(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"communicate_or_seek_help":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    decision = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
        confidence_threshold=0.70,
    )
    assert decision.entry_status == "communicate_context_only"
    assert decision.task is None
    assert decision.audit["is_help_action"] is False
    assert decision.audit["helper_triggered"] is False


def test_mobile_entry_low_confidence_mapping_noops(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    mapping = tmp_path / "mapping.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"check_information":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    mapping.write_text(
        '{"mobile_intention_mapping":{"check_information":{"mapping_confidence":0.40}}}',
        encoding="utf-8",
    )
    decision = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
        mapping_path=str(mapping),
        confidence_threshold=0.70,
    )
    assert decision.entry_status == "low_confidence_mapping_noop"
    assert decision.task is None


def test_mobile_entry_generates_unique_task_ids_for_same_family(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"check_information":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    task_a = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    ).task
    task_b = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=7200.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    ).task
    assert task_a is not None
    assert task_b is not None
    assert task_a.task_family == task_b.task_family
    assert task_a.task_id != task_b.task_id


def test_mobile_entry_decision_is_world_neutral_for_selection(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"use_payment_or_finance":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    low_world = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={
            "friction_level": 0,
            "risk_level": 0,
            "malicious_friction_level": 0,
            "accessibility_level": 3,
        },
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )
    high_world = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={
            "friction_level": 3,
            "risk_level": 3,
            "malicious_friction_level": 3,
            "accessibility_level": 0,
        },
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )
    assert low_world.selected_mobile_intention == high_world.selected_mobile_intention
    assert low_world.entry_status == high_world.entry_status
    assert low_world.mapped_task_family == high_world.mapped_task_family
    assert low_world.task_generated == high_world.task_generated
    assert low_world.task is not None
    assert high_world.task is not None
    assert high_world.task.difficulty > low_world.task.difficulty


def test_mobile_entry_rejects_validation_artifact_path(tmp_path) -> None:
    validation = tmp_path / "elder_validation_artifact.json"
    validation.write_text("{}", encoding="utf-8")
    try:
        evaluate_mobile_entry_for_agent(
            agent_id=1,
            day=0,
            tick_seconds=3600.0,
            env={},
            calibration_path=str(validation),
        )
    except ValueError as exc:
        assert "validation" in str(exc)
    else:
        raise AssertionError("validation artifact path should be rejected")


def test_mobile_entry_rejects_artifact_marked_as_validation(tmp_path) -> None:
    artifact = tmp_path / "heldout_targets.json"
    artifact.write_text('{"uses_validation_data":true}', encoding="utf-8")
    try:
        evaluate_mobile_entry_for_agent(
            agent_id=1,
            day=0,
            tick_seconds=3600.0,
            env={},
            calibration_path=str(artifact),
        )
    except ValueError as exc:
        assert "uses_validation_data" in str(exc)
    else:
        raise AssertionError("validation-marked artifact should be rejected")


def test_mobile_entry_rerank_override_must_be_top_k(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{'
        '"check_information":0.6,'
        '"use_payment_or_finance":0.4'
        '}}, "uses_validation_data":false}',
        encoding="utf-8",
    )

    decision = evaluate_mobile_entry_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=3600.0,
        env={},
        entry_mode="mobile_intention_llm_rerank_online_mc",
        calibration_path=str(calibration),
        selected_intention_override="use_payment_or_finance",
        rerank_audit_payload={
            "rerank_run_id": "run-1",
            "rerank_schedule_role": "read",
            "rerank_parse_status": "ok",
            "rerank_confidence": 0.9,
        },
        rerank_top_k=2,
    )

    assert decision.selected_mobile_intention == "use_payment_or_finance"
    assert decision.task is not None
    assert decision.task.task_family == "payment_risk_confirmation"
    assert decision.audit["rule_selected_mobile_intention"] in {
        "check_information",
        "use_payment_or_finance",
    }
    assert decision.audit["rerank_selected_mobile_intention"] == "use_payment_or_finance"
    assert decision.audit["llm_drives_real_entry"] is True

    try:
        evaluate_mobile_entry_for_agent(
            agent_id=1,
            day=0,
            tick_seconds=3600.0,
            env={},
            entry_mode="mobile_intention_llm_rerank_online_mc",
            calibration_path=str(calibration),
            selected_intention_override="login_or_verify_account",
            rerank_top_k=2,
        )
    except ValueError as exc:
        assert "top-k" in str(exc)
    else:
        raise AssertionError("rerank override outside top-k should be rejected")
