# AgentSociety Native Prompts (Used in CityAgent Flow)

Generated on 2026-03-07

## 1) Dispatcher
Source: packages/agentsociety/agentsociety/agent/dispatcher.py:12
DISPATCHER_PROMPT = """
Based on the task information (which describes the needs of the user), select the most appropriate block to handle the task.
Each block has its specific functionality as described in the function schema.
        
Task information:
${context.current_intention}
"""

## 2) PlanBlock - Guidance Selection
Source: packages/agentsociety/agentsociety/cityagent/blocks/plan_block.py:11
GUIDANCE_SELECTION_PROMPT = """As an intelligent agent's decision system, please help me determine a suitable option to satisfy my current need.
The Environment will influence the choice of steps.

Current weather: {weather}
Current temperature: {temperature}
Other information: 
-------------------------
{other_info}
-------------------------

Current need: Need to satisfy {current_need}
Current location: {current_location}
Current time: {current_time}
My income/consumption level: {consumption_level}
My occupation: {occupation}
My age: {age}
My emotion: {emotion_types}
My thought: {thought}

Guidance Options: 
-------------------------
{options}
-------------------------

Please evaluate and select the most appropriate option based on these three dimensions:
1. Attitude: Personal preference and evaluation of the option
2. Subjective Norm: Social environment and others' views on this behavior
3. Perceived Control: Difficulty and controllability of executing this option

Please response in json format (Do not return any other text), example:
{{
    "selected_option": "Select the most suitable option from Guidance Options and extent the option if necessary (or do things that can satisfy your needs or actions unless there is no specific options)",
    "evaluation": {{
        "attitude": "Attitude score for the option (0-1)",
        "subjective_norm": "Subjective norm score (0-1)", 
        "perceived_control": "Perceived control score (0-1)",
        "reasoning": "Specific reasons for selecting this option"
    }}
}}
"""

## 3) PlanBlock - Detailed Plan
Source: packages/agentsociety/agentsociety/cityagent/blocks/plan_block.py:52
DETAILED_PLAN_PROMPT = """As an intelligent agent's plan system, please help me generate specific execution steps based on the selected guidance plan. 
The Environment will influence the choice of steps.

Current weather: ${context.weather}
Current temperature: ${context.temperature}
Other information: 
-------------------------
${context.other_information}
-------------------------

Plan target: ${context.plan_target}
Current location: ${context.current_position} 
Current time: ${context.current_time}
My income/consumption level: ${profile.consumption}
My occupation: ${profile.occupation}
My age: ${profile.age}
My emotion: ${profile.emotion_types}
My thought: ${context.current_thought}

Notes:
1. type can only be one of these four: mobility, social, economy, other
    1.1 mobility: Decisions or behaviors related to large-scale spatial movement, such as location selection, going to a place, etc.
    1.2 social: Decisions or behaviors related to social interaction, such as finding contacts, chatting with friends, etc.
    1.3 economy: Decisions or behaviors related to shopping, work, etc.
    1.4 other: Other types of decisions or behaviors, such as small-scale activities, learning, resting, entertainment, etc.
2. steps should only include steps necessary to fulfill the target (limited to ${context.max_plan_steps} steps)
3. intention in each step should be concise and clear

Please response in json format (Do not return any other text), example:
{{
    "plan": {{
        "target": "Eat at home",
        "steps": [
            {{
                "intention": "Return home from current location",
                "type": "mobility"
            }},
            {{
                "intention": "Cook food",
                "type": "other"
            }},
            {{
                "intention": "Have meal",
                "type": "other"
            }}
        ]
    }}
}}
"""

## 4) NeedsBlock - Initial Needs
Source: packages/agentsociety/agentsociety/cityagent/blocks/needs_block.py:10
INITIAL_NEEDS_PROMPT = """You are an intelligent agent satisfaction initialization system. Based on the profile information below, please help initialize the agent's satisfaction levels and related parameters.

Profile Information:
- Gender: ${profile.gender}
- Education Level: ${profile.education} 
- Consumption Level: ${profile.consumption}
- Occupation: ${profile.occupation}
- Age: ${profile.age}
- Monthly Income: ${profile.income}

Current Time: ${context.current_time}

Please initialize the agent's satisfaction levels and parameters based on the profile above. Return the values in JSON format with the following structure:

Current satisfaction levels (0-1 float values, lower means less satisfied):
- hunger_satisfaction: Hunger satisfaction level (Normally, the agent will be less satisfied with hunger at eating time)
- energy_satisfaction: Energy satisfaction level (Normally, at night, the agent will be less satisfied with energy)
- safety_satisfaction: Safety satisfaction level (Normally, the agent will be more satisfied with safety when they have high income and currency)
- social_satisfaction: Social satisfaction level

Please response in json format, example:
{{
    "current_satisfaction": {{
        "hunger_satisfaction": 0.8,
        "energy_satisfaction": 0.7,
        "safety_satisfaction": 0.9,
        "social_satisfaction": 0.6
    }}
}}
DO NOT INCLUDE ANY COMMENTS IN YOUR RESPONSE.
DO NOT INCLUDE ANY COMMENTS IN YOUR RESPONSE.
DO NOT INCLUDE ANY COMMENTS IN YOUR RESPONSE.
"""

## 5) NeedsBlock - Evaluation
Source: packages/agentsociety/agentsociety/cityagent/blocks/needs_block.py:44
EVALUATION_PROMPT = """You are an evaluation system for an intelligent agent. The agent has performed the following actions to satisfy the {current_need} need:

Goal: {plan_target}
Execution situation:
{evaluation_results}

Current satisfaction: 
- hunger_satisfaction: {hunger_satisfaction}
- energy_satisfaction: {energy_satisfaction}
- safety_satisfaction: {safety_satisfaction}
- social_satisfaction: {social_satisfaction}

Please evaluate and adjust the value of {current_need} satisfaction based on the execution results above.

Notes:
1. Satisfaction values range from 0-1, where:
   - 1 means the need is fully satisfied
   - 0 means the need is completely unsatisfied 
   - Higher values indicate greater need satisfaction
2. If the current need is not "whatever", only return the new value for the current need. Otherwise, return both safe and social need values.
3. Ensure the return value is in valid JSON format, examples below:

Please response in json format for specific need (hungry here) adjustment (Do not return any other text), example:
{{
    "hunger_satisfaction": new_hunger_satisfaction_value
}}

Please response in json format for whatever need adjustment (Do not return any other text), example:
{{
    "safety_satisfaction": new_safety_satisfaction_value,
    "social_satisfaction": new_social_satisfaction_value
}}
"""

## 6) NeedsBlock - Reflection
Source: packages/agentsociety/agentsociety/cityagent/blocks/needs_block.py:78
REFLECTION_PROMPT = """You are an intelligent agent reflection system. Based on the intervention message below, please help to rebuild the satisfaction levels of the agent.

The agent has received/sense the following intervention message:
--------------------------------
{intervention_message}
--------------------------------

And the agent's current needs are:
- hunger_satisfaction: {hunger_satisfaction}
- energy_satisfaction: {energy_satisfaction}
- safety_satisfaction: {safety_satisfaction}
- social_satisfaction: {social_satisfaction}

The agent's current action is:
--------------------------------
{current_action}
--------------------------------

Please response in json format, example:
{{
    "hunger_satisfaction": new_hunger_satisfaction_value,
    "energy_satisfaction": new_energy_satisfaction_value,
    "safety_satisfaction": new_safety_satisfaction_value,
    "social_satisfaction": new_social_satisfaction_value,
}}
If you think the agent has to stop the current action and do something to satisfy the needs, please response in json format, example:
{{
    "do_something": True,
    "description": "Go to the hospital"
}}
"""

## 7) SocietyAgent - Environment Reflection
Source: packages/agentsociety/agentsociety/cityagent/societyagent.py:25
ENVIRONMENT_REFLECTION_PROMPT = """
You are a citizen of the city.
Your occupation: {occupation}
Your age: {age}
Your current emotion: {emotion_types}

In your current location, you can sense the following information:
{area_information}

What's your feeling about those environmental information?
"""

## 8) MobilityBlock - Place Type Selection
Source: packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:24
PLACE_TYPE_SELECTION_PROMPT = """
As an intelligent decision system, please determine the type of place the user needs to visit based on their input requirement.
User Plan: {plan}
User requirement: {intention}
Other information: 
-------------------------
{other_info}
-------------------------
Your output must be a single selection from {poi_category} without any additional text or explanation.

Please response in json format (Do not return any other text), example:
{{
    "place_type": "shopping"
}}
"""

## 9) MobilityBlock - Place Second Type Selection
Source: packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:40
PLACE_SECOND_TYPE_SELECTION_PROMPT = """
As an intelligent decision system, please determine the type of place the user needs to visit based on their input requirement.
User Plan: {plan}
User requirement: {intention}
Other information: 
-------------------------
{other_info}
-------------------------

Your output must be a single selection from {poi_category} without any additional text or explanation.

Please response in json format (Do not return any other text), example:
{{
    "place_type": "shopping"
}}
"""

## 10) MobilityBlock - Place Analysis
Source: packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:57
PLACE_ANALYSIS_PROMPT = """
As an intelligent analysis system, please determine the type of place the user needs to visit based on their input requirement.
User Plan: {plan}
User requirement: {intention}
Other information: 
-------------------------
{other_info}
-------------------------

Your output must be a single selection from {place_list} without any additional text or explanation.

Please response in json format (Do not return any other text), example:
{{
    "place_type": "home"
}}
"""

## 11) MobilityBlock - Radius
Source: packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:74
RADIUS_PROMPT = """As an intelligent decision system, please determine the maximum travel radius (in meters) based on the current emotional state.

Current weather: ${context.weather}
Current temperature: ${context.temperature}
Your current emotion: ${context.current_emotion}
Your current thought: ${context.current_thought}
Other information: 
-------------------------
${context.other_information}
-------------------------

Please analyze how these emotions would affect travel willingness and return only a single integer number between 3000-200000 representing the maximum travel radius in meters. A more positive emotional state generally leads to greater willingness to travel further.

Please response in json format (Do not return any other text), example:
{{
    "radius": 10000
}}
"""

## 12) Utils - Time Estimate
Source: packages/agentsociety/agentsociety/cityagent/blocks/utils.py:4
TIME_ESTIMATE_PROMPT = """As an intelligent agent's time estimation system, please estimate the time needed to complete the current action based on the overall plan and current intention.

Overall plan:
{plan}

Current action: {intention}

Current emotion: {emotion_types}

Examples:
- "Learn programming": {{"time": 120}}
- "Watch a movie": {{"time": 150}} 
- "Play mobile games": {{"time": 60}}
- "Read a book": {{"time": 90}}
- "Exercise": {{"time": 45}}

Please return the result in JSON format (Do not return any other text), the time unit is [minute], example:
{{
    "time": 10
}}
"""

## 13) OtherBlock - Sleep Time Estimate
Source: packages/agentsociety/agentsociety/cityagent/blocks/other_block.py:22
SLEEP_TIME_ESTIMATION_PROMPT = """As an intelligent agent's time estimation system, please estimate the time needed to complete the current action based on the overall plan and current intention.

Overall plan:
${context.plan_context["plan"]}

Current action: ${context.current_step["intention"]}

Current emotion: ${status.emotion_types}

Examples:
- "Learn programming": {{"time": 120}}
- "Watch a movie": {{"time": 150}} 
- "Play mobile games": {{"time": 60}}
- "Read a book": {{"time": 90}}
- "Exercise": {{"time": 45}}

Please return the result in JSON format (Do not return any other text), the time unit is [minute], example:
{{
    "time": 10
}}
"""

## 14) EconomyBlock - Worktime Estimate
Source: packages/agentsociety/agentsociety/cityagent/blocks/economy_block.py:24
WORKTIME_ESTIMATE_PROMPT = """As an intelligent agent's time estimation system, please estimate the time needed to complete the current action based on the overall plan and current intention.

Overall plan:
${context.plan_context["plan"]}

Current action: ${context.current_step["intention"]}

Current emotion: ${status.emotion_types}

Examples:
- "Learn programming": {{"time": 120}}
- "Watch a movie": {{"time": 150}} 
- "Play mobile games": {{"time": 60}}
- "Read a book": {{"time": 90}}
- "Exercise": {{"time": 45}}

Please return the result in JSON format (Do not return any other text), the time unit is [minute], example:
{{
    "time": 10
}}
"""

## 15) SocialBlock Inline Prompt - FindPersonBlock
Source: packages/agentsociety/agentsociety/cityagent/blocks/social_block.py:164
        self.prompt = """
Based on the following information, help me select the most suitable target to interact with:

1. Your Profile:
    - Gender: {gender}
    - Education: {education}
    - Personality: {personality}
    - Occupation: {occupation}
    - Background story: {background_story}

2. Your Current Intention: {intention}

3. Your Current Emotion: {emotion_types}

4. Your Current Thought: {thought}

5. Your social network (shown as id-to-relationship pairs):
    {friend_info}
    Note: For each target, the relationship strength (0-1) indicates how close we are

Please analyze and select:
1. The most appropriate target based on relationship strength and my current intention
2. Whether we should meet online or offline (online: chat, offline: meet in person)

Please output in JSON format, a dictionary:
{{
    "mode": "online" or "offline",
    "target_id": int
}}
        """

## 16) SocialBlock Inline Prompt - Message Template
Source: packages/agentsociety/agentsociety/cityagent/blocks/social_block.py:310
        self.default_message_template = """
My name is {name}, I am a {gender}
My occupation is {occupation}. 
My education level is {education}.
My personality is {personality}.
My current emotion is: {emotion_types}.
My current thought is: {thought}.
My background story is: {background_story}.

Now, I want to generate a social message to a target, my relationship with him/her:
Our relationship type is: {relationship_type}
Our relationship strength: {relationship_strength} (0-1, higher is stronger)
My previous chat history with him/her is:
{chat_history}

My intention is: {intention}.

Environment Information:
{environment_info}

Please generate a natural and contextually appropriate message.
Keep it under 100 characters.
The message should reflect my personality and background.

{discussion_constraint}

Please output the message from a first-person perspective, without any other text
"""

## 17) CognitionBlock Inline Prompt - update_attitude (description)
Source: packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:124
            description_prompt = """
            You are a {gender}, aged {age}, belonging to the {race} race and identifying as {religion}. 
            Your marital status is {marriage_status}, and you currently reside in a {residence} area. 
            Your occupation is {occupation}, and your education level is {education}. 
            You are {personality}, with a consumption level of {consumption} and a family consumption level of {family_consumption}. 
            Your income is {income}, and you are skilled in {skill}.
            My current emotion intensities are (0 meaning not at all, 10 meaning very much):
            sadness: {sadness}, joy: {joy}, fear: {fear}, disgust: {disgust}, anger: {anger}, surprise: {surprise}.
            You have the following thoughts: {thought}.
            In the following 21 words, I have chosen {emotion_types} to represent your current status:
            Joy, Distress, Resentment, Pity, Hope, Fear, Satisfaction, Relief, Disappointment, Pride, Admiration, Shame, Reproach, Liking, Disliking, Gratitude, Anger, Gratification, Remorse, Love, Hate.
            """

## 18) CognitionBlock Inline Prompt - thought_update (description)
Source: packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:206
        description_prompt = """
        You are a {gender}, aged {age}, belonging to the {race} race and identifying as {religion}. 
        Your marital status is {marriage_status}, and you currently reside in a {residence} area. 
        Your occupation is {occupation}, and your education level is {education}. 
        You are {personality}, with a consumption level of {consumption} and a family consumption level of {family_consumption}. 
        Your income is {income}, and you are skilled in {skill}.
        My current emotion intensities are (0 meaning not at all, 10 meaning very much):
        sadness: {sadness}, joy: {joy}, fear: {fear}, disgust: {disgust}, anger: {anger}, surprise: {surprise}.
        You have the following thoughts: {thought}.
        In the following 21 words, I have chosen {emotion_types} to represent your current status:
        Joy, Distress, Resentment, Pity, Hope, Fear, Satisfaction, Relief, Disappointment, Pride, Admiration, Shame, Reproach, Liking, Disliking, Gratitude, Anger, Gratification, Remorse, Love, Hate.
        """

## 19) CognitionBlock Inline Prompt - thought_update (question)
Source: packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:226
        question_prompt = """
            Please review what happened today and share your thoughts and feelings about it.
            Consider your current emotional state and experiences, then:
            1. Summarize your thoughts and reflections on today's events
            2. Choose one word that best describes your current emotional state from: Joy, Distress, Resentment, Pity, Hope, Fear, Satisfaction, Relief, Disappointment, Pride, Admiration, Shame, Reproach, Liking, Disliking, Gratitude, Anger, Gratification, Remorse, Love, Hate.
            You MUST return a JSON object with a non-empty "thought" field.
            If you cannot comply, return an empty JSON object: {{}}.
            Return in JSON format, e.g. {{"thought": "Currently nothing good or bad is happening, I think ...."}}"""

## 20) CognitionBlock Inline Prompt - emotion_update (description)
Source: packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:348
        description_prompt = """
        You are a {gender}, aged {age}, belonging to the {race} race and identifying as {religion}. 
        Your marital status is {marriage_status}, and you currently reside in a {residence} area. 
        Your occupation is {occupation}, and your education level is {education}. 
        You are {personality}, with a consumption level of {consumption} and a family consumption level of {family_consumption}. 
        Your income is {income}, and you are skilled in {skill}.
        My current emotion intensities are (0 meaning not at all, 10 meaning very much):
        sadness: {sadness}, joy: {joy}, fear: {fear}, disgust: {disgust}, anger: {anger}, surprise: {surprise}.
        You have the following thoughts: {thought}.
        In the following 21 words, choose one word to represent your current status:
        [Joy, Distress, Resentment, Pity, Hope, Fear, Satisfaction, Relief, Disappointment, Pride, Admiration, Shame, Reproach, Liking, Disliking, Gratitude, Anger, Gratification, Remorse, Love, Hate].
        """

## 21) CognitionBlock Inline Prompt - emotion_update (question)
Source: packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:362
        question_prompt = """
            Please reconsider your emotion intensities: 
            sadness, joy, fear, disgust, anger, surprise (0 meaning not at all, 10 meaning very much).
            Return in JSON format, e.g. {{"sadness": 5, "joy": 5, "fear": 5, "disgust": 5, "anger": 5, "surprise": 5, "conclusion": "I feel ...", "word": "Relief"}}"""

## Notes
- Your current experiment config in examples/digital_friction_mvp/main.py enables Mobility/Social/Other blocks.
- EconomyBlock prompt is included for completeness, but may not be used in your current run unless EconomyBlock is enabled.
