import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
import json

import pytest

from help_mode_design import (
    COMPLETION_ACTION,
    CONDITIONS,
    SCENE,
    digest,
    help_episodes,
    load_residents,
    prepare_design,
    route_help_plan,
    run_help_plan,
    verify_plan_pair,
)
from probe_hourly_intention import SIM_HOUR, login_offer
from run_hourly_intention_pairs import CapturePlan


@pytest.fixture(scope="module")
def prepared():
    residents = load_residents(None)
    return residents, asyncio.run(prepare_design(residents))


def test_each_resident_and_pair_has_a_reproducible_blinded_stimulus(prepared):
    residents, design = prepared
    assert design == asyncio.run(prepare_design(residents))
    assert len({r["history_sha256"] for r in design["profiles"]}) == 10
    assert all(
        r["history_source"] == "synthetic_72_hours" and r["reference_hours"] == 72
        for r in design["profiles"]
    )
    points = design["manifest"]
    assert len(points) == 80
    control_counts = Counter()
    contrast_first = Counter()
    for person, resident in residents.items():
        cells = design["stimuli"][str(person)]
        verify_plan_pair(resident, cells)
        for stimulus in cells.values():
            body = json.loads(stimulus["messages"][1]["content"].split("\n", 1)[1])
            assert set(body["digital_needs"]["need_pressures"].values()) == {0.3}
            assert body["digital_needs"]["dominant_need"] is None
        pairs = defaultdict(list)
        for row in points:
            if row["profile_id"] == person:
                assert row["selected_rank"] == resident.rank
                assert row["plan_stimulus_sha256"] == digest(cells[row["condition"]])
                pairs[row["pair_id"]].append(row)
        assert len(pairs) == 4 and all(len(p) == 2 for p in pairs.values())
        assert Counter(p[0]["kind"] for p in pairs.values()) == {
            "contrast": 3,
            "repeat": 1,
        }
        for x, y in pairs.values():
            assert {x["member"], y["member"]} == {"A", "B"}
            assert x["pair_seed"] == y["pair_seed"] and x["sample_u"] == y["sample_u"]
            if x["kind"] == "repeat":
                assert (
                    x["condition"] == y["condition"]
                    and x["plan_stimulus_sha256"] == y["plan_stimulus_sha256"]
                )
                control_counts[x["condition"]] += 1
            else:
                assert {x["condition"], y["condition"]} == set(CONDITIONS)
                contrast_first[x["condition"]] += 1
    assert control_counts == {"proxy": 5, "guided": 5}
    assert contrast_first == {"proxy": 15, "guided": 15}


def test_last_operation_is_the_only_change_and_pair_rejects_contamination(prepared):
    residents, design = prepared
    resident = residents[7]
    guided = help_episodes(7, "guided")
    proxy = help_episodes(7, "proxy")
    assert guided[:2] == proxy[:2]
    assert [e["outcome_type"] for e in guided] == [
        "failure_after_attempt",
        "failure_after_attempt",
        "success_with_help",
    ]
    assert sorted(e["tick_seconds"] for e in guided) == [
        e["tick_seconds"] for e in guided
    ]
    assert len(set(e["episode_id"] for e in guided)) == 3
    assert len(set(e["task_id"] for e in guided)) == 1
    assert {k for k in guided[2] if guided[2][k] != proxy[2][k]} == {
        "completion_action"
    }
    assert all(
        not {"helplessness_delta", "autonomy_preservation", "proxy_completion_level"}
        & e.keys()
        for e in guided + proxy
    )
    for field in ("completion_action", "pre_hour_psychology", "parameters"):
        stimuli = deepcopy(design["stimuli"]["7"])
        s = stimuli["proxy"]
        msg = s["messages"][1]
        prefix, raw = msg["content"].split("\n", 1)
        body = json.loads(raw)
        if field == "parameters":
            s["parameters"]["temperature"] += 0.1
        elif field == "completion_action":
            body["inputs"]["recent_task_episodes"][2][field] = COMPLETION_ACTION[
                "guided"
            ]
        else:
            body["inputs"][field]["helplessness"] += 1
        msg["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
        with pytest.raises(ValueError):
            verify_plan_pair(resident, stimuli)


def test_plan_can_route_to_each_residents_fresh_login_or_leave_it_unhandled(prepared):
    residents, design = prepared
    resident = residents[9]
    today, _, offer = login_offer(scene=SCENE, profile_id=resident.profile_id)
    assert today.task_id != help_episodes(resident.profile_id, "proxy")[0]["task_id"]
    for token, kind in (
        (f"engage_goal@o1@open:{offer['required_channel']}", "engage_goal"),
        (f"defer_goal@o1@{SIM_HOUR + 2}", "defer_goal"),
        ("drop_goal@o1", "drop_goal"),
        ("no_app", "no_app"),
    ):
        receiver = CapturePlan("opportunity_v1", action=token)
        plan = asyncio.run(run_help_plan(receiver, resident, "proxy"))
        route, task = route_help_plan(plan, resident)
        assert receiver.requests == [design["stimuli"]["9"]["proxy"]]
        assert route["policy_choice"] == kind
        assert task == (today if kind == "engage_goal" else None)
    assert [e["outcome_type"] for e in help_episodes(9, "proxy")] == [
        "failure_after_attempt",
        "failure_after_attempt",
        "success_with_help",
    ]


def test_help_plan_selects_five_actionable_candidates_before_top_k(prepared):
    residents, _ = prepared
    resident = deepcopy(residents[1])
    residue = {
        "finance_candidate_review": 100,
        "taxonomy_profile_only": 99,
        "unknown_or_unmapped": 98,
    }
    actions = {
        "finance_context": 10,
        "health_service_context": 9,
        "device_tool_context": 8,
        "navigation_transport_context": 7,
        "shopping_lifestyle_context": 6,
    }
    resident.history.habits["context_by_hour"]["9"] = {**residue, **actions}
    capture = CapturePlan("opportunity_v1")
    asyncio.run(run_help_plan(capture, resident, "proxy"))
    body = json.loads(capture.requests[0]["messages"][1]["content"].split("\n", 1)[1])
    # The goal-specific public service channel may also be available.
    assert set(actions) <= set(body["channels"])
    assert not set(residue).intersection(body["channels"])
