# Task Family Advice: 泛数字任务分类与相似度计算方案

## 1. 主方案：6 类泛数字 task family

本研究不以某一个具体 App 或单一生活场景为单位，而是将老年人在数字服务中反复遇到的操作环节抽象为 6 类泛数字 task family。

这样做的目的不是建立一个完整的数字素养分类体系，而是为当前 digital friction -> helplessness 实验提供一个清晰、可解释、可计算的任务空间。

推荐的 6 类 task family 如下：

| 编号 | Task family | 核心含义 | 典型 friction |
|---|---|---|---|
| 1 | 入口导航与服务定位 | 打开 App / 网页后找到正确入口，理解当前页面结构，定位目标服务 | 找不到入口、页面跳转混乱、功能名称不清楚 |
| 2 | 账号登录与身份验证 | 通过账号、密码、验证码、人脸识别、实名认证等方式进入系统 | 验证码过期、密码错误、重复验证、人脸识别失败 |
| 3 | 信息查询与可信判断 | 搜索、浏览、筛选并理解数字服务中的信息，判断信息是否可靠 | 信息太多、术语难懂、结果不明确、真假难辨 |
| 4 | 资料填写与材料上传 | 输入个人信息、地址、证件号、申请材料，并上传图片或文件 | 填写错误、格式不符、材料上传失败、权限被拒绝 |
| 5 | 服务申请与流程提交 | 选择服务类型、时间、地点或项目，完成预约、申请、下单、提交等多步骤流程 | 步骤太多、选项复杂、提交失败、不知道是否成功 |
| 6 | 支付结算与风险确认 | 确认金额、选择支付方式、完成付款，并处理风险提示或支付异常 | 支付失败、金额不确定、风险弹窗、担心诈骗或误付 |

这 6 类任务对应的是数字服务中的通用操作环节，而不是具体 App 名称。例如，“服务申请与流程提交”可以出现在医院挂号、政务申请、出行订票、社区服务预约等多个场景中。

在当前实验中，task family 的作用是承载 self-efficacy、controllability belief 和 helplessness 相关状态。一次任务失败后，如果 agent 将失败解释为较广范围的问题，scope spillover 会优先影响语义相似的 task family。

因此，这里的 task family 需要满足三个要求：

- 足够 general，不能只绑定在医院、购物或政务某一个场景；
- 边界足够清楚，便于解释一次失败为什么会扩散到另一类任务；
- 数量不能过多，避免机制分析和实验解释变得混乱。

## 2. Similarity：基于标准化任务描述的 embedding similarity

任务相似度不建议直接比较 task family 名称。例如，不能只比较“登录验证”和“支付结算”几个字，因为名称太短，无法充分表达任务目标、操作过程和失败点。

更合适的做法是：为每个 task family 写一段标准化描述，再使用 embedding 方法计算语义相似度。

每个 task family 的描述建议包含 4 个部分：

- `task goal`：这个任务要完成什么目标；
- `typical user actions`：用户通常要做哪些操作；
- `required information or confirmation`：需要输入、确认或授权什么信息；
- `common failure points`：常见失败点或数字摩擦在哪里。

示例描述：

```text
账号登录与身份验证：
用户需要通过手机号、账号密码、短信验证码、人脸识别或实名认证等方式进入数字服务系统。用户通常需要输入身份信息、接收并填写验证码、确认账号安全或完成系统要求的验证步骤。常见失败点包括验证码过期、密码遗忘、重复验证、人脸识别失败、身份信息不匹配。
```

```text
服务申请与流程提交：
用户需要选择服务类型、时间、地点或项目，并按照系统步骤完成预约、申请、下单或提交。用户通常需要阅读服务说明、选择选项、填写必要信息、确认提交结果。常见失败点包括流程步骤过多、选项难以理解、提交失败、系统没有明确反馈。
```

```text
支付结算与风险确认：
用户需要确认订单、费用或账单金额，选择支付方式，并完成线上付款。用户通常需要核对金额、选择银行卡或第三方支付工具、输入支付密码或完成安全验证。常见失败点包括支付失败、风险弹窗、银行卡绑定失败、金额理解错误、担心诈骗或误付。
```

计算流程可以写成：

```text
标准化任务描述 -> embedding 向量 -> cosine similarity -> similarity matrix
```

形式化表示：

```text
e_i = Embed(description_i)
sim(i, j) = cos(e_i, e_j)
```

其中：

- `description_i` 表示第 `i` 个 task family 的标准化文本描述；
- `e_i` 表示该描述对应的 embedding 向量；
- `sim(i, j)` 表示两个 task family 的语义相似度。

该 similarity matrix 可以作为 Gaussian scope spillover 的输入：

```text
d(i, j) = 1 - sim(i, j)
w(i, j) = exp(-d(i, j)^2 / (2 sigma^2))
```

在当前实验中，建议继续使用归一化版本：

```text
\hat{w}(i, j) = w(i, j) / sum_{k != i} w(i, k)
```

这样一次失败的总扩散量不会因为 task family 数量增加而失控，而是被分配到相似任务上。越相似的任务获得越大的 spillover weight，越不相似的任务获得越小的 spillover weight。

当前 scope spillover 可以保持为：

```text
A_t = beta * U_t * scope_amplitude_t
Delta SE_{j,t}^{spill} = - A_t * \hat{w}(i, j)
```

其中：

- `U_t` 表示当前失败事件的 uncontrollability；
- `scope_amplitude_t` 表示 LLM 判断的本次失败归因扩散强度；
- `beta` 表示整体缩放参数；
- `Delta SE_{j,t}^{spill}` 表示失败从 source task family `i` 扩散到 target task family `j` 后，对 `j` 的 self-efficacy 产生的负向更新。

## 3. 相关可支持的文献

### 3.1 UK Essential Digital Skills Framework

UK Essential Digital Skills Framework 是当前方案最直接的任务设计依据。

它面向成人日常数字生活，将基本数字技能分为：

- digital foundation skills
- communicating
- handling information and content
- transacting
- problem solving
- being safe and legal online

其中 `transacting` 部分尤其重要，因为它明确包含：

- online account setup
- using online public services
- filling in online forms
- uploading documents or photographs
- online payment
- online banking
- booking appointments

这些内容可以直接支撑本文将数字服务拆成登录验证、资料填写、材料上传、服务申请、支付结算等跨场景任务环节。

参考链接：

https://www.gov.uk/government/publications/essential-digital-skills-framework/essential-digital-skills-framework

### 3.2 DigComp 2.2

DigComp 2.2 是欧盟 Joint Research Centre 提出的数字能力框架，提供了更宏观的数字能力分类依据。

它将数字能力分为五大类：

- information and data literacy
- communication and collaboration
- digital content creation
- safety
- problem solving

其中 information and data literacy 可以支撑“信息查询与可信判断”；safety 可以支撑“账号登录与身份验证”“支付结算与风险确认”；problem solving 可以支撑“入口导航”“流程提交失败后的处理”等数字摩擦环节。

参考链接：

https://joint-research-centre.ec.europa.eu/digcomp/digital-competence-framework_en

### 3.3 老年人数字素养与移动设备能力研究

老年人数字素养相关研究可以说明：这些泛数字任务并不是年轻用户特有的问题，而是老年人在数字融入过程中确实会遇到的能力要求和困难来源。

Oh et al. (2021) 对老年数字素养测量进行了系统综述，指出老年数字素养涉及信息处理、安全、问题解决、沟通等多个维度。该研究可以用于支撑：本文的 task family 设计适用于老年数字任务情境。

Roque and Boot (2018) 提出的 Mobile Device Proficiency Questionnaire 专门评估老年人的移动设备能力，涉及移动设备基础操作、沟通、互联网使用、隐私、故障处理和软件管理等方面。该研究可以支撑：老年人在手机和移动 App 中遇到的问题具有跨场景的共同操作基础。

参考链接：

https://pubmed.ncbi.nlm.nih.gov/33533727/

https://pubmed.ncbi.nlm.nih.gov/27255686/

### 3.4 Internet Skills / Digital Divide

van Deursen 和 van Dijk 关于 internet skills 与 digital divide 的研究，将互联网技能划分为 operational、formal、information 和 strategic skills。

这一路线可以用于说明：数字任务不只是具体 App 功能，而是依赖一组可迁移的互联网操作技能、信息导航技能和目标达成技能。

参考链接：

https://journals.sagepub.com/doi/10.1177/1461444810386774

### 3.5 E-service / E-government transaction 研究

电子政务和 e-service 研究通常将线上服务发展分为 information、interaction、transaction 等阶段。transaction 阶段往往涉及身份确认、在线表单、材料提交、数字签名、在线支付等环节。

这类研究可以支撑：在线公共服务和交易型数字服务中确实存在一组反复出现的操作流程，而本文的 task family 正是对这些流程的实验化抽象。

可参考：

- Layne and Lee (2001), Developing fully functional E-government
- Yildiz (2007), E-government research: Reviewing the literature

