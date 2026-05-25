from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from proto.family_helper_agent import FamilyHelperAgent
from proto.support_protocol import SupportRequest, SupportResponse


class _Status:
    def __init__(self, initial=None):
        self.data = {
            "support_histories": {},
            "chat_histories": {},
            **(initial or {}),
        }

    async def get(self, key, default_value=None):
        return self.data.get(key, default_value)

    async def update(self, key, value, mode="replace"):
        self.data[key] = value


class _Memory:
    def __init__(self, initial=None):
        self.status = _Status(initial)


class _Environment:
    def get_datetime(self):
        return 0, 0.0

    async def get_person(self, agent_id):
        return {"person": {"motion": {}}}

    async def add_person(self, payload):
        return None

    @property
    def economy_client(self):
        return SimpleNamespace(add_agents=lambda payload: None)


class _Helper(FamilyHelperAgent):
    async def update_motion(self):
        return None

    def _support_response_block(self):
        class _Block:
            async def generate_response(_, request):
                return SupportResponse(
                    request_id=request.request_id,
                    requester_agent_id=request.requester_agent_id,
                    helper_agent_id=request.helper_agent_id,
                    support_style="enabling",
                    instruction_quality="high",
                    autonomy_preservation="high",
                    proxy_completion_level="none",
                    emotional_tone="patient",
                    response_delay="immediate",
                    confidence=0.9,
                    responded=True,
                    response_text="I will guide you step by step.",
                    rationale="test",
                    source="llm_family_helper",
                    audit_status="ok",
                )

        return _Block()


def _request() -> SupportRequest:
    return SupportRequest(
        request_id="r1",
        requester_agent_id=10,
        helper_agent_id=20,
        day=0,
        tick=1.0,
        task_id="task",
        task_family="service_application_submission",
        friction_type="form_complexity",
        difficulty=0.6,
        need_type="daily_task",
        support_sensitivity=0.7,
    )


def _agent() -> _Helper:
    return _Helper(
        id=20,
        name="helper",
        toolbox=SimpleNamespace(llm=None, environment=_Environment(), messager=None, embedding=None, database_writer=None),
        memory=_Memory(),
        agent_params=None,
        blocks=[],
    )


def test_provide_support_returns_structured_response_and_updates_history() -> None:
    agent = _agent()
    response = asyncio.run(agent.provide_support(_request()))
    assert response.support_style == "enabling"
    histories = asyncio.run(agent.memory.status.get("support_histories"))
    assert histories["10"][0]["response"]["support_style"] == "enabling"
    assert "outcome_type" not in histories["10"][0]["response"]


def test_do_chat_reuses_support_generation_logic() -> None:
    agent = _agent()
    message = SimpleNamespace(
        from_id=10,
        to_id=20,
        day=0,
        t=1.0,
        payload={"type": "social", "content": json.dumps(_request().to_dict())},
    )
    response = json.loads(asyncio.run(agent.do_chat(message)))
    assert response["support_style"] == "enabling"
    assert "success" not in response


def test_do_chat_invalid_request_returns_unavailable() -> None:
    agent = _agent()
    message = SimpleNamespace(
        from_id=10,
        to_id=20,
        day=0,
        t=1.0,
        payload={"type": "social", "content": "hello"},
    )
    response = json.loads(asyncio.run(agent.do_chat(message)))
    assert response["support_style"] == "unavailable"
    assert response["audit_status"] == "invalid_request"


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )


def _main_ast() -> ast.Module:
    return ast.parse(_main_source())


def _compile_main_function(function_name: str, namespace: dict):
    tree = _main_ast()
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            module = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(module)
            exec(compile(module, filename="main.py", mode="exec"), namespace)
            return namespace[function_name]
    raise AssertionError(f"{function_name} not found in main.py")


def _call_contains_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == name for child in ast.walk(node))


class _MappingAgent:
    def __init__(self, initial=None):
        self.status = _Status(initial)
        self.registry = {}

    def set_support_helper_registry(self, registry):
        self.registry = dict(registry)


class _MappingSimulation:
    def __init__(self, *, older_type, helper_type):
        self.older_type = older_type
        self.helper_type = helper_type
        self.older_agents = {
            1: _MappingAgent(
                {
                    "family_helper_agent_id": -1,
                    "support_ecology_mode": "off",
                }
            ),
            2: _MappingAgent(
                {
                    "family_helper_agent_id": -1,
                    "support_ecology_mode": "off",
                }
            ),
        }
        self.helper_agents = {
            7: _MappingAgent({"relationship_profiles": {}}),
            8: _MappingAgent({"relationship_profiles": {}}),
        }
        self._id2agent = {**self.older_agents, **self.helper_agents}

    async def filter(self, types=None, filter_str=None):
        if types == (self.older_type,):
            return list(self.older_agents)
        if types == (self.helper_type,):
            return list(self.helper_agents)
        return []


def test_workflow_runs_family_helper_mapping_after_init_status() -> None:
    tree = _main_ast()
    workflow_assign_index = None
    mapping_append_index = None
    survey_extend_index = None

    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "workflow_steps"
            for target in node.targets
        ):
            assert _call_contains_name(node, "init_status")
            workflow_assign_index = index
        elif (
            workflow_assign_index is not None
            and isinstance(node, ast.If)
            and _call_contains_name(node, "init_family_helper_mapping")
        ):
            mapping_append_index = index
        elif (
            workflow_assign_index is not None
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "extend"
            and _call_contains_name(node, "tech_acceptance_survey")
        ):
            survey_extend_index = index
            break

    assert workflow_assign_index is not None
    assert mapping_append_index is not None
    assert survey_extend_index is not None
    assert workflow_assign_index < mapping_append_index < survey_extend_index


def test_family_helper_mapping_repairs_init_status_reset() -> None:
    class _RuntimeConfig:
        proto_support_ecology_mode = "family_helper_llm"

    class _OlderAgentType:
        pass

    class _HelperAgentType:
        pass

    namespace = {
        "AgentSociety": object,
        "EXPERIMENT_ENGINE": "proto",
        "RUNTIME_CONFIG": _RuntimeConfig(),
        "DigitalHelplessnessAgent": _OlderAgentType,
        "FamilyHelperAgent": _HelperAgentType,
        "SUPPORT_HELPER_REGISTRY_ATTRIBUTE": "_support_helper_registry",
    }
    init_mapping = _compile_main_function("init_family_helper_mapping", namespace)
    simulation = _MappingSimulation(
        older_type=_OlderAgentType,
        helper_type=_HelperAgentType,
    )

    asyncio.run(init_mapping(simulation))

    older_one = simulation.older_agents[1]
    older_two = simulation.older_agents[2]
    assert older_one.status.data["family_helper_agent_id"] == 7
    assert older_two.status.data["family_helper_agent_id"] == 8
    assert older_one.status.data["support_ecology_mode"] == "family_helper_llm"
    assert older_one.status.data["support_helper_mapping_audit"] == {
        "status": "mapped",
        "support_ecology_mode": "family_helper_llm",
        "older_agent_count": 2,
        "helper_agent_count": 2,
        "mapped_count": 2,
        "requester_agent_id": 1,
        "helper_agent_id": 7,
    }
    assert older_one.registry[7] is simulation.helper_agents[7]
    assert older_two.registry[8] is simulation.helper_agents[8]
    assert (
        simulation.helper_agents[7]
        .status.data["relationship_profiles"]["1"]["helper_agent_id"]
        == 7
    )
