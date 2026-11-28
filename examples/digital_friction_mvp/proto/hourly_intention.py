"""Persistent opportunities and the single unfinished digital goal of one resident."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from .models import DigitalTask

_TERMINAL = {"completed", "dropped", "expired"}
# Descriptions specify a visible need, without revealing the experiment's difficulty.
_FAMILIES = {
    "account_login_verification": (
        "Sign into your account to access a service.",
        "public_service_context",
    ),
    "navigation_service_location": (
        "Look up where to find a service.",
        "navigation_transport_context",
    ),
    "information_search_judgment": (
        "Find information and decide whether it is reliable.",
        "education_work_context",
    ),
    "profile_form_upload": (
        "Fill in a profile form and upload supporting information.",
        "public_service_context",
    ),
    "service_application_submission": (
        "Submit an application for a service.",
        "public_service_context",
    ),
    "payment_risk_confirmation": (
        "Review a payment before confirming it.",
        "finance_context",
    ),
}
_PUBLIC_FIELDS = (
    "opportunity_id",
    "source",
    "task_family",
    "visible_description",
    "required_channel",
    "offered_at_sim_hour",
    "visible_from_sim_hour",
    "known_deadline_sim_hour",
    "status",
)


def visible_task_description(task: DigitalTask) -> str:
    """Public wording shared by the opportunity menu and the admitted-task probe."""
    return task.visible_description or _FAMILIES[task.task_family][0]


def opportunity_id_for_task(task_id: str) -> str:
    # Scheduled logins are one opportunity per resident and day. The legacy policy
    # may assign it later if another task occupies 09:00. Its arrival tick is not its identity.
    if task_id.startswith("scheduled_login_account_login_verification_"):
        prefix, slot, tick = task_id.rsplit("_", 2)
        if slot.isdigit() and tick.isdigit():
            task_id = prefix
    return "opp-" + sha256(task_id.encode()).hexdigest()[:20]


class IntentionLedger:
    """A seven-day run discovers at most one natural and one scheduled offer per hour.

    Retain identities through the observation window, including closed offers. The
    environment owns each template; only the public projection goes into a prompt.
    """

    def __init__(self, raw_state: dict | None = None):
        self.state = (
            deepcopy(raw_state)
            if raw_state
            else {
                "opportunities": {},
                "goal": None,
                "last_decided_hour": -1,
            }
        )

    @property
    def goal(self) -> dict | None:
        goal = self.state["goal"]
        return goal if goal and goal["status"] not in _TERMINAL else None

    def publish(
        self,
        task: DigitalTask,
        *,
        source: str,
        sim_hour: int,
        required_channel: str | None = None,
        known_deadline_sim_hour: int | None = None,
    ) -> dict:
        if (
            known_deadline_sim_hour is not None
            and type(known_deadline_sim_hour) is not int
        ):
            raise ValueError("A known deadline must be an integer simulation hour")
        oid = opportunity_id_for_task(task.task_id)
        if oid not in self.state["opportunities"]:
            _, default_channel = _FAMILIES[task.task_family]
            self.state["opportunities"][oid] = {
                "opportunity_id": oid,
                "source": source,
                "task_family": task.task_family,
                "visible_description": visible_task_description(task),
                "required_channel": required_channel or default_channel,
                "offered_at_sim_hour": sim_hour,
                "visible_from_sim_hour": sim_hour + int(source == "natural_context"),
                "known_deadline_sim_hour": known_deadline_sim_hour,
                "status": "offered",
                "template": task.to_dict(),
            }
        stored = self.state["opportunities"][oid]
        return {k: stored[k] for k in _PUBLIC_FIELDS}

    def visible(self, sim_hour: int) -> list[dict]:
        return [
            {k: offer[k] for k in _PUBLIC_FIELDS}
            for offer in self.state["opportunities"].values()
            if offer["status"] not in _TERMINAL
            and offer["visible_from_sim_hour"] <= sim_hour
            and (
                offer["known_deadline_sim_hour"] is None
                or sim_hour <= offer["known_deadline_sim_hour"]
            )
        ]

    def expire(self, sim_hour: int) -> list[str]:
        expired = []
        for oid, offer in self.state["opportunities"].items():
            deadline = offer["known_deadline_sim_hour"]
            if offer["status"] in _TERMINAL or deadline is None or sim_hour <= deadline:
                continue
            if self.goal and self.goal["opportunity_id"] == oid:
                self.goal["status"] = "expired"
            offer["status"] = "expired"
            expired.append(oid)
        return expired

    def review_due(self, sim_hour: int) -> bool:
        return (
            self.goal is None
            or self.goal["status"] != "deferred"
            or sim_hour >= self.goal["next_review_at_sim_hour"]
        )

    def _create_goal(self, offer: dict, sim_hour: int) -> dict:
        goal = {
            "goal_id": "goal-" + offer["opportunity_id"],
            "opportunity_id": offer["opportunity_id"],
            "task_family": offer["task_family"],
            "required_channel": offer["required_channel"],
            "visible_description": offer["visible_description"],
            "status": "offered",
            "known_deadline_sim_hour": offer["known_deadline_sim_hour"],
            "created_at_sim_hour": sim_hour,
            "accepted_at_sim_hour": None,
            "next_review_at_sim_hour": None,
            "decision_index": 0,
            "operation_attempt_count": 0,
            "linked_task_id": offer["template"]["task_id"],
            "last_episode_ids": [],
        }
        self.state["goal"] = goal
        return goal

    def restore_pending(
        self,
        task: DigitalTask,
        sim_hour: int,
        episodes: list[dict],
        required_channel: str | None = None,
    ) -> None:
        oid = opportunity_id_for_task(task.task_id)
        if oid in self.state["opportunities"]:
            return
        if self.goal is not None:
            raise ValueError(
                "An untracked pending task conflicts with an existing goal"
            )
        self.publish(
            task,
            source="existing_pending",
            sim_hour=sim_hour,
            required_channel=required_channel,
        )
        offer = self.state["opportunities"][oid]
        goal = self._create_goal(offer, sim_hour)
        recorded = [e for e in episodes if e.get("task_id") == task.task_id]
        goal.update(
            status="needs_review",
            decision_index=max(task.defer_count, len(recorded)),
            operation_attempt_count=sum(
                e.get("outcome_type", e.get("outcome"))
                not in {None, "avoid_without_attempt"}
                for e in recorded
            ),
            last_episode_ids=[e["episode_id"] for e in recorded if e.get("episode_id")],
        )
        offer["status"] = "needs_review"

    def apply(
        self, intent: dict, *, sim_hour: int, max_defer_hours: int = 24
    ) -> DigitalTask | None:
        kind = intent["kind"]
        oid, gid = intent.get("opportunity_id"), intent.get("goal_id")
        if kind in {"habitual_app", "no_app"}:
            if oid or gid:
                raise ValueError("An untargeted activity cannot name a goal")
            return None
        goal = self.goal
        if goal:
            if (
                kind == "engage_goal"
                or gid != goal["goal_id"]
                or oid not in (None, goal["opportunity_id"])
            ):
                raise ValueError("Cannot replace or bypass an unfinished goal")
            if not self.review_due(sim_hour):
                raise ValueError("This goal is deferred until its review hour")
            oid = goal["opportunity_id"]
        elif gid or kind not in {"engage_goal", "defer_goal", "drop_goal"}:
            raise ValueError("This intent needs an unfinished goal")
        if oid not in {o["opportunity_id"] for o in self.visible(sim_hour)}:
            raise ValueError("Unknown or invisible opportunity")
        offer = self.state["opportunities"][oid]
        kind_to_status = {
            "engage_goal": "engaged",
            "continue_goal": "engaged",
            "defer_goal": "deferred",
            "drop_goal": "dropped",
        }
        if kind not in kind_to_status:
            raise ValueError("Unknown goal action")
        next_review = intent.get("next_review_at_sim_hour")
        if kind == "defer_goal":
            deadline = offer.get("known_deadline_sim_hour")
            if (
                type(next_review) is not int
                or not sim_hour < next_review <= sim_hour + max_defer_hours
                or (deadline is not None and next_review > deadline)
            ):
                raise ValueError("Invalid future review hour")
        elif next_review is not None:
            raise ValueError("Only a deferral can schedule a review")
        goal = goal or self._create_goal(offer, sim_hour)
        goal["status"] = offer["status"] = kind_to_status[kind]
        goal["next_review_at_sim_hour"] = next_review
        if goal["status"] != "engaged":
            return None
        if goal["accepted_at_sim_hour"] is None:
            goal["accepted_at_sim_hour"] = sim_hour
        goal["decision_index"] += 1
        return DigitalTask.from_dict(offer["template"])

    def settle(
        self, *, success: bool, operation_started: bool, episode_id: str | None
    ) -> None:
        goal = self.goal
        if not goal or goal["status"] != "engaged":
            raise ValueError(
                "A goal must have entered execution before recording a result"
            )
        goal["operation_attempt_count"] += int(operation_started)
        if episode_id:
            goal["last_episode_ids"] = [*goal["last_episode_ids"], episode_id]
        status = "completed" if success else "needs_review"
        goal["status"] = status
        self.state["opportunities"][goal["opportunity_id"]]["status"] = status

    def schedule_retry(self, review_hour: int, *, sim_hour: int, max_defer_hours: int) -> None:
        """Set a reminder for a settled goal without re-entering it or counting an attempt."""
        goal = self.goal
        if not goal or goal["status"] != "needs_review":
            raise ValueError("Only a settled unfinished goal can schedule a retry")
        self.apply(
            {"kind": "defer_goal", "goal_id": goal["goal_id"], "next_review_at_sim_hour": review_hour},
            sim_hour=sim_hour, max_defer_hours=max_defer_hours,
        )
