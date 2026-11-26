"""Prepare and run a paired seven-day study of prior login difficulty."""

import argparse
from datetime import datetime
import fcntl
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from uuid import uuid4

from prepare_login_cohort import prepare_cohort
from proto.app_entry.bundle_loader import get_replay_source
from proto.runtime import scheduled_login_difficulty_delta
from run_social_memory_week import DATA, EXAMPLE, ROOT, SETTINGS, WORLD


ARMS = ("standard", "elevated")


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths():
    files = ["main.py", "world_runner.py", "config_runtime.py", "persistence.py",
             "run_social_memory_week.py", "prepare_login_cohort.py", "run_login_difficulty_study.py"]
    return [EXAMPLE / name for name in files] + sorted((EXAMPLE / "proto").rglob("*.py"))


def make_design(folder, count, seeds):
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Pass one or more distinct simulation seeds")
    if not 1 <= count <= 6:
        raise ValueError("The 60+ reference cohort supports 1 to 6 profiles")
    folder.mkdir(parents=True, exist_ok=False)
    inputs = folder / "inputs"
    inputs.mkdir()
    devices = prepare_cohort(inputs, count)
    replay = get_replay_source(bundle_path=str(inputs / "replay.csv"), device_mapping_path=str(inputs / "devices.csv"),
                               replay_days=(1, 2, 3))
    if replay.selected_devices != [(d["rank"], d["device_id"]) for d in devices]:
        raise ValueError("Replay device mapping differs from the selected profiles")
    runs = []
    order = list(ARMS)
    random.Random(9421).shuffle(order)
    for index, seed in enumerate(seeds):
        for arm in (order if index % 2 == 0 else list(reversed(order))):
            group = f"{folder.name}_s{seed}_{arm}"
            runs.append(dict(seed=seed, arm=arm, group=group, dir=f"runs/{group}"))
    settings = dict(SETTINGS, AGENT_COUNT=str(count), STAGE_DAYS="7", PROTO_SCHEDULED_LOGIN_HOUR="9",
                    PROTO_LLM_STRATEGY_PROMPT_FORMAT="field_rules_no_priors",
                    PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH=str(inputs / "replay.csv"),
                    PROTO_APP_ENTRY_REPLAY_DEVICE_PATH=str(inputs / "devices.csv"),
                    DIGITAL_FRICTION_PROFILES_PATH=str(inputs / "profiles.json"))
    design = dict(
        seeds=seeds, profile_count=count, devices=devices, arms=list(ARMS), runs=runs,
        scheduled_hour=9, exposure_days=[4, 5, 6], probe_day=7,
        difficulty_increment=scheduled_login_difficulty_delta("elevated", 4),
        primary="Elevated minus standard proportion avoiding the first scheduled Day 7 login, paired by rank and seed.",
        unit="Simulated profile linked to a reference device. Seeds are repeated simulations of these profiles.",
        sampling_frame="Age 60+ within 59 previously selected active devices. The upstream 59-device selection used full-week activity.",
        interpretation="Difficulty is an experimental task parameter. Observed devices supply app usage, not strategies or psychological outcomes.",
        settings=settings, replay_hours_per_device=72, order_seed=9421,
        source_sha256={str(p.relative_to(EXAMPLE)): sha(p) for p in source_paths()},
        input_sha256={p.name: sha(p) for p in (inputs / "profiles.json", inputs / "replay.csv", inputs / "devices.csv")},
    )
    save(folder / "design.json", design)
    return design


def run_environment(settings, run, folder):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PROTO_", "PARALLEL_")) and k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    env.update(settings)
    env.update(EXP_SEED=str(run["seed"]), PROTO_LOGIN_DIFFICULTY_ARM=run["arm"],
               PARALLEL_GROUP_NAME=run["group"], PROTO_LLM_TRACE_DIR=str(folder / "trace"),
               PYTHONUNBUFFERED="1")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def completed(folder, group):
    manifest = folder / f"exp_group_manifest_{group}.json"
    if not manifest.is_file():
        return False
    rows = json.loads(manifest.read_text())
    return (len(rows) == 1 and rows[0].get("group_id") == group and rows[0].get("world_name") == WORLD
            and rows[0].get("status") == "ok" and rows[0].get("return_code") == 0
            and (folder / f"app_entry_replay_summary_{group}.csv").is_file())


def run_arm(run, folder, settings, key):
    folder.mkdir(parents=True, exist_ok=False)
    env = run_environment(settings, run, folder)
    env["LLM_API_KEY"] = key
    cmd = [sys.executable, str(EXAMPLE / "world_runner.py"), "--group-id", run["group"],
           "--seed-list", str(run["seed"]), "--world-batch", WORLD, "--analysis-dir", str(folder), "--summarize"]
    print(f"开始 seed={run['seed']} arm={run['arm']}。日志 {folder / 'run.log'}", flush=True)
    with (folder / "run.log").open("x", encoding="utf-8") as log, subprocess.Popen(
        cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
    ) as proc:
        for line in proc.stdout:
            log.write(line.replace(key, "[redacted]"))
            log.flush()
        code = proc.wait()
    if code or not completed(folder, run["group"]):
        raise RuntimeError(f"Run failed, see {folder / 'run.log'}")


def execute(folder, design, retry_failed):
    for rel, digest in design["source_sha256"].items():
        if sha(EXAMPLE / rel) != digest:
            raise ValueError(f"Source changed since preparation: {rel}. Prepare a new study.")
    for name, digest in design["input_sha256"].items():
        if sha(folder / "inputs" / name) != digest:
            raise ValueError(f"Study input has changed: {name}")
    if not os.access(DATA / "agentsociety-sim-oss", os.X_OK) or not Path(design["settings"]["MAP_FILE_PATH"]).is_file():
        raise FileNotFoundError("Local simulator or map is missing")
    key = None
    for run in design["runs"]:
        target = folder / run["dir"]
        if completed(target, run["group"]):
            continue
        if target.exists() and not retry_failed:
            raise RuntimeError(f"Partial run in {target}. --retry-failed preserves it and retries the same arm.")
        if key is None:
            key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
            if key in ("", "<YOUR-API-KEY>"):
                key = getpass("智谱 API Key（输入隐藏）：").strip()
            if key in ("", "<YOUR-API-KEY>"):
                raise ValueError("Missing API key")
        if target.exists():
            target.rename(target.with_name(target.name + "_incomplete_" + uuid4().hex[:8]))
        run_arm(run, target, design["settings"], key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_subparsers(dest="mode", required=True)
    prep = mode.add_parser("prepare", help="Verify the cohort and freeze the design offline")
    prep.add_argument("--profiles", type=int, choices=range(1, 7), default=2)
    prep.add_argument("--seeds", nargs="+", type=int, default=[101])
    prep.add_argument("--out", type=Path)
    run = mode.add_parser("run", help="Run and analyze a prepared study")
    run.add_argument("folder", type=Path)
    run.add_argument("--retry-failed", action="store_true")
    analysis = mode.add_parser("analyze", help="Analyze archived decisions without new model requests")
    analysis.add_argument("folder", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.mode == "prepare":
        label = "login_difficulty_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
        folder = (args.out or (DATA / "runs/login_difficulty" / label)).resolve()
        design = make_design(folder, args.profiles, args.seeds)
        print(f"{len(design['devices'])} 个画像，每个 72 个参考小时，{len(design['runs'])} 次七天模拟。")
        print(folder / "design.json")
        return
    folder = args.folder.resolve()
    design = json.loads((folder / "design.json").read_text())
    from analysis_login_difficulty import analyze_study
    if args.mode == "run":
        with (folder / ".run.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            execute(folder, design, args.retry_failed)
    report = analyze_study(folder, DATA / "sqlite.db")
    save(folder / "results.json", report)
    print(f"complete={report['complete']} {folder / 'results.json'}")
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
