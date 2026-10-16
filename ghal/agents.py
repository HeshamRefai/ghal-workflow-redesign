"""وكلاء نموذج TDF (القسم 4.5) — تفكيك سير العمل إلى:

- TaskAgent: تنفيذ المهام كثيفة المعرفة.
- DecisionAgent: توجيه المسار حسب الحالة والقرار.
- FlowAgent: إدارة تدفق العملية في وقت التشغيل.
- CoordinationAgent: تنسيق العمل والتبعيات بين وكلاء عدة.
- Process Harness: طبقة سياسات حول المحرك الحتمي (انظر runtime.py).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .models import (Decision, DecisionKind, Event, Evidence,
                     ExceptionCase, ProcessState, Step)


class TaskAgent:
    """ينفّذ مهمة كثيفة المعرفة: قراءة، استخراج، تلخيص، تحقق، مطابقة.

    تُسجَّل له «قدرة» (capability) كدالة قابلة للاستدعاء تعمل على
    ProcessState وتعيد نتيجة + أدلة. عند انخفاض ثقته يولّد استثناءاً
    بدلاً من التخمين.
    """

    def __init__(self, name: str = "agent:task",
                 confidence_threshold: float = 0.6):
        self.name = name
        self.confidence_threshold = confidence_threshold
        self.capabilities: dict[str, Callable[[ProcessState, Step],
                                              tuple[Any, float, list[Evidence]]]] = {}

    def register(self, step_name: str, fn) -> None:
        self.capabilities[step_name] = fn

    def can_handle(self, step: Step) -> bool:
        return step.name in self.capabilities

    def execute(self, state: ProcessState, step: Step) -> dict:
        fn = self.capabilities.get(step.name)
        if fn is None:
            exc = ExceptionCase(
                kind="missing_capability",
                description=f"لا قدرة مسجلة لدى {self.name} على «{step.name}»",
                step=step.name, severity=0.6)
            state.open_exceptions.append(exc)
            return {"status": "escalated", "reason": "missing_capability",
                    "exception": exc}
        result, confidence, evidence = fn(state, step)
        state.evidence.extend(evidence)
        if confidence < self.confidence_threshold:
            exc = ExceptionCase(
                kind="low_confidence",
                description=f"ثقة الوكيل {confidence:.2f} دون العتبة "
                            f"في «{step.name}»",
                step=step.name, severity=0.5)
            state.open_exceptions.append(exc)
            return {"status": "escalated", "reason": "low_confidence",
                    "confidence": confidence, "partial": result,
                    "exception": exc}
        state.actions_taken.append(f"{self.name}:{step.name}")
        return {"status": "done", "result": result,
                "confidence": confidence}


class DecisionAgent:
    """يوجّه المسار حسب الحالة والقرار — يقرأ الأدلة المتراكمة ويقرر
    الخطوة التالية أو يطلب تصعيداً (معالجة انفجار الفروع — 5.4)."""

    def __init__(self, name: str = "agent:decision"):
        self.name = name

    def decide_next(self, state: ProcessState,
                    remaining: list[Step]) -> Decision:
        if state.open_exceptions:
            top = max(state.open_exceptions, key=lambda e: e.severity)
            d = Decision(
                subject=f"توجيه بعد استثناء في «{top.step or state.stage}»",
                outcome="escalate",
                kind=DecisionKind.CONTEXTUAL,
                actor=self.name,
                rationale=f"استثناء مفتوح: {top.description}",
                evidence_ids=[e.id for e in state.evidence[-5:]],
                confidence=0.8)
            state.decisions.append(d)
            return d
        if remaining:
            nxt = remaining[0]
            d = Decision(
                subject="الخطوة التالية",
                outcome=nxt.name,
                kind=DecisionKind.DETERMINISTIC,
                actor=self.name,
                rationale="المسار الطبيعي وفق إصدار التصميم الحالي.",
                confidence=0.95)
            state.decisions.append(d)
            return d
        d = Decision(subject="نهاية العملية", outcome="complete",
                     kind=DecisionKind.DETERMINISTIC, actor=self.name,
                     rationale="لا خطوات متبقية.", confidence=1.0)
        state.decisions.append(d)
        return d


class FlowAgent:
    """يدير تدفق العملية في وقت التشغيل: يتتبع الحالة، يحدّث المرحلة،
    ويسجّل أحداث التنفيذ."""

    def __init__(self, name: str = "agent:flow"):
        self.name = name
        self.events: list[Event] = []

    def emit(self, state: ProcessState, step: str, action: str,
             actor: str, **payload) -> Event:
        e = Event(step=step, actor=actor, action=action,
                  case_id=state.case_id, payload=payload)
        self.events.append(e)
        state.stage = step
        return e


class CoordinationAgent:
    """ينسّق بين وكلاء عدة: يوزّع الخطوات على مالكيها ويدير التبعيات
    ويعيد المحاولة والتصعيد عند تعارض الملكية."""

    def __init__(self, name: str = "agent:coordination"):
        self.name = name
        self.registry: dict[str, TaskAgent] = {}

    def register(self, agent: TaskAgent) -> None:
        self.registry[agent.name] = agent

    def executor_for(self, step: Step) -> Optional[TaskAgent]:
        for agent in self.registry.values():
            if agent.can_handle(step):
                return agent
        return None

    def handoff(self, state: ProcessState, step: Step,
                from_actor: str, to_actor: str, reason: str,
                flow: FlowAgent) -> None:
        """بروتوكول التسليم بين الإنسان والوكيل (9.10):
        متى يُسلَّم، ما السياق الواجب إرساله، ما القرار المطلوب،
        وما المهلة والبديل عند عدم الاستجابة، وكيف تُسجَّل النتيجة."""
        flow.emit(state, step.name, "handoff", from_actor,
                  to=to_actor, reason=reason,
                  context={"evidence": [e.id for e in state.evidence[-5:]],
                           "open_exceptions": [x.description
                                               for x in state.open_exceptions],
                           "required_decision": "approve_or_correct",
                           "timeout_min": 60,
                           "fallback": "تصعيد لصاحب العملية"})
        state.current_owner = to_actor
