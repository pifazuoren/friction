# 本次实验动作全量统计与合理性评估（dd948d54）

## A. 数据规模与完整性
- 动作总条数：864
- 唯一动作文本：655
- step 数：144（期望 144）
- 每 step 动作数：min=6, max=6（均为6）
- 核心 6 个 agent：[500019134, 500022131, 500033414, 500038614, 500055778, 500055517]
- 非核心 agent 出现：{500025041: 1, 500023827: 11, 500007323: 12}

## B. 全量动作分布（严格口径）
- meal: 384 (44.44%)
- sleep: 224 (25.93%)
- other: 248 (28.70%)
- mobility: 8 (0.93%)

## C. 高频动作 Top15
1. Enjoy the meal — 20 (2.31%)
2. Serve the meal — 18 (2.08%)
3. Clean up after eating — 15 (1.74%)
4. Ensure a comfortable sleeping environment — 15 (1.74%)
5. Prepare a comfortable sleeping environment — 9 (1.04%)
6. Start cooking the meal — 8 (0.93%)
7. Prepare a comfortable sleep environment — 7 (0.81%)
8. Cook the meal — 6 (0.69%)
9. Return home from current location — 6 (0.69%)
10. Enjoy the meal at home — 5 (0.58%)
11. Ensure a comfortable sleep environment — 5 (0.58%)
12. Prepare the sleeping environment — 5 (0.58%)
13. Lie down in the bed — 5 (0.58%)
14. Prepare breakfast — 5 (0.58%)
15. Adjust the room temperature if necessary — 4 (0.46%)

## D. 按天分布（meal/sleep/other/mobility）
- day 0: meal=48(44.4%), sleep=25(23.1%), other=34(31.5%), mobility=1(0.9%)
- day 1: meal=70(48.6%), sleep=36(25.0%), other=36(25.0%), mobility=2(1.4%)
- day 2: meal=61(42.4%), sleep=46(31.9%), other=37(25.7%), mobility=0(0.0%)
- day 3: meal=70(48.6%), sleep=38(26.4%), other=35(24.3%), mobility=1(0.7%)
- day 4: meal=57(39.6%), sleep=35(24.3%), other=51(35.4%), mobility=1(0.7%)
- day 5: meal=59(41.0%), sleep=38(26.4%), other=45(31.2%), mobility=2(1.4%)
- day 6: meal=19(52.8%), sleep=6(16.7%), other=10(27.8%), mobility=1(2.8%)

## E. 按人分布（核心6人）
- 500019134: meal=67/144(46.5%), sleep=31.2%, other=21.5%, mobility=0.7%, digital=0.0%
- 500022131: meal=63/144(43.8%), sleep=31.9%, other=23.6%, mobility=0.7%, digital=0.0%
- 500033414: meal=56/144(38.9%), sleep=24.3%, other=36.1%, mobility=0.7%, digital=0.0%
- 500038614: meal=65/144(45.1%), sleep=27.8%, other=26.4%, mobility=0.7%, digital=0.0%
- 500055778: meal=75/144(52.1%), sleep=20.8%, other=26.4%, mobility=0.7%, digital=0.0%
- 500055517: meal=50/120(41.7%), sleep=21.7%, other=35.8%, mobility=0.8%, digital=0.0%

## F. 连续行为（Longest Run）
- aid 500055517: meal 连续 11 步（day2 t75601 -> day3 t25201）
- aid 500055778: meal 连续 10 步（day1 t7201 -> day1 t39601）
- aid 500019134: meal 连续 9 步（day5 t7201 -> day5 t36001）
- aid 500022131: meal 连续 9 步（day4 t79201 -> day5 t21601）
- aid 500038614: meal 连续 7 步（day1 t1 -> day1 t21601）
- aid 500033414: meal 连续 6 步（day1 t28801 -> day1 t46801）
- aid 500007323: meal 连续 2 步（day5 t25201 -> day5 t28801）
- aid 500023827: meal 连续 2 步（day4 t75601 -> day4 t79201）

## G. 事件触发时点动作上下文
- step 28801 (day0 t28801): event=1, meal=3, sleep=0, other=3, mobility=0
- step 43201 (day0 t43201): event=1, meal=5, sleep=0, other=1, mobility=0
- step 354001 (day3 t54001): event=1, meal=1, sleep=5, other=0, mobility=0
- step 357601 (day3 t57601): event=1, meal=1, sleep=4, other=1, mobility=0
- step 428801 (day4 t28801): event=1, meal=2, sleep=4, other=0, mobility=0
- step 457601 (day4 t57601): event=1, meal=4, sleep=0, other=2, mobility=0
- step 572001 (day5 t72001): event=1, meal=1, sleep=4, other=1, mobility=0

## H. 供给-暴露-触发链路（按天）
- day 0: attempt=31, exposure=24, seeded=6, surface=8, completed=6, emitted=2, pre_match_miss=82, skip=71
- day 1: attempt=20, exposure=21, seeded=6, surface=13, completed=6, emitted=0, pre_match_miss=124, skip=124
- day 2: attempt=41, exposure=17, seeded=6, surface=11, completed=6, emitted=0, pre_match_miss=127, skip=103
- day 3: attempt=17, exposure=17, seeded=6, surface=21, completed=6, emitted=2, pre_match_miss=130, skip=127
- day 4: attempt=48, exposure=28, seeded=6, surface=9, completed=6, emitted=2, pre_match_miss=121, skip=96
- day 5: attempt=34, exposure=34, seeded=6, surface=10, completed=6, emitted=1, pre_match_miss=112, skip=110
- day 6: attempt=8, exposure=8, seeded=6, surface=10, completed=3, emitted=0, pre_match_miss=34, skip=34

## I. 合理性评估（结论）
- 生活行为合理性：中高。退休画像下，meal/sleep占比高是可解释的，且动作文本丰富（唯一动作655）。
- 数字摩擦任务匹配性：偏低。动作文本层面 digital≈0%，mobility<1%，导致可触发场景上下文不足。
- 触发链路短板：pre_match_miss 与 scenario_skip 仍高，说明大量 step 没进入有效触发决策。
- 行为结构偏置：meal 连续 run 最长可到11步，易出现“吃饭链条”主导。
