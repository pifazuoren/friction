# 11 月 28 日的实验复核入口

在仓库根目录使用安装了项目依赖的 Python。下列命令中的路径是本机运行归档；完整日志、SQLite、设备文件保存在各自的私有目录。

```bash
probes='report/2026结项/仓库发布/2026-11-28/probes'
runs='agentsociety_data/runs'
first_week="$runs/scheduled_login/scheduled_login_20261128_150446_837442"
second_week="$runs/scheduled_login/scheduled_login_20261128_164754_f22f29"
six_cases="$runs/resident_choice_smoke/resident_choice_20261128_163129_9306a0_final"
help_cases="$runs/support_preference_smoke/support_preference_20261128_145509_b1c66e"

python "$probes/verify_week_activity.py" "$first_week" "$second_week"
python "$probes/run_resident_choice.py" --source "$first_week" --verify-run "$six_cases"
python "$probes/verify_support_preference.py" "$help_cases"
```

- 第一条从两轮的同一批设备和前三天的历史复算用机与空闲。它还从第二轮原始逐次日志重算 687 个自由时段的首次建议和执行。
- 第二条重建四个小时的决策和两次受挫后的复查选择，核对实际发出的提示与全部六个结果。这是历史版本的专项检查，使用当时的 V3 自由时段提示。
- 第三条核对两名人物在第 4 天请求帮助的方式、家人实际回复，以及第 5 天模型收到的提示。第 4 天预先指定进入求助分支，第 5 天允许自由选择。两个日期之间没有连续运行。

以上三条均离线读取归档，输出写到终端。要采集新回答，才使用下面的命令；输出目录必须是新的。两项分别最多调用 `glm-4-flashx` 18 次和 24 次，凭证通过隐藏输入提供。

```bash
python "$probes/run_resident_choice.py" --source "$first_week" --online --output-dir "$runs/resident_choice_smoke/new_run"
python "$probes/run_support_preference.py" --online --output-dir "$runs/support_preference_smoke/new_run"
```
