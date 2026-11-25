"""Run paired Day 4 app-entry experiments using the August GLM configuration."""

import argparse
import csv
from datetime import datetime
from getpass import getpass
from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from urllib.parse import urlsplit


EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
SNAPSHOT = EXAMPLE / "analysis/config_snapshot_smoke_phase3a_plan_v3_1agent_day4_seed101.json"
WORLD = "baseline_low_friction"


def configure_http_client(env):
    # HTTPX initializes ALL_PROXY even if explicit HTTP and HTTPS proxies take
    # precedence. Retain both explicit routes when the optional SOCKS client is absent.
    http = env.get("http_proxy") or env.get("HTTP_PROXY", "")
    https = env.get("https_proxy") or env.get("HTTPS_PROXY", "")
    if all(urlsplit(proxy).scheme in {"http", "https"} for proxy in (http, https)):
        for name in ("ALL_PROXY", "all_proxy"):
            if urlsplit(env.get(name, "")).scheme in {"socks5", "socks5h"} and find_spec("socksio") is None:
                env.pop(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", type=int, choices=(1, 10), default=1)
    parser.add_argument("--prompt-key", action="store_true",
                        help="Prompt without echo if no Zhipu credential is configured")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "report/2026结项/在线入口对照")
    args = parser.parse_args()
    env = os.environ.copy()
    key = env.get("LLM_API_KEY") or env.get("ZHIPUAI_API_KEY")
    if not key and args.prompt_key and sys.stdin.isatty():
        key = getpass("智谱 API key（输入隐藏，仅本次运行使用）：").strip()
    if not key or key.strip() == "<YOUR-API-KEY>":
        parser.exit(2, "未检测到智谱凭据。可在本机终端使用 --prompt-key，或设置 "
                       "ZHIPUAI_API_KEY。本次未发起 API 请求。\n")

    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["config_payload"]
    env.update({k: v for k, v in payload.items() if isinstance(v, str)})
    env.update(LLM_API_KEY=key, AGENT_COUNT=str(args.agents))
    configure_http_client(env)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]
    directory = args.output_dir.resolve() / f"{stamp}_{args.agents}台"
    directory.mkdir(parents=True)
    print(f"实验与逐小时结果保存至 {directory}", flush=True)

    device_path = ROOT / payload["PROTO_APP_ENTRY_REPLAY_DEVICE_PATH"]
    with device_path.open(encoding="utf-8-sig", newline="") as handle:
        selected = sorted(csv.DictReader(handle), key=lambda r: int(r["selected_rank"]))[:args.agents]
    scoring = [sys.executable, str(EXAMPLE / "analysis_entry_calibration_comparison.py"),
               "--output-dir", str(directory / "配对评分")]
    scoring.extend("--device=" + row["device_id"] for row in selected)
    for method, version in (("old", "app_entry_plan_v3"), ("new", "app_entry_plan_v4_calibrated")):
        run = f"day4_{stamp}_{args.agents}agents_{method}"
        env["PROTO_APP_ENTRY_PLAN_PROMPT_VERSION"] = version
        command = [
            sys.executable, str(EXAMPLE / "world_runner.py"), "--group-id", run,
            "--world-batch", WORLD, "--seed-list", "101", "--analysis-dir",
            str(directory), "--summarize",
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        manifest = json.loads((directory / f"exp_group_manifest_{run}.json").read_text())
        if len(manifest) != 1 or manifest[0]["status"] != "ok":
            raise SystemExit(f"运行未完成，请检查 {directory / ('exp_group_manifest_' + run + '.json')}")
        rollout = directory / f"app_entry_rollout_hourly_{run}.csv"
        scoring.extend([f"--{method}-rollout", str(rollout)])
        errors = directory / f"app_entry_rollout_errors_{run}.csv"
        if errors.exists():
            scoring.extend([f"--{method}-errors", str(errors)])
    subprocess.run(scoring, cwd=ROOT, check=True)
    print(f"比较结果：{directory / '配对评分/summary.csv'}")


if __name__ == "__main__":
    main()
