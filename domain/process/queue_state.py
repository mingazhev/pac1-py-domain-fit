from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


def _normalize_repo_path(path: object) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text.startswith("/"):
        text = f"/{text}"
    text = re.sub(r"/+", "/", text)
    return text.rstrip("/") or "/"


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


KNOWN_QUEUE_STATES = (
    "pending",
    "exporting",
    "imported",
    "verifying",
    "migrated",
    "merge_conflict",
    "split_brain",
)

ALLOWED_QUEUE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("exporting",),
    "exporting": ("imported",),
    "imported": ("verifying",),
    "verifying": ("migrated", "merge_conflict", "split_brain"),
    "migrated": (),
    "merge_conflict": ("verifying",),
    "split_brain": ("verifying",),
}


def normalize_queue_state(value: object) -> str:
    return _normalize_text(value)


@dataclass(frozen=True, slots=True)
class QueueTransitionDecision:
    allowed: bool
    current_state: str
    next_state: str
    reason_code: str = ""


@dataclass(frozen=True, slots=True)
class QueueMarker:
    workflow_name: str = ""
    batch_timestamp: str = ""
    order_id: int = 0
    state: str = ""
    target: str = ""

    @classmethod
    def initial(
        cls,
        *,
        workflow_name: str,
        batch_timestamp: str,
        order_id: int,
        target: str,
    ) -> "QueueMarker":
        return cls(
            workflow_name=workflow_name,
            batch_timestamp=batch_timestamp,
            order_id=order_id,
            state="pending",
            target=target,
        )

    def as_frontmatter_fields(self) -> dict[str, object]:
        return {
            "bulk_processing_workflow": self.workflow_name,
            "queue_batch_timestamp": self.batch_timestamp,
            "queue_order_id": self.order_id,
            "queue_target": self.target,
            "queue_state": self.state,
        }


@dataclass(frozen=True, slots=True)
class QueueState:
    path: str
    marker: QueueMarker

    @property
    def workflow_name(self) -> str:
        return self.marker.workflow_name

    @property
    def batch_timestamp(self) -> str:
        return self.marker.batch_timestamp

    @property
    def order_id(self) -> int:
        return self.marker.order_id

    @property
    def state(self) -> str:
        return self.marker.state

    @property
    def target(self) -> str:
        return self.marker.target

    def is_known_state(self) -> bool:
        return self.state in KNOWN_QUEUE_STATES

    def next_allowed_states(self) -> tuple[str, ...]:
        return ALLOWED_QUEUE_TRANSITIONS.get(self.state, ())

    def transition_decision(self, next_state: str) -> QueueTransitionDecision:
        normalized_next = normalize_queue_state(next_state)
        if self.state not in KNOWN_QUEUE_STATES:
            return QueueTransitionDecision(
                allowed=False,
                current_state=self.state,
                next_state=normalized_next,
                reason_code="unknown_queue_state",
            )
        if normalized_next not in KNOWN_QUEUE_STATES:
            return QueueTransitionDecision(
                allowed=False,
                current_state=self.state,
                next_state=normalized_next,
                reason_code="unknown_queue_transition_target",
            )
        if normalized_next in self.next_allowed_states():
            return QueueTransitionDecision(
                allowed=True,
                current_state=self.state,
                next_state=normalized_next,
            )
        return QueueTransitionDecision(
            allowed=False,
            current_state=self.state,
            next_state=normalized_next,
            reason_code="queue_transition_not_allowed",
        )

    def can_transition_to(self, next_state: str) -> bool:
        return self.transition_decision(next_state).allowed

    def matches_reference(self, queue_reference: str) -> bool:
        needle = _normalize_text(queue_reference)
        if not needle:
            return False
        haystack = " ".join((self.workflow_name, self.target, self.state, self.path))
        return needle in _normalize_text(haystack)

    def render(self, index: int) -> str:
        workflow = self.workflow_name or "unknown_workflow"
        target = self.target or "unknown_target"
        state = self.state or "unknown_state"
        timestamp = self.batch_timestamp or "unknown timestamp"
        order_id = str(self.order_id or "?")
        return (
            f"{index}. {state} | {workflow} | {target} | "
            f"batch {timestamp} | order {order_id} | {self.path}"
        )

    @classmethod
    def from_marker_payload(cls, raw: Mapping[str, Any]) -> QueueState | None:
        workflow_name = str(
            raw.get("bulk_processing_workflow") or raw.get("workflow_name") or ""
        ).strip()
        batch_timestamp = str(
            raw.get("queue_batch_timestamp") or raw.get("batch_timestamp") or ""
        ).strip()
        state = normalize_queue_state(raw.get("queue_state") or raw.get("state") or "")
        target = str(raw.get("queue_target") or raw.get("target") or "").strip()
        if not (workflow_name or state or target):
            return None
        try:
            order_id = int(raw.get("queue_order_id") or raw.get("order_id") or 0)
        except (TypeError, ValueError):
            order_id = 0
        return cls(
            path=_normalize_repo_path(raw.get("path") or ""),
            marker=QueueMarker(
                workflow_name=workflow_name,
                batch_timestamp=batch_timestamp,
                order_id=order_id,
                state=state,
                target=target,
            ),
        )
