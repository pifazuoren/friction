import uuid
from datetime import datetime

from agentsociety.survey.models import Page, Question, QuestionType, Survey


def _with_recent_window(title: str) -> str:
    return f"请基于最近7天的真实经历作答：{title}"


def tech_acceptance_survey() -> Survey:
    survey_id = uuid.uuid4()
    questions = [
        Question(
            name="tech_acceptance",
            title=_with_recent_window(
                "你对使用手机APP处理日常事务的接受度是多少？（0=完全不接受，100=完全接受）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="trust_in_apps",
            title=_with_recent_window(
                "你对手机APP提供的服务或提示有多信任？（0=完全不信任，100=完全信任）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="avoidance_tendency",
            title=_with_recent_window(
                "遇到复杂数字流程时，你有多倾向于放弃或转向线下处理？（0=完全不倾向，100=非常倾向）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="helpless_control_loss",
            title=_with_recent_window(
                "面对数字流程时，你有多常觉得“我无法掌控这个过程”？（0=从不，100=总是）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="helpless_expect_failure",
            title=_with_recent_window(
                "开始操作前，你有多常预期“这次大概率会失败”？（0=从不，100=总是）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="helpless_effort_futile",
            title=_with_recent_window(
                "你有多常感觉“再努力学习这些APP也没用”？（0=完全不，100=非常强）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="helpless_low_self_efficacy",
            title=_with_recent_window(
                "你有多认同“遇到新数字任务时我通常处理不好”？（0=完全不认同，100=完全认同）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="behavior_delay_online",
            title=_with_recent_window(
                "你有多常因为担心出错而拖延线上办理？（0=从不，100=总是）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="behavior_proxy_reliance",
            title=_with_recent_window(
                "你有多常请家人/朋友代办数字任务？（0=从不，100=总是）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="behavior_offline_switch",
            title=_with_recent_window(
                "你有多常直接放弃线上流程并改线下办理？（0=从不，100=总是）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="digital_self_efficacy",
            title=_with_recent_window(
                "你觉得自己能独立完成常见数字任务吗？（0=完全不能，100=完全能）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="perceived_effective_support",
            title=_with_recent_window(
                "遇到数字问题时，你觉得自己能获得有效帮助吗？（0=完全不能，100=完全能）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="perceived_usefulness",
            title=_with_recent_window(
                "这些数字服务对你的日常生活有多大帮助？（0=完全没帮助，100=非常有帮助）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
        Question(
            name="digital_anxiety",
            title=_with_recent_window(
                "使用数字服务会让我感到紧张或不安吗？（0=完全不会，100=非常强）"
            ),
            type=QuestionType.RATING,
            min_rating=0,
            max_rating=100,
        ),
    ]
    page = Page(name="tech_acceptance", elements=questions)
    return Survey(
        id=survey_id,
        title="技术接受度",
        description="请根据你的真实想法作答",
        pages=[page],
        created_at=datetime.now(),
    )
