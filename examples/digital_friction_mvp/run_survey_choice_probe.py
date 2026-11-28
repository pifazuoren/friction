"""Freeze same-question, answer-blind prompts, then obtain independent GLM replies."""

import argparse
import getpass
import hashlib
import json
import os
import random
import re
from pathlib import Path


MODEL = "glm-4-flashx"
ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/"
BACKGROUND = {1: "年龄段", 2: "教育程度", 3: "居住情况", 4: "手机熟练程度", 5: "日常手机用途",
              6: "近一个月想用手机办事却没办顺利的频率", 13: "平时可以向谁求助", 14: "平时获得帮助的方式"}
SCENES = (("self", 17), ("guidance", 20), ("proxy", 23))
SYSTEM = ("根据给定背景代入这位答题者，独立回答这一次问卷。按你认为最可能的情况选一个首选行动，"
          "并评估无人帮助时独自登录的把握。六种行动都可以选。只返回一个 JSON 对象，"
          "action 为 A 到 F 的一个大写字母，confidence 为 1 到 5 的整数。")
SETTINGS = {"model": MODEL, "temperature": 0.1, "max_tokens": 80}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_instrument(text):
    blocks = dict(re.findall(r"(?ms)^\*\*(\d+)\. [^\n]+?\*\*\n(.*?)(?=^\*\*\d+\. |^###? |\Z)", text))
    choices = {q: dict(re.findall(r"(?m)^- ([A-H])\. (.+)$", blocks[str(q)])) for q in BACKGROUND}
    factors = [s for s in re.findall(r"(?m)^\| ([^|]+?) \|\s*\|$", blocks["16"])]
    if len(factors) != 8:
        raise ValueError("Expected eight named factors in Q16")
    scenes = {}
    for (name, q), chunk in zip(SCENES, re.split(r"(?m)^### 情境.+\n", text)[1:], strict=True):
        description, tail = chunk.split(f"**{q}. ", 1)
        first_question = tail.split("**", 1)[0]
        options = re.findall(r"(?m)^- ([A-F]\. .+)$", blocks[str(q)])
        if len(options) != 6:
            raise ValueError(f"Bad choice list at Q{q}")
        confidence_question = re.search(rf"\*\*{q+1}\. (.*?)\*\*", chunk).group(1)
        scenes[name] = (description.strip() + "\n\n" + first_question + "\n" + "\n".join(options) +
                        "\n" + confidence_question + " 1＝完全没有把握，5＝非常有把握。")
    return choices, factors, scenes


def coded_background(section, choices, factors):
    background = {}
    for q, title in BACKGROUND.items():
        value = re.search(rf"(?m)^- \*\*Q{q} [^*]+\*\*\s*([^\n]+)", section)
        if not value:
            raise ValueError(f"Missing Q{q}")
        codes = [re.match(r"\s*([A-H])[.．]", part) for part in value[1].split("；")]
        if not all(codes) or (q not in {5, 13, 14} and len(codes) != 1):
            raise ValueError(f"Invalid categorical codes at Q{q}")
        # Decode using only labels from the blank questionnaire; free text never enters a prompt.
        background[title] = "、".join(choices[q][code[1]].split("：")[0] for code in codes)
    ratings = {}
    for factor in factors:
        match = re.search(rf"\| {re.escape(factor)} \| ([1-5]) \|", section)
        if not match:
            raise ValueError("Missing Q16 rating")
        ratings[factor] = int(match[1])
    background["平时这些因素对自己是否求助的影响程度（1到5，从小到大）"] = ratings
    return background


def freeze(args):
    choices, factors, scenes = read_instrument(args.instrument.read_text(encoding="utf-8"))
    sections = re.split(r"(?m)^## (?:模拟)?答卷 ([A-Za-z0-9_-]+)[^\n]*\n", args.source.read_text(encoding="utf-8"))
    people = sections[1::2]
    if not people or len(set(people)) != len(people):
        raise ValueError("Expected distinct respondent codes")
    cases = []
    for person, section in zip(people, sections[2::2], strict=True):
        background = coded_background(section, choices, factors)
        for condition, scenario in scenes.items():
            user = "已知背景\n" + json.dumps(background, ensure_ascii=False, indent=2) + "\n\n本次问卷\n" + scenario
            cases.append(dict(case_id=f"{person}_{condition}", person=person, condition=condition,
                              messages=[dict(role="system", content=SYSTEM), dict(role="user", content=user)]))
    random.Random(101).shuffle(cases)
    payload = b"".join(encode(case) + b"\n" for case in cases)
    args.run_dir.mkdir(parents=True, exist_ok=False)
    (args.run_dir / "blind_inputs.jsonl").write_bytes(payload)
    save_json(args.run_dir / "design.json", dict(
        source_sha256=digest(args.source.read_bytes()), instrument_sha256=digest(args.instrument.read_bytes()),
        model=MODEL, endpoint=ENDPOINT, settings=SETTINGS, order_seed=101, cases=len(cases), people=len(people),
        inputs_sha256=digest(payload), source_type=args.source_type, background_questions=[*BACKGROUND,16],
        withheld="Q17–25 incl. reasons, all other responses outside the background whitelist",
        scoring="six-way action match by condition, independent-login confidence MAE, within-person guidance/proxy comparison",
        baseline="leave-one-person-out action mode (ties A through F) and confidence median for each condition",
        interpretation="isolated questionnaire prompts; one initial response, no format retries, no AgentSociety rule or rollout"))
    print(f"Frozen {len(cases)} independent prompts for {len(people)} profiles.")


def parsed_answer(raw):
    try:
        answer = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if (type(answer) is dict and set(answer) == {"action", "confidence"}
            and answer["action"] in list("ABCDEF") and type(answer["confidence"]) is int
            and 1 <= answer["confidence"] <= 5):
        return answer
    return None


def predict(args):
    import httpx
    from openai import OpenAI

    design = json.loads((args.run_dir / "design.json").read_bytes())
    payload = (args.run_dir / "blind_inputs.jsonl").read_bytes()
    if digest(payload) != design["inputs_sha256"] or SETTINGS != design["settings"] or ENDPOINT != design["endpoint"]:
        raise ValueError("Frozen inputs or model settings changed")
    cases = [json.loads(line) for line in payload.splitlines()]
    output = args.run_dir / "model_answers.jsonl"
    previous = [json.loads(line) for line in output.read_bytes().splitlines()] if output.exists() else []
    if len(previous) > len(cases) or any(row["case_id"] != case["case_id"] or
            row["input_sha256"] != digest(encode(case["messages"])) for row, case in zip(previous, cases)):
        raise ValueError("Response records do not match the frozen run")
    if len(previous) == len(cases):
        return
    key = os.environ.get("ZHIPUAI_API_KEY") or getpass.getpass("智谱 API Key（隐藏输入）：")
    with OpenAI(api_key=key, base_url=ENDPOINT, timeout=45, max_retries=0,
                http_client=httpx.Client(trust_env=False)) as client, output.open("a", encoding="utf-8") as out:
        for i, case in enumerate(cases[len(previous):], start=len(previous)+1):
            reply = client.chat.completions.create(**SETTINGS, messages=case["messages"])
            if reply.model != MODEL:
                raise RuntimeError(f"Unexpected response model: {reply.model}")
            raw = reply.choices[0].message.content
            parsed = parsed_answer(raw)
            row = dict(case_id=case["case_id"], input_sha256=digest(encode(case["messages"])), model=reply.model,
                       response_id=reply.id, raw=raw, valid=bool(parsed), action=parsed["action"] if parsed else None,
                       confidence=parsed["confidence"] if parsed else None, usage=reply.usage.model_dump() if reply.usage else {})
            out.write(encode(row).decode() + "\n")
            out.flush()
            if i % 10 == 0 or i == len(cases):
                print(f"{i}/{len(cases)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--instrument", required=True, type=Path)
    prepare.add_argument("--source", required=True, type=Path)
    prepare.add_argument("--source-type", choices=("synthetic", "unverified", "researcher_reported_survey", "documented_survey"),
                         required=True)
    for command in (prepare, commands.add_parser("predict")):
        command.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    (freeze if args.command == "prepare" else predict)(args)
