# Digital Friction MVP TODO

## 2026-03-21

- [ ] 记录并坚持 `perceived_uncontrollability` 的融合原则：当前优先采用“门控式融合”，不采用连续 `alpha` 比例融合
  - 当前结论：
    - 先用规则给 `perceived_uncontrollability` 基线值
    - 仅当 LLM 输出合法且 `confidence >= threshold` 时，允许做最多 `1` 档修正
    - 低置信度、解析失败、schema 不合法时，直接回退规则
  - 为什么当前更适合门控式融合：
    - 该变量现在是 `0/1/2` 三档有序变量，本质更接近 ordinal，而不是天然连续变量
    - 直接做 `rule * (1-alpha) + llm * alpha`，会隐含“0->1”和“1->2”等距，这个假设现在不够稳
    - 额外引入 `alpha` 会新增一个很难解释的参数，老师后续容易继续追问“为什么是这个比例”
    - LLM-as-judge 目前仍有不稳定和过度自信风险，更适合做有限修正，而不是深度接管
    - 对当前 proto 来说，目标是增强可解释性，不是把模型变成新的连续拟合系统
  - 当前推荐表达：
    - `rule baseline + confidence-gated LLM adjustment`
    - 中文可以说成“规则主导、LLM 仅做高置信度小幅修正”
  - 后续升级方向：
    - 如果未来把 `perceived_uncontrollability` 改成潜在连续变量，再考虑 `alpha` 融合或 latent-score 融合
    - 当前阶段先不引入连续混合权重
  - 可引用的方法依据：
    - Hedeker 2015：ordinal outcome 不宜轻易按连续变量处理
    - Badham et al. 2017：多标准加权会引入额外任意权重问题
    - Collins et al. 2024：ABM 应优先服务当前研究目的，简单且可验证的机制更优先
    - Zhao et al. 2024 / Haldar & Hockenmaier 2025：LLM judge 的 calibration 与一致性仍有限

## 2026-03-05

- [ ] 拆分 `main.py` 中大块静态数据（保持逻辑不变）
  - 迁移到 `examples/digital_friction_mvp/scenario_catalog.py`：
    - `EVENT_SCENARIOS`
    - `INTENTION_SCENARIO_MAP`
    - `_STEP_TYPE_SCENARIO_MAP`
    - `_STATUS_GATE_SCENARIO_NAMES`
    - `_SCENARIO_BY_NAME`
  - 迁移到 `examples/digital_friction_mvp/digital_lexicon.py`：
    - `_DIGITAL_CONTEXT_TOKENS`
    - `_DIGITAL_ANCHOR_TOKENS`
    - `_DIGITAL_SOFT_TOKENS`
    - `_DIGITAL_STATUS_CONDITIONAL_TOKENS`
    - `_DIGITAL_DIRECT_TOKENS`
  - 保留在 `main.py`：
    - `_DIGITAL_TOKEN_PATTERN_CACHE`（运行期缓存，避免跨模块副作用）
  - 目标：
    - `main.py` 预计减少约 `377~422` 行（迁移而非删除）
  - 验收：
    - `ruff check`
    - `python -m py_compile`
    - 固定 seed 下关键统计一致（attempt/emitted/outcome/source 分布）

## 2026-03-07

- [ ] 在不改 AgentSociety 原生 4 类 `step_type` 前提下，增加 `step_subtype` 精细语义
  - 背景：
    - `step_type` 由上游计划提示词约束为 `mobility/social/economy/other`，粒度过粗
  - 方案：
    - 从 `step_intention` / `status_text` / `step_eval_text` 推断 `step_subtype`
    - 保持原字段 `step_type` 不变，仅在数字摩擦判定链路使用 `step_subtype`
    - 在 `decision_json` 与审计导出中增加 `step_subtype` 字段
    - `step_subtype` 初版候选（英文键 + 中文释义）：
      - `ride_booking`（网约车下单）
      - `pickup_coordination`（上车点协调）
      - `route_navigation`（路线导航）
      - `contact_lookup`（联系人查找）
      - `message_send`（消息发送）
      - `call_connect`（通话连接）
      - `payment_checkout`（支付结算）
      - `transfer_confirm`（转账确认）
      - `order_place`（提交订单）
      - `order_tracking`（订单跟踪）
      - `login_auth`（登录认证）
      - `captcha_verify`（验证码校验）
      - `account_security`（账号安全校验）
      - `app_update_permission`（应用更新与权限设置）
      - `medical_appointment_booking`（医疗预约挂号）
      - `gov_service_submission`（政务事项提交）
      - `document_upload`（材料上传）
      - `risk_notification_handle`（风险提醒处理）
      - `unknown`（未知/未识别子类型）
  - 兼容：
    - 旧逻辑继续可用（无 `step_subtype` 时回退到当前规则）
  - 验收：
    - `python -m py_compile examples/digital_friction_mvp/main.py`
    - 新增导出中可看到 `step_subtype`，且场景对齐率提升

## 2026-03-09

- [ ] 统一 `action` 与 `step_intention` 的时点语义（先记录，暂不改代码）
  - 现状：
    - 离线对齐检验显示存在稳定“一步错位”（`step_intention(t)` 常对应 `action(t-1)`）
    - 目前主要影响分析解读，不是触发主链路正确性
  - 后续可选修复方向：
    - 运行时预筛统一单一时点信号源（建议仅用 `step_intention` 链路）
    - 在 `decision_json` 增加时点审计字段（`plan_index`/`used_step_index`/`alignment_mode`）
    - 分析导出显式提供 `same/prev/next` 对齐视图，避免误读
  - 暂缓原因：
    - 当前优先级在实验迭代，先不动核心判定路径

## 2026-03-10

- [ ] 评估并按开关引入 `EconomyBlock`（先做最小可运行版本）
  - 目标：
    - 在不破坏现有数字摩擦主链路的前提下，增加经济行为外部效度
  - 计划步骤：
    - 增加 `ECONOMY_BLOCK_ENABLED` 配置开关（默认关闭，便于 A/B）
    - 在 `DigitalFrictionAgent` 的 `blocks` 注册处按开关接入 `EconomyBlock`
    - 显式补齐经济机构 agent（`firms/banks/governments/nbs`），避免仅 citizen 场景下的依赖缺失
    - 为 `MonthEconomyPlanBlock` 增加可控开关（建议默认关闭）以减少额外 LLM 噪声
    - 增加审计字段（是否启用 economy、是否触发月度计划、step_type 分布）
    - 进行 smoke + A/B 验证（同 seed 对比 attempt/emitted/LLM 调用量）
  - 验收：
    - 无新增关键 warning（尤其 `EconomyBlock MonthPlanBlock`）
    - 数字摩擦核心指标可解释（能清楚区分“经济块引入效应”）
    - 文档同步更新（`Development_Log.md`、`friction_shuoming.md`）

- [ ] 问卷升级为“严格量表版”（仅作用于 `DigitalFrictionAgent`）
  - 目标：
    - 从“构念级对齐”升级为“题项与计分规则可追溯”的严格版本。
  - 量表范围（短版拼接）：
    - TAM（PU/PEOU）+ UTAUT（行为意向相关项）
    - GSES（自我效能）+ Pearlin Mastery（掌控感，含反向项）
    - Trust in Automation（信任维度）
    - eHEALS / MDPQ（老年数字能力与设备熟练度）
  - 实施步骤：
    - 确定每个量表保留题项、反向题与统一评分区间（建议统一 0-100 映射）
    - 在 `surveys.py` 重写题目文本与维度分组（保留稳定字段名映射）
    - 在 `main.py` 增加严格版维度聚合与计分规则（含反向计分）
    - 在 `agent.py` 的 survey prompt 中加入“按量表题意作答”约束，不改变 JSON schema
    - 保持作用域隔离：仅 `DigitalFrictionAgent.survey_recent_alignment=True` 生效
  - 验收：
    - 每个维度都能追溯到量表来源与题项映射表
    - 反向题计分与维度聚合可复算
    - `python -m py_compile examples/digital_friction_mvp/surveys.py packages/agentsociety/agentsociety/agent/agent.py examples/digital_friction_mvp/main.py` 通过
    - 文档同步（`Development_Log.md`、`analysis/survey_prompt_literature_alignment.md`、`friction_shuoming.md`）
