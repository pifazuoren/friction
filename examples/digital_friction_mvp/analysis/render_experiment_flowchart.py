#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


COLORS = {
    "input": "#4F81BD",
    "process": "#5CB85C",
    "output": "#D9534F",
    "opt": "#7E57C2",
    "text": "#1F1F1F",
    "border": "#2F2F2F",
}


def draw_box(ax, x, y, w, h, text, color, fontsize=10):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=1.3,
        edgecolor=COLORS["border"],
        facecolor=color,
        alpha=0.95,
        zorder=2,
    )
    ax.add_patch(box)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color="white",
        linespacing=1.25,
        zorder=3,
    )


def draw_arrow(
    ax,
    x1,
    y1,
    x2,
    y2,
    *,
    dashed=False,
    color="#333333",
    lw=1.8,
    curve=0.0,
):
    style = "Simple,tail_width=0.45,head_width=6,head_length=8"
    arrow = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle=style,
        mutation_scale=1.0,
        linewidth=lw,
        linestyle="--" if dashed else "-",
        color=color,
        connectionstyle=f"arc3,rad={curve}",
        zorder=1,
    )
    ax.add_patch(arrow)


def main() -> None:
    plt.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Heiti TC",
        "Arial Unicode MS",
        "Noto Sans CJK SC",
        "SimHei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)
    ax.set_facecolor("white")
    ax.set_xticks(range(0, 101, 2))
    ax.set_yticks(range(0, 61, 2))
    ax.grid(color="#EBEBEB", linewidth=0.6)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.text(
        50,
        58,
        "Digital Friction MVP 完整流程图（左→右）",
        ha="center",
        va="center",
        fontsize=22,
        color=COLORS["text"],
        fontweight="bold",
    )

    draw_box(
        ax,
        1.2,
        42,
        11,
        8.5,
        "输入A\n运行参数\nWORLD/SEED\n阈值与策略",
        COLORS["input"],
    )
    draw_box(
        ax,
        1.2,
        30,
        11,
        8.5,
        "输入B\nAgent画像\nstatus/history\nstep_signal",
        COLORS["input"],
    )
    draw_box(
        ax,
        1.2,
        18,
        11,
        8.5,
        "输入C\n阶段环境\nworld levels\nsurvey测量",
        COLORS["input"],
    )

    draw_box(
        ax,
        14,
        33.2,
        14,
        12,
        "① 初始化与编排\ninit_status\n+ profile导出初始状态\n+ 可选 economy audit\n+ 首轮 survey 测量同步",
        COLORS["process"],
    )
    draw_box(
        ax,
        30,
        33.2,
        14,
        12,
        "② 决策间隔循环\nstage env 生效\n→ nudge_mobility_if_stuck(legacy)\n→ STEP\nagent 在 forward 内自取任务",
        COLORS["process"],
    )
    draw_box(
        ax,
        46,
        33.2,
        14,
        12,
        "③ agent 内部决策\nstage切换自重置\n→ assign_task_if_missing\n→ 提取 memory features\n→ choose_attempt_strategy",
        COLORS["process"],
    )
    draw_box(
        ax,
        62,
        33.2,
        14,
        12,
        "④ 结果与心理更新\nresolve_attempt_outcome\n→ LLM仅校准不可控感\n→ helplessness update\n→ experience memory update",
        COLORS["process"],
    )
    draw_box(
        ax,
        78,
        33.2,
        19,
        12,
        "⑤ 审计与状态写回\n更新 helpless/trust/avoidance\n写 event_log + attempt rows\n写 memory snapshot / decision_json",
        COLORS["process"],
    )
    draw_box(
        ax,
        58,
        17.8,
        22,
        10.5,
        "⑥ 阶段末结算与测量\nstage_settlement + save_context\nsurvey + measurement-only sync\n输出: stage摘要与对照指标",
        COLORS["process"],
    )

    draw_box(
        ax,
        82.2,
        18.0,
        15.0,
        9.5,
        "输出1\nSQLite 审计层\nattempt rows / stage summary\nstatus snapshot / event_log",
        COLORS["output"],
    )
    draw_box(
        ax,
        82.2,
        6.4,
        15.0,
        9.5,
        "输出2\n分析层结果\nworld summary + paired\nstage对比 / 明细追踪",
        COLORS["output"],
    )

    draw_box(
        ax,
        44.2,
        49.2,
        16.0,
        7.6,
        "优化① 状态显式化\nproto schema\nprofile-derived init",
        COLORS["opt"],
    )
    draw_box(
        ax,
        62.3,
        49.2,
        16.0,
        7.6,
        "优化② agent内闭环\n任务分配内收\nstage reset 内收",
        COLORS["opt"],
    )
    draw_box(
        ax,
        80.4,
        49.2,
        16.0,
        7.6,
        "优化③ 测量分层\nsurvey只做测量\nLLM只校准不可控感",
        COLORS["opt"],
    )

    draw_arrow(ax, 12.2, 46.2, 14, 42.8, color="#4B4B4B")
    draw_arrow(ax, 12.2, 34.2, 14, 39.2, color="#4B4B4B")
    draw_arrow(ax, 12.2, 22.2, 14, 35.2, color="#4B4B4B")

    draw_arrow(ax, 28, 39.2, 30, 39.2)
    draw_arrow(ax, 44, 39.2, 46, 39.2)
    draw_arrow(ax, 60, 39.2, 62, 39.2)
    draw_arrow(ax, 76, 39.2, 78, 39.2)
    draw_arrow(ax, 87.5, 33.2, 87.5, 27.5)
    draw_arrow(ax, 80, 23.1, 82.2, 23.1)
    draw_arrow(ax, 80, 18.4, 82.2, 11.2)

    draw_arrow(ax, 69.0, 33.0, 69.0, 28.2, color="#3A3A3A")
    draw_arrow(ax, 44.0, 36.5, 30.2, 36.5, dashed=True, color="#6E6E6E", curve=-0.25)
    draw_arrow(ax, 97.0, 10.8, 90.0, 49.2, dashed=True, color="#6E6E6E", curve=0.16)
    draw_arrow(ax, 88.8, 27.5, 70.4, 49.2, dashed=True, color="#6E6E6E", curve=0.20)
    draw_arrow(ax, 66.0, 49.2, 53.5, 45.2, dashed=True, color="#6E6E6E", curve=0.12)
    draw_arrow(ax, 74.0, 49.2, 69.0, 45.2, dashed=True, color="#6E6E6E", curve=0.10)

    legend = (
        "图例 Legend\n"
        "颜色: 蓝=输入 | 绿=处理 | 红=输出 | 紫=优化/反馈\n"
        "形状: 矩形=模块；实线箭头=主数据流；虚线箭头=反馈循环\n"
        "当前 proto 主链: 任务分配 → 策略选择 → 结果生成 → helplessness 更新 → 记录\n"
        "LLM 边界: 不决定策略/成功失败/更新公式，只校准主观不可控感"
    )
    ax.text(
        1.2,
        1.6,
        legend,
        ha="left",
        va="bottom",
        fontsize=10,
        color=COLORS["text"],
        linespacing=1.25,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="white",
            edgecolor="#9A9A9A",
            linewidth=1.0,
        ),
    )

    output_dir = Path(__file__).resolve().parent
    png_path = output_dir / "digital_friction_full_workflow_1920x1080.png"
    svg_path = output_dir / "digital_friction_full_workflow.svg"
    fig.savefig(png_path, dpi=100, facecolor="white")
    fig.savefig(svg_path, facecolor="white")
    plt.close(fig)

    print(png_path)
    print(svg_path)


if __name__ == "__main__":
    main()
