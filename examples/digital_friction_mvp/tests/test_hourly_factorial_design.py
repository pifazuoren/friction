import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
import json

import pytest

from hourly_factorial_design import prepare_design, request_manifest, verify_design_stimuli
from probe_hourly_intention import (
    DEFERRABLE_SERVICE_DESCRIPTION,
    PROFILE_ID,
    SCENES,
    SIM_HOUR,
    load_history,
    login_offer,
)
from proto.hourly_intention import IntentionLedger
from proto.models import DigitalTask
from proto.paired_random import PairedRandomProvider
from run_hourly_intention_pairs import prepare


def test_24_point_manifest_pairs_strategy_draws_and_counterbalances_first_member():
    points = request_manifest()
    assert len(points) == 24 and points == request_manifest()
    assert set(row["kind"] for row in points) == {"contrast", "repeat"}
    assert Counter(row["scene"] for row in points) == {"S0": 12, "S1": 12}
    groups = defaultdict(list)
    for row in points:
        groups[row["pair_id"]].append(row)
    assert len(groups) == 12
    offer_id = login_offer()[2]["opportunity_id"]
    first_contrast = []
    for members in groups.values():
        first, second = members
        assert {first["member"], second["member"]} == {"A", "B"}
        assert first["scene"] == second["scene"] and first["kind"] == second["kind"]
        assert first["pair_seed"] == second["pair_seed"]
        expected_draw = PairedRandomProvider(first["pair_seed"]).rng(PROFILE_ID, offer_id, 1, "strategy").random()
        assert first["sample_u"] == second["sample_u"] == expected_draw
        if first["kind"] == "contrast":
            assert {first["condition"], second["condition"]} == {"success", "failure"}
            first_contrast.append(first["condition"])
        else:
            assert first["condition"] == second["condition"] == ("success" if first["scene"] == "S0" else "failure")
    assert Counter(first_contrast) == {"success": 5, "failure": 5}
    assert len({p["sample_u"] for p in points}) == 6
    for scene in SCENES:
        contrast_counts = Counter(p["condition"] for p in points if p["scene"] == scene and p["kind"] == "contrast")
        assert contrast_counts == {"success": 5, "failure": 5}


def test_transport_stimuli_and_alternative_routes_preserve_original_s0_both_histories():
    history = load_history(None)
    design = asyncio.run(prepare_design(history))
    stimuli = design["stimuli"]
    previous = asyncio.run(prepare(history, modes=("opportunity_v1",)))
    assert previous["opportunity_v1"] == stimuli["S0"]
    for scene in SCENES:
        routes = design["preflight"][scene]
        assert {k for k, v in routes.items() if v["task_admitted"]} == {"engage_goal"}
        assert routes["defer_goal"]["next_review_at_sim_hour"] == SIM_HOUR + 24
        assert set(routes) == {"engage_goal", "defer_goal", "drop_goal", "no_app"}
        for condition in ("success", "failure"):
            body = json.loads(stimuli[scene][condition]["messages"][1]["content"].split("\n", 1)[1])
            offer, = body["inputs"]["available_opportunities"]
            assert body["schema_version"] == "hourly_plan_compact_v4"
            assert offer["visible_description"] == login_offer(scene=scene)[2]["visible_description"]
            assert body["digital_needs"]["dominant_need"] == "tool_need"
            assert offer["known_deadline_sim_hour"] is None
    # Tampering the same way in both outcome arms evades a within-scene-only check.
    tampered = deepcopy(stimuli)
    for request in tampered["S1"].values():
        request["parameters"]["temperature"] += 0.1
    with pytest.raises(ValueError, match="visible_description"):
        verify_design_stimuli(tampered)
    # Tampering the same way in all cells evades all relative checks, hence freeze the state too.
    tampered = deepcopy(stimuli)
    for cells in tampered.values():
        for request in cells.values():
            message = request["messages"][1]
            prefix, raw = message["content"].split("\n", 1)
            body = json.loads(raw)
            body["inputs"]["pre_hour_psychology"]["helplessness"] += 1
            message["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
    with pytest.raises(ValueError, match="preregistered resident"):
        verify_design_stimuli(tampered)


def test_task_content_survives_reloaded_ledger_and_preserves_old_task_wire_format():
    original, _, baseline_offer = login_offer()
    original_wire = original.to_dict()
    assert "visible_description" not in original_wire
    assert DigitalTask.from_dict(original_wire).to_dict() == original_wire
    task, ledger, offer = login_offer(scene="S1")
    assert task.to_dict() == {**original_wire, "visible_description": DEFERRABLE_SERVICE_DESCRIPTION}
    assert offer == {**baseline_offer, "visible_description": DEFERRABLE_SERVICE_DESCRIPTION}
    recovered = IntentionLedger(json.loads(json.dumps(ledger.state)))
    admitted = recovered.apply({"kind": "engage_goal", "opportunity_id": offer["opportunity_id"]}, sim_hour=SIM_HOUR)
    assert admitted == task
    assert admitted.visible_description == recovered.goal["visible_description"] == offer["visible_description"]
    with pytest.raises(ValueError, match="Unknown login scene"):
        login_offer(scene="bad")
