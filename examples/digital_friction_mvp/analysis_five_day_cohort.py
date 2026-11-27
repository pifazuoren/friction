"""Describe each profile's five-day opportunity-mode run from the frozen local evidence."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import UUID

from check_social_memory_run import MODULES, WORLD, load_rows, request_packet
from proto.metrics import attempt_rows_table_name
from proto.support_protocol import classify_support_delivery


DAYS = (4, 5)
HELP = "seek_help_then_attempt"
OUTCOMES = {
    "success_self": "自主成功", "success_with_help": "借助帮助成功",
    "failure_after_attempt": "尝试后失败", "failure_even_with_help": "有帮助仍失败",
    "abandon_midway": "中途放弃", "avoid_without_attempt": "回避未操作",
}
MEMORY_STATUS = {
    "verified": "已核对", "no_day4_completed_task": "第4天无已结算经历",
    "no_day5_strategy_opportunity": "第5天无策略机会", "missing_evidence": "证据缺失",
    "technical_failure": "技术失败", "no_natural_opportunity": "无自然机会",
}
HELPER_STATUS = {
    "verified": "请求人与助手均已核对", "prompt_only": "仅有帮助模型请求",
    "partly_persisted": "部分请求缺 SQLite 记录", "conflict": "对应关系冲突", "unverified": "请求身份缺证或冲突",
    "no_observed_request": "未观察到求助请求", "incomplete_trace": "无请求记录且小时记录不完整",
    "choice_without_call": "已选求助，缺帮助模型请求",
}


def trace_by_day(folder, group, agents):
    """Keep routing and help evidence, leaving prompts and identifiers out of the report."""
    traces = defaultdict(list)
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                r = json.loads(line)
                if (r.get("group_id"), r.get("world")) != (group, WORLD):
                    raise ValueError("trace group or world differs from the experiment manifest")
                agent, day = str(r.get("agent_id")), r.get("talkingdata_day")
                if day not in DAYS:
                    continue
                if agent not in agents:
                    raise ValueError("trace contains an unmapped elderly agent")
                if r.get("module") == "hourly_intention" or (r.get("module"), r.get("kind")) in {
                    ("helper", "request"), ("strategy", "sample"), ("task", "decision"),
                }:
                    record = {k: v for k, v in r.items() if k not in {"messages", "parameters"}}
                    if (r["module"], r["kind"], r.get("phase")) == ("helper", "request", "initial"):
                        try:
                            packet = request_packet(r)
                            if packet["task"]["task_id"] == r["task_id"] and packet["relationship"]["relationship_type"] == "family":
                                record["prompt_helper_id"] = packet["relationship"]["mapped_helper_agent_id"]
                        except (KeyError, ValueError, TypeError):
                            pass  # An unreadable on-wire target is reported as unverified.
                    traces[agent, day].append(record)
    return traces


def day_summary(records, attempts, *, agent_id):
    routes = [r for r in records if r["kind"] == "hourly_intention" and r["module"] == "hourly_intention"]
    route_hours = Counter(r["hour"] for r in routes)
    accepted = [r for r in routes if r["status"] == "accepted"]
    offered = [r for r in records if r["kind"] == "opportunity_published"]
    helper_calls = defaultdict(set)
    for r in records:
        if (r["module"], r["kind"], r.get("phase")) == ("helper", "request", "initial"):
            target = r.get("prompt_helper_id")
            helper_calls[r["tick_id"], r["task_id"]].add(target if type(target) is int and target >= 0 else None)
    help_choices = [r for r in records if (r["module"], r["kind"], r.get("action")) == ("strategy", "sample", HELP)]
    failures = [r for r in records if (r["module"], r["kind"], r.get("status")) == ("task", "decision", "technical_failure")]
    decisions = {r["episode_id"]: r for r in records
                 if (r["module"], r["kind"], r.get("status")) == ("task", "decision", "completed")}
    operations_by_episode = defaultdict(list)
    for r in records:
        if (r["module"], r["kind"], r.get("status")) == ("hourly_intention", "goal_outcome", "completed"):
            operations_by_episode[r.get("episode_id")].append(r)
    issues = []
    if set(route_hours) != set(range(24)) or any(n != 1 for n in route_hours.values()):
        issues.append("小时路由记录缺失或重复")
    if set(decisions) != {a["episode_id"] for a in attempts}:
        issues.append("任务决策与 SQLite 经历集合不同")
    outcomes, deliveries, after_help, strategies, fallbacks = Counter(), Counter(), Counter(), Counter(), Counter()
    helpers_dispatched = set()
    operations = Counter()
    verified_requests = invalid_requests = invalid_failure_requests = 0
    for a in attempts:
        outcome, decision = a["outcome"], decisions.get(a["episode_id"], {})
        result = outcome["outcome_type"]
        markers = operations_by_episode[a["episode_id"]]
        if len(markers) == 1 and markers[0].get("task_id") == a["task"]["task_id"] and type(markers[0].get("operation_started")) is bool:
            started = markers[0]["operation_started"]
            operations["recorded_starts"] += int(started)
            operations["recorded_decisions"] += 1
            if result not in OUTCOMES or started != (result != "avoid_without_attempt") or markers[0].get("outcome_type") != result:
                issues.append("操作启动标记与 SQLite 结局不一致")
        elif not markers and result in OUTCOMES:
            operations["inferred_starts"] += int(result != "avoid_without_attempt")
            operations["inferred_decisions"] += 1
            issues.append("缺少操作启动标记，按已知结局推定")
        else:
            operations["unknown_decisions"] += 1
            issues.append("操作启动标记缺失、冲突或无效")
        outcomes[result] += 1
        strategies[a.get("strategy_deliberation", {}).get("source", "missing")] += 1
        for key in ("task_appraisal", "strategy_deliberation", "event_appraisal"):
            source = a.get(key, {}).get("source")
            if source is None or "fallback" in source:
                fallbacks[f"{key}/{source or 'missing'}"] += 1
        if (decision.get("task_id"), decision.get("outcome"), decision.get("help_used")) != (
            a["task"]["task_id"], result, outcome["help_used"]
        ):
            issues.append("任务结果与 trace 不一致")
        req, resp = a.get("support_request") or {}, a.get("support_response") or {}
        if a["requested_strategy_type"] != HELP:
            if req or resp or a.get("support_delivery_status") != "not_requested" or outcome["help_used"]:
                issues.append("未选求助的任务出现帮助记录")
            continue
        ident = a.get("support_request_id")
        call = (decision.get("tick_id"), a["task"]["task_id"])
        targets = helper_calls.get(call, set())
        if (ident and req.get("request_id") == decision.get("support_request_id") == ident and type(req.get("requester_agent_id")) is int
                and req["requester_agent_id"] == agent_id and req.get("task_id") == a["task"]["task_id"]
                and type(req.get("helper_agent_id")) is int and targets == {req["helper_agent_id"]}):
            helpers_dispatched.add(call)
            verified_requests += 1
        else:
            deliveries["unverified"] += 1
            invalid_requests += 1
            issues.append("求助请求的请求人、助手或任务缺少一致证据")
            continue
        delivery = classify_support_delivery(resp)
        if (resp.get("request_id") != ident or resp.get("helper_agent_id") != req.get("helper_agent_id")
                or type(resp.get("requester_agent_id")) is not int or resp["requester_agent_id"] != agent_id
                or delivery != a.get("support_delivery_status") or decision.get("support_delivery_status") != delivery
                or bool(outcome["help_used"]) != (delivery == "delivered")):
            delivery = "unverified"
            issues.append("帮助响应与任务结果不一致")
        deliveries[delivery] += 1
        if delivery == "delivered":
            after_help[result] += 1
    for r in failures:
        call = (r["tick_id"], r["task_id"])
        if r.get("requested_action") != HELP:
            continue
        # The dispatcher builds this ID from the caller, clock and task even when
        # the failed exchange never produces a completed SQLite attempt.
        tick = r.get("tick_seconds")
        expected_id = (f"{agent_id}-{r['simulation_day']}-{int(tick)}-{r['task_id']}"
                       if type(tick) in (int, float) and type(r.get("simulation_day")) is int else None)
        targets = helper_calls.get(call, set())
        if expected_id and r.get("support_request_id") == expected_id and len(targets) == 1 and None not in targets:
            helpers_dispatched.add(call)
            deliveries["technical_failure"] += 1
        else:
            invalid_failure_requests += 1
            issues.append("失败求助缺少可与请求人、时刻和助手关联的证据")
    if helpers_dispatched != set(helper_calls):
        issues.append("部分帮助模型请求缺少可核对的任务记录")
    return {
        "offers": dict(Counter(r["source"] for r in offered)),
        "valid_hours": len(accepted), "failed_hours": sum(r["status"] == "technical_failure" for r in routes),
        "missing_hours": sorted(set(range(24)) - set(route_hours)),
        "choices": dict(Counter(r["executed_choice"] for r in accepted)),
        "task_entries": sum(bool(r.get("task_started")) for r in accepted),
        "recorded_decisions": len(attempts), "distinct_decided_tasks": len({a["task"]["task_id"] for a in attempts}),
        "operations": operations["recorded_starts"] + operations["inferred_starts"], "operation_evidence": dict(operations),
        "outcomes": dict(outcomes), "strategy_sources": dict(strategies), "fallback_or_missing": dict(fallbacks),
        "task_technical_failures": len(failures),
        "help_choices": len(help_choices), "dispatched_help": len(helpers_dispatched),
        "delivery": dict(deliveries), "outcomes_with_delivered_help": dict(after_help),
        "help_request_evidence": {"tasks_with_helper_call": len(helper_calls), "verified_persisted_requests": verified_requests,
                                  "unverified_persisted_requests": invalid_requests,
                                  "unverified_failed_requests": invalid_failure_requests,
                                  "ambiguous_call_targets": sum(None in v or len(v) != 1 for v in helper_calls.values())},
        "_helper_targets": sorted({h for targets in helper_calls.values() for h in targets if h is not None}),
        "issues": sorted(set(issues)),
    }


def summarize_helper_mapping(profiles, resident_ids):
    """Only actual initial helper prompts provide observed targets, including failed calls."""
    targets_by_rank, owners = {}, defaultdict(set)
    for p in profiles:
        targets = set()
        for day in p["days"].values():
            targets.update(day.pop("_helper_targets"))
        targets_by_rank[p["rank"]] = targets
        for target in targets:
            owners[target].add(p["rank"])
    labels = {target: f"H{i:02}" for i, target in enumerate(sorted(owners), 1)}
    status_counts = Counter()
    actual_calls = unverified_calls = 0
    conflict = False
    for p in profiles:
        days = p["days"].values()
        facts = [s["help_request_evidence"] for s in days]
        targets = targets_by_rank[p["rank"]]
        calls = sum(f["tasks_with_helper_call"] for f in facts)
        bad = sum(f["unverified_persisted_requests"] + f["unverified_failed_requests"] + f["ambiguous_call_targets"] for f in facts)
        verified = sum(f["verified_persisted_requests"] for f in facts)
        actual_calls += calls
        unverified_calls += bad
        if len(targets) > 1 or any(len(owners[h]) > 1 or h in resident_ids for h in targets):
            status = "conflict"
            conflict = True
        elif bad:
            status = "unverified"
        elif not calls and any(s["help_choices"] for s in days):
            status = "choice_without_call"
        elif not calls:
            status = "no_observed_request" if all(not s["missing_hours"] for s in days) else "incomplete_trace"
        elif verified != calls:
            status = "prompt_only" if not verified else "partly_persisted"
        else:
            status = "verified"
        p["observed_helper"] = {"status": status, "helper_labels": [labels[t] for t in sorted(targets)],
                                "tasks_with_helper_call": calls, "verified_persisted_requests": verified}
        status_counts[status] += 1
    return {"observed_one_to_one": False if conflict else (None if not actual_calls or unverified_calls else True),
            "residents_with_observed_target": sum(bool(s) for s in targets_by_rank.values()),
            "distinct_observed_helpers": len(owners), "status_counts": dict(status_counts)}


def build_report(folder, db):
    group = folder.name
    manifest, = json.loads((folder / f"exp_group_manifest_{group}.json").read_text())
    exp = str(UUID(manifest["exp_id"]))
    if (manifest["group_id"], manifest["world_name"], manifest["total_days"]) != (group, WORLD, 5):
        raise ValueError("expected one matching five-day baseline world")
    rows = load_rows(folder, "app_entry_replay_summary", group)
    ranks = {r["agent_id"]: int(r["selected_rank"]) for r in rows}
    n = manifest["agent_count"]
    if (len(rows) != len(ranks) or len(set(ranks.values())) != len(ranks)
            or not set(ranks.values()) <= set(range(1, n + 1))
            or any((r["group_id"], r["world_name"], r["exp_id"]) != (group, WORLD, exp) for r in rows)):
        raise ValueError("invalid or mixed replay cohort")
    acceptance_path = folder / "acceptance.json"
    audit = json.loads(acceptance_path.read_text()) if acceptance_path.exists() else {}
    if audit and audit.get("group_id") != group:
        raise ValueError("acceptance report belongs to a different run")
    people = audit.get("agents", {})
    if n == len(ranks) == 1 and not people and audit:
        people = {next(iter(ranks)): audit}
    traces = trace_by_day(folder, group, ranks)
    profiles = []
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        table = attempt_rows_table_name(exp)
        for agent, rank in sorted(ranks.items(), key=lambda pair: pair[1]):
            check = people.get(agent, {})
            daily = {}
            for d in DAYS:
                raw = conn.execute(f"SELECT payload_json FROM {table} WHERE agent_id=? AND day=? ORDER BY t,id",
                                   (agent, d - 1))
                summary = day_summary(traces[agent, d], [json.loads(row[0]) for row in raw], agent_id=int(agent))
                offers = check.get("hourly_intention", {}).get("opportunities")
                summary["distinct_visible_offers"] = None if offers is None else sum(
                    any(day == d for day, _ in offer["visible_hours"]) for offer in offers
                )
                daily[str(d)] = summary
            intention = check.get("hourly_intention", {})
            examples = intention.get("day5_memory_examples")
            modules = check.get("cross_day", {}).get("modules", {})
            profiles.append({
                "rank": rank, "verified_replay_hours": check.get("replay", {}).get("verified_hours"),
                "audited": check.get("acceptance_ok"), "audit_issue_count": len(check.get("issues", [])),
                "stable": check.get("stability_gate", {}).get("eligible_by_technical_stability"),
                "days": daily, "day5_memory": {m: modules.get(m, {}).get("status", "missing_evidence") for m in MODULES},
                "day4_episodes_in_valid_day5_plan": None if examples is None else len({x["episode_id"] for x in examples}),
                "day5_valid_plan_hours_with_day4_episode": None if examples is None else len({x["day5_hour"] for x in examples}),
            })
    return {"group": group, "planned_profiles": n, "profiles": profiles,
            "observed_helper_mapping": summarize_helper_mapping(profiles, {int(agent) for agent in ranks}),
            "stability_gate": audit.get("stability_gate"),
            "missing_ranks": sorted(set(range(1, n + 1)) - set(ranks.values())), "accepted": audit.get("acceptance_ok")}


def display_counts(counts):
    return "、".join(f"{OUTCOMES.get(key, key)} {count}" for key, count in sorted(counts.items())) or "0"


def known(value):
    return "缺证" if value is None else str(value)


def render(report):
    profiles = report["profiles"]
    days = [s for p in profiles for s in p["days"].values()]
    valid = sum(s["valid_hours"] for s in days)
    outcomes, after_help = Counter(), Counter()
    for s in days:
        outcomes.update(s["outcomes"])
        after_help.update(s["outcomes_with_delivered_help"])
    help_total = sum(s["dispatched_help"] for s in days)
    lines = ["# 五天单世界模拟结果", "",
             f"计划 {report['planned_profiles']} 名合成老人，取得 {len(profiles)} 人的回放映射。前三天回放设备活动，第 4、5 天由模拟产生任务和结果。",
             "", f"第 4、5 天共有 {valid}/{48 * report['planned_profiles']} 个人小时取得有效决定，"
             f"留下 {sum(outcomes.values())} 条任务决策，实际开始操作 {sum(s['operations'] for s in days)} 次。"
             f"已记录的结果包括{display_counts(outcomes)}。可以核对的求助请求有 {help_total} 次，"
             f"其中 {sum(after_help.values())} 次收到帮助。"
             f"第 5 天共有 {sum(bool(p['day5_valid_plan_hours_with_day4_episode']) for p in profiles)} 人的有效计划输入含有可核对的第 4 天经历。",
             "", "## 按人和日期核对", "",
             "发布按当天新机会计数，可见按当天实际计划输入中出现过的不同机会计数。启动含继续办理同一任务。实际操作排除了回避。",
             "", "|编号|日|有效小时 / 24|发布（登录 / 自然）|可见|启动|实际操作|已记录结果|求助选择 / 发出 / 送达|送达后的结果|",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for p in profiles:
        for d, s in p["days"].items():
            offers, delivery = s["offers"], s["delivery"]
            lines.append(f"|{p['rank']:02}|{d}|{s['valid_hours']}|{offers.get('scheduled_login', 0)} / "
                         f"{offers.get('natural_context', 0)}|{known(s['distinct_visible_offers'])}|{s['task_entries']}|"
                         f"{s['operations']}|{display_counts(s['outcomes'])}|{s['help_choices']} / {s['dispatched_help']} / "
                         f"{delivery.get('delivered', 0)}|{display_counts(s['outcomes_with_delivered_help'])}|")
    mapping = report["observed_helper_mapping"]
    relation = {True: "已观察到的目标一人对应一名助手", False: "已观察到助手对应关系冲突",
                None: "可用证据不足以核实一人对应一名助手"}[mapping["observed_one_to_one"]]
    lines += ["", "求助按一次任务决策计。发出要求帮助请求能和同一任务的帮助模型调用对应，送达要求请求、回复和已使用帮助字段相符。送达后的结果来自模拟抽样，这个单世界没有同一决策下未求助的对照，无法估计帮助的因果效果。",
              "", "## 实际请求中的家庭助手", "",
              f"{mapping['residents_with_observed_target']} 名老人的初次求助模型请求包含助手目标，共出现 "
              f"{mapping['distinct_observed_helpers']} 名不同助手。{relation}。助手编号仅标识本归档中观察到的目标。",
              "", "|编号|请求中的助手|有帮助模型调用的任务|已核对 SQLite 请求身份的任务|对应证据|",
              "|---|---|---|---|---|"]
    for p in profiles:
        h = p["observed_helper"]
        lines.append(f"|{p['rank']:02}|{'、'.join(h['helper_labels']) or '—'}|{h['tasks_with_helper_call']}|"
                     f"{h['verified_persisted_requests']}|{HELPER_STATUS[h['status']]}|")
    lines += [
              "", "## 第 5 天实际请求中的第 4 天经历", "",
              "|编号|已核对回放小时|需求输入|计划输入|策略输入|有效计划读到的不同经历|含这些经历的有效计划小时|",
              "|---|---|---|---|---|---|---|"]
    for p in profiles:
        m = p["day5_memory"]
        labels = "|".join(MEMORY_STATUS.get(m[k], m[k]) for k in MODULES)
        lines.append(f"|{p['rank']:02}|{known(p['verified_replay_hours'])}|{labels}|"
                     f"{known(p['day4_episodes_in_valid_day5_plan'])}|{known(p['day5_valid_plan_hours_with_day4_episode'])}|")
    lines += ["", "“已核对”表示实际发给模型的输入包含可与该人 SQLite 经历逐项对应的记录。输入可见性不能单独说明经历改变了后续选择。", "",
              "## 技术状态与证据覆盖", ""]
    audit_label = {True: "通过", False: "未通过", None: "缺证"}[report["accepted"]]
    lines.append(f"整体验收{audit_label}。各行仅汇总已取得的记录。")
    gate = report["stability_gate"] or {}
    if gate.get("minimum_valid_rate") is not None:
        met = "通过" if gate["eligible_by_technical_stability"] else "未通过"
        lines.append(f"项目技术稳定性门槛为有效率至少 {gate['minimum_valid_rate']:.0%}，并核查逐人稳定性与底层任务故障，本轮{met}。")
    if report["missing_ranks"]:
        lines.append("缺少回放映射的编号为 " + "、".join(map(str, report["missing_ranks"])) + "。")
    lines.append("")
    for p in profiles:
        details = []
        if p["audited"] is not True:
            details.append(f"个人验收{'缺证' if p['audited'] is None else '未通过'}")
        if p["stable"] is not True:
            details.append(f"稳定性{'缺证' if p['stable'] is None else '未达标'}")
        for d, s in p["days"].items():
            quality = [f"小时技术失败 {s['failed_hours']}", f"小时缺失 {len(s['missing_hours'])}",
                       f"任务技术失败 {s['task_technical_failures']}"]
            if s["fallback_or_missing"]:
                quality.append("降级或缺失 " + display_counts(s["fallback_or_missing"]))
            for delivery, count in s["delivery"].items():
                if delivery != "delivered":
                    quality.append(f"帮助状态 {delivery} {count}")
            quality.extend(s["issues"])
            details.append(f"第 {d} 天" + "，".join(quality))
        lines.append(f"- {p['rank']:02}　" + "。".join(details) + "。")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.run_dir, args.db)
    (args.run_dir / "five_day_cohort_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (args.run_dir / "five_day_cohort_report.md").write_text(render(report))
