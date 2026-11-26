"""Exercise a complete digital task with a controlled family-helper reply."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from proto.models import AttemptStrategy, DigitalTask
from proto.support_protocol import SupportResponse, SupportTechnicalError


class FamilyHelper:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    async def provide_support(self, request):
        self.requests.append(request)
        if self.reply == "request_error":
            raise RuntimeError("simulated transport failure")
        if self.reply == "parse_failed":
            return SupportResponse.unavailable(request=request, source="llm_unavailable", audit_status=self.reply)
        if self.reply == "unavailable":
            return SupportResponse(
                request_id=request.request_id, requester_agent_id=request.requester_agent_id,
                helper_agent_id=request.helper_agent_id, confidence=0.9,
                source="llm_family_helper", audit_status="ok", rationale="The helper is busy.",
            )
        return SupportResponse.from_llm_payload(
            request=request, source="llm_family_helper", audit_status="ok",
            payload={
                "support_style": "enabling", "instruction_quality": "high",
                "autonomy_preservation": "high", "proxy_completion_level": "none",
                "emotional_tone": "patient", "response_delay": "immediate",
                "confidence": 0.9, "responded": True, "response_text": "I can guide you.",
                "rationale": "The requester keeps control.",
            },
        )


@pytest.fixture
def run_task(monkeypatch):
    from test_proto_agent_status_summary import _FakeEnvironment, _FakeStatusStore
    import proto.agent as agent_module
    from proto.state_schema import build_initial_proto_status

    config = {
        "PROTO_TASK_ENTRY_MODE": "fixed_assignment",
        "PROTO_SUPPORT_ECOLOGY_MODE": "family_helper_llm",
        "PROTO_OUTCOME_MODEL_MODE": "rule_v1",
        "PROTO_LLM_PSYCHOLOGY_MODE": "off",
        "PROTO_LLM_UNCONTROLLABILITY_MODE": "off",
        "PROTO_STREAM_EPISODE_RECORDING_ENABLED": "false",
        "PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED": "false",
        "PROTO_STREAM_ATTRIBUTION_RETRIEVAL_ENABLED": "false",
        "EXP_SEED": "101", "PARALLEL_PAIR_SEED": "101", "WORLD_NAME": "baseline_low_friction",
    }
    for key, value in config.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(agent_module, "choose_attempt_strategy", lambda **_: AttemptStrategy(
        strategy_type="seek_help_then_attempt", support_requested=True,
    ))
    data = build_initial_proto_status(digital_experience=0.5, vision_limit=0.2, past_fraud_experience=0.2)
    task = DigitalTask("help-test", "payment_risk_confirmation", "payment_risk_popup", 0.3, "daily_task", 0.7, 0)
    data.update(proto_assigned_task_json=json.dumps(task.to_dict()), family_helper_agent_id=20)
    data["digital_emotion_state"]["last_updated_day"] = 0
    agent = agent_module.DigitalHelplessnessAgent.__new__(agent_module.DigitalHelplessnessAgent)
    agent._id = 7
    agent.step_count = 0
    agent._memory = SimpleNamespace(status=_FakeStatusStore(data))
    environment = _FakeEnvironment(day=0, tick_seconds=21600.0, env={"stage_name": "steady"})
    agent._toolbox = SimpleNamespace(environment=environment, llm=None)
    return agent, agent.memory.status.data


@pytest.mark.parametrize("reply", ["request_error", "parse_failed"])
def test_technical_failure_does_not_complete_the_attempt(run_task, reply):
    agent, data = run_task
    helper = FamilyHelper(reply)
    agent.set_support_helper_registry({20: helper})
    keys = ("helplessness_score", "avoidance_tendency", "trust_in_apps", "digital_emotion_state",
            "help_effect_memory", "recent_episode_buffer", "event_log", "proto_stage_attempt_rows_json",
            "proto_assigned_task_json", "help_request_count", "success_count", "failure_count")
    before = {k: deepcopy(data.get(k)) for k in keys}
    with pytest.raises(SupportTechnicalError):
        asyncio.run(agent.forward())
    assert len(helper.requests) == 1
    signal = data["friction_step_signal"]
    assert signal["step_type"] == signal["support_delivery_status"] == "technical_failure"
    assert signal["requested_strategy_type"] == "seek_help_then_attempt"
    assert signal["support_request_id"] == helper.requests[0].request_id
    assert signal["support_ecology_status"] == reply
    assert {k: data.get(k) for k in keys} == before


@pytest.mark.parametrize(("reply", "delivery", "effective"), [
    ("unavailable", "not_delivered", "attempt_self"),
    ("enabling", "delivered", "seek_help_then_attempt"),
])
def test_forward_records_requested_and_effective_help_separately(run_task, reply, delivery, effective):
    agent, data = run_task
    helper = FamilyHelper(reply)
    agent.set_support_helper_registry({20: helper})
    asyncio.run(agent.forward())
    assert len(helper.requests) == 1
    decision = data["event_log"][-1]["decision"]
    row, = json.loads(data["proto_stage_attempt_rows_json"])
    episode, = data["recent_episode_buffer"]
    for record in (decision, row, episode):
        assert record["requested_strategy_type"] == "seek_help_then_attempt"
        assert record["strategy_type"] == effective
        assert record["support_delivery_status"] == delivery
        assert record["support_request_id"] == helper.requests[0].request_id
    help_memory = data["help_effect_memory"]["overall"]
    delivered = delivery == "delivered"
    assert episode["help_used"] is delivered
    assert episode["outcome_type"] == row["outcome_type"]
    assert help_memory["help_attempt_count"] == int(delivered)
    assert help_memory["help_success_count"] + help_memory["help_failure_count"] == int(delivered)
    assert data["help_request_count"] == 1
    if not delivered:
        assert row["outcome_type"] not in {"success_with_help", "failure_even_with_help"}


def test_declined_help_reaches_next_day_app_and_strategy_in_two_forwards(run_task, monkeypatch):
    from proto import agent as agent_module
    from proto.attempt_strategy import choose_attempt_strategy
    from test_app_entry_rollout import _habit, _needs_payload, _plan_payload
    from test_cross_day_episode_prompts import RecordingLLM

    agent, data = run_task
    agent.environment._day = 3  # TalkingData Day 4.
    helper = FamilyHelper("unavailable")
    agent.set_support_helper_registry({20: helper})
    asyncio.run(agent.forward())
    prior, = data["recent_episode_buffer"]
    assert prior["day"] == 3 and prior["episode_id"]
    assert prior["outcome_type"] in {"success_self", "failure_after_attempt", "abandon_midway"}
    assert prior["requested_strategy_type"] == "seek_help_then_attempt"
    assert prior["strategy_type"] == "attempt_self" and not prior["help_used"]
    assert prior["support_delivery_status"] == "not_delivered"
    assert prior["support_request_id"] == helper.requests[0].request_id
    assert data["help_effect_memory"]["overall"]["help_attempt_count"] == 0
    assert not data["proto_assigned_task_json"]

    # The same agent carries its actual Day 4 task memory into Day 5. Supply only
    # the replay calibration that a combined-mode agent normally builds on Days 1–3.
    data.update(proto_app_entry_replay_device_id="fixture", proto_app_entry_replay_selected_rank=1,
                proto_day4_replay_snapshot={"schema_version": "fixture"}, proto_app_entry_habit_memory=_habit())
    agent.environment._day = 4
    agent.environment._tick_seconds = 9 * 3600
    agent.environment._time_text = "09:00:00"
    for name, value in {
        "PROTO_TASK_ENTRY_MODE": "app_context_replay_then_llm_rollout",
        "STAGE_MODE": "single", "PROTO_TASK_OCCURRENCE_GATE_ENABLED": "false",
        "PROTO_LLM_PSYCHOLOGY_MODE": "hybrid", "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED": "true",
        "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED": "false", "PROTO_LLM_TASK_APPRAISAL_ENABLED": "false",
        "PROTO_LLM_DAILY_REFLECTION_ENABLED": "false", "PROTO_LLM_EVENT_APPRAISAL_ENABLED": "false",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(agent_module, "choose_attempt_strategy", choose_attempt_strategy)
    llm = RecordingLLM(_needs_payload(), _plan_payload(), {
        "attempt_self_score": .9, "seek_help_score": .05, "avoid_score": .05,
        "dominant_strategy": "attempt_self", "judge_confidence": .95, "reason": "Try independently.",
    })
    agent._toolbox.llm = llm
    asyncio.run(agent.forward())
    needs_prompt, plan_prompt, strategy_prompt = llm.prompts
    assert needs_prompt["inputs"]["talkingdata_day"] == plan_prompt["inputs"]["talkingdata_day"] == 5
    for packet in (needs_prompt["inputs"], plan_prompt["inputs"], strategy_prompt["task_relevant_memory"]):
        record, = packet["recent_task_episodes"]
        for key in ("episode_id", "day", "task_id", "requested_strategy_type", "strategy_type",
                    "support_request_id", "support_delivery_status", "help_used", "outcome_type"):
            assert record[key] == prior[key]
    assert len(data["recent_episode_buffer"]) == 2
    assert data["recent_episode_buffer"][-1]["day"] == 4
    assert data["recent_episode_buffer"][-1]["task_id"] != prior["task_id"]
    assert data["proto_app_entry_rollout_rows_json"][-1]["task_generated"]
    assert data["help_effect_memory"]["overall"]["help_success_count"] == 0


def test_scheduled_login_reaches_real_task_flow_and_next_day_prompt(run_task, monkeypatch):
    import proto.agent as agent_module
    from proto.attempt_strategy import choose_attempt_strategy
    from test_app_entry_rollout import _habit, _needs_payload, _plan_payload
    from test_cross_day_episode_prompts import RecordingLLM

    agent, data = run_task
    data.update(proto_assigned_task_json="", proto_app_entry_replay_device_id="fixture",
                proto_app_entry_replay_selected_rank=1, proto_app_entry_habit_memory=_habit(),
                proto_day4_replay_snapshot={"schema_version": "fixture"})
    for key, value in {
        "PROTO_TASK_ENTRY_MODE": "app_context_replay_then_llm_rollout", "STAGE_MODE": "single",
        "PROTO_SCHEDULED_LOGIN_HOUR": "9", "PROTO_LLM_PSYCHOLOGY_MODE": "hybrid",
        "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED": "true", "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED": "false",
        "PROTO_LLM_TASK_APPRAISAL_ENABLED": "false", "PROTO_LLM_DAILY_REFLECTION_ENABLED": "false",
        "PROTO_LLM_EVENT_APPRAISAL_ENABLED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(agent_module, "choose_attempt_strategy", choose_attempt_strategy)
    agent.set_support_helper_registry({20: FamilyHelper("enabling")})
    agent.environment._tick_seconds = 9 * 3600 + 1
    agent.environment._time_text = "09:00:01"
    for day in (3, 4):
        agent.environment._day = day
        llm = RecordingLLM(_needs_payload(), _plan_payload(), {
            "attempt_self_score": .5, "seek_help_score": .5, "avoid_score": 0,
            "dominant_strategy": "attempt_self", "judge_confidence": .95, "reason": "Two viable actions.",
        })
        agent._toolbox.llm = llm
        asyncio.run(agent.forward())
        strategy = llm.prompts[-1]
        episode = data["recent_episode_buffer"][-1]
        assert episode["task_id"] == strategy["task"]["task_id"]
        assert episode["task_id"].startswith("scheduled_login_account_login_verification_")
        assert episode["day"] == data["proto_last_scheduled_login_day"] == day
        assert not data["proto_app_entry_rollout_rows_json"][-1]["task_generated"]
        if day == 4:
            previous = data["recent_episode_buffer"][-2]
            memory, = strategy["task_relevant_memory"]["recent_task_episodes"]
            assert memory["episode_id"] == previous["episode_id"]
            assert memory["outcome_type"] == previous["outcome_type"]


@pytest.fixture
def replay_hour(run_task, monkeypatch):
    from proto import runtime
    from proto.app_entry.bundle import HourlyAppEntryBundle

    agent, data = run_task
    for name, value in {
        "PROTO_TASK_ENTRY_MODE": "app_context_replay_then_llm_rollout",
        "STAGE_MODE": "single",
        "PROTO_TASK_OCCURRENCE_GATE_ENABLED": "false",
        "PROTO_BAYESIAN_CONTROL_AUDIT_ENABLED": "true",
        "PROTO_BAYESIAN_POLICY_LITE_MODE": "shadow",
        "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE": "shadow",
    }.items():
        monkeypatch.setenv(name, value)
    data["proto_app_entry_replay_device_id"] = "test-device"
    data["proto_app_entry_replay_selected_rank"] = 1
    data["proto_assigned_task_json"] = ""
    agent.environment._day = 2

    def set_hour(hour, context):
        agent.environment._tick_seconds = hour * 3600
        agent.environment._time_text = f"{hour:02d}:00:00"

        def bundle_for_device(*, device_id, talkingdata_day, hour):
            return HourlyAppEntryBundle.from_dict({
                "device_id": device_id, "day": talkingdata_day, "hour": hour,
                "active": True, "active_event_app_exposures": 2,
                "app_context_counts": {context: 2}, "primary_context": context,
            })

        source = SimpleNamespace(bundle_for_device=bundle_for_device,
                                 bundle_hash="test-bundles", device_mapping_hash="test-map")
        monkeypatch.setattr(runtime, "get_replay_source", lambda **_: source)

    return agent, data, set_hour


@pytest.mark.parametrize(("roll", "expected"), [
    (0.35, "success_with_help"), (0.99999, "failure_even_with_help"),
])
def test_final_replay_snapshot_includes_last_hour_task_and_help(replay_hour, monkeypatch, roll, expected):
    from proto import agent as agent_module
    from proto.outcome_model import resolve_attempt_outcome

    agent, data, set_hour = replay_hour
    set_hour(23, "finance_context")
    agent.set_support_helper_registry({20: FamilyHelper("enabling")})

    def controlled_draw(**kwargs):
        kwargs["rng"] = SimpleNamespace(random=lambda: roll)
        return resolve_attempt_outcome(**kwargs)

    monkeypatch.setattr(agent_module, "resolve_attempt_outcome", controlled_draw)
    asyncio.run(agent.forward())
    snap = data["proto_day4_replay_snapshot"]
    assert (snap["created_at_talkingdata_day"], snap["created_at_hour"]) == (3, 23)
    assert snap["app_entry_habit_memory"] == data["proto_app_entry_habit_memory"]
    for key in ("helplessness_score", "trust_in_apps", "avoidance_tendency", "task_domain_memory",
                "help_effect_memory", "recent_episode_buffer", "proto_bayesian_control_memory",
                "proto_bayesian_policy_memory", "proto_bayesian_controllability_lite_memory"):
        assert snap[key] == data[key], key
    episode, = snap["recent_episode_buffer"]
    assert episode["outcome_type"] == expected
    assert episode["help_used"] and episode["support_delivery_status"] == "delivered"
    assert snap["help_effect_memory"]["overall"]["help_attempt_count"] == 1
    assert snap["help_effect_memory"]["overall"]["help_success_count"] == int(expected == "success_with_help")
    for key in ("proto_bayesian_control_memory", "proto_bayesian_policy_memory",
                "proto_bayesian_controllability_lite_memory"):
        assert snap[key], key

    # Later mutations to live memory cannot alter the frozen Day 3 evidence.
    data["recent_episode_buffer"].clear()
    assert len(snap["recent_episode_buffer"]) == 1


def test_idle_last_hour_freezes_habits_without_adding_a_task(replay_hour):
    agent, data, set_hour = replay_hour
    set_hour(22, "media_entertainment_context")
    asyncio.run(agent.forward())
    assert not data.get("proto_day4_replay_snapshot")
    set_hour(23, "media_entertainment_context")
    asyncio.run(agent.forward())
    snap = data["proto_day4_replay_snapshot"]
    assert snap["created_at_hour"] == 23
    assert snap["app_entry_habit_memory"]["total_hours_seen"] == 2
    assert len(data["proto_app_entry_context_only_rows_json"]) == 2
    assert snap["recent_episode_buffer"] == data["recent_episode_buffer"] == []


def test_failed_final_hour_does_not_freeze_or_double_count_on_retry(replay_hour):
    agent, data, set_hour = replay_hour
    set_hour(23, "finance_context")
    agent.set_support_helper_registry({20: FamilyHelper("request_error")})
    with pytest.raises(SupportTechnicalError):
        asyncio.run(agent.forward())
    assert not data.get("proto_day4_replay_snapshot")
    assert not data["recent_episode_buffer"]
    agent.set_support_helper_registry({20: FamilyHelper("enabling")})
    asyncio.run(agent.forward())
    snap = data["proto_day4_replay_snapshot"]
    assert snap["app_entry_habit_memory"]["total_hours_seen"] == 1
    assert len(snap["recent_episode_buffer"]) == 1
