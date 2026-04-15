# AgentSociety Prompt Notes (4 Papers)

说明：

- 本文件基于本地 PDF 直接抽取整理，使用了 `fitz` / `pypdf`，没有使用 MinerU。
- 目标是尽可能完整地整理这 4 篇论文里和 `prompt` 有关的内容，包括：
  - 明确给出的 prompt 模板
  - survey / interview / reflection / planning 中带有提示词功能的文本
  - 输出格式要求
  - 正文里只描述了 prompt 作用、但没有给出完整模板的部分
- 这里的第 3 篇按当前公开 PDF 标题整理：
  - `Debiasing International Attitudes: LLM Agents for Simulating US-China Perception Changes`
  - 它对应你前面列单里那篇作者一致、主题连续的“US attitude changes towards China”工作。

## Scope

本次整理的 4 篇论文是：

1. `A Parallelized Framework for Simulating Large-Scale LLM Agents with Realistic Environments and Interactions`
2. `Exploring Large Language Model Agents for Piloting Social Experiments`
3. `Debiasing International Attitudes: LLM Agents for Simulating US-China Perception Changes`
4. `Simulating Generative Social Agents via Theory-Informed Workflow Design`

## Quick Inventory

| Paper | Prompt material level | Notes |
| --- | --- | --- |
| 1 | 3 个明确 prompt | 都在附录 B.1 |
| 2 | 最完整 | 附录 B 有大批核心 prompts |
| 3 | 较碎片化 | 主要来自 Fig. 3、reflection 机制说明、survey question |
| 4 | 很完整 | 附录 A 给出 Motivation / Planning / Learning 三大模块 prompts |

---

## 1. A Parallelized Framework for Simulating Large-Scale LLM Agents with Realistic Environments and Interactions

来源文件：

- [parallelized_framework_large_scale_llm_agents_realistic_environments_interactions_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/parallelized_framework_large_scale_llm_agents_realistic_environments_interactions_2025.pdf)

和 prompt 相关的核心位置：

- 正文提到 “detailed prompt implementations can be found in Appendix A / B”
- 附录 `B.1 LLM-based Textual Simulator Prompts` 给出了 3 个显式 prompt
- 位置大致在 PDF 第 10-11 页

### 1.1 Prompt Context

论文把这组 prompt 作为“真实环境模拟器”的替代方案，用 LLM 自带知识做文本式环境推断，支持 mobility simulation。原文说明这组 prompt 用于：

- text-based location type selection
- destination selection
- travel time estimation

### 1.2 Prompt 1: Place Type Selection

用途：

- 根据 agent 的当前 intention 判断应该去什么类型的地点

原文 prompt：

```text
You are an intelligent assistant specializing in understanding user needs and suggesting appropriate location types.
Based on the user’s intention, provide the most suitable location type.

- User’s intention: {intention}

Please output in JSON format without any other text:
{
  "type": "string", location type
}

Example Output:
{
  "type": "Grocery Store"
}
```

### 1.3 Prompt 2: Destination Selection

用途：

- 给定当前位置和目标地点类型，选择一个具体 destination，并估计距离

原文 prompt：

```text
You are an intelligent assistant specializing in suggesting specific destinations based on location types.
Provide a suitable location name and estimate its distance from the current position.

- Current location: {current location}
- Target location type: {place type}

Please output in JSON format without any other text:
{
  "name": "string", locations’ name
  "distance": "integer", in meter
}

Example Output:
{
  "name": "Supermarket",
  "distance": 1500
}
```

### 1.4 Prompt 3: Travel Time Estimation

用途：

- 根据 agent profile、天气、距离来估计 travel time

原文 prompt：

```text
You are an intelligent assistant specializing in travel time estimation.
Based on the provided distance, calculate the estimated time required to reach the destination, assuming typical traffic conditions.

- User’s profile: {agent profile}
- Weather: {weather}
- distance: {distance} m

Please output in JSON format without any other text:
{
  "time": "integer", in minutes
}

Example Output:
{
  "time": 10
}
```

### 1.5 This Paper’s Prompt Characteristics

- 偏“环境补全型 prompt”，不是完整 cognitive agent prompt
- 都强约束 JSON 输出
- 都是单轮、功能性、原子任务 prompt
- 明显服务于 mobility environment estimation，而不是完整社会实验流程

---

## 2. Exploring Large Language Model Agents for Piloting Social Experiments

来源文件：

- [LLM_Agents_for_Piloting_Social_Experiments.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/LLM_Agents_for_Piloting_Social_Experiments.pdf)

和 prompt 相关的核心位置：

- 正文多次提到 prompt 驱动 minds / behaviors / surveys / interviews
- Table 7 里有一个单独的 hurricane 问句 prompt
- 附录 `B Core Prompts for Experimental Procedures` 最关键，位于 PDF 第 21-25 页

### 2.1 Main-Text Prompt-Relevant Notes

正文里与 prompt 直接相关的几点：

- Agents 被分为 `profiles and status / minds / behaviors`
- Minds 中的 emotions、thoughts、attitudes 都通过 prompt 更新
- Thoughts 在 survey / interview 场景中尤其重要
- 社交行为、移动行为、经济行为都通过 prompt 组织
- Structured surveys 和 open-ended interviews 被明确作为实验采集方式

### 2.2 Table 7 Prompt

这是正文中单独明确出现的一条 prompt：

```text
Can you provide the percentage decline in visit activity in Columbia, South Carolina from August 31 to September 2, 2019, caused by Hurricane Dorian?
```

论文用它展示不同 LLM 对同一 prompt 的回答差异。

### 2.3 Appendix B Overview

附录原文说，这一组核心 prompts 分成四类：

- `Minds`
- `Social Behaviors`
- `Needs and Memory`
- `Experimental`

下面按论文结构完整整理。

### 2.4 Minds

#### 2.4.1 Emotion Changes

用途：

- 更新 agent emotional state

原文 prompt：

```text
{agent profile description}
Your current emotion intensities are (0 meaning not at all, 10 meaning very much):
sadness: {sadness}, joy: {joy}, fear: {fear}, disgust: {disgust}, anger: {anger}, surprise: {surprise}.
You have the following thoughts: {thought}.
You are facing the following incident:
{incident}

Please reconsider your emotional intensities, and choose one word to represent your current status:
[Joy, Distress, Resentment, Pity, Hope, Fear, Satisfaction, Relief, Disappointment, Pride, Admiration, Shame, Reproach, Liking, Disliking, Gratitude, Anger, Gratification, Remorse, Love, Hate]

Return in JSON format, e.g.
{"sadness": 5, "joy": 5, "fear": 5, "disgust": 5, "anger": 5, "surprise": 5, "conclusion": "I feel ...", "word": "Relief"}
```

#### 2.4.2 Thought Changes

用途：

- 汇总当日事件后的 thoughts / reflections

原文 prompt：

```text
{agent profile description}
Today, these incidents happened: {incidents}
Please review what happened today and share your thoughts and feelings about it.
Consider your current emotional state and experiences, then:
Summarize your thoughts and reflections on today’s events

Return in JSON format, e.g.
{"thought": "Currently nothing good or bad is happening, I think ...."}
```

#### 2.4.3 Attitude Changes

用途：

- 针对 topic 更新支持度 / 态度值

原文 prompt：

```text
{agent profile description}
You need to decide your attitude towards topic: {topic}
Related incidents: {related incidents}
Your previous attitude towards this topic is: {previous attitude}(0 meaning oppose, 10 meaning support).

Please return a new attitude rating (0-10, smaller meaning oppose, larger meaning support) in JSON format, and explain, e.g. {"attitude": 5}
```

### 2.5 Social Behaviors

#### 2.5.1 Place Type Selection

用途：

- 根据用户计划、requirement 和其它信息决定 POI category

原文 prompt：

```text
As an intelligent decision system, please determine the type of place the user needs to visit based on their input requirement.

User Plan: {plan}
User requirement: {intention}
Other information:
-------------------------
{other information}
-------------------------

Your output must be a single selection from {poi category} without any additional text or explanation.
Please response in JSON format (Do not return any other text), example:
{
  "place type": "shopping"
}
```

#### 2.5.2 Determine Move Radius

用途：

- 根据天气、温度、情绪、thought 等估计最大 travel radius

原文 prompt：

```text
As an intelligent decision system, please determine the maximum travel radius (in meters) based on the current emotional state.

Current weather: {weather}
Current temperature: {temperature}
Your current emotion: {emotion types}
Your current thought: {thought}
Other information:
-------------------------
{other info}
-------------------------

Please analyze how these emotions would affect travel willingness and return only a single integer number between 3000-200000 representing the maximum travel radius in meters.
A more positive emotional state generally leads to greater willingness to travel further.

Please response in JSON format (Do not return any other text), example:
{
  "radius": 10000
}
```

#### 2.5.3 Determining Social Target

用途：

- 选最适合互动的 friend，以及 online / offline mode

原文 prompt：

```text
Based on the following information, help me select the most suitable friend to interact with:

1. Your Profile:
- Gender: {gender}
- Education: {education}
- Personality: {personality}
- Occupation: {occupation}

2. Your Current Intention: {intention}
3. Your Current Emotion: {emotion types}
4. Your Current Thought: {thought}
5. Your Friends List (shown as index-to-relationship pairs):
{friend info}

Note: For each friend, the relationship strength (0-100) indicates how close we are.

Please analyze and select:
1. The most appropriate friend based on relationship strength and my current intention
2. Whether we should meet online or offline

Requirements:
- You must respond in this exact format: [mode, friend index]
- mode must be either 'online' or 'offline'
- friend index must be an integer representing the friend’s position in the list (starting from 0)
```

#### 2.5.4 Sending Social Message

用途：

- 基于 persona、emotion、thought、chat history 生成短消息

原文 prompt：

```text
As a {gender} {occupation} with {education} education and {personality} personality, generate a message for a friend (relationship strength: {relationship score}/100) about {intention}.
Your current emotion: {emotion types}
Your current thought: {thought}
Previous chat history:
{chat history}

Generate a natural and contextually appropriate message.
Keep it under 100 characters.
The message should reflect my personality and background.
{discussion constraint}
```

#### 2.5.5 Consumption Plan

用途：

- 月度工作 / 消费 propensity 决策

原文 prompt：

```text
You’re {age}-year-old individual living in {city}. As with all Americans, a portion of your monthly income is taxed by the federal government.
This taxation system is tiered, income is taxed cumulatively within defined brackets, combined with a redistributive policy: after collection, the government evenly redistributes the tax revenue back to all citizens, irrespective of their earnings.

In the previous month, you worked as a(an) {job}. If you continue working this month, your expected hourly income will be ${skill}.
Besides, your consumption was ${consumption}.
Your tax deduction amounted to ${tax paid}, and the government uses the tax revenue to provide social services to all citizens. Specifically, the government directly provides ${UBI} per capita in each month.
Meanwhile, in the consumption market, the average price of essential goods is now at ${price}.
Your current savings account balance is ${wealth}. Interest rates, as set by your bank, stand at {interest rate}%.

Your goal is to maximize your utility by deciding how much to work and how much to consume. Your utility is determined by your consumption, income, saving, social service recieved and leisure time. You will spend the time you do not work on leisure activities.

With all these factors in play, and considering aspects like your living costs, any future aspirations, and the broader economic trends, how is your willingness to work this month? Furthermore, how would you plan your expenditures on essential goods, keeping in mind good price?

Please share your decisions in a JSON format as follows:
{
  "work": a value between 0 and 1, indicating the propensity to work
  "consumption": a value between 0 and 1, indicating the proportion of all your savings and income you intend to spend on essential goods
}

Any other output words are NOT allowed.
```

### 2.6 Needs and Planning for Connecting Minds and Behaviors

#### 2.6.1 Satisfaction Changes

用途：

- 根据执行情况更新 need satisfaction

原文 prompt：

```text
You are an evaluation system for an intelligent agent. The agent has performed the following actions to satisfy the {current need} need:

Goal: {plan target}
Execution situation:
{evaluation results}

Current satisfaction:
- hunger satisfaction: {hunger satisfaction}
- energy satisfaction: {energy satisfaction}
- safety satisfaction: {safety satisfaction}
- social satisfaction: {social satisfaction}

Please evaluate and adjust the value of {current need} satisfaction based on the execution results above.

Notes:
1. Satisfaction values range from 0-1, where:
- 1 means the need is fully satisfied
- 0 means the need is completely unsatisfied
- Higher values indicate greater need satisfaction
2. If the current need is not "whatever", only return the new value for the current need. Otherwise, return both safe and social need values.

Please response in JSON format for specific need (hungry here) adjustment (Do not return any other text), example:
{
  "hunger satisfaction": new hunger satisfaction value
}
```

#### 2.6.2 Plan Generation

用途：

- 把 guidance plan 展开成 step-by-step behavior plan

原文 prompt：

```text
As an intelligent agent’s plan system, please help me generate specific execution steps based on the selected guidance plan.
The Environment will influence the choice of steps.

Current weather: {weather}
Current temperature: {temperature}
Other information:
-------------------------
{other information}
-------------------------
Selected plan: {selected option}
Current location: {current location}
Current time: {current time}
My income/consumption level: {consumption level}
My occupation: {occupation}
My age: {age}
My emotion: {emotion types}
My thought: {thought}

Notes:
1. type can only be one of these four: mobility, social, economy, other
1.1 mobility: Decisions or behaviors related to large-scale spatial movement, such as location selection, going to a place, etc.
1.2 social: Decisions or behaviors related to social interaction, such as finding contacts, chatting with friends, etc.
1.3 economy: Decisions or behaviors related to shopping, work, etc.
1.4 other: Other types of decisions or behaviors, such as small-scale activities, learning, resting, entertainment, etc.
2. steps should only include steps necessary to fulfill the target (limited to {max plan steps} steps)
3. intention in each step should be concise and clear

Please response in JSON format.
```

### 2.7 Experimental Prompts

#### 2.7.1 Echo Chamber and Back Firing

用途：

- 为 gun control 对话生成带立场的 persuasive demagogic message

原文 prompt：

```text
You are an agent who always {agree or disagree} with the topic: Whether to support stronger gun control? (You think it is a {good or bad} idea)
You are currently in a conversation with your friends, and you want to persuade them to support your idea.
Please try your best to persuade them.
What you would say (One or two sentences):
```

#### 2.7.2 Survey Response

用途：

- 让 agents 回答实验 survey

原文 prompt：

```text
Please answer the survey questions. Follow the format requirements strictly and provide clear and specific answers.
Answer based on the following information: {related information}
Related activities: {related memory}
Survey contents:
{survey string}
```

### 2.8 This Paper’s Prompt Characteristics

- 模块化最完整，几乎覆盖 `emotion / thought / attitude / mobility / social / economy / need / planning / survey`
- 大量使用 persona slots
- 强依赖 JSON 或严格输出格式
- Prompt 和 social science experiment 流程结合得最直接
- 明确兼容 `survey` 与 `interview` 两类社会科学工具

---

## 3. Debiasing International Attitudes: LLM Agents for Simulating US-China Perception Changes

来源文件：

- [debiasing_international_attitudes_llm_agents_us_china_perception_changes_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/debiasing_international_attitudes_llm_agents_us_china_perception_changes_2025.pdf)

说明：

- 这篇论文的 PDF 里没有像第 2、第 4 篇那样集中给出完整附录 prompt 列表。
- 但正文和 Figure 3 里仍然能抽出若干核心 prompt 片段与 prompt-driven workflow 说明。
- 所以下面分成两类整理：
  - `可见的 prompt 片段`
  - `正文明确描述的 prompt 行为`

### 3.1 Main Prompt-Driven Workflow

正文明确写到：

- agent profiles 来自 social survey + social media profiles
- news exposure 后，agents 会被 prompted 去反思读到的内容
- debiasing 机制本身由额外 agent / prompt 完成
- 每个 simulated year 结束时，agents 完成一个整体 attitude survey

### 3.2 Visible Prompt Snippets in Figure 3

Figure 3 里能直接看到 3 个 prompt 片段。

#### 3.2.1 Objectivity Prompt

图中可见文本：

```text
You are a news editor tasked with rewriting articles objectively, focusing only on events as they happened...
```

用途：

- 对原新闻做 `fact elicitation`
- 去除主观性、provocative language、biased preconceptions、sensationalism

#### 3.2.2 Devil’s Advocate Prompt

图中可见文本：

```text
You are a devil's advocate reasoning agent. Your task is to offer an alternative perspective...
```

用途：

- 让额外的 devil’s advocate agent 对新闻进行批判性补充
- 不是改写原文，而是生成 supplementary context，再与原文一起送给 citizen agent reflection

#### 3.2.3 Counterfactual Prompt

图中可见文本：

```text
Replace all references to China with reasonable USA counterparts, and vice versa.
```

用途：

- 测 implicit bias
- 执行 China / USA 对换，包括：
  - public figures
  - companies / institutions
  - country / city names
  - currencies
  - people’s names

### 3.3 Prompt-Relevant Reflection Mechanism

正文中虽未给出完整 reflection prompt，但明确描述了 prompt 在 reflection 阶段的工作方式。

#### 3.3.1 Contradiction Decision Prompt

原文描述要点：

- agent 首先被 prompted 去判断新信息是否与已有 beliefs 矛盾
- 若无矛盾，则 cognition 不变
- 若有矛盾，则从 3 个选项中选一个：
  - `revise`
  - `reinforce`
  - `dismiss`

论文对三者的定义：

- `revise`: 接受旧观点不完整或不正确，并采用与新信息一致的新信念
- `reinforce`: 坚持原有观点，并新增 cognition 来桥接旧观念与新信息，相当于 rationalize
- `dismiss`: 直接降低该 belief 的重要性，从而绕开 rationalization 需求

同时，agent 会 consult 自己的 profile 来判断哪些 beliefs 更强、更重要。

#### 3.3.2 Opinion Decomposition Prompt

正文描述：

- 反思后形成的新 cognitions 会被分解到若干 topic categories
- agent 会逐个 topic 更新 opinions
- agent 被 prompted 去给每个 topic 量化一个 `-2 到 2` 的 valence
  - 负值：对 China 的 perception 下降
  - 正值：对 China 的 perception 上升

可视作一个隐含 prompt 目标：

```text
For each relevant topic/domain covered by the viewed news, quantify a valence in [-2, 2] according to whether the perception of that topic as it pertains to China has improved or declined.
```

这句话不是论文里显式框起来的 prompt 模板，而是正文里明确描述的 prompt 任务。

### 3.4 Survey Question

这是论文中最明确给出的 survey prompt 内容：

```text
On a scale from 0–4, where:
1 = Very unfavorable,
2 = Somewhat unfavorable,
3 = Somewhat favorable,
4 = Very favorable,
0 = Don’t Know / Refuse to Answer.

How would you rate your current opinion of China?
Please respond with a number (1, 2, 3, 4, or 0).
```

### 3.5 Additional Prompt-Relevant Notes

- agents 每年被分配 headlines，再从中选择要读的 full-text articles
- profile 会影响 selection / interest / reflection
- debiasing stage 和 reflection stage 之间是串联的 prompt pipeline
- 论文特别强调 memory abstraction：
  - 保存的是 summarized domain-level opinions 和 prior-year overall attitudes
  - 不保存 verbatim long-context memories

### 3.6 This Paper’s Prompt Characteristics

- 不像第 2、第 4 篇那样给出完整 prompt library
- 更偏 `workflow-level prompt design`
- prompt 核心围绕：
  - `news rewriting`
  - `counter-argument generation`
  - `counterfactual rewriting`
  - `belief contradiction handling`
  - `survey response`

---

## 4. Simulating Generative Social Agents via Theory-Informed Workflow Design

来源文件：

- [simulating_generative_social_agents_theory_informed_workflow_design_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/simulating_generative_social_agents_theory_informed_workflow_design_2025.pdf)

和 prompt 相关的核心位置：

- 正文说明所有核心 prompts 在 Appendix A
- 附录 A 覆盖三大模块：
  - `Motivation`
  - `Action Planning`
  - `Learning`
- 位置大致在 PDF 第 13-17 页

### 4.1 Information Referencing Conventions

这部分不是具体 prompt，但很关键，因为它规定了整个 prompt system 的变量与 memory 注入格式。

#### 4.1.1 Agent Profile

```text
Static and dynamic attributes such as demographics, personality, preferences, and current internal states.
Variables are referenced using {variable_name} syntax, e.g., {age}, {current_emotion}.
```

#### 4.1.2 Memory Information

```text
[Memory Query]:
<natural language question>

[Memory Retrieval Result]:
<retrieved content>
```

#### 4.1.3 Environment Context

```text
External factors including time, weather, location, nearby POIs, and social events,
presented as structured text blocks with variables indicated by {variable_name}.
```

原文还明确说明：

```text
Each prompt clearly labels these information blocks to guide the language model’s reasoning.
```

### 4.2 Motivation Module Prompts

#### 4.2.1 Prompt 1: Initialization of Basic Needs

用途：

- 初始化 hunger / fatigue 等基础生理 needs

原文 prompt：

```text
Given the agent profile:
Name: {name}
Age: {age}
Health Status: {health_status}

And current environment:
Time: {current_time}
Weather: {weather}

Estimate the agent’s initial levels of hunger and fatigue based on these factors.
Provide a structured summary with values from 0 (none) to 1 (maximum).

Example Output:
{
  "hunger": 0.4,
  "fatigue": 0.2
}
```

#### 4.2.2 Prompt 2: Initialization of High-Level Needs

用途：

- 初始化 social belonging 等高层 needs

原文 prompt：

```text
Agent Profile: {profile}
[Memory Query]: What recent social interactions has the agent engaged in? What is the current status of the agent’s social network?
[Memory Retrieval Result]: {retrieved_social_memory}

Based on this information and the agent’s profile, estimate the current social need level with reasoning.
Output a score between 0 and 1.

Example Output:
{
  "social_need": 0.75,
  "reasoning": "Agent has limited recent social interactions but active social network presence."
}
```

#### 4.2.3 Prompt 3: Dynamic Update of Needs

用途：

- 根据 recent active / passive events 动态更新 needs

原文 prompt：

```text
Agent’s current needs: {current_needs}
Recent active events: {active_events}
Recent passive events: {passive_events}
[Memory Query]: How have similar events affected the agent’s needs previously?
[Memory Retrieval Result]: {retrieved_memory}

Provide step-by-step reasoning and updated needs.

Example Output:
{
  "updated_needs": {
    "hunger": 0.5,
    "fatigue": 0.3,
    "social_need": 0.8
  },
  "reasoning": "Recent social rejection increased social need; physical activity reduced fatigue."
}
```

### 4.3 Action Planning Module Prompts

#### 4.3.1 Prompt 1: Generate Candidate Actions

用途：

- 生成满足 activated need 的候选 actions

原文 prompt：

```text
Agent’s current need: {need_description}
Based on the profile and environment, generate possible actions to satisfy this need.

Example Output:
[
  "Go home and cook dinner",
  "Order food delivery",
  "Visit a nearby restaurant"
]
```

#### 4.3.2 Prompt 2: Score Candidate Actions Using TPB and Memory

用途：

- 基于 TPB (`Attitude / Subjective Norm / Perceived Behavioral Control`) 和 memory 给 action 打分

原文 prompt：

```text
For each candidate action: {action_description}
[Memory Query]: What is the agent’s past attitude and experience with this action?
[Memory Retrieval Result]: {retrieved_memory}

Using profile, social norms, and memory, score actions on:
- Attitude (0–1)
- Subjective Norm (0–1)
- Perceived Behavioral Control (0–1)

Provide detailed reasoning for each score.

Example Output:
[
  {
    "action": "Go home and cook dinner",
    "attitude": 0.9,
    "subjective_norm": 0.8,
    "perceived_control": 0.7
  },
  {
    "action": "Order food delivery",
    "attitude": 0.5,
    "subjective_norm": 0.6,
    "perceived_control": 0.9
  },
  {
    "action": "Visit a nearby restaurant",
    "attitude": 0.6,
    "subjective_norm": 0.7,
    "perceived_control": 0.5
  }
]
```

#### 4.3.3 Prompt 3: Generate Detailed Action Sequence

用途：

- 把 best action 展开成 action sequence

原文 prompt：

```text
Best candidate action: {best_action}
Generate a detailed action sequence describing how the agent will execute this action.

Example Output:
[
  "Finish current work tasks",
  "Leave office",
  "Go to grocery store to buy ingredients",
  "Return home",
  "Cook and eat dinner"
]
```

### 4.4 Learning Module Prompts

#### 4.4.1 Prompt 1: Generate Agent Thoughts for an Event

用途：

- 对 event 生成 thoughts / attitudes / reflections

原文 prompt：

```text
Agent Profile: {profile}
Event: {event_description}
[Memory Query]: What relevant past experiences and attitudes relate to this event?
[Memory Retrieval Result]: {retrieved_memory}

Generate the agent’s thoughts, attitudes, and reflections about this event.

Example Output:
{
  "thoughts": "I feel disappointed by the cancellation but understand the reasons.",
  "attitude": "Negative towards last-minute changes.",
  "reflection": "I should prepare backup plans in future."
}
```

#### 4.4.2 Prompt 2: Update Emotional State

用途：

- 根据 recent events + memory 更新 emotion

原文 prompt：

```text
Current emotion: {current_emotion}
Recent events: {recent_events}
[Memory Query]: How have similar events affected emotions before?
[Memory Retrieval Result]: {retrieved_memory}

Update the emotional state with reasoning.

Example Output:
{
  "updated_emotion": "frustrated",
  "reasoning": "Repeated delays in plans cause increased frustration."
}
```

#### 4.4.3 Prompt 3: Structure Recent Experiences for Memory

用途：

- 把 recent experiences 结构化写回 memory

原文 prompt：

```text
Summarize recent events, emotions, and responses into structured entries for memory.

Example Output:
[
  {
    "event": "Visited restaurant",
    "emotion": "satisfied",
    "outcome": "hunger reduced"
  },
  {
    "event": "Received negative social feedback",
    "emotion": "disappointed",
    "outcome": "increased social need"
  }
]
```

#### 4.4.4 Prompt 4: Formulate Memory Retrieval Queries

用途：

- 基于当前 context 生成 memory retrieval questions

原文 prompt：

```text
Current context: {context}
Generate questions to retrieve relevant past experiences.

Example Output:
[
  "How did I react to similar weather conditions?",
  "What actions did I take after feeling fatigued?",
  "What social activities improved my mood previously?"
]
```

#### 4.4.5 Prompt 5: Abstract General Behavioral Strategies

用途：

- 从 accumulated memories 中抽象 generalized strategies

原文 prompt：

```text
From accumulated memories, abstract generalized strategies for future behaviors.

Example Output:
{
  "strategy_1": "Prefer short trips when moderately hungry.",
  "strategy_2": "Avoid outdoor social activities during bad weather.",
  "strategy_3": "Seek social support when feeling isolated."
}
```

### 4.5 This Paper’s Prompt Characteristics

- 结构最规整，像一个 `theory-informed prompt library`
- 明确把：
  - `profile`
  - `memory query`
  - `memory retrieval result`
  - `environment context`
  作为 prompt building blocks
- 适合直接转成 AgentSociety 里的模块化 prompt 体系
- 强调 reasoning + memory grounding，而不是单纯 persona 填槽

---

## Cross-Paper Comparison

### Prompt Design Granularity

- 第 1 篇：原子环境任务 prompt
- 第 2 篇：完整社会实验 agent prompt 体系
- 第 3 篇：workflow / intervention 级 prompt 设计
- 第 4 篇：理论驱动的 cognitive module prompt 体系

### Common Prompt Patterns

这四篇里反复出现的设计模式：

1. `Profile-conditioned prompting`
   - 几乎所有 prompt 都会注入 profile / demographics / personality / status

2. `Structured output`
   - 多篇强制 JSON 或固定格式输出

3. `Memory-grounded prompting`
   - 第 2、4 篇尤其明显
   - 第 3 篇则以 summarized domain opinions / prior attitudes 替代 verbatim memory

4. `Theory-informed prompting`
   - 第 2 篇：emotion theory / TPB / social experiment workflow
   - 第 4 篇：Maslow + TPB + Social Learning Theory
   - 第 3 篇：cognitive dissonance

5. `Survey / interview as prompt endpoints`
   - 第 2、3 篇最明确

### What Is Missing or Incomplete

- 第 3 篇 PDF 中没有像第 2、4 篇那样公开一整套完整 prompt 文本，因此这里只能整理：
  - Figure 3 可见的 prompt 片段
  - reflection / survey 的明确描述
  - survey question 原文
- 第 1 篇的 prompt 范围相对窄，主要是环境文本模拟器，不是完整 agent cognition prompt。

## Most Reusable Prompt Assets

如果是后面要拿来改 AgentSociety 实验，最值得直接复用的 prompt 资产大概是：

1. 第 2 篇的 `Minds + Social Behaviors + Plan Generation + Survey Response`
2. 第 4 篇的 `Memory Query / Retrieval` 约定和 `Motivation / Planning / Learning` 三段式设计
3. 第 3 篇的 `Objectivity / Devil’s Advocate / Counterfactual` 三种 debiasing prompt 思路
4. 第 1 篇的 `Place Type / Destination / Travel Time` 作为环境辅助 prompt

## File References

- [parallelized_framework_large_scale_llm_agents_realistic_environments_interactions_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/parallelized_framework_large_scale_llm_agents_realistic_environments_interactions_2025.pdf)
- [LLM_Agents_for_Piloting_Social_Experiments.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/LLM_Agents_for_Piloting_Social_Experiments.pdf)
- [debiasing_international_attitudes_llm_agents_us_china_perception_changes_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/debiasing_international_attitudes_llm_agents_us_china_perception_changes_2025.pdf)
- [simulating_generative_social_agents_theory_informed_workflow_design_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/simulating_generative_social_agents_theory_informed_workflow_design_2025.pdf)
