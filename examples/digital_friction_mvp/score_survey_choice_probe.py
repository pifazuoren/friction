"""Score frozen predictions against the held-out choices and ratings in the supplied questionnaire file."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import mean, median


CONDITIONS = {"self": (17, 18), "guidance": (20, 21), "proxy": (23, 24)}
ACTIONS = "ABCDEF"
DEFAULT_INSTRUMENT = Path(__file__).resolve().parents[2] / "问卷.md"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def messages_hash(messages):
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_labels(path):
    # Only the multiple-choice letter and confidence number are retained from each target row.
    parts = re.split(r"^## (?:模拟)?答卷 ([A-Za-z0-9_-]+)[^\n]*$", path.read_text(encoding="utf-8"), flags=re.M)
    labels = {}
    for person, block in zip(parts[1::2], parts[2::2]):
        if person in labels:
            raise ValueError(f"Duplicate questionnaire {person}")
        labels[person] = {}
        for condition, (choice_id, confidence_id) in CONDITIONS.items():
            pattern = rf"^\|[^|\n]+\|\s*Q{choice_id}\s+([A-F])\.[^|\n]*\|\s*Q{confidence_id}\s+([1-5])\s*\|"
            found = re.findall(pattern, block, flags=re.M)
            if len(found) != 1:
                raise ValueError(f"Expected one held-out answer for {person} {condition}, found {len(found)}")
            action, confidence = found[0]
            labels[person][condition] = (action, int(confidence))
    if len(labels) < 2:
        raise ValueError("Leave-one-person-out scoring requires at least two people")
    return labels


def indexed_jsonl(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["case_id"] in rows:
            raise ValueError(f"Duplicate case {row['case_id']} in {path.name}")
        rows[row["case_id"]] = row
    return rows


def parse_reply(raw):
    if not isinstance(raw, str):
        return None
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    if (not isinstance(obj, dict) or set(obj) != {"action", "confidence"}
            or obj["action"] not in tuple(ACTIONS)
            or type(obj["confidence"]) is not int or not 1 <= obj["confidence"] <= 5):
        return None
    return obj["action"], obj["confidence"]


def parse_single_fence(raw):
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"```json\r?\n([\s\S]*?)\r?\n```", raw.strip())
    if match is None or "```" in match[1]:
        return None
    return parse_reply(match[1])


def verify_answer(answer, prompt_hash, allow_json_fence):
    if answer is None:
        return "missing", None, None, "missing"
    if answer.get("input_sha256") != prompt_hash:
        raise ValueError(f"Prediction input hash mismatch for {answer['case_id']}")
    parsed = parse_reply(answer.get("raw"))
    if (type(answer.get("valid")) is not bool or answer["valid"] != (parsed is not None)
            or (answer.get("action"), answer.get("confidence")) != (parsed or (None, None))
            or (parsed and type(answer.get("confidence")) is not int)):
        raise ValueError(f"Logged prediction disagrees with its raw reply for {answer['case_id']}")
    if parsed:
        return "valid", *parsed, "strict_valid"
    recovered = parse_single_fence(answer.get("raw")) if allow_json_fence else None
    if recovered:
        return "valid", *recovered, "wrapped_recovered"
    return "invalid", None, None, "invalid"


def leave_one_out(labels, person, condition):
    others = [answers[condition] for identity, answers in labels.items() if identity != person]
    votes = Counter(choice for choice, _ in others)
    action = max(ACTIONS, key=lambda option: votes[option])
    return action, median(value for _, value in others)


def accuracy(rows, predictor):
    by_action = {}
    for option in ACTIONS:
        observed = [r for r in rows if r["reference_action"] == option]
        by_action[option] = {
            "reference_n": len(observed),
            "predicted_n": sum(r[f"{predictor}_action"] == option for r in rows),
            "correct_n": sum(r[f"{predictor}_action"] == option for r in observed),
        }
    return {
        "n": len(rows),
        "correct_actions": sum(v["correct_n"] for v in by_action.values()),
        "by_action": by_action,
        "confidence_mae": mean(abs(r["reference_confidence"] - r[f"{predictor}_confidence"]) for r in rows)
                          if rows else None,
    }


def summarize_cases(rows):
    valid = [r for r in rows if r["status"] == "valid"]
    return {
        "scheduled": len(rows),
        "coverage": {s: sum(r["status"] == s for r in rows) for s in ("valid", "invalid", "missing")},
        "parse_counts": {s: sum(r["parse"] == s for r in rows)
                         for s in ("strict_valid", "wrapped_recovered", "invalid", "missing")},
        "model": accuracy(valid, "model"),
        "baseline_on_same_cases": accuracy(valid, "baseline"),
        "baseline_all_cases": accuracy(rows, "baseline"),
    }


def sign(value):
    return (value > 0) - (value < 0)


def add_pair_fields(wide, predictor):
    guide = wide[f"guidance_{predictor}_action"]
    proxy = wide[f"proxy_{predictor}_action"]
    if guide is None or proxy is None:
        return
    wide[f"{predictor}_action_changed"] = guide != proxy
    wide[f"{predictor}_self_attempt_delta"] = int(guide == "A") - int(proxy == "A")
    wide[f"{predictor}_confidence_delta"] = wide[f"guidance_{predictor}_confidence"] - wide[f"proxy_{predictor}_confidence"]


def describe_pairs(people, predictor):
    subset = [p for p in people if f"{predictor}_action_changed" in p]
    if not subset:
        return {"paired_people": 0}
    result = {
        "paired_people": len(subset),
        "reference_changed": sum(p["reference_action_changed"] for p in subset),
        "predicted_changed": sum(p[f"{predictor}_action_changed"] for p in subset),
        "change_or_stay_correct": sum(p["reference_action_changed"] == p[f"{predictor}_action_changed"] for p in subset),
        "both_actions_exact": sum(all(p[f"{arm}_reference_action"] == p[f"{arm}_{predictor}_action"]
                                      for arm in ("guidance", "proxy")) for p in subset),
    }
    for field in ("self_attempt_delta", "confidence_delta"):
        reference = [p[f"reference_{field}"] for p in subset]
        predicted = [p[f"{predictor}_{field}"] for p in subset]
        result[field] = {
            "reference_mean": mean(reference),
            "predicted_mean": mean(predicted),
            "absolute_error_mean": mean(abs(a-b) for a, b in zip(reference, predicted)),
            "direction_correct": sum(sign(a) == sign(b) for a, b in zip(reference, predicted)),
            "reference_directions": dict(Counter(sign(a) for a in reference)),
            "predicted_directions": dict(Counter(sign(a) for a in predicted)),
        }
    return result


def score(source, folder, instrument, allow_json_fence=False):
    design = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    if file_hash(source) != design["source_sha256"] or file_hash(instrument) != design["instrument_sha256"]:
        raise ValueError("Scoring source or survey instrument differs from frozen design")
    labels = read_labels(source)
    blind_path = folder / "blind_inputs.jsonl"
    raw_path = folder / "model_answers.jsonl"
    input_digest = file_hash(blind_path)
    if input_digest != design["inputs_sha256"]:
        raise ValueError("Blind input archive differs from the frozen design")
    cases = indexed_jsonl(blind_path)
    answers = indexed_jsonl(raw_path) if raw_path.exists() else {}
    expected = {f"{person}_{condition}" for person in labels for condition in CONDITIONS}
    if set(cases) != expected or set(answers) - expected:
        raise ValueError("Blind cases or recorded predictions do not align with scheduled survey cases")
    if len(cases) != design["cases"] or len(labels) != design["people"]:
        raise ValueError("Frozen design counts differ from the reconstructed cohort")
    if any(a.get("model") != design["model"] for a in answers.values()):
        raise ValueError("Prediction model differs from the frozen design")
    cases_by_arm = {condition: [] for condition in CONDITIONS}
    people = []
    for person, reference in sorted(labels.items()):
        wide = {"person": person}
        for condition, (action, confidence) in reference.items():
            identity = f"{person}_{condition}"
            case = cases[identity]
            if case["person"] != person or case["condition"] != condition:
                raise ValueError(f"Misaligned blind case {identity}")
            status, pred, rating, reply_parse = verify_answer(answers.get(identity), messages_hash(case["messages"]),
                                                              allow_json_fence)
            baseline_action, baseline_conf = leave_one_out(labels, person, condition)
            row = dict(status=status, parse=reply_parse, reference_action=action, reference_confidence=confidence,
                       model_action=pred, model_confidence=rating, baseline_action=baseline_action,
                       baseline_confidence=baseline_conf)
            cases_by_arm[condition].append(row)
            wide.update({f"{condition}_{k}": v for k, v in row.items()})
        for predictor in ("reference", "model", "baseline"):
            add_pair_fields(wide, predictor)
        people.append(wide)
    pair_complete = [p for p in people if "model_action_changed" in p]
    report = {
        "source_sha256": design["source_sha256"], "instrument_sha256": design["instrument_sha256"],
        "blind_inputs_sha256": input_digest, "model_answers_sha256": file_hash(raw_path) if raw_path.exists() else None,
        "model": design["model"], "reference_type": design["source_type"],
        **({"reference_note": design["source_note"]} if design.get("source_note") else {}),
        "format_policy": ("post-hoc sensitivity: also accept an entire single json Markdown fence containing the strict schema"
                          if allow_json_fence else "primary: strict JSON"),
        "action_options": dict(zip(ACTIONS, ("自己尝试", "请家人指导", "请家人代办", "推迟", "其他方式", "不再办理"))),
        "scheduled_people": len(labels), "contrast": "guidance minus proxy",
        "baseline": "Same scenario, excluding all records from the target person. Most frequent action (A–F tie break), median confidence.",
        "by_condition": {k: summarize_cases(v) for k, v in cases_by_arm.items()},
        "all_conditions": summarize_cases([r for group in cases_by_arm.values() for r in group]),
        "guidance_vs_proxy": {
            "model": describe_pairs(people, "model"),
            "baseline_on_same_people": describe_pairs(pair_complete, "baseline"),
            "baseline_all_people": describe_pairs(people, "baseline"),
            "missing_or_invalid_pair": len(people) - len(pair_complete),
        },
    }
    suffix = "_unwrapped" if allow_json_fence else ""
    person_file = folder / f"survey_comparison_by_person{suffix}.csv"
    fields = list(dict.fromkeys(field for p in people for field in p))
    with person_file.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(people)
    (folder / f"survey_comparison{suffix}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--instrument", type=Path, default=DEFAULT_INSTRUMENT)
    parser.add_argument("--allow-json-fence", action="store_true", help="Post-hoc sensitivity, written to separate files.")
    args = parser.parse_args()
    summary = score(args.source, args.run_dir, args.instrument, args.allow_json_fence)
    print(json.dumps(summary["all_conditions"], ensure_ascii=False))
