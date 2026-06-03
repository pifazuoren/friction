# Memory-driven App Entry 思想说明

## 1. 核心想法

Memory-driven App Entry 的核心不是让 Day 4--7 继续复用 May 1--3 的 app-context prior。

相反，我们真正想做的是：

> Day 4--7 不再把 TalkingData prior 当作 app entry 生成器，而是让 LLM 基于 agent 的 profile、前三天记忆、helplessness、trust、avoidance 和 controllability belief，自己生成后续 app entry 行为。

也就是说，Day 4--7 应该更像一次真正的 LLM simulation rollout，而不是 prior replay。

TalkingData 在这里的角色要收窄：

- TalkingData 用来定义 app-context taxonomy；
- TalkingData 用来校准 Day 1--3 的 reference 入口；
- TalkingData May 4--7 作为 held-out validation；
- TalkingData May 1--3 prior 不再直接控制 Day 4--7 app-context 生成。

这样做的原因很简单：May 1--3 和 May 4--7 的总体 app-context 分布本来就非常相似。如果我们继续用 May 1--3 prior 生成 Day 4--7，再拿 May 4--7 做验证，那么 prior-only 本身就会表现很好。这种验证很难说明 LLM simulation 的意义。

因此，我们希望把 Day 4--7 设计成：

> taxonomy-constrained, memory-driven LLM app-entry rollout.

通俗说，就是：

> LLM 不能乱造 app 类型，只能在合法 app context 里选；但具体要不要进入手机场景、进入哪类 app context，要由 agent 的前三天经历和心理状态来驱动。

## 2. 为什么不能继续依赖 May 1--3 prior

May 1--3 prior 是一个很强的 statistical baseline。

因为 TalkingData 里 May 1--3 和 May 4--7 的总体 app-context exposure 很稳定，所以只要按 May 1--3 分布继续抽，May 4--7 的总体比例自然就会很像。

这可以说明：

> 数据集中的 app 使用场景具有短期稳定性。

但它不能说明：

> agent 的前三天经历真的影响了后四天行为。

如果我们想把论文讲成 LLM agent simulation，而不是简单的 distribution replay，就不能让 prior 在 Day 4--7 继续主导生成。

所以我们应该保留 prior-only 作为强 baseline，但不把它当作主方法。

主方法应该是：

> Memory-driven LLM App Entry.

prior-only 的作用是告诉审稿人：

> 这是一个很强的简单基线；如果只看总体分布，它已经很难被打败。

而 memory-driven 的价值是：

> 它不只是拟合总体分布，还能解释个体 agent 为什么在经历不同事件后进入不同数字场景。

## 3. Day 4--7 生成时 LLM 可以看到什么

Day 4--7 的 LLM app entry 不应该看到 May 4--7 validation prior，也不应该直接读取 May 1--3 app-context 概率表来抽样。

它应该看到的是 agent 自身状态和合法选择空间。

LLM 可以看到：

- agent profile；
- 当前 day / hour；
- Day 1--3 recent memory；
- 近期成功、失败、放弃、求助经历；
- helplessness level；
- trust level；
- avoidance tendency；
- controllability belief；
- 最近哪些 task family 让 agent 感到可控或不可控；
- 合法 app-context 列表；
- 哪些 context 是 context-only；
- 哪些 context 是 task-eligible。

LLM 需要决定：

- 当前是否发生一次 app entry；
- 如果发生，进入哪个 app context；
- 这个选择的简短理由；
- 这个选择和 agent 记忆/心理状态之间有什么关系。

这样，Day 4--7 的 app entry 就真正由 agent internal state 驱动，而不是由 prior 直接决定。

## 4. TalkingData 在 Day 4--7 的角色

在这个新口径里，TalkingData May 4--7 只用于验证，不参与生成。

TalkingData May 1--3 也不应该作为 Day 4--7 的 app-context generator。

但是 TalkingData 仍然有重要作用。

第一，它定义了现实 app 使用的分类边界。

我们不是让 LLM 随便创造 app 类别，而是让它只能从清洗后的 app-context taxonomy 中选择。例如：

- finance context；
- public service context；
- health service context；
- shopping lifestyle context；
- navigation transport context；
- education work context；
- communication social context；
- media entertainment context；
- device tool context；
- taxonomy profile only；
- unknown or unmapped。

第二，它提供 held-out validation。

Day 4--7 跑完以后，我们用 TalkingData May 4--7 检查 baseline world 的 app-context exposure 是否严重偏离真实数据。

这时验证才比较干净：

> validation data 没有参与 Day 4--7 生成，只在最后用于检查。

第三，它提供 prior-only baseline。

我们可以保留一个 prior-only 版本，用 May 1--3 prior 直接生成 Day 4--7。这个版本不是主方法，而是强基线。

如果 memory-driven 的总体分布略差于 prior-only，这不一定是失败。因为 prior-only 本来就是针对稳定分布的强统计基线。

关键是 memory-driven 能不能产生 prior-only 没有的心理机制解释。

## 5. Memory-driven App Entry 不是纯自由生成

虽然 Day 4--7 不再用 app-context prior 作为生成器，但这不等于让 LLM 完全自由发挥。

LLM 仍然受到几个边界约束。

第一，合法 app context 受 taxonomy 限制。

LLM 只能从我们定义好的 app-context 列表中选择，不能自己发明新类别。

第二，DigitalTask 仍然由 occurrence gate 决定。

即使 LLM 选择 finance context，也不代表一定生成支付任务。它只表示 agent 进入了金融相关 app 使用场景。是否真的遇到困难 DigitalTask，还要经过 task occurrence gate。

第三，context-only 和 task-eligible 要区分。

LLM 可以选择 communication social、media entertainment、device tool 这样的 context-only 场景。这些场景代表普通手机使用，不应该强行生成困难任务。

第四，LLM 的理由要被审计。

如果 LLM 说 agent 因为最近支付失败而减少 finance context，这是一种可解释的 memory effect。

如果 LLM 无缘无故大量减少所有 app entry，或者把所有失败都解释成完全不用手机，这就需要被 audit 捕捉。

所以这个方案不是：

> LLM 想怎么生成就怎么生成。

而是：

> LLM 在合法 app-context 空间内，根据 agent memory 和心理状态生成 app entry。

## 6. App Entry 和 DigitalTask 仍然要分开

Memory-driven App Entry 只决定 app entry，不直接决定困难任务。

这点非常重要。

TalkingData 只有 app 使用记录，没有 app 内部任务真值。即使 agent 进入 finance context，也可能只是查看余额、浏览账单或接收通知，不一定是在付款、转账或做风险确认。

因此，Day 4--7 的流程应该是：

> LLM 决定 app entry；
> app entry 得到 selected app context；
> task-eligible context 进入 occurrence gate；
> gate pass 后才生成 DigitalTask；
> gate fail 则记录为普通 app-context exposure。

这样能避免把普通 app 使用强行解释成困难任务。

同时，这也保留了我们现在入口层重构的意义：

> app exposure 和 DigitalTask occurrence 是两个不同层次。

## 7. Baseline world 的新解释

在 Memory-driven App Entry 中，baseline world 不应该被说成 “真实世界本身”。

更准确地说，baseline world 是：

> a normal-world LLM simulation checked against held-out app-context exposure data.

也就是：

> 一个由 LLM memory-driven rollout 生成的正常世界，并用 TalkingData May 4--7 检查它是否严重偏离真实 app 使用数据。

如果 baseline world 在 Day 4--7 的 app-context exposure 上和 TalkingData validation 接近，我们可以说：

> baseline world 在 app-entry 层面具有一定外部 plausibility。

但不能说：

> baseline world 完全等于现实世界。

更稳的论文表述是：

> The baseline world is not a replay of the validation prior. It is a memory-driven LLM rollout constrained by a fixed app-context taxonomy and evaluated against held-out app-context exposure data.

中文就是：

> baseline 不是把验证集先验复读一遍，而是在固定 app-context 分类下，让带记忆的 LLM agent 自己生活，再用 held-out 数据检查它像不像。

这个说法比 “使用 prior 校准 Day 4--7” 更能体现 LLM simulation 的意义。

## 8. prior-only、memory-driven、shuffled-memory 的关系

为了让实验更清楚，Day 4--7 可以分成三种对照。

### prior-only

prior-only 使用 May 1--3 app-context prior 直接生成 Day 4--7。

它回答的是：

> 如果只利用短期稳定分布，能不能预测 May 4--7？

它是强 statistical baseline。

### memory-driven

memory-driven 不直接使用 app-context prior 生成 Day 4--7，而是让 LLM 根据 agent 的 profile、memory 和心理状态生成 app entry。

它回答的是：

> agent 的前三天经历是否能驱动后四天的数字行为变化？

这是我们的主方法。

### shuffled-memory

shuffled-memory 把前三天记忆打乱或错配给其他 agent。

它回答的是：

> app entry 的变化真的是由 agent-specific memory 造成的吗？

如果真实 memory-driven 和 shuffled-memory 没区别，说明 memory 没有真正发挥作用。

如果真实 memory-driven 能产生更合理的心理行为关系，而 shuffled-memory 不能，就能说明 agent-specific memory 对后续 app entry 有贡献。

## 9. 我们不一定要在总体分布上赢 prior-only

由于 May 1--3 和 May 4--7 的总体 app-context 分布本来就很接近，prior-only 在总体分布拟合上会非常强。

因此，我们不应该把目标设成：

> memory-driven 必须在总体 TVD / JS divergence 上打败 prior-only。

这既不现实，也不一定是我们真正想证明的东西。

更合理的目标是：

> memory-driven 的总体分布不能严重跑偏，同时要产生 prior-only 无法表达的心理机制信号。

也就是说：

- prior-only 负责证明短期 app exposure 分布稳定；
- memory-driven 负责证明 agent memory 和心理状态能解释个体差异；
- shuffled-memory 负责证明这种解释不是随机的。

所以，memory-driven 的成功标准不是 “总体比例更像”，而是：

> 在保持基本外部 plausibility 的同时，产生可解释的 individual-level behavioral heterogeneity。

## 10. 我们真正想验证什么

Memory-driven App Entry 的验证应该分成两类。

第一类是外部合理性。

我们检查 Day 4--7 baseline world 的 app-context exposure 是否离 TalkingData May 4--7 validation 太远。

这不是为了证明 baseline 等于现实世界，而是为了证明：

> LLM rollout 没有跑到完全不现实的手机使用分布。

第二类是机制合理性。

我们检查 agent 的前三天经历和心理状态是否能解释后四天 app entry 差异。例如：

- helplessness 高的 agent 是否更少进入 task-eligible context；
- avoidance 高的 agent 是否更倾向 context-only app 使用；
- trust 高的 agent 是否更愿意进入需要求助或服务支持的 context；
- controllability belief 高的 agent 是否更愿意重新进入困难任务相关 context；
- 最近 payment / login / service 失败是否降低对应 context 的进入；
- 最近成功是否恢复对应 context 的进入；
- shuffled-memory 是否削弱这些关系。

这些才是 prior-only 无法提供的证据。

## 11. 论文口径

论文里可以这样表述：

> We separate held-out app-context validation from app-entry generation. In Days 4--7, agents do not replay the May 1--3 app-context prior. Instead, a taxonomy-constrained LLM app-entry policy generates entry decisions from each agent's profile, recent memory, helplessness, trust, avoidance, and controllability beliefs. TalkingData May 4--7 is used only as held-out validation, while prior-only and shuffled-memory rollouts serve as baselines.

中文意思是：

> 我们把验证数据和生成机制分开。Day 4--7 不再复用 May 1--3 的 app-context prior，而是让 LLM 根据 agent 的画像、近期记忆、helplessness、trust、avoidance 和可控性信念生成 app entry。TalkingData May 4--7 只作为 held-out validation；prior-only 和 shuffled-memory 作为对照组。

这句话能把我们的立场说清楚：

- 不是 validation leakage；
- 不是 pure prior replay；
- 不是 unconstrained LLM free generation；
- 而是 taxonomy-constrained, memory-driven LLM simulation。

## 12. 对整个实验的意义

加入这个版本的 Memory-driven App Entry 后，实验叙事会更强。

原来的叙事容易被理解成：

> 我们用 TalkingData prior 生成入口，再观察 helplessness。

新的叙事是：

> 我们用 TalkingData 定义现实 app-context taxonomy，并保留 May 4--7 作为 held-out validation；Day 1--3 让 agent 积累数字摩擦经历；Day 4--7 让 LLM agent 带着记忆和心理状态继续生活；然后检查 baseline 是否仍然具有外部 plausibility，并比较不同 friction/support worlds 下的 helplessness、trust、avoidance 和 strategy dynamics。

这样，LLM simulation 的意义就更明确：

> LLM 不只是 rerank prior，而是在固定分类空间内，把 agent 的个体经历和心理状态转化成后续数字行为。

