from __future__ import annotations

import asyncio
import json
import sys
import types


def _install_optional_dependency_stubs() -> None:
    if "openai.types.chat" not in sys.modules:
        openai_module = types.ModuleType("openai")
        openai_types_module = types.ModuleType("openai.types")
        openai_chat_module = types.ModuleType("openai.types.chat")

        class _AsyncOpenAI:
            def __init__(self, *args, **kwargs):
                pass

        class _OpenAIError(Exception):
            pass

        class _APIConnectionError(_OpenAIError):
            pass

        class _NotGiven:
            pass

        class _CompletionParams:
            class ResponseFormat:
                pass

        openai_module.NOT_GIVEN = object()
        openai_module.APIConnectionError = _APIConnectionError
        openai_module.AsyncOpenAI = _AsyncOpenAI
        openai_module.NotGiven = _NotGiven
        openai_module.OpenAIError = _OpenAIError

        openai_chat_module.ChatCompletionMessageParam = dict
        openai_chat_module.ChatCompletionToolChoiceOptionParam = dict
        openai_chat_module.ChatCompletionToolParam = dict
        openai_chat_module.completion_create_params = _CompletionParams
        openai_types_module.chat = openai_chat_module
        openai_module.types = openai_types_module

        sys.modules["openai"] = openai_module
        sys.modules["openai.types"] = openai_types_module
        sys.modules["openai.types.chat"] = openai_chat_module

    if "ray" not in sys.modules:
        ray_module = types.ModuleType("ray")
        actor_module = types.ModuleType("ray.actor")

        class ObjectRef:
            pass

        def _remote(obj=None, **kwargs):
            if obj is None:
                return lambda inner: inner
            return obj

        actor_module.ActorHandle = object
        ray_module.actor = actor_module
        ray_module.ObjectRef = ObjectRef
        ray_module.remote = _remote
        sys.modules["ray"] = ray_module
        sys.modules["ray.actor"] = actor_module

    if "qdrant_client.http.models" not in sys.modules:
        qdrant_client_module = types.ModuleType("qdrant_client")
        http_module = types.ModuleType("qdrant_client.http")
        models_module = types.ModuleType("qdrant_client.http.models")

        class _QdrantClient:
            def __init__(self, *args, **kwargs):
                pass

            def create_collection(self, *args, **kwargs):
                return None

            def upsert(self, *args, **kwargs):
                return None

            def delete(self, *args, **kwargs):
                return None

        class _Distance:
            COSINE = "cosine"

        class _Placeholder:
            def __init__(self, *args, **kwargs):
                pass

        models_module.Distance = _Distance
        for _name in (
            "VectorParams",
            "SparseVectorParams",
            "SparseIndexParams",
            "PointStruct",
            "SparseVector",
            "PointIdsList",
            "NamedSparseVector",
            "FieldCondition",
            "Filter",
        ):
            setattr(models_module, _name, _Placeholder)

        http_module.models = models_module
        qdrant_client_module.QdrantClient = _QdrantClient
        qdrant_client_module.http = http_module
        sys.modules["qdrant_client"] = qdrant_client_module
        sys.modules["qdrant_client.http"] = http_module
        sys.modules["qdrant_client.http.models"] = models_module

    if "fastembed" not in sys.modules:
        fastembed_module = types.ModuleType("fastembed")

        class SparseTextEmbedding:
            def __init__(self, *args, **kwargs):
                pass

        fastembed_module.SparseTextEmbedding = SparseTextEmbedding
        sys.modules["fastembed"] = fastembed_module

    if "grpc.aio" not in sys.modules:
        grpc_module = sys.modules.get("grpc")
        if grpc_module is None:
            grpc_module = types.ModuleType("grpc")
            sys.modules["grpc"] = grpc_module
        aio_module = types.ModuleType("grpc.aio")

        class _Channel:
            pass

        class _AioServer:
            async def start(self):
                return None

            async def stop(self, *args, **kwargs):
                return None

            async def wait_for_termination(self):
                return None

            def add_insecure_port(self, *args, **kwargs):
                return None

        class _ServicerContext:
            pass

        aio_module.Channel = _Channel
        aio_module.Server = _AioServer
        aio_module.ServicerContext = _ServicerContext
        aio_module.server = lambda *args, **kwargs: _AioServer()
        aio_module.secure_channel = lambda *args, **kwargs: _Channel()
        aio_module.insecure_channel = lambda *args, **kwargs: _Channel()
        grpc_module.aio = aio_module
        grpc_module.Channel = _Channel
        grpc_module.secure_channel = lambda *args, **kwargs: _Channel()
        grpc_module.insecure_channel = lambda *args, **kwargs: _Channel()
        sys.modules["grpc.aio"] = aio_module

    if "boto3" not in sys.modules:
        boto3_module = types.ModuleType("boto3")

        class _S3Client:
            def put_object(self, *args, **kwargs):
                return None

            def get_object(self, *args, **kwargs):
                return {"Body": types.SimpleNamespace(read=lambda: b"")}

            def head_object(self, *args, **kwargs):
                return None

            def delete_object(self, *args, **kwargs):
                return None

        boto3_module.client = lambda *args, **kwargs: _S3Client()
        sys.modules["boto3"] = boto3_module

    if "botocore.exceptions" not in sys.modules:
        botocore_module = types.ModuleType("botocore")
        exceptions_module = types.ModuleType("botocore.exceptions")

        class ClientError(Exception):
            def __init__(self, *args, **kwargs):
                super().__init__(*args)
                self.response = {"Error": {"Code": "404"}}

        exceptions_module.ClientError = ClientError
        botocore_module.exceptions = exceptions_module
        sys.modules["botocore"] = botocore_module
        sys.modules["botocore.exceptions"] = exceptions_module

    if "pyproj" not in sys.modules:
        pyproj_module = types.ModuleType("pyproj")

        class _Proj:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, *args, **kwargs):
                return 0.0, 0.0

        pyproj_module.Proj = _Proj
        sys.modules["pyproj"] = pyproj_module

    if "shapely" not in sys.modules:
        shapely_module = types.ModuleType("shapely")
        geometry_module = types.ModuleType("shapely.geometry")

        class _Point:
            def __init__(self, *args, **kwargs):
                self.args = args

        class _Polygon:
            def __init__(self, *args, **kwargs):
                self.args = args

        geometry_module.Point = _Point
        geometry_module.Polygon = _Polygon
        shapely_module.geometry = geometry_module
        sys.modules["shapely"] = shapely_module
        sys.modules["shapely.geometry"] = geometry_module


_install_optional_dependency_stubs()


for _module_name, _module in list(sys.modules.items()):
    if not _module_name.startswith("pycityproto"):
        continue
    module_file = getattr(_module, "__file__", None)
    if not isinstance(module_file, str):
        setattr(_module, "__file__", f"<stub:{_module_name}>")

from proto.agent import DigitalHelplessnessAgent
from proto.logical_clock import enable_proto_logical_clock
from proto.task_assignment import evaluate_mobile_entry_for_agent


class _ForbiddenLLM:
    def __getattr__(self, name: str):
        raise AssertionError(f"status_summary should not access llm.{name}")


class _DummyLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def atext_request(self, **kwargs):
        self.calls += 1
        return self.response


class _FakeStatusStore:
    def __init__(self, initial: dict[str, object] | None = None):
        self.data = dict(initial or {})

    async def get(self, key: str, default=None):
        return self.data.get(key, default)

    async def update(self, key: str, value):
        self.data[key] = value


class _FakeMemory:
    def __init__(self, initial: dict[str, object] | None = None):
        self.status = _FakeStatusStore(initial)


class _FakeEnvironment:
    def __init__(
        self,
        *,
        day: int = 0,
        time_text: str = "06:00:01",
        tick_seconds: float | None = None,
        env: dict[str, object] | None = None,
    ):
        self._day = day
        self._time_text = time_text
        self._tick_seconds = (
            float(tick_seconds)
            if tick_seconds is not None
            else float(day * 0 + 21601.0)
        )
        self.environment = dict(env or {})

    def get_datetime(self, format_time: bool = False):
        if format_time:
            return self._day, self._time_text
        return self._day, self._tick_seconds

    async def step(self, n: int):
        self._tick_seconds += float(n)

    async def get_metrics(self):
        return []


class _FakeAgent:
    def __init__(
        self,
        *,
        status: dict[str, object] | None = None,
        day: int = 0,
        time_text: str = "06:00:01",
        tick_seconds: float | None = None,
        env: dict[str, object] | None = None,
        llm=None,
    ):
        self.memory = _FakeMemory(status)
        self.environment = _FakeEnvironment(
            day=day,
            time_text=time_text,
            tick_seconds=tick_seconds,
            env=env,
        )
        self.llm = llm if llm is not None else _ForbiddenLLM()
        self.step_count = 0
        self.motion_updates = 0
        self.id = 7

    async def _build_survey_summary(self):
        raise AssertionError("early-return idle step should not build survey summary")

    async def _run_minimal_daily_housekeeping(self, *, current_day: int, env):
        return await DigitalHelplessnessAgent._run_minimal_daily_housekeeping(
            self,
            current_day=current_day,
            env=env,
        )

    async def _write_idle_step_state(self):
        return await DigitalHelplessnessAgent._write_idle_step_state(self)

    async def update_motion(self):
        self.motion_updates += 1


def test_status_summary_idle_step_uses_local_compact_text() -> None:
    agent = _FakeAgent(
        status={
            "proto_active_stage_key": "steady",
            "current_intention": "No digital task assigned",
            "friction_step_signal": {
                "step_type": "idle",
                "step_outcome": "none",
                "status_text": "No digital task assigned",
            },
            "helplessness_score": 48.25,
            "trust_in_apps": 61.0,
            "avoidance_tendency": 35.0,
        },
        day=0,
        time_text="06:00:01",
    )

    asyncio.run(DigitalHelplessnessAgent.status_summary(agent))

    assert agent.memory.status.data["status_summary"] == (
        "day=0 time=06:00 stage=steady step=idle "
        "intention=No digital task assigned outcome=none "
        "helplessness=48.2 trust=61.0 avoidance=35.0 "
        "note=No digital task assigned"
    )


def test_status_summary_digital_task_collapses_whitespace_and_truncates_note() -> None:
    long_note = "   failed    after    popup   " + ("x" * 200)
    agent = _FakeAgent(
        status={
            "proto_active_stage_key": "shock",
            "current_intention": "payment_risk_confirmation:attempt_self",
            "friction_step_signal": {
                "step_type": "digital_task",
                "step_outcome": "failure_after_attempt",
                "status_text": long_note,
            },
            "helplessness_score": 72.44,
            "trust_in_apps": 28.0,
            "avoidance_tendency": 81.37,
        },
        day=1,
        time_text="14:30:45",
    )

    asyncio.run(DigitalHelplessnessAgent.status_summary(agent))

    summary = agent.memory.status.data["status_summary"]
    assert "day=1 time=14:30 stage=shock step=digital_task" in summary
    assert "intention=payment_risk_confirmation:attempt_self" in summary
    assert "outcome=failure_after_attempt" in summary
    assert "helplessness=72.4 trust=28.0 avoidance=81.4" in summary
    note_text = summary.split(" note=", 1)[1]
    assert note_text.startswith("failed after popup ")
    assert len(note_text) <= 160


def test_status_summary_falls_back_safely_when_fields_are_missing() -> None:
    agent = _FakeAgent(
        status={},
        day=2,
        time_text="19:05:59",
        env={"stage_name": "recovery"},
    )

    asyncio.run(DigitalHelplessnessAgent.status_summary(agent))

    assert agent.memory.status.data["status_summary"] == (
        "day=2 time=19:05 stage=recovery step=unknown "
        "intention=unknown outcome=none "
        "helplessness=0.0 trust=0.0 avoidance=0.0 "
        "note=unknown"
    )


def test_forward_returns_early_for_non_window_idle_step_and_marks_housekeeping() -> None:
    agent = _FakeAgent(
        status={
            "proto_assigned_task_json": "",
            "proto_last_housekeeping_day": -1,
            "helplessness_score": 44.0,
            "digital_emotion_state": {
                "anxiety": 4.2,
                "frustration": 3.8,
                "relief": 5.1,
                "confidence": 4.7,
                "last_updated_day": 0,
            },
        },
        day=1,
        time_text="08:00:01",
        tick_seconds=28801.0,
        env={"stage_name": "steady"},
    )

    result = asyncio.run(DigitalHelplessnessAgent.forward(agent))

    assert result == 0.0
    assert agent.step_count == 1
    assert agent.memory.status.data["proto_last_housekeeping_day"] == 1
    assert (
        agent.memory.status.data["current_intention"]
        == "No mobile digital activity entered"
    )
    assert agent.memory.status.data["friction_step_signal"]["step_type"] == "idle"
    assert agent.memory.status.data["proto_active_stage_key"] == "steady"


def test_mobile_entry_eval_tick_accepts_logical_clock_plus_one_offset() -> None:
    agent = _FakeAgent()

    assert DigitalHelplessnessAgent._is_mobile_entry_eval_tick(
        agent,
        tick_seconds=3600.0,
        interval_minutes=60,
    )
    assert DigitalHelplessnessAgent._is_mobile_entry_eval_tick(
        agent,
        tick_seconds=3601.0,
        interval_minutes=60,
    )
    assert DigitalHelplessnessAgent._is_mobile_entry_eval_tick(
        agent,
        tick_seconds=7201.0,
        interval_minutes=60,
    )
    assert not DigitalHelplessnessAgent._is_mobile_entry_eval_tick(
        agent,
        tick_seconds=3599.0,
        interval_minutes=60,
    )
    assert not DigitalHelplessnessAgent._is_mobile_entry_eval_tick(
        agent,
        tick_seconds=3602.0,
        interval_minutes=60,
    )


def test_mobile_entry_llm_shadow_cannot_change_real_entry(monkeypatch, tmp_path) -> None:
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"check_information":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "mobile_intention_llm_shadow")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_CALIBRATION_PATH", str(calibration))
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "0")
    llm = _DummyLLM(
        '{"selected_mobile_intention":"not_allowed","confidence":0.99,'
        '"reason":"try to override"}'
    )
    agent = _FakeAgent(llm=llm)
    config = __import__("config_runtime").load_runtime_config()
    decision = evaluate_mobile_entry_for_agent(
        agent_id=7,
        day=1,
        tick_seconds=28800.0,
        env={},
        entry_mode="mobile_intention_llm_shadow",
        calibration_path=str(calibration),
    )

    llm_shadow = asyncio.run(
        DigitalHelplessnessAgent._build_mobile_entry_llm_shadow(
            agent,
            entry_decision=decision,
            runtime_config=config,
            stable_profile={"age": 70, "gender": "female", "digital_experience": 0.5},
            day=1,
            tick_seconds=28800.0,
        )
    )

    assert decision.selected_mobile_intention == "check_information"
    assert decision.task_generated is True
    assert decision.task is not None
    assert decision.task.task_family == "information_search_judgment"
    assert llm_shadow["llm_affected_real_entry"] is False
    assert llm_shadow["llm_parse_status"] in {"out_of_set_intention", "parse_failed"}
    assert llm.calls >= 1


def test_mobile_entry_llm_rerank_writes_per_world_audit_schedule(
    monkeypatch,
    tmp_path,
) -> None:
    calibration = tmp_path / "reference_calibration.json"
    schedule = tmp_path / "rerank_schedule.jsonl"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{'
        '"check_information":0.6,'
        '"use_payment_or_finance":0.4'
        '}}, "uses_validation_data":false}',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "mobile_intention_llm_rerank_online_mc")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_CALIBRATION_PATH", str(calibration))
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH", str(schedule))
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_RUN_ID", "run-1")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_TOP_K", "2")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "0")
    llm = _DummyLLM(
        '{"selected_mobile_intention":"use_payment_or_finance",'
        '"confidence":0.95,"reason":"payment candidate fits"}'
    )
    writer = _FakeAgent(llm=llm)
    config = __import__("config_runtime").load_runtime_config()
    base_decision = evaluate_mobile_entry_for_agent(
        agent_id=writer.id,
        day=1,
        tick_seconds=28800.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )

    selected, audit = asyncio.run(
        DigitalHelplessnessAgent._resolve_mobile_entry_rerank_override(
            writer,
            entry_decision=base_decision,
            runtime_config=config,
            stable_profile={"age": 70, "gender": "female", "digital_experience": 0.5},
            day=1,
            tick_seconds=28800.0,
        )
    )

    assert selected == "use_payment_or_finance"
    assert audit["rerank_parse_status"] == "ok"
    assert schedule.exists()
    row = json.loads(schedule.read_text(encoding="utf-8").strip())
    assert row["selected_mobile_intention"] == "use_payment_or_finance"
    assert llm.calls >= 1


def test_mobile_entry_llm_rerank_can_accept_low_confidence_with_audit(
    monkeypatch,
    tmp_path,
) -> None:
    calibration = tmp_path / "reference_calibration.json"
    schedule = tmp_path / "rerank_schedule_low_confidence.jsonl"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{'
        '"check_information":0.6,'
        '"use_payment_or_finance":0.4'
        '}}, "uses_validation_data":false}',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "mobile_intention_llm_rerank_online_mc")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_CALIBRATION_PATH", str(calibration))
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH", str(schedule))
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_RUN_ID", "run-low-conf")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_TOP_K", "2")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_LLM_MIN_CONFIDENCE", "0.70")
    monkeypatch.setenv(
        "PROTO_MOBILE_INTENTION_RERANK_LOW_CONFIDENCE_POLICY",
        "accept_with_audit",
    )
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "0")
    config = __import__("config_runtime").load_runtime_config()
    decision = evaluate_mobile_entry_for_agent(
        agent_id=7,
        day=1,
        tick_seconds=28800.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )
    agent = _FakeAgent(
        llm=_DummyLLM(
            '{"selected_mobile_intention":"use_payment_or_finance",'
            '"confidence":0.55,"reason":"uncertain but in top-k"}'
        )
    )

    selected, audit = asyncio.run(
        DigitalHelplessnessAgent._resolve_mobile_entry_rerank_override(
            agent,
            entry_decision=decision,
            runtime_config=config,
            stable_profile={"age": 70, "gender": "female"},
            day=1,
            tick_seconds=28800.0,
        )
    )

    assert selected == "use_payment_or_finance"
    assert audit["rerank_parse_status"] == "low_confidence_accepted"
    row = json.loads(schedule.read_text(encoding="utf-8").strip())
    assert row["parse_status"] == "low_confidence_accepted"
    assert row["confidence"] == 0.55


def test_mobile_entry_llm_rerank_rejects_invalid_json_before_audit_write(
    monkeypatch,
    tmp_path,
) -> None:
    calibration = tmp_path / "reference_calibration.json"
    schedule = tmp_path / "missing_schedule.jsonl"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{'
        '"check_information":0.6,'
        '"use_payment_or_finance":0.4'
        '}}, "uses_validation_data":false}',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "mobile_intention_llm_rerank_online_mc")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_CALIBRATION_PATH", str(calibration))
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH", str(schedule))
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_RUN_ID", "run-2")
    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_TOP_K", "2")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "0")
    config = __import__("config_runtime").load_runtime_config()
    base_decision = evaluate_mobile_entry_for_agent(
        agent_id=7,
        day=1,
        tick_seconds=28800.0,
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )
    writer = _FakeAgent(llm=_DummyLLM("not json"))

    try:
        asyncio.run(
            DigitalHelplessnessAgent._resolve_mobile_entry_rerank_override(
                writer,
                entry_decision=base_decision,
                runtime_config=config,
                stable_profile={"age": 70, "gender": "female"},
                day=1,
                tick_seconds=28800.0,
            )
        )
    except ValueError as exc:
        assert "invalid_schema" in str(exc)
    else:
        raise AssertionError("invalid rerank JSON should fail fast")
    assert not schedule.exists()


def test_before_forward_keeps_minimal_motion_sync_when_logical_clock_enabled() -> None:
    agent = _FakeAgent()

    class _FakeSimulation:
        def __init__(self, environment):
            self.environment = environment

    enable_proto_logical_clock(_FakeSimulation(agent.environment))

    asyncio.run(DigitalHelplessnessAgent.before_forward(agent))

    assert agent.motion_updates == 1
