# Initial Formulation for Digital Friction Helplessness Mechanism

## 1. 这份文档是做什么的

这是一份面向当前 `digital_friction_mvp` 项目的**初步理论 formulation**，目标不是逐行复现现有代码，而是回答下面三个问题：

1. 我们现在的 helplessness / self-efficacy / attribution 机制，怎样写成更像心理学建模的形式化表达？
2. 其他心理学与计算精神病学论文，通常怎样量化“信念、情绪、控制感、选择倾向”这类心理变量？
3. 哪些函数家族适合借到当前项目里，哪些虽然经典但暂时不建议直接上？

这份 formulation 的定位是：

- **理论导向**
- **项目可落地**
- **参数暂不实证化**

也就是说，本文最看重的是：

- 结构是否清楚
- 各变量应该处在哪一层
- 哪些函数形状有比较稳的文献支撑

而不是立刻给出“最终正确的系数”。

---

## 2. 我们当前最需要的，不是一个更大的总公式

从目前项目状态看，最容易出问题的不是“变量不够多”，而是把太多心理变量都堆进一条更新式里。

更稳的做法是把系统拆成四层：

1. **学习层**：我从这次事件学到了什么  
2. **状态层**：我当前的 helplessness / anxiety / confidence 处在什么水平  
3. **信念层**：我是否开始相信“以后也会这样”“这一类任务都这样”  
4. **决策层**：我下一次还会不会尝试

对应到函数家族上，最自然的分工是：

- 学习层：`error-correction`
- 状态层：`recency-weighted state update`
- 信念层：`Bayesian-style belief update`
- 决策层：`sigmoid / soft threshold`

这比“一个总公式里同时塞 helplessness、support、usefulness、anxiety、attribution、risk”要清楚得多。

---

## 3. 可参考的心理学函数家族

### 3.1 Error-Correction Learning

最经典的形式来自 Rescorla-Wagner：

\[
V_{t+1}=V_t+\alpha \delta_t,\qquad \delta_t=r_t-\hat r_t
\]

它的核心思想是：

- 人不是机械记住“发生过什么”
- 而是在更新“我原来以为会怎样”和“这次实际怎样”之间的误差

这类函数适合量化：

- action-outcome contingency
- controllability belief
- task-specific self-efficacy 的短期修正

对我们项目最有帮助的地方是：

- 它天然不是“失败次数累加”
- 它强调 expectation error
- 它支持早期经验权重大、后期逐渐稳定

### 3.2 Recency-Weighted State Update

代表性的形式可以参考 momentary well-being 建模：

\[
S_t = w_0 + \sum_{j=1}^{t}\gamma^{t-j} x_j
\]

其中：

- \(S_t\) 是当前主观状态
- \(x_j\) 是过去事件贡献
- \(\gamma\in[0,1]\) 控制近期经验比远期经验更重要

这类函数特别适合量化：

- helplessness
- anxiety
- short-horizon subjective burden

它适合我们项目的原因是：

- helplessness 很像一个滚动心理状态
- 它不该只是总失败数
- 它应该更受近期不可控体验影响

### 3.3 Bayesian Belief Updating

标准写法是：

\[
P(\theta \mid D)\propto P(D\mid \theta)P(\theta)
\]

如果写成更直观的均值更新形式，常见是：

\[
\mu_{\text{post}}
=
\frac{\pi_{\text{prior}}\mu_{\text{prior}}+\pi_{\text{data}}x}
{\pi_{\text{prior}}+\pi_{\text{data}}}
\]

这里最重要的不是公式表面，而是它表达了：

- 旧信念有多稳
- 新证据有多可信
- 两者共同决定更新幅度

这类函数适合量化：

- generalized helplessness belief
- attribution style 的逐渐固化
- “我是不是就是不行”这种跨事件信念

### 3.4 Prospect-Style Asymmetry

经典价值函数写成：

\[
v(x)=
\begin{cases}
x^\alpha, & x\ge 0 \\
-\lambda(-x)^\beta, & x<0
\end{cases}
\qquad \lambda > 1
\]

它要表达的是：

- 同量级的坏事往往比好事更“重”
- gain 和 loss 的心理处理通常不对称

这类函数在我们项目里最自然的借法是：

- failure 的伤害项可以比 success 的修复项更强
- 但不要把这种不对称夸张到“成功几乎永远没用”

### 3.5 State-Space / Mean-Reverting Dynamics

更一般的形式可以写成：

\[
x_t = A x_{t-1} + B u_t + w_t
\]

或者连续时间里的均值回复过程：

\[
dX_t=\theta(\mu-X_t)\,dt+\sigma\,dW_t
\]

它表达的是：

- 人有一个相对稳定的基线
- 事件会把状态拉偏
- 如果没有新打击，状态可能慢慢回到基线附近

这类函数适合量化：

- helplessness 的恢复速度
- 个体差异化的情绪惯性
- stage-level 而不是 event-level 的缓慢漂移

### 3.6 Evidence Accumulation

典型如 drift-diffusion：

\[
dx_t = v\,dt + \sigma\,dW_t
\]

当状态到达某个决策边界时，个体做出选择。

它很适合量化：

- 单次尝试/回避决策
- hesitation
- confidence

但对我们当前项目来说，它不是最优先。

原因是我们当前主要问题不是“单次反应时”，而是“跨事件心理状态如何变化”。

---

## 4. 对当前项目最值得借的函数，不是全部一起上

### 4.1 推荐优先借的

1. `error-correction`
2. `recency-weighted state`
3. `Bayesian-style belief stabilization`
4. `Prospect-style asymmetry`

### 4.2 暂时不建议直接上主线的

1. 完整 active inference
2. 完整 drift-diffusion 主导架构
3. 过细的连续微分方程情绪系统

原因不是这些方法不好，而是：

- 解释成本太高
- 与当前代码距离太远
- 论文里不好讲成一条清楚主线

---

## 5. 面向当前项目的变量定义

为便于后续统一，这里先给出一组初步变量。

- \(H_t\)：event \(t\) 前的 helplessness
- \(U_t\)：event-level uncontrollability
- \(C_{k,t}\)：任务 \(k\) 上的 controllability belief
- \(SE_{k,t}\)：任务 \(k\) 上的 task self-efficacy
- \(M_{k,t}\)：任务 \(k\) 上的 controllable success memory
- \(A^{stab}_t\)：本次 attribution 的 stability 维度
- \(A^{scope}_t\)：本次 attribution 的 scope 维度
- \(PU_{k,t}\)：任务 \(k\) 的 perceived usefulness
- \(R_{k,t}\)：任务 \(k\) 的 perceived risk
- \(P(\text{attempt}_{k,t}=1)\)：本轮是否尝试的概率

其中：

- \(k\) 表示 task 或 task family
- 各变量可以归一化到 \([0,1]\) 或保留项目现有 0-100 尺度

从理论表达上，我更推荐统一到 \([0,1]\)，因为这样更利于比较不同项的角色。

---

## 6. 一个适合当前项目的初步分层 formulation

下面这组不是“现有代码逐行等价式”，而是我认为**最适合当前项目后续收敛**的一版初步 formulation。

### 6.1 任务级 controllability belief 更新

先定义一个 event-level experienced contingency signal：

\[
q_t \in [0,1]
\]

它表示这次事件让 agent 感受到“我的反应与结果是有关的”的程度。

于是任务级 controllability belief 可以写成：

\[
C_{k,t+1} = (1-\alpha_c)C_{k,t} + \alpha_c q_t
\]

也可以写成误差修正形式：

\[
C_{k,t+1}=C_{k,t}+\alpha_c(q_t-C_{k,t})
\]

这条式子的直觉是：

- 如果这次体验是“我做了确实有用”，那么 \(q_t\) 高，\(C_{k,t}\) 上升
- 如果这次体验是“我做了也没用”，那么 \(q_t\) 低，\(C_{k,t}\) 下降

这条式子适合承接：

- `event-level uncontrollability`
- action-outcome contingency
- learned controllability

### 6.2 task self-efficacy 更新

定义：

- \(m_t\)：mastery quality，表示这次成功有多像“真正自己掌握了”
- \(f_t\)：failure impact，表示这次失败对能力判断的冲击

可以写成：

\[
SE_{k,t+1}
=
\mathrm{clip}\Big(
SE_{k,t}+\alpha_m m_t-\alpha_f f_t,\ 0,\ 1
\Big)
\]

为了体现“自己做成”和“被帮助做成”不一样，可以进一步约束：

\[
m_t(\text{success\_self}) > m_t(\text{success\_with\_help})
\]

而且 \(f_t\) 不建议只由 failure 决定，更适合写成：

\[
f_t = U_t \cdot (1-C_{k,t})
\]

也就是说：

- 同样是失败
- 如果这次主观上强烈不可控，而且自己原本也不太相信能掌控
- 那它对 self-efficacy 的打击会更强

### 6.3 controllable success memory 更新

为了避免“过去成功次数”过于粗糙，建议只记高质量 mastery：

\[
M_{k,t+1}
=
\lambda_M M_{k,t} + (1-\lambda_M)m_t
\]

其中：

- \(m_t\) 越接近“独立掌握且主观可控”
- 对 \(M_{k,t}\) 的提升越大

这个式子很适合表达：

- 为什么 success_self 比 success_with_help 更有长期保护价值
- 为什么 mastery 的作用是累积性的，但不是永久不变

### 6.4 helplessness 的核心冲击项

我不建议把 helplessness 写成一个纯 outcome 计数器。

更好的写法是先定义一个 event impact：

\[
I_t=
\begin{cases}
\beta_- \, g(U_t)\, \big(1+\beta_E(1-SE_{k,t})\big)\,\big(1-\beta_M M_{k,t}\big), & \text{failure / abandon / helpless\_avoid}\\[6pt]
-\beta_+\, m_t, & \text{success}
\end{cases}
\]

其中：

- \(g(U_t)\) 可以是分段函数，也可以是 sigmoid
- \(\beta_- > \beta_+\)，表示失败冲击通常大于单次成功修复

这条式子保留了三个核心思想：

1. 本次是否伤人，最近端主驱动是 `event-level uncontrollability`
2. 低 self-efficacy 会放大冲击
3. controllable success memory 会削弱冲击

### 6.5 attribution 不直接决定本次主冲击，而是决定持续性与泛化

这一层我建议不要直接改成：

\[
I_t = I_t + \text{attribution\_bonus}
\]

而是把 attribution 主要接到两个位置：

1. recovery / persistence
2. generalization

先定义 recovery rate：

\[
r_t
=
r_0
+\eta_{tr}\mathbf{1}(A^{stab}_t=\text{transient})
-\eta_{st}\mathbf{1}(A^{stab}_t=\text{stable})
\]

这里表示：

- transient attribution 让恢复更快
- stable attribution 让恢复更慢

于是 helplessness 主状态可以写成：

\[
H_{t+1}
=
\mathrm{clip}\big((1-r_t)H_t + I_t,\ 0,\ 1\big)
\]

这条式子要表达的是：

- 本次伤害大小主要由 \(I_t\) 决定
- 之后拖多久，更多由 attribution 的 stability 决定

### 6.6 task-family generalization

定义任务家族层的 generalized pressure：

\[
G_{f,t+1}
=
\mathrm{clip}\Big(
\lambda_G G_{f,t}
+ \eta_g H_t \cdot \mathbf{1}(A^{scope}_t=\text{family-generalizing}),
\ 0,\ 1
\Big)
\]

如果只想做更平滑版本，也可以写成：

\[
G_{f,t+1}
=
\mathrm{clip}\Big(
\lambda_G G_{f,t}
+ \eta_g H_t \cdot s_t,
\ 0,\ 1
\Big)
\]

其中 \(s_t \in [0,1]\) 表示 scope 的连续强度。

它的作用不是替代 helplessness，而是回答：

- 这次伤害会不会扩散到相似数字任务

### 6.7 attempt / avoid 概率

任务尝试概率不建议直接由 helplessness 决定。

更合理的形式是：

\[
PU_{k,t}
=
\theta_0
+\theta_E SE_{k,t}
-\theta_A Anxiety_t
-\theta_R R_{k,t}
+\theta_S Support_t
\]

然后：

\[
P(\text{attempt}_{k,t}=1)
=
\sigma\Big(
\phi_0
+\phi_U PU_{k,t}
+\phi_E SE_{k,t}
-\phi_H H_t
-\phi_R R_{k,t}
\Big)
\]

这里表达的是：

- `support` 更适合走上游路径
- `usefulness` 与 `self-efficacy` 决定“值不值得做”“我做不做得来”
- `helplessness` 更像一种压低尝试意愿的背景负荷

这也更符合 TAM / UTAUT 和老年数字接受文献。

---

## 7. 一组更适合当前项目的最小版本

如果只做最小可用版，我建议先保留下面 4 条：

### 7.1 Controllability Learning

\[
C_{k,t+1}=C_{k,t}+\alpha_c(q_t-C_{k,t})
\]

### 7.2 Self-Efficacy Update

\[
SE_{k,t+1}
=
\mathrm{clip}(SE_{k,t}+\alpha_m m_t-\alpha_f f_t,\ 0,\ 1)
\]

### 7.3 Helplessness Update

\[
I_t=
\begin{cases}
\beta_- g(U_t)(1+\beta_E(1-SE_{k,t}))(1-\beta_M M_{k,t}), & \text{negative event}\\[4pt]
-\beta_+ m_t, & \text{success}
\end{cases}
\]

\[
H_{t+1}
=
\mathrm{clip}\big((1-r_t)H_t+I_t,\ 0,\ 1\big)
\]

### 7.4 Attribution Persistence / Generalization

\[
r_t
=
r_0
+\eta_{tr}\mathbf{1}(transient)
-\eta_{st}\mathbf{1}(stable)
\]

\[
G_{f,t+1}
=
\mathrm{clip}\Big(\lambda_G G_{f,t}+\eta_g H_t\mathbf{1}(family\text{-}generalizing),0,1\Big)
\]

这四条已经足够表达一条很清楚的故事：

- 事件先改 controllability 与 efficacy
- 再通过 uncontrollability 决定本次伤害
- 过去 mastery 提供保护
- attribution 决定拖多久、扩多远

---

## 8. 哪些地方不要这样用

### 8.1 不要让 support 直接减 helplessness

不建议写成：

\[
H_{t+1}=H_t+\cdots-\omega_S Support_t
\]

更建议：

- support 先影响 self-efficacy
- 或影响 usefulness
- 或影响 mastery quality

### 8.2 不要让 attribution 直接决定本次 raw delta

不建议写成：

\[
I_t = I_t + \omega_A A_t
\]

更建议：

- stability 决定 persistence
- scope 决定 generalization
- locus 先只做解释层

### 8.3 不要把 anxiety 当作 helplessness 的直接替代

anxiety 和 helplessness 有关系，但不是同一个东西。

更建议：

- anxiety 先影响 usefulness / appraisal / attempt
- helplessness 主要保留为 uncontrollability 驱动的无助状态

### 8.4 不要一上来上完整 Bayesian + OU + DDM

如果一开始全部接入，会有三个问题：

1. 机制太重
2. 参数太多
3. 实验与论文都不好解释

---

## 9. 一个更适合论文表达的总框架

如果要把当前机制讲成论文里的 formulation，我建议总结构写成：

\[
\text{Event} \rightarrow
\text{Uncontrollability} \rightarrow
\text{Helplessness Impact}
\rightarrow
\text{Persistence / Generalization}
\rightarrow
\text{Future Attempt}
\]

然后分别说明：

### 9.1 学习层

\[
C_{k,t+1}=C_{k,t}+\alpha_c(q_t-C_{k,t})
\]

### 9.2 任务能力层

\[
SE_{k,t+1}
=
\mathrm{clip}(SE_{k,t}+\alpha_m m_t-\alpha_f f_t,\ 0,\ 1)
\]

### 9.3 无助状态层

\[
H_{t+1}
=
\mathrm{clip}\big((1-r_t)H_t+I_t,\ 0,\ 1\big)
\]

### 9.4 泛化层

\[
G_{f,t+1}
=
\mathrm{clip}\Big(\lambda_G G_{f,t}+\eta_g H_t s_t,\ 0,\ 1\Big)
\]

### 9.5 行为层

\[
P(\text{attempt}_{k,t}=1)=
\sigma(\phi_0+\phi_U PU_{k,t}+\phi_E SE_{k,t}-\phi_H H_t-\phi_R R_{k,t})
\]

这比“所有变量都塞进 \(\Delta H_t\)”更利于发表，也更容易做消融实验。

---

## 10. 这份 formulation 与当前代码的关系

这份文档不是当前代码的逐行翻译。

如果要区分：

- [FormaleEquation.tex](FormaleEquation.tex)：更偏**代码一致性版本**
- `formulation.md`：更偏**理论收敛版本**

两者的关系是：

1. `FormaleEquation.tex` 回答“当前代码究竟在算什么”
2. `formulation.md` 回答“如果要把它讲成一个更像心理学机制模型，我们该怎么组织”

---

## 11. 我目前最推荐的采用方式

如果从今天开始往代码里逐步靠，我建议按下面顺序用这些 formulation：

1. 先保留当前 `event-level uncontrollability` 作为 helplessness 最近端主驱动
2. 把 `task self-efficacy` 稳定为放大器，而不是再和其他项并列堆加
3. 把 `controllable success memory` 明确成长期保护项
4. 把 attribution 明确限制为 persistence + generalization
5. 把 `support / usefulness / anxiety / risk` 放回 appraisal 和 attempt 层

如果只做最小落地版，就先做：

- Controllability learning
- Self-efficacy update
- Helplessness update
- Attribution persistence/generalization

这已经足够形成一条比较漂亮的论文主线。

---

## 12. 参考文献与借法说明

下面列的是这份 formulation 主要借鉴的外部论文与各自提供的函数思路。

### 12.1 Rescorla, R. A., & Wagner, A. R. (1972)

可借内容：

- error-correction learning
- expectation error
- contingency belief update

链接：

- https://www.researchgate.net/publication/233820243_A_theory_of_Pavlovian_conditioning_Variations_in_the_effectiveness_of_reinforcement_and_nonreinforcement

### 12.2 Rutledge et al. (2014)

可借内容：

- recency-weighted subjective state
- exponential decay of past events
- 当前心理状态由最近经验加权形成

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC4143018/

### 12.3 Tversky, A., & Kahneman, D. (1979)

可借内容：

- gain-loss asymmetry
- failure impact > success relief

链接：

- https://www.econometricsociety.org/publications/econometrica/browse/1979/03/01/prospect-theory-analysis-decision-under-risk

### 12.4 Feldmann et al. (2022)

可借内容：

- Bayesian belief updating
- prior precision 与 new evidence 的权衡
- depressive symptomatology 里的 belief update 视角

链接：

- https://pubmed.ncbi.nlm.nih.gov/36114811/

### 12.5 Oravecz et al. (2011)

可借内容：

- affective dynamics
- mean reversion
- inertia / variability / recovery

链接：

- https://pubmed.ncbi.nlm.nih.gov/21823796/

### 12.6 Lodewyckx et al. (2011)

可借内容：

- hierarchical state-space affect dynamics
- 个体差异化的动态状态建模

链接：

- https://pubmed.ncbi.nlm.nih.gov/21516216/

### 12.7 Ratcliff (1978)

可借内容：

- evidence accumulation
- decision threshold

但当前阶段不建议作为主线。

链接：

- https://web.stanford.edu/~jlmcc/Presentations/Ratcliff_1978.pdf

---

## 13. 一句话结论

对当前项目来说，最值得借的不是某一篇论文里的“现成大公式”，而是几种成熟的**函数角色分工**：

- 用 `error-correction` 表达学习
- 用 `recency-weighted update` 表达状态
- 用 `Bayesian update` 表达广义信念
- 用 `Prospect-style asymmetry` 表达失败与成功的不对称

真正好的 formulation 不是把所有变量塞进一个总式，而是让每类变量待在它最应该待的那一层。

---

## 14. 新补充的一组更可靠文献支持

这一节补的是相对更“硬”的外部支持，优先保留：

1. 原始研究论文
2. 高质量综述或理论整合
3. 对已有计算模型的复现或参数可靠性研究

这里的目的不是继续扩展机制，而是帮助后续论文写作时更稳地回答：

- 这些函数形状在心理学里是不是常见
- 有没有更可靠的实证支持
- 哪些来源适合放在 Related Work / Formulation Rationale / Limitations 里

### 14.1 与 helplessness / controllability 最相关的支持

#### Maier, S. F., & Seligman, M. E. P. (2016)

标题：

- *Learned Helplessness at Fifty: Insights from Neuroscience*

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC4920136/

为什么重要：

- 这篇不是单一实验，而是非常核心的整合论文
- 它重新组织了 learned helplessness 的机制：被动反应并不一定是“学出来的”，学习到的是 control
- 对我们项目最重要的启发是：**主轴应该围绕 controllability / uncontrollability detection，而不是简单 failure counting**

适合支持什么：

- `event-level uncontrollability` 作为主驱动
- “learned control” 比 “learned passivity” 更适合作为主线
- 为什么 mastery / control experience 有保护作用

可靠性判断：

- **高**
- 虽然是综述型整合，不是单一原始实验，但在 helplessness 文献里非常权威

#### Ly, V., Wang, K. S., Bhanji, J., & Delgado, M. R. (2019)

标题：

- *A Reward-Based Framework of Perceived Control*

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC6379460/

为什么重要：

- 这篇直接把 perceived control 和 reinforcement learning / contingency 学习联系起来
- 它明确指出：实际控制经验与 perceived control 之间可以用 reward-based / contingency-based 框架理解

适合支持什么：

- controllability belief 的更新
- 为什么 control 不是静态人格，而是可以被经验塑造
- 为什么过去控制成功会形成 context-specific 和 general perceived control

可靠性判断：

- **高**
- 这是高质量综述，不是公式论文，但非常适合给我们“controllability learning”提供理论桥梁

### 14.2 与状态动态最相关的支持

#### Rutledge, R. B., Skandali, N., Dayan, P., & Dolan, R. J. (2014)

标题：

- *A Computational and Neural Model of Momentary Subjective Well-Being*

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC4143018/

为什么重要：

- 这是很典型的原始计算论文
- 它把主观幸福感写成对近期 rewards、expectations、prediction errors 的加权和
- 它非常适合支持“心理状态是 recency-weighted，而不是历史总量”

适合支持什么：

- helplessness / anxiety 这类 rolling state
- exponential decay / forgetting factor
- “近期经验权重大于久远经验”的状态更新

可靠性判断：

- **很高**
- PNAS 原始论文，而且是这个方向最常被引用的代表之一

#### Vanhasbroeck, N., et al. (2021)

标题：

- *Testing a Computational Model of Subjective Well-Being: A Preregistered Replication of Rutledge et al. (2014)*

链接：

- https://pubmed.ncbi.nlm.nih.gov/33632071/

为什么重要：

- 它不是新模型，而是对 Rutledge 模型做预注册复现
- 对我们最有价值的不是新增机制，而是**告诉我们“这种状态动态模型不是一次性的偶然结果”**

适合支持什么：

- 如果后面论文里采用 recency-weighted affect / burden update
- 可以用来增强这个函数家族的可信性

可靠性判断：

- **高**
- 不是原始发现，但它提高了模型的稳健性说服力

### 14.3 与“内部信号也能驱动学习”最相关的支持

#### Guggenmos, M., et al. (2022)

标题：

- *The Value of Confidence: Confidence Prediction Errors Drive Value-Based Learning in the Absence of External Feedback*

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC9560614/

为什么重要：

- 这篇表明：即便没有外部反馈，人也可能用内部 confidence signal 来更新价值学习
- 这对我们项目很有启发，因为老年数字任务里很多“我是不是掌握了”的判断，本来就不全依赖明确外部奖励

适合支持什么：

- mastery quality
- self-efficacy / confidence 的内生强化
- 为什么“主观掌握感”可以成为学习更新的一部分

可靠性判断：

- **高**
- 原始研究，且直接比较了 confidence-based 模型和更标准的模型

### 14.4 与决策概率函数最相关的支持

#### Ratcliff 系列与后续 DDM 教程文献

代表链接：

- https://web.stanford.edu/~jlmcc/Presentations/Ratcliff_1978.pdf
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9784241/

为什么重要：

- Ratcliff 1978 是经典来源
- 后面的实用综述则说明 DDM 已经成为决策建模的稳定工具箱

适合支持什么：

- 如果未来要更细地建 attempt vs avoid 的边界过程
- 或想把 hesitation / confidence 一起纳入

为什么暂时不作为主线：

- 你们现在核心问题是跨事件心理变化，不是毫秒级决策过程
- 所以 DDM 更像 future extension，而不是当前 formulation 主轴

可靠性判断：

- **高**
- 但对当前项目是“方法储备”，不是“最贴主题的直接主证据”

### 14.5 与参数可靠性最相关的支持

#### Mkrtchian, A., et al. (2023)

标题：

- *Reliability of Decision-Making and Reinforcement Learning Computational Parameters*

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC11104400/

为什么重要：

- 很多计算模型的问题不在于“写不出公式”，而在于参数不稳定
- 这篇可以提醒我们后面做实验时，不要只看模型 fit，还要看参数在 repeated sessions 或 repeated seeds 下是否稳定

适合支持什么：

- 论文 limitations
- 为什么后续要做 sensitivity analysis
- 为什么参数解释要谨慎，结构通常比参数值更可信

可靠性判断：

- **高**
- 这类研究不直接告诉我们该用哪条公式，但非常适合支持方法论上的谨慎表述

### 14.6 与 confidence / belief-state / softmax 决策最相关的支持

#### Lockwood, P. L., et al. / 同类 Bayesian confidence 建模文献

这里可用的一个例子是：

- *Neurocomputational mechanisms of confidence in self and others*
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9307648/

为什么重要：

- 这类论文把 belief state、confidence、expected value、softmax 组合到同一套决策模型里
- 它说明：把 latent confidence / belief 转成 choice probability，本来就是认知建模里的常规做法

适合支持什么：

- 为什么我们可以把 `PU / SE / H / risk` 放进 attempt probability 的 sigmoid / softmax
- 为什么“心理状态 -> 行为概率”这一步用概率映射是合理的

可靠性判断：

- **中高**
- 这类论文更偏 decision neuroscience，不是 helplessness 专题，但对行为层 formulation 很有帮助

### 14.7 与 RL 作为跨领域通用函数家族最相关的支持

#### Chase, H. W., et al. (2015)

标题：

- *Reinforcement Learning Models and Their Neural Correlates: An Activation Likelihood Estimation Meta-Analysis*

链接：

- https://pmc.ncbi.nlm.nih.gov/articles/PMC4437864/

为什么重要：

- 它不是在讲 helplessness，但它说明 RL 的 prediction error / expected value 框架已经广泛用于人类学习与决策研究
- 这会让我们借用 error-correction family 时更“站得住”

适合支持什么：

- 为什么 `error-correction` 是一个稳妥的底层学习函数
- 为什么这不是拍脑袋选的形式

可靠性判断：

- **高**
- 但它支持的是“函数家族的广泛有效性”，不是某个具体 helplessness 变量本身

---

## 15. 现在最适合写进论文的支持层次

如果要把这些文献用于论文，我建议分三层写。

### 15.1 第一层：最核心、最贴机制

优先放：

1. Maier & Seligman (2016)
2. Ly et al. (2019)
3. Rutledge et al. (2014)

这一层回答：

- 为什么主线是 uncontrollability / control learning
- 为什么状态更新适合做成近期经验加权

### 15.2 第二层：增强稳健性

优先放：

1. Vanhasbroeck et al. (2021)
2. Mkrtchian et al. (2023)

这一层回答：

- 这种状态动态模型不是一次性现象
- 参数解释应该谨慎，可靠性要单独关注

### 15.3 第三层：方法扩展与储备

优先放：

1. Guggenmos et al. (2022)
2. Ratcliff / DDM 文献
3. confidence / softmax / Bayesian decision 文献

这一层回答：

- 为什么内部 confidence 信号也能驱动学习
- 为什么后面如果扩展到更细决策层，是有成熟工具的

---

## 16. 一个更稳的说法

如果以后老师或评审问：

“你们这个 formulation 是不是太主观了？”

更稳的回答是：

1. helplessness 主轴参考的是 learned helplessness / controllability 文献
2. 状态更新形状参考的是已经用于幸福感和情绪动态的 recency-weighted computational models
3. 行为概率映射参考的是认知决策模型里成熟的 sigmoid / softmax / belief-state 写法
4. 我们承认具体系数仍是 prototype 参数，但函数角色分工并不是随意拼接

这比只说“我们参考了 Bandura / Seligman”会更扎实。
