"""Run ten paired GLM strategy judgments and three identical-input controls."""

import argparse
import asyncio
import copy
from datetime import datetime
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import random
from types import SimpleNamespace
from uuid import uuid4

from analysis_strategy_memory_pairs import summarize
from compare_strategy_prompt_runs import compare_runs, stimuli_match
from probe_strategy_memory_pair import run_pair_member
from proto.llm_trace import bind_trace_context, traced_agent_tick


EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
MODEL = "glm-4-flashx"
ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/"
SEED = 101


def schedule():
    rng = random.Random(SEED)
    orders = [("A", "B"), ("B", "A")] * 5
    rng.shuffle(orders)
    pairs = []
    for i, order in enumerate(orders, 1):
        pairs.append(dict(pair_id=f"contrast-{i:02d}", kind="contrast", order=order,
                          conditions={"A": "success", "B": "failure"}, sample_u=rng.random()))
    for i, condition in enumerate(("success", "failure", "success"), 1):
        order = rng.sample(["A", "B"], 2)
        pairs.append(dict(pair_id=f"repeat-{i:02d}", kind="repeat", order=order,
                          conditions={"A": condition, "B": condition}, sample_u=rng.random()))
    rng.shuffle(pairs)
    return pairs


class OfflineCapture:
    """Capture the initial messages at the production transport boundary."""
    def __init__(self):
        self.dialogs = []

    async def atext_request(self, *, dialog, **kwargs):
        self.dialogs.append(copy.deepcopy(dialog))
        return json.dumps({
            "attempt_self_score": .45, "seek_help_score": .35, "avoid_score": .20,
            "dominant_strategy": "attempt_self", "judge_confidence": .90, "reason": "Offline check",
        })


async def check_stimuli(prompt_format="scored_example"):
    dialogs = {}
    for condition in ("success", "failure"):
        capture = OfflineCapture()
        result = await run_pair_member(capture, condition, .5, prompt_format=prompt_format)
        if len(capture.dialogs) != 1 or result["source"] != "hybrid_blended":
            raise ValueError("Offline verification did not reach the strategy model and production sampler")
        dialogs[condition] = capture.dialogs[0]
    a, b = dialogs["success"], dialogs["failure"]
    if len(a) != 2 or len(b) != 2 or a[0] != b[0] or a[1]["role"] != b[1]["role"]:
        raise ValueError("Unexpected production strategy message structure")
    prefix_a, body_a = a[1]["content"].split("\n", 1)
    prefix_b, body_b = b[1]["content"].split("\n", 1)
    left, right = json.loads(body_a), json.loads(body_b)
    episodes_a = left["task_relevant_memory"]["recent_task_episodes"]
    episodes_b = right["task_relevant_memory"]["recent_task_episodes"]
    if len(episodes_a) != 1 or len(episodes_b) != 1:
        raise ValueError("The controlled prompt must contain one target episode")
    old, new = episodes_a[0], episodes_b[0]
    if (old["outcome_type"], new["outcome_type"], old["negative_feedback"], new["negative_feedback"]) != (
        "success_self", "failure_after_attempt", False, True
    ) or old["strategy_type"] != "attempt_self" or not old["episode_id"]:
        raise ValueError("Wrong day-four strategy, outcome or feedback")
    old.update(outcome_type=new["outcome_type"], negative_feedback=new["negative_feedback"])
    if prefix_a != prefix_b or left != right:
        raise ValueError("Success/failure messages differ outside the two target episode fields")
    return dialogs


def verify_reference(reference, stimuli, pairs, prompt_format="field_rules"):
    design = json.loads((reference / "design.json").read_text(encoding="utf-8"))
    original = json.loads((reference / "stimuli.json").read_text(encoding="utf-8"))
    if design["model"] != MODEL or design["pairs"] != json.loads(json.dumps(pairs)):
        raise ValueError("The model, pair order or shared random draws differ from the reference run")
    if not stimuli_match(original, stimuli, prompt_format):
        raise ValueError("The system prompt, message structure or fields differ outside the selected change")


class ZhipuStrategyClient:
    def __init__(self, client, expected_dialog):
        self.client = client
        self.expected_dialog = expected_dialog
        self.requests = 0
        self.transport_errors = []
        self.returned_models = []
        self.configs = [SimpleNamespace(model=MODEL)]

    async def atext_request(self, *, dialog, temperature, max_tokens, timeout, retries):
        if not self.requests and dialog != self.expected_dialog:
            raise RuntimeError("Live strategy prompt differs from the verified stimulus")
        self.requests += 1
        try:
            reply = await self.client.chat.completions.create(
                model=MODEL, messages=dialog, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout,
            )
        except Exception as error:
            self.transport_errors.append({
                "error_type": type(error).__name__, "http_status": getattr(error, "status_code", None),
            })
            raise
        self.returned_models.append(reply.model)
        return reply.choices[0].message.content or ""


@traced_agent_tick
async def run_arm(transport, pair, arm, prompt_format="scored_example"):
    condition = pair["conditions"][arm]
    bind_trace_context(pair_id=pair["pair_id"], arm=arm, condition=condition, sample_u=pair["sample_u"])
    result = await run_pair_member(transport, condition, pair["sample_u"], prompt_format=prompt_format)
    if transport.requests == 0 or result.get("cache_hit"):
        raise RuntimeError("Strategy model was bypassed; stopping the pair experiment")
    return {
        **result, "pair_id": pair["pair_id"], "kind": pair["kind"], "arm": arm,
        "condition": condition, "sample_u": pair["sample_u"], "requests": transport.requests,
        "returned_models": transport.returned_models, "transport_errors": transport.transport_errors,
    }


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


async def study(client, folder, stimuli, pairs, prompt_format="scored_example"):
    rows = []
    with (folder / "decisions.jsonl").open("x", encoding="utf-8") as stream:
        for index, pair in enumerate(pairs, 1):
            print(f"[{index}/13] {pair['pair_id']}", flush=True)
            for arm in pair["order"]:
                transport = ZhipuStrategyClient(client, stimuli[pair["conditions"][arm]])
                row = await run_arm(transport, pair, arm, prompt_format)
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                rows.append(row)
                save_json(folder / "summary.json", summarize(rows))
                if any(e["http_status"] in {401, 403, 429} for e in row["transport_errors"]):
                    raise SystemExit("智谱未接受本次请求，实验已停止；已完成的判断保存在结果目录。")
    summary = summarize(rows)
    print(f"已记录 {len(rows)} 次判断，实际请求 {summary['requests_total']} 次；"
          f"其中 {summary['coverage']['hybrid_arms']} 次采纳了模型评分。")
    if not summary["coverage"]["hybrid_arms"]:
        raise SystemExit("全部判断使用了规则回退，本轮没有可用于比较的在线模型评分。")
    contrast = summary["contrast"]["all_complete"]
    repeats = summary["repeat"]["all_complete"]
    differences = contrast["mean_weight_difference_B_minus_A"]
    noise = repeats["mean_absolute_weight_difference"]
    print("策略        失败减成功的平均差    相同输入平均绝对差（百分点，含回退）")
    for action, label in (("attempt_self", "独立尝试"), ("seek_help_then_attempt", "求助再试"), ("avoid", "回避任务")):
        print(f"{label}        {100 * differences[action]:+7.2f}              {100 * noise[action]:6.2f}")
    print(f"相同抽样值下动作不同：成败对照 {contrast['action_flips']}/10 对，"
          f"相同输入 {repeats['action_flips']}/3 对。")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify the two stimuli offline and exit")
    parser.add_argument("--prompt-format", choices=("scored_example", "field_rules", "field_rules_no_priors"),
                        default="scored_example")
    parser.add_argument("--reference-run", type=Path,
                        help="Verify against the preceding variant: scored_example for field_rules, "
                             "or field_rules for field_rules_no_priors")
    args = parser.parse_args()
    reference = args.reference_run.resolve() if args.reference_run else None
    if reference and args.prompt_format == "scored_example":
        parser.error("--reference-run requires field_rules or field_rules_no_priors")
    os.chdir(ROOT)
    os.umask(0o077)
    for key in tuple(os.environ):
        if key.startswith("PROTO_"):
            del os.environ[key]
    os.environ.update(PROTO_TASK_ENTRY_MODE="fixed_assignment", PROTO_LLM_PSYCHOLOGY_MODE="hybrid",
                      PROTO_LLM_STRATEGY_DELIBERATION_ENABLED="true", PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED="false",
                      PROTO_LLM_PSYCHOLOGY_MIN_CONFIDENCE="0.65", PROTO_LLM_PSYCHOLOGY_RETRIES="1",
                      PROTO_LLM_PSYCHOLOGY_TIMEOUT="45")
    stimuli = await check_stimuli(args.prompt_format)
    pairs = schedule()
    if reference:
        verify_reference(reference, stimuli, pairs, args.prompt_format)
        change = ("隐藏了提示中的规则概率" if args.prompt_format == "field_rules_no_priors"
                  else "替换了输出示例")
        print(f"已与上一轮核对模型、任务、13 对顺序和抽样值，本轮仅{change}。", flush=True)
    print("已验证两组实际提示，只改变昨天独立登录的成败和相应的负反馈字段。", flush=True)
    if args.check:
        return
    import httpx
    from openai import AsyncOpenAI

    key = os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or ""
    if not key.strip() or key.strip() == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（输入隐藏，回车开始）：")
    if not key.strip() or key.strip() == "<YOUR-API-KEY>":
        parser.exit(2, "没有输入有效密钥，实验未启动。\n")
    run_id = "strategy_pairs_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
    folder = ROOT / "agentsociety_data/runs/strategy_memory_pairs" / run_id
    folder.mkdir(parents=True)
    os.environ.update(PROTO_LLM_TRACE_DIR=str(folder / "trace"), PARALLEL_GROUP_NAME=run_id)
    print(f"本次结果目录：{folder}", flush=True)
    save_json(folder / "stimuli.json", stimuli)
    sources = [Path(__file__), EXAMPLE / "analysis_strategy_memory_pairs.py", EXAMPLE / "probe_strategy_memory_pair.py",
               EXAMPLE / "config_runtime.py", *(EXAMPLE / "proto").rglob("*.py")]
    save_json(folder / "design.json", {
        "model": MODEL, "prompt_format": args.prompt_format, "reference_run": reference.name if reference else None,
        "order_and_sampling_seed": SEED, "pairs": pairs,
        "primary_comparison": "failure minus success, including rule fallback",
        "noise_comparison": "absolute differences within identical-input pairs",
        "sdk_retries": 0, "strategy_cache": False,
        "source_sha256": {str(p.relative_to(EXAMPLE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    })
    async with AsyncOpenAI(api_key=key.strip(), base_url=ENDPOINT, max_retries=0,
                           http_client=httpx.AsyncClient(trust_env=False)) as client:
        await study(client, folder, stimuli, pairs, args.prompt_format)
    print(f"结果汇总：{folder / 'summary.json'}")
    if reference:
        save_json(folder / "prompt_comparison.json", compare_runs(reference, folder))
        print(f"与原实验的对照：{folder / 'prompt_comparison.json'}")


if __name__ == "__main__":
    asyncio.run(main())
