# TalkingData Entry Layer 修改 TODO

## 1. 核心判断

当前 TalkingData 接入有两个概念混在了一起：

```text
TalkingData app category
```

和：

```text
digital friction task family
```

TalkingData 记录的是用户在某个时间点有哪些 app / app category 活跃。它不能直接告诉我们用户在 app 内部是在登录、上传材料、提交申请、确认付款，还是只是浏览页面。

因此，当前这条链路过于直接：

```text
TalkingData category
→ mobile intention
→ digital task family
```

更合理的链路应该是：

```text
TalkingData category
→ app context / mobile-use context
→ task opportunity distribution
→ digital task family or context-only
```

一句话：

```text
TalkingData 负责“用户进入什么手机使用场景”；
我们的模型负责“这个场景里可能出现什么数字摩擦任务”。
```

## 2. 当前 May 1-3 分类概率

当前 `elder_reference_may1_may3` artifact 的 global prior 约为：

```text
unknown_or_unmapped           75.81%
use_payment_or_finance        11.35%
submit_service_application     6.69%
communicate_or_seek_help       2.69%
browse_entertainment           1.81%
find_location_or_service       1.01%
check_information              0.38%
login_or_verify_account        0.17%
upload_or_manage_profile       0.09%
```

这说明 `unknown_or_unmapped` 不是一个真实单一行为，而是一个巨大的混合桶。

其中包含：

```text
真实不可解释类别
数据标签/画像标签
娱乐/媒体/生活类 app context
交通/酒店/出行类 context
工具类 context
社交/身份关系 context
金融相关但被漏判的类别
```

所以仅靠 prompt 告诉 LLM “尊重 unknown” 并不够。更根本的修法是：

```text
先拆 unknown 大桶；
再把 app category 映射为 app context；
最后由 app context 生成可能的 digital task。
```

## 3. 当前 Digital Task Family

我们现在真正的 digital friction tasks 是 6 类：

```text
navigation_service_location       入口导航与服务定位
account_login_verification        账号登录与身份验证
information_search_judgment       信息查询与可信判断
profile_form_upload               资料填写与材料上传
service_application_submission    服务申请与流程提交
payment_risk_confirmation         支付结算与风险确认
```

这些不是 app category，而是 app 内部可能出现的操作步骤。

例如：

```text
银行 app 里可能出现登录验证、信息查询、付款确认、风险判断。
政务/医疗 app 里可能出现入口查找、登录认证、材料上传、服务提交。
出行 app 里可能出现服务定位、信息判断、付款确认。
```

因此不应继续采用：

```text
finance app category = payment_risk_confirmation
service app category = service_application_submission
```

这种一步硬映射。

## 4. 新分类层：App Context

第一版建议将 TalkingData category 映射到 `app_context`，而不是直接映射到 task。

建议的 app context：

```text
finance_context
public_service_context
health_service_context
shopping_lifestyle_context
navigation_transport_context
communication_social_context
media_entertainment_context
device_tool_context
education_work_context
taxonomy_profile_label
unknown_or_unmapped
```

说明：

```text
finance_context:
  银行、理财、证券、贷款、P2P、信用卡、支付、风险类 category。

public_service_context:
  政务、公共服务、生活缴费、办事服务、机构服务等 category。

health_service_context:
  医疗、健康、挂号、药品、健康服务等 category。

shopping_lifestyle_context:
  购物、商城、酒店、生活消费、母婴、美容、家电等 category。

navigation_transport_context:
  地图、导航、公交、汽车、航班、旅游、酒店预订、出行服务等 category。

communication_social_context:
  社交、聊天、联系人、亲属、社区、平台通信等 context。

media_entertainment_context:
  小说、漫画、影视、音乐、游戏、阅读、广播、娱乐等 category。

device_tool_context:
  日历、备忘录、网盘、文件、系统工具、设备工具等 category。

education_work_context:
  教育、科技、工作、招聘、学习相关 category。

taxonomy_profile_label:
  明显不是用户具体 app 行为的标签，例如 Industry tag、Property Industry、
  Custom label、Higher income、Quality、Nature 等。

unknown_or_unmapped:
  仍然完全无法解释或无法归类的 category。
```

## 5. App Context 到 Task Opportunity

第二层不是每个 context 都生成 task。

建议第一版规则：

```text
task-eligible contexts:
  finance_context
  public_service_context
  health_service_context
  shopping_lifestyle_context
  navigation_transport_context
  education_work_context

context-only contexts:
  communication_social_context
  media_entertainment_context
  device_tool_context
  taxonomy_profile_label
  unknown_or_unmapped
```

注意：`communication_social_context` 第一版不直接生成 task。它可以作为 help/social context 记录，但不应直接变成 FamilyHelperAgent 或 help-seeking task。

### 5.1 初步 task opportunity distribution

第一版可以使用保守的手工分布，后续再根据实验和人工 review 调整。

```text
finance_context:
  account_login_verification        0.25
  information_search_judgment       0.20
  payment_risk_confirmation         0.40
  service_application_submission    0.15

public_service_context:
  navigation_service_location       0.25
  account_login_verification        0.20
  profile_form_upload               0.25
  service_application_submission    0.30

health_service_context:
  navigation_service_location       0.20
  account_login_verification        0.15
  information_search_judgment       0.20
  profile_form_upload               0.20
  service_application_submission    0.25

shopping_lifestyle_context:
  navigation_service_location       0.15
  account_login_verification        0.15
  information_search_judgment       0.20
  payment_risk_confirmation         0.30
  service_application_submission    0.20

navigation_transport_context:
  navigation_service_location       0.55
  information_search_judgment       0.20
  account_login_verification        0.10
  payment_risk_confirmation         0.15

education_work_context:
  navigation_service_location       0.15
  account_login_verification        0.10
  information_search_judgment       0.50
  profile_form_upload               0.15
  service_application_submission    0.10
```

这些分布不是 TalkingData 直接标签，而是从 app context 到可能 app-internal task 的桥接假设。论文中必须说明它是 prototype mapping / scenario bridge，而不是 ground truth label。

## 6. Unknown 拆分策略

当前 `unknown_or_unmapped` 不应继续作为唯一大桶。

第一版把原 unknown 拆成：

```text
taxonomy_profile_label
finance_context 或 finance_candidate_review
media_entertainment_context
shopping_lifestyle_context
navigation_transport_context
device_tool_context
communication_social_context
education_work_context
unknown_or_unmapped
```

建议先保留 `finance_candidate_review` 作为 audit-only 中间状态：

```text
P2P
financial
High risk
Low Risk
Debit and credit
Securities
A shares
fixed income
Financial Supermarket
```

这类 category 很可能属于 finance context，但第一版不要全部无审查地改成 payment task。可以先标记为：

```text
app_context = finance_context
review_status = finance_candidate_needs_review
task_eligible = false 或 conservative
```

后续人工确认后，再逐步升级到 task-eligible finance context。

## 7. 需要新增的中间产物

第一步先做 audit，不直接改仿真。

新增或生成：

```text
category_to_app_context_audit.csv
```

字段建议：

```text
category_raw
category_normalized
old_mobile_intention
new_app_context
task_eligible
candidate_task_families_json
count_reference
mass_reference
count_validation
mass_validation
mapping_basis
review_status
```

目的：

```text
先看分类是否合理；
先看拆分后概率；
先确认 task-like context 有没有异常膨胀；
再决定是否进入仿真。
```

## 8. 后续代码修改方向

### 8.1 Artifact 构建

修改或扩展：

```text
examples/digital_friction_mvp/build_mobile_intention_artifacts.py
```

从直接输出：

```text
mobile_intention_prior_by_bucket_hour
```

扩展为同时输出：

```text
app_context_prior_by_bucket_hour
category_to_app_context_audit.csv
task_opportunity_prior_by_context.json
```

旧字段可以先保留，避免一次性破坏现有流程。

### 8.2 Task Entry

当前流程：

```text
mobile_intention → mapped_task_family → DigitalTask
```

目标流程：

```text
app_context → task_eligible? → task_family distribution → DigitalTask / context-only
```

第一版可以兼容旧字段：

```text
如果 artifact 有 app_context_prior，则走新逻辑；
否则继续走旧 mobile_intention 逻辑。
```

### 8.3 LLM Rerank

LLM rerank 不再直接 rerank task intention，而是 rerank：

```text
app_context
```

prompt 重点：

```text
candidate contexts 是 empirical reference prior。
不要把 media/tool/taxonomy context 脑补成 finance/service task。
如果从 context-only 改成 task-eligible context，需要强理由。
```

LLM 输出仍保持简单：

```text
selected_app_context
confidence
reason
```

第一版如果不想大改 schema，可以先保留 `selected_mobile_intention` 字段名，但内部值扩展为 app context；不过论文和后续可读性更推荐明确改名为 `selected_app_context`。

## 9. Audit 字段

新增 audit 重点不是“是否选 unknown”，而是：

```text
是否从 context-only 改成 task-eligible
是否从高 prior context 改到低 prior context
是否最终生成 task
```

建议字段：

```text
rule_selected_app_context
llm_selected_app_context
final_selected_app_context
rule_selected_prior
llm_selected_prior
final_selected_prior
rule_task_eligible
llm_task_eligible
final_task_eligible
changed_context_only_to_task_eligible
changed_to_lower_prior
prior_drop_from_rule_to_llm
generated_task_family
task_opportunity_distribution_json
context_mapping_basis
context_review_status
```

## 10. 验证指标

修改后需要分别验证三层。

### 10.1 App Context Fit

和 TalkingData May 4-7 heldout 对比：

```text
app_context_tvd
app_context_js
hourly_app_context_tvd
context-only mass gap
task-eligible context mass gap
```

### 10.2 Task Opportunity Fit

这不是 TalkingData 直接标签，只能做内部 sanity check：

```text
task_generated/evaluated rate
task_family distribution
task_eligible_context → generated_task_family audit
```

### 10.3 Mechanism Experiment

四个 world 仍然比较：

```text
success_rate
negative_feedback_rate
avoid_without_attempt
abandon_midway
help_seek_rate
helplessness_delta
support_response status
Bayesian/Huys audit
```

## 11. 实验影响

这个修改会影响：

```text
任务入口分布
任务生成数量
task family 构成
TalkingData validation 指标
后续 outcome / helplessness 的输入压力
```

但不应直接改：

```text
outcome_model
state_update
Bayesian posterior update
Huys-Dayan policy
FamilyHelperAgent
support response schema
```

也就是说，后续机制保持不变，只是入口更合理。

## 12. 推荐实施顺序

### Phase A: 只做审计，不改仿真

```text
生成 category_to_app_context_audit.csv
统计 May 1-3 / May 4-7 的 app_context 分布
检查 unknown 是否被合理拆分
检查 finance_candidate_review 的质量
```

### Phase B: 新 artifact，但不接入主实验

```text
生成 app_context_prior_by_bucket_hour.json
生成 task_opportunity_prior_by_context.json
扩展 validation 脚本支持 app_context
```

### Phase C: 接入 entry layer smoke

```text
新增或切换 task entry mode
app_context → task opportunity → DigitalTask
先跑 1-day smoke
检查 task_generated/evaluated rate
检查 context-only mass
检查 task family distribution
```

### Phase D: 跑 7-day 4-world

```text
比较新旧 entry layer
比较 TalkingData heldout fit
比较四 world ordering 是否仍然合理
检查 helplessness 是否因入口变化显著变化
```

## 13. 论文口径

推荐写法：

```text
TalkingData provides app-level mobile-use traces rather than labels for
app-internal task steps. We therefore first map app categories into mobile-use
contexts, and then use a context-to-task opportunity bridge to instantiate
digital friction tasks inside the simulation.
```

中文解释：

```text
TalkingData 告诉我们用户进入了什么 app 使用场景；
我们的仿真再根据这个场景生成可能遇到的数字摩擦任务。
```

不应写：

```text
TalkingData 直接标注了用户正在登录/付款/上传材料/提交服务。
```

## 14. 当前判断

这个修改是必要的，但应该分阶段做。

最优先不是直接改主实验，而是：

```text
先生成 app_context audit；
先看分类和概率；
再决定如何接入仿真。
```

一句话：

```text
把 TalkingData 从“任务标签来源”降级为“app context 来源”，
再由 context bridge 生成 digital friction task。
这会让实验入口层更真实，也更容易被审稿人接受。
```
