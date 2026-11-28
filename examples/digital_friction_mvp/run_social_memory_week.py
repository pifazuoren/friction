"""Run a continuous five- or seven-day social-memory experiment in one baseline world."""

import argparse
from dataclasses import asdict
from datetime import datetime
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from config_runtime import load_runtime_config
from proto.app_entry import (
    DEFAULT_PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V3, PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V5,
    RESIDENT_DECISION_PLAN_VERSION,
)
from proto.app_entry.bundle_loader import get_replay_source


EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
DATA = ROOT / "agentsociety_data"
REFERENCE_DIR = DATA / "elderly/10person_v3"
PREFIX = "talkingdata_elderly_10_"
WORLD = "baseline_low_friction"
SEED = "101"
SETTINGS = {
    "AGENT_COUNT": "1", "STAGE_MODE": "single", "STAGE_SINGLE_NAME": "steady",
    "STAGE_DAYS": "7", "EVENT_DECISION_INTERVAL_MINUTES": "60",
    "EXPERIMENT_ENGINE": "proto", "EXPERIMENT_MODE": "parallel_worlds",
    "WORLD_BATCH": WORLD, "WORLD_NAME": WORLD, "EXP_SEED": SEED,
    "PROTO_LOGICAL_CLOCK_ENABLED": "true",
    "PROTO_TASK_ENTRY_MODE": "app_context_replay_then_llm_rollout",
    "PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH": str(REFERENCE_DIR / f"{PREFIX}reference_hourly_bundle_day1_3.csv"),
    "PROTO_APP_ENTRY_REPLAY_DEVICE_PATH": str(REFERENCE_DIR / f"{PREFIX}selected_devices.csv"),
    "PROTO_APP_ENTRY_REPLAY_DAYS": "1,2,3",
    "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION": "app_entry_plan_v3",
    "PROTO_TASK_OCCURRENCE_GATE_ENABLED": "true",
    "PROTO_LLM_PSYCHOLOGY_MODE": "hybrid",
    "PROTO_LLM_TASK_APPRAISAL_ENABLED": "true",
    "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED": "true",
    "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED": "false",
    "PROTO_LLM_UNCONTROLLABILITY_MODE": "off",
    "PROTO_LLM_EVENT_APPRAISAL_ENABLED": "false",
    "PROTO_LLM_DAILY_REFLECTION_ENABLED": "false",
    "PROTO_LLM_STAGE_INTERVIEW_ENABLED": "false",
    "PROTO_LLM_FINAL_INTERVIEW_ENABLED": "false",
    "PROTO_BAYESIAN_POLICY_LITE_MODE": "off",
    "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE": "off",
    "PROTO_SUPPORT_ECOLOGY_MODE": "family_helper_llm",
    "PROTO_OUTCOME_MODEL_MODE": "appraisal_rule_v2",
    "LLM_MODEL": "glm-4-flashx", "LLM_CONCURRENCY": "1",
    "MAP_FILE_PATH": str(DATA / "beijing.pb"),
    "DIGITAL_FRICTION_PROFILES_PATH": str(EXAMPLE / "profiles.json"),
}


def checked_replay(config):
    replay = get_replay_source(bundle_path=config.proto_app_entry_replay_bundle_path,
                               device_mapping_path=config.proto_app_entry_replay_device_path,
                               replay_days=config.proto_app_entry_replay_days)
    # The source validates every selected device, day and hour when it loads.
    return replay, replay.selected_devices[0][1]


def matched_cohort(replay, profiles_path, count):
    """Validate the same profile IDs and ranked device assignment used by AgentSociety."""
    profiles = json.loads(Path(profiles_path).read_text(encoding="utf-8"))
    if not isinstance(profiles, list) or len(profiles) < count:
        raise ValueError("Not enough distinct profiles for the requested residents")
    ids = [int(p["id"]) for p in profiles[:count]]
    if len(set(ids)) != count:
        raise ValueError("Duplicate resident profile IDs")
    assignments = replay.assignments_for_agent_ids(ids)
    return [dict(agent_id=agent_id, profile_id=agent_id, selected_rank=assignment.selected_rank,
                 device_id=assignment.device_id) for agent_id, assignment in assignments.items()]


def freeze_cohort_inputs(folder, settings):
    inputs = folder / "inputs"
    inputs.mkdir()
    for setting, filename in (
        ("DIGITAL_FRICTION_PROFILES_PATH", "profiles.json"),
        ("PROTO_APP_ENTRY_REPLAY_DEVICE_PATH", "devices.csv"),
        ("PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH", "replay.csv"),
    ):
        frozen = inputs / filename
        copyfile(settings[setting], frozen)
        settings[setting] = str(frozen)


def use_shuffled_reference(settings, directory, seed):
    from analysis_entry_calibration_comparison import write_shuffled_reference
    output = directory / "shuffled_reference_day1_3.csv"
    write_shuffled_reference(Path(SETTINGS["PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH"]), output, seed)
    settings["PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH"] = str(output)
    os.environ.update(settings)
    config = load_runtime_config()
    replay, device = checked_replay(config)
    return config, replay, device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify local resources without making model requests")
    parser.add_argument("--scheduled-login", action="store_true",
                        help="Offer a login daily from 09:00 on day four through the final day")
    parser.add_argument("--days", type=int, choices=(5, 7),
                        help="Total simulation days (default: five with scheduled login, otherwise seven)")
    parser.add_argument("--agents", type=int, choices=range(1, 11), default=1,
                        help="Residents in one world (up to ten with scheduled login and opportunity_v1)")
    parser.add_argument("--llm-concurrency", type=int, default=1,
                        help="Maximum concurrent provider requests, shared across residents")
    parser.add_argument("--hourly-intention-mode", choices=("legacy", "opportunity_v1"), default="legacy",
                        help="Select the legacy policy or give the hourly plan control of visible opportunities")
    parser.add_argument("--max-defer-hours", type=int, default=24, help="Maximum future review interval")
    parser.add_argument("--free-hour-history", choices=("hybrid", "counts", "description"),
                        help="Opportunity mode: sample from personal device history and the LLM recommendation "
                             "(hybrid, default), or reproduce the older counts/description prompts")
    parser.add_argument("--history-shuffle-seed", type=int,
                        help="Permute day 1–3 hours within each device-day in the natural window")
    parser.add_argument("--paired-environment-seed", type=int,
                        help="Use matching opportunity/decision-keyed environment draws in the scheduled A/B study")
    args = parser.parse_args()
    if args.llm_concurrency < 1:
        parser.error("--llm-concurrency must be positive")
    if args.free_hour_history and args.hourly_intention_mode != "opportunity_v1":
        parser.error("--free-hour-history requires --hourly-intention-mode opportunity_v1")
    if args.agents > 1 and not (args.scheduled_login and args.hourly_intention_mode == "opportunity_v1"):
        parser.error("cohort runs require --scheduled-login --hourly-intention-mode opportunity_v1")
    if args.max_defer_hours < 1:
        parser.error("--max-defer-hours must be positive")
    if args.history_shuffle_seed is not None and args.scheduled_login:
        parser.error("use the history-shuffle control in the natural window")
    if args.paired_environment_seed is not None and not args.scheduled_login:
        parser.error("--paired-environment-seed requires --scheduled-login")
    os.chdir(ROOT)
    os.umask(0o077)
    for key in list(os.environ):
        if key.startswith(("PROTO_", "PARALLEL_")) or key.lower() in {"http_proxy", "https_proxy", "all_proxy"}:
            del os.environ[key]
    days = args.days or (5 if args.scheduled_login else 7)
    settings = SETTINGS.copy()
    if args.hourly_intention_mode == "opportunity_v1":
        settings["PROTO_APP_ENTRY_PLAN_PROMPT_VERSION"] = RESIDENT_DECISION_PLAN_VERSION
        settings["PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION"] = {
            None: DEFAULT_PHONE_USE_NEEDS_VERSION, "hybrid": PHONE_USE_NEEDS_V5,
            "counts": PHONE_USE_NEEDS_V3, "description": PHONE_USE_NEEDS_VERSION,
        }[args.free_hour_history]
    settings.update(AGENT_COUNT=str(args.agents), LLM_CONCURRENCY=str(args.llm_concurrency),
                    STAGE_DAYS=str(days),
                    PROTO_HOURLY_INTENTION_MODE=args.hourly_intention_mode,
                    PROTO_HOURLY_INTENTION_MAX_DEFER_HOURS=str(args.max_defer_hours))
    if args.paired_environment_seed is not None:
        settings["PROTO_PAIRED_ENVIRONMENT_SEED"] = str(args.paired_environment_seed)
    if args.scheduled_login:
        settings.update(PROTO_SCHEDULED_LOGIN_HOUR="9", PROTO_LLM_STRATEGY_PROMPT_FORMAT="field_rules_no_priors")
        if days == 7:
            settings["PROTO_LOGIN_DIFFICULTY_ARM"] = "standard"
    os.environ.update(settings)
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    os.environ["PYTHONUNBUFFERED"] = "1"
    label = "scheduled_login" if args.scheduled_login else "social_memory"
    group = label + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]
    folder = DATA / "runs" / ("scheduled_login" if args.scheduled_login else "social_memory_7d") / group
    os.environ["PARALLEL_GROUP_NAME"] = group
    os.environ["PROTO_LLM_TRACE_DIR"] = str(folder / "trace")
    config = load_runtime_config()
    heldout = REFERENCE_DIR / f"{PREFIX}validation_hourly_bundle_day4_7.csv"
    required_files = [Path(settings["MAP_FILE_PATH"]), Path(settings["DIGITAL_FRICTION_PROFILES_PATH"]),
                      Path(config.proto_task_occurrence_prior_path), EXAMPLE / "check_social_memory_run.py"]
    if args.hourly_intention_mode == "opportunity_v1":
        required_files.append(EXAMPLE / "check_hourly_intention_run.py")
    if args.scheduled_login:
        required_files.append(EXAMPLE / "check_scheduled_login.py")
    compare_cohort = args.agents > 1 and days == 7
    if compare_cohort or not args.scheduled_login:
        required_files.append(heldout)
    for required in required_files:
        if not required.is_file():
            parser.exit(2, f"缺少实验文件 {required}\n")
    if not os.access(DATA / "agentsociety-sim-oss", os.X_OK):
        parser.exit(2, "本地模拟器不存在或不能执行。\n")
    replay, device = checked_replay(config)
    cohort = None
    if args.agents > 1:
        cohort = matched_cohort(replay, settings["DIGITAL_FRICTION_PROFILES_PATH"], args.agents)
    print(f"已核对 {args.agents} 台设备各 72 个回放小时。glm-4-flashx，1 个基线世界，"
          f"{args.agents} 位老人，{days} 个模拟日，模型并发上限 {args.llm_concurrency}。", flush=True)
    print(f"小时决策模式 {config.proto_hourly_intention_mode}，延期窗口 {config.proto_hourly_intention_max_defer_hours} 小时。", flush=True)
    if args.hourly_intention_mode == "opportunity_v1":
        print(f"自由时段的用机判断版本为 {config.proto_app_entry_phone_use_needs_version}。", flush=True)
    if config.proto_paired_environment_seed is not None:
        print(f"策略与结果的配对环境抽样种子为 {config.proto_paired_environment_seed}。", flush=True)
    if args.scheduled_login:
        print(f"第 4 至 {days} 天每天从 09:00 起安排一次普通难度登录机会，求助和办理结果按模拟流程执行。", flush=True)
    if args.check:
        if args.history_shuffle_seed is not None:
            with TemporaryDirectory() as temp:
                use_shuffled_reference(settings, Path(temp), args.history_shuffle_seed)
            print(f"已核对前三天的时段置乱对照，种子 {args.history_shuffle_seed}。")
        return
    key = os.environ.get("LLM_API_KEY") or os.environ.get("ZHIPUAI_API_KEY")
    if not key or not key.strip() or key.strip() == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（输入隐藏，回车开始实验）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        parser.exit(2, "未输入有效密钥，实验未启动。\n")
    os.environ["LLM_API_KEY"] = key.strip()
    folder.mkdir(parents=True)
    original_reference_hash = replay.bundle_hash
    if cohort is not None:
        freeze_cohort_inputs(folder, settings)
        if compare_cohort:
            frozen_heldout = folder / "inputs/heldout.csv"
            copyfile(heldout, frozen_heldout)
            heldout = frozen_heldout
        os.environ.update(settings)
        config = load_runtime_config()
        previous_replay = replay
        replay, device = checked_replay(config)
        if (replay.bundle_hash != previous_replay.bundle_hash
                or replay.device_mapping_hash != previous_replay.device_mapping_hash
                or cohort != matched_cohort(replay, settings["DIGITAL_FRICTION_PROFILES_PATH"], args.agents)):
            raise RuntimeError("The cohort inputs changed after preflight")
    if args.history_shuffle_seed is not None:
        config, replay, device = use_shuffled_reference(settings, folder, args.history_shuffle_seed)
    print(f"本次结果目录：{folder}", flush=True)
    code_archive = folder / "experiment_source.zip"
    sources = [
        EXAMPLE / name for name in (
            "main.py", "world_runner.py", "persistence.py", "config_runtime.py",
            "analysis_parallel_worlds.py", "analysis_entry_calibration_comparison.py",
            "run_social_memory_week.py", "check_social_memory_run.py",
            "check_hourly_intention_run.py", "check_hourly_choice_evidence.py", "analysis_app_entry_validation.py",
        )
    ]
    sources.extend((EXAMPLE / "proto").rglob("*.py"))
    if args.scheduled_login:
        sources.append(EXAMPLE / "check_scheduled_login.py")
    if cohort is not None:
        sources.append(EXAMPLE / "analysis_five_day_cohort.py")
    with ZipFile(code_archive, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(sources):
            archive.write(path, path.relative_to(ROOT))
    snapshot = {
        "settings": settings, "runtime": asdict(config),
        **({"cohort": cohort} if cohort is not None else {}),
        "history_shuffle_seed": args.history_shuffle_seed, "original_reference_hash": original_reference_hash,
        "reference_hash": replay.bundle_hash, "device_mapping_hash": replay.device_mapping_hash,
        **({"evaluation_heldout_sha256": hashlib.sha256(heldout.read_bytes()).hexdigest()} if compare_cohort else {}),
        "profiles_sha256": hashlib.sha256(Path(SETTINGS["DIGITAL_FRICTION_PROFILES_PATH"]).read_bytes()).hexdigest(),
        "task_priors_sha256": hashlib.sha256(Path(config.proto_task_occurrence_prior_path).read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(code_archive.read_bytes()).hexdigest(),
    }
    (folder / "resolved_config.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    os.environ["PROTO_RUN_SOURCE_SHA256"] = snapshot["source_sha256"]
    runner = [sys.executable, str(EXAMPLE / "world_runner.py"), "--group-id", group,
              "--seed-list", SEED, "--world-batch", WORLD, "--analysis-dir", str(folder), "--summarize"]
    with (folder / "run.log").open("w") as log, subprocess.Popen(
        runner, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
    ) as run:
        for line in run.stdout:
            line = line.replace(key.strip(), "[redacted]")
            sys.stdout.write(line)
            log.write(line)
            log.flush()
        runner_status = run.wait()
    manifest_path = folder / f"exp_group_manifest_{group}.json"
    if not manifest_path.is_file():
        parser.exit(1, f"仿真未写出运行清单，请查看 {folder / 'run.log'}\n")
    report = folder / "acceptance.json"
    check = subprocess.run([sys.executable, str(EXAMPLE / "check_social_memory_run.py"),
                            "--run-dir", str(folder), "--group-id", group, "--db", str(DATA / "sqlite.db"),
                            "--trace", str(folder / "trace"), "--output", str(report), "--expected-days", str(days),
                            *(["--expected-agents", str(args.agents)] if args.agents > 1 else [])])
    evidence_status = 0
    if cohort is not None and report.is_file() and json.loads(report.read_text()).get("run_complete"):
        evidence_status = subprocess.run([sys.executable, str(EXAMPLE / "analysis_five_day_cohort.py"),
                                          "--run-dir", str(folder), "--db", str(DATA / "sqlite.db"),
                                          *(["--heldout", str(heldout)] if compare_cohort else [])]).returncode
    if args.scheduled_login and args.hourly_intention_mode == "legacy":
        evidence_status = subprocess.run([sys.executable, str(EXAMPLE / "check_scheduled_login.py"),
                                          "--run-dir", str(folder), "--db", str(DATA / "sqlite.db")]).returncode
    rollout = folder / f"app_entry_rollout_hourly_{group}.csv"
    errors = folder / f"app_entry_rollout_errors_{group}.csv"
    if rollout.is_file() and not args.scheduled_login:
        from analysis_entry_calibration_comparison import compare, write_csv
        for day in range(4, days + 1):
            day_dir = folder / f"scores/day{day}"
            day_dir.mkdir(parents=True)
            summary, hourly = compare(Path(SETTINGS["PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH"]), heldout,
                                      [("glm-4-flashx", rollout, errors if errors.is_file() else None)], [device], day,
                                      shuffle_seed=101 if args.history_shuffle_seed is None else args.history_shuffle_seed)
            write_csv(day_dir / "summary.csv", summary)
            write_csv(day_dir / "hourly.csv", hourly)
    print(f"实验验收与日志：{folder}", flush=True)
    if runner_status or check.returncode or evidence_status:
        sys.exit(1)


if __name__ == "__main__":
    main()
