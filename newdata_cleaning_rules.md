# TalkingData 新版数据清洗规则

## 1. 修改目的

旧版清洗规则没有明显把原始数据 join 错，但它把 TalkingData 的 `category` 展平成了一行一个标签：

```text
device_id + timestamp + app_id 的某个 label/category
```

这会导致一个问题：同一个 app 如果被 TalkingData 贴了多个标签，就会在清洗结果里变成多行。

例如同一个 active app 可能同时带有：

```text
Finance
Bank
Industry tag
Property Industry 2.0
High risk
Higher income
```

旧数据如果直接按 `category` 计数，就会把这些标签看成多次手机行为。实际上它们更可能只是同一个 app 的多个标签。因此新版清洗目标是：

```text
不要数标签行；
要数 event-app 使用记录。
```

新版链路应从：

```text
event + app + category row
```

改为：

```text
event_id + app_id
→ collect all labels/categories for this app
→ classify app_context
→ build mobile exposure / app-context prior
```

## 2. 保留旧版清洗中仍然合理的部分

以下规则继续保留：

```text
1. 使用 Kaggle TalkingData Mobile User Demographics 原始数据。
2. 使用 gender_age_train.csv 筛选年龄大于 45 岁用户。
3. 丢弃 2016-04-30 的异常少量启动日数据。
4. 保留活跃天数足够的用户。
5. 使用 2016-05-04 00:00:00 作为 reference / validation 切分点。
6. reference = May 1-3。
7. validation = May 4-7。
8. 两端保留同一批用户，便于 within-user validation。
```

也就是说，新版不是推翻旧版，而是修改中间表结构和统计口径。

## 3. 原始文件

继续使用原始 Kaggle 文件：

```text
gender_age_train.csv
events.csv
app_events.csv
app_labels.csv
label_categories.csv
phone_brand_device_model.csv
```

各表含义：

```text
gender_age_train.csv:
  device_id, gender, age, group

events.csv:
  event_id, device_id, timestamp, longitude, latitude

app_events.csv:
  event_id, app_id, is_installed, is_active

app_labels.csv:
  app_id, label_id

label_categories.csv:
  label_id, category

phone_brand_device_model.csv:
  device_id, phone_brand, device_model
```

## 4. 旧问题：category 不是一次行为

`label_categories.csv` 中确实存在这些原始标签：

```text
Industry tag
Property Industry 1.0
Property Industry 2.0
Services 1
Custom label
Higher income
Low income
Personal Effectiveness 1
```

它们不是清洗时凭空产生的。但这些标签不像具体 app 使用场景，更像 TalkingData 标签体系里的上层标签、行业标签、画像标签或属性标签。

因此新版清洗不应把：

```text
category = Industry tag
```

解释成：

```text
用户进行了一次 Industry tag 行为
```

而应解释成：

```text
某个 active app 被 TalkingData 贴了 Industry tag 这个标签。
```

## 5. 新核心表：event_app_labels

新版清洗应先生成一个中间表：

```text
event_app_labels.csv
```

粒度为：

```text
one row = one event_id + one app_id
```

而不是：

```text
one row = one event_id + one app_id + one label_id
```

建议字段：

```text
event_id
device_id
gender
age
timestamp
date
hour
longitude
latitude
app_id
is_installed
is_active
label_ids_json
categories_json
phone_brand
device_model
```

其中：

```text
label_ids_json:
  该 app_id 在 app_labels.csv 中对应的所有 label_id。

categories_json:
  这些 label_id 对应的所有 category 名称。
```

示例：

```json
{
  "event_id": 2,
  "app_id": "4775896950989639373",
  "is_active": 1,
  "categories_json": [
    "Property Industry 1.0",
    "Services 1",
    "Property Industry 2.0",
    "Custom label",
    "Industry tag"
  ]
}
```

这表示同一个 app 有多个标签，而不是用户做了 5 次行为。

## 6. 新 app_context 分类

在 `event_app_labels` 基础上，为每个 event-app 记录生成：

```text
app_context
```

建议第一版 app_context：

```text
finance_context
finance_candidate_review
public_service_context
health_service_context
shopping_lifestyle_context
navigation_transport_context
communication_social_context
media_entertainment_context
device_tool_context
education_work_context
taxonomy_profile_only
unknown_or_unmapped
```

注意：`taxonomy_profile_only` 只表示这个 app 目前只看到了画像/标签体系类信息，不能安全识别具体使用场景。

## 7. 标签分类原则

### 7.1 强场景标签

这些标签可以作为 app_context 的主要证据：

```text
Finance / Internet banking / Pay / mobile bank
Medical / health / hospital / doctor
online shopping / online malls / fashion / hotel
map / navigation / transport / travel / taxi
IM / chat / Tencent / community / social
game / video / music / radio / novel / comic / reading
calendar / camera / file / browser / dictionary / tool
education / office / work / technology information
government / public / utility / convenience services
```

### 7.2 taxonomy/profile 标签

这些标签不应单独决定 app_context：

```text
Industry tag
Property Industry 1.0
Property Industry 2.0
Custom label
Services 1
Higher income
Low income
Personal Effectiveness 1
Total Cost 1
High Flow
Low liquidity
High risk
Low Risk
Quality 1
Nature 1
Relatives 1
Irritation / Fun 1
```

它们可以作为 audit 信息保留，但第一版不直接用于生成 digital task。

### 7.3 金融候选标签

以下标签可能与金融有关，但不应全部自动变成 payment task：

```text
P2P
P2P net loan
High risk
Low Risk
Debit and credit
Securities
A shares
fixed income
Financial Supermarket
stock
loan
liquidity
profitability
```

第一版建议归为：

```text
finance_candidate_review
```

并设置：

```text
task_eligible = false
```

后续人工确认后，再决定是否升级为 `finance_context`。

## 8. app_context 判定优先级

对每个 `event_id + app_id` 的 `categories_json`，按以下优先级判定：

```text
1. 如果存在强场景标签，则根据强场景标签判定 app_context。
2. 如果没有强场景标签，但存在金融候选标签，则判定为 finance_candidate_review。
3. 如果只存在 taxonomy/profile 标签，则判定为 taxonomy_profile_only。
4. 如果标签为空、unknown 或无法解释，则判定为 unknown_or_unmapped。
```

如果一个 app 同时命中多个强场景，第一版按保守优先级处理：

```text
finance_context
health_service_context
public_service_context
navigation_transport_context
shopping_lifestyle_context
education_work_context
communication_social_context
media_entertainment_context
device_tool_context
```

同时输出 audit 字段记录所有命中：

```text
matched_contexts_json
context_mapping_basis
context_review_status
```

## 9. 新 reference / validation 输出

新版不要只输出 category-level prior，而应输出 app-context prior。

建议输出：

```text
elder_reference_event_app_context.csv
elder_validation_event_app_context.csv
app_context_prior_by_bucket_hour_reference.json
app_context_prior_by_bucket_hour_validation.json
app_context_summary_reference.csv
app_context_summary_validation.csv
app_context_summary_comparison.csv
category_label_audit.csv
```

其中：

```text
elder_reference_event_app_context.csv:
  May 1-3 的 event-app 级 app_context 数据。

elder_validation_event_app_context.csv:
  May 4-7 的 event-app 级 app_context 数据。

app_context_prior_by_bucket_hour_reference.json:
  用 May 1-3 生成 runtime prior。

app_context_prior_by_bucket_hour_validation.json:
  只用于 heldout validation，不进入 runtime。
```

## 10. 统计口径

新版统计应使用：

```text
active event-app count
```

而不是：

```text
active category row count
```

也就是说：

```text
一个 active app 不管有多少 label，都只贡献一次 app_context exposure。
```

如果一个 event 下有多个 active app，则每个 active app 计一次。

这样可以保留 TalkingData 的多 app 活跃事实，同时避免多标签重复计数。

## 11. task 生成口径

TalkingData 新版仍然不直接标注 digital friction task。

合理链路是：

```text
TalkingData active app
→ app_context
→ task opportunity distribution
→ digital friction task / context-only
```

不能写成：

```text
TalkingData category 直接等于登录/付款/上传/服务申请任务
```

第一版 task-eligible context：

```text
finance_context
public_service_context
health_service_context
shopping_lifestyle_context
navigation_transport_context
education_work_context
```

第一版 context-only：

```text
finance_candidate_review
communication_social_context
media_entertainment_context
device_tool_context
taxonomy_profile_only
unknown_or_unmapped
```

## 12. heldout validation

May 1-3 仍作为 reference，May 4-7 仍作为 heldout validation。

验证对象从旧的：

```text
mobile_intention distribution
task_family distribution
```

改为优先验证：

```text
app_context distribution
hourly mobile active exposure
task-eligible context mass
context-only mass
per-user app_context preference stability
```

建议指标：

```text
app_context_tvd
app_context_js
hourly_app_context_tvd
task_eligible_context_mass_gap
context_only_mass_gap
per_user_context_rank_correlation
```

## 13. 保留必要 ID，方便回溯

旧版清洗删除了：

```text
event_id
app_id
label_id
```

这让后续语义审计很困难。新版至少在中间表保留：

```text
event_id
app_id
label_ids_json
categories_json
```

最终 runtime artifact 可以不保留全部 ID，但 audit 文件必须保留，以便检查：

```text
某个 app_context 是由哪些原始标签判定出来的。
```

## 14. 推荐输出目录

建议不要覆盖旧数据，而是生成新版目录：

```text
/Users/pifazuoren/Downloads/SeniorApp/TalkingData/v2_event_app_context/
```

建议结构：

```text
v2_event_app_context/
  event_app_labels_reference.csv
  event_app_labels_validation.csv
  elder_reference_event_app_context.csv
  elder_validation_event_app_context.csv
  app_context_prior_by_bucket_hour_reference.json
  app_context_prior_by_bucket_hour_validation.json
  app_context_summary_reference.csv
  app_context_summary_validation.csv
  app_context_summary_comparison.csv
  category_label_audit.csv
  cleaning_manifest.json
```

## 15. 对现有实验的影响

新版数据清洗会改变的是：

```text
mobile entry prior
app_context prior
task opportunity upstream
TalkingData validation 指标
```

不应直接改变：

```text
outcome_model
helplessness_update
FamilyHelperAgent
Bayesian posterior
Huys-Dayan policy
support response schema
```

也就是说，它只修正“任务入口层”的数据基础。

## 16. 最小实施顺序

### Phase 1: event-app audit

```text
读取原始 Kaggle 数据
生成 event_app_labels_reference.csv
生成 event_app_labels_validation.csv
统计高频 label set
确认多标签重复计数问题
```

### Phase 2: app_context mapping

```text
对 event-app 的 categories_json 分类
生成 app_context summary
比较 May 1-3 和 May 4-7
```

### Phase 3: artifact-only

```text
生成 app_context_prior_by_bucket_hour_reference.json
生成 validation target
先不接入主仿真
```

### Phase 4: runtime smoke

```text
新增或切换 entry mode
app_context -> task opportunity -> task
先跑 1-day smoke
再跑 7-day 4-world
```

## 17. 论文表述建议

推荐写法：

```text
TalkingData provides app-level mobile exposure traces with multi-label app
taxonomy annotations. We therefore aggregate labels at the event-app level,
map each active app exposure into a mobile-use context, and then instantiate
digital-friction tasks through a context-to-task opportunity bridge.
```

中文含义：

```text
TalkingData 告诉我们用户在什么时候暴露于哪些 app 使用场景；
它不直接告诉我们用户是否正在登录、付款、上传材料或提交申请。
因此我们先在 event-app 粒度合并标签并判断 app context，
再由 app context 生成可能的数字摩擦任务。
```

不应写：

```text
TalkingData 直接提供了 digital task label。
```

## 18. 当前结论

旧版清洗的 join 逻辑大概率没有明显错误，但旧版输出过早删除了 `event_id/app_id/label_id`，并把多标签 app 展平成 category 行，导致后续很容易把标签行误读为行为行。

新版清洗应保留 event-app 粒度，把标签作为 app 的属性集合，而不是把每个标签当作一次独立行为。
