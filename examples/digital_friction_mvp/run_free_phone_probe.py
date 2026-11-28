"""Re-ask production Needs on paired archived free hours, with one extra historical fact."""
import argparse
import asyncio
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import random

from check_hourly_intention_run import request_payload
from proto.app_entry.needs import DigitalNeedsBlock, PHONE_USE_NEEDS_V3, PHONE_USE_NEEDS_VERSION, stated_phone_use_decision
from proto.app_entry.rollout import with_phone_use_habit_fact
from proto.llm_trace import LLMRunInterrupted
from run_strategy_memory_pairs import ENDPOINT, MODEL


def fingerprint(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


async def ask(transport, case, arm):
    body = request_payload({"messages": case["old_messages"]})
    inputs = body["inputs"]
    version = PHONE_USE_NEEDS_V3
    if arm == "new":
        inputs = with_phone_use_habit_fact(inputs, case["same_hour_context_counts"])
        version = PHONE_USE_NEEDS_VERSION
    params = case["old_parameters"]
    return await DigitalNeedsBlock().forward(llm=transport, input_payload=inputs, prompt_version=version,
                                              timeout=params["timeout"], retries=params["retries"], json_attempts=1)


class Capture:
    async def atext_request(self, *, dialog, **params):
        self.messages, self.params = dialog, params
        raise LLMRunInterrupted("Captured the first request offline")


async def make_design(folder, cases):
    manifest = json.loads((folder / "selection_design.json").read_text())
    selection_hash = hashlib.sha256((folder / "selection.jsonl").read_bytes()).hexdigest()
    if selection_hash != manifest["selection_sha256"]:
        raise ValueError("Selection changed since sampling")
    source = folder.parents[1] / "scheduled_login" / manifest["source"]
    # Use the upstream frozen hash only; outcome labels are never opened by this runner.
    archived_config = json.loads((source / "resolved_config.json").read_text())
    cases_order = list(cases.values())
    rng = random.Random(101)
    rng.shuffle(cases_order)
    schedule = []
    for i, case in enumerate(cases_order):
        messages = {}
        for arm in ("old", "new"):
            capture = Capture()
            try:
                await ask(capture, case, arm)
            except LLMRunInterrupted:
                pass
            if capture.params != case["old_parameters"]:
                raise ValueError("Archived first request parameters changed")
            messages[arm] = capture.messages
        if messages["old"] != case["old_messages"] or fingerprint(messages["old"]) != case["old_messages_sha256"]:
            raise ValueError(f"Old request differs from archive for {case['case_id']}")
        old, new = (request_payload({"messages": messages[a]}) for a in ("old", "new"))
        fact = new["inputs"]["day1_3_habit"].pop("device_history_fact")
        version = new.pop("schema_version")
        if (not fact or version != PHONE_USE_NEEDS_VERSION or old.pop("schema_version") != PHONE_USE_NEEDS_V3
                or old != new or messages["old"][0] != messages["new"][0]):
            raise ValueError("The paired messages differ beyond the version and historical fact")
        for arm in (("old", "new") if i % 2 == 0 else ("new", "old")):
            schedule.append(dict(case_id=case["case_id"], arm=arm, initial_sha256=fingerprint(messages[arm])))
    return dict(model=MODEL, selection_sha256=selection_hash, heldout_sha256=archived_config["evaluation_heldout_sha256"],
                n_cases=len(cases), schedule=schedule, max_requests=len(schedule)*2,
                split="Disjoint residents. One frozen wording used on both splits, no tuning on the results.",
                endpoint="Independently re-asked Needs intent, after at most one format repair. No Plan or writeback.",
                comparison="On paired valid held-out hours, compare active recall and idle recall together; a uniform shift alone does not establish improvement.")


class ProbeTransport:
    def __init__(self, client, spec, params):
        self.client = client
        self.spec = spec
        self.params = params
        self.exchanges = []

    async def atext_request(self, *, dialog, **params):
        if not self.exchanges and (fingerprint(dialog) != self.spec["initial_sha256"] or params != self.params):
            raise LLMRunInterrupted("Initial request differs from the verified pair")
        if len(self.exchanges) >= 2:
            raise LLMRunInterrupted("Exceeded the two-request limit for this arm")
        try:
            reply = await self.client.chat.completions.create(
                model=MODEL, messages=dialog, temperature=params["temperature"],
                max_tokens=params["max_tokens"], timeout=params["timeout"])
        except Exception as exc:
            raise LLMRunInterrupted(f"Provider error {type(exc).__name__}, status {getattr(exc,'status_code',None)}") from None
        if reply.model != MODEL:
            raise LLMRunInterrupted("Provider returned a different model")
        raw = reply.choices[0].message.content or ""
        self.exchanges.append(dict(messages=dialog, parameters=params, raw=raw, model=reply.model,
                                   response_id=reply.id, usage=reply.usage.model_dump() if reply.usage else {}))
        return raw


async def run(folder, prepare_only):
    cases = {c["case_id"]: c for c in load_lines(folder / "selection.jsonl")}
    design = await make_design(folder, cases)
    design_path = folder / "experiment_design.json"
    if design_path.exists():
        if json.loads(design_path.read_bytes()) != design:
            raise ValueError("The generated design differs from the frozen design")
    else:
        with design_path.open("x", encoding="utf-8") as out:
            json.dump(design, out, indent=2, ensure_ascii=False)
            out.write("\n")
    print(f"Verified {len(cases)} pairs at the production request boundary.", flush=True)
    if prepare_only:
        return
    dest = folder / "probe_decisions.jsonl"
    completed = load_lines(dest) if dest.exists() else []
    for i, row in enumerate(completed):
        if any(row[k] != v for k, v in design["schedule"][i].items()):
            raise ValueError("Saved responses disagree with the frozen schedule")
    if len(completed) == len(design["schedule"]):
        return
    import httpx
    from openai import AsyncOpenAI

    key = os.environ.get("ZHIPUAI_API_KEY") or getpass("智谱 API Key（隐藏输入）：")
    async with AsyncOpenAI(api_key=key, base_url=ENDPOINT, max_retries=0,
                           http_client=httpx.AsyncClient(trust_env=False)) as client:
        with dest.open("a", encoding="utf-8") as out:
            for i, spec in enumerate(design["schedule"][len(completed):], len(completed)+1):
                case = cases[spec["case_id"]]
                transport = ProbeTransport(client, spec, case["old_parameters"])
                try:
                    result = await ask(transport, case, spec["arm"])
                    accepted, status = result.phone_use_decision, result.audit["parse_status"]
                except ValueError as exc:
                    if not str(exc).startswith("DigitalNeedsBlock JSON output failed after bounded attempts:"):
                        raise
                    accepted, status = None, str(exc).rsplit(": ", 1)[-1]
                row = dict(**spec, model=MODEL, raw_initial_choice=stated_phone_use_decision(transport.exchanges[0]["raw"]),
                           accepted_choice=accepted, parse_status=status, requests=len(transport.exchanges),
                           exchanges=transport.exchanges)
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                if i % 8 == 0 or i == len(design["schedule"]):
                    print(f"{i}/{len(design['schedule'])} decisions recorded", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.run_dir.resolve(), args.prepare_only))
