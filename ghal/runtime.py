"""حزام العملية — Process Harness (القسمان 2.5 و9).

طبقة وكيلية محكومة بالسياسات تحيط بمحرك عملية حتمي. المحرك الحتمي
يضمن التسلسل والقواعد، وطبقة الحزام تضيف: فهم السياق، استدعاء
الوكلاء المناسبين، تطبيق السياسات، طلب موافقة بشرية عند الحاجة،
تسجيل الأدلة والقرارات، التعامل مع الاستثناءات، وقياس الانحراف بين
التصميم والتنفيذ.

هذا هو وقت التشغيل المنفّذ الذي يربط كل المكونات:
    Autonomy Boundary → Human Attention Router → Task Agents
    → Continuous Audit → Exception Intelligence → Trust → Memory
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .agents import (CoordinationAgent, DecisionAgent, FlowAgent,
                     TaskAgent)
from .attention import HumanAttentionRouter
from .audit import ContinuousAuditRuntime
from .autonomy import AutonomyBoundaryEngine
from .exceptions import ExceptionIntelligenceEngine
from .memory import ProcessMemory
from .models import (AutonomyLevel, Event, ExceptionCase, ProcessState,
                     ProcessVersion, Step)
from .trust import TrustEngine


@dataclass
class CaseResult:
    case_id: str
    status: str                      # completed / completed_with_review / failed
    executed_by_agent: int = 0
    human_reviews: int = 0
    exceptions: int = 0
    events: list[Event] = field(default_factory=list)
    audit_alerts: int = 0
    final_trust: float = 0.0


# نوع دالة الموافقة البشرية: تستقبل (الحالة، الخطوة، سبب التصعيد) وتعيد
# (موافقة؟, ملاحظة)
HumanApprovalFn = Callable[[ProcessState, Step, str], tuple[bool, str]]


class ProcessHarness:
    """التنفيذ المراقَب للعملية المعاد تصميمها."""

    def __init__(self,
                 design: ProcessVersion,
                 task_agent: Optional[TaskAgent] = None,
                 human_approval: Optional[HumanApprovalFn] = None,
                 memory: Optional[ProcessMemory] = None):
        self.design = design
        self.flow = FlowAgent()
        self.decision_agent = DecisionAgent()
        self.coordination = CoordinationAgent()
        self.task_agent = task_agent or TaskAgent()
        self.coordination.register(self.task_agent)
        self.autonomy = AutonomyBoundaryEngine()
        self.attention = HumanAttentionRouter()
        self.audit = ContinuousAuditRuntime()
        self.exceptions = ExceptionIntelligenceEngine()
        self.trust = TrustEngine()
        self.memory = memory or ProcessMemory()
        self.human_approval = human_approval or (lambda s, st, r: (False, "لا معتمِد"))
        self.approved_steps: set[str] = set()

    # --------------------------------------------------------------
    def run_case(self, inputs: dict[str, Any]) -> CaseResult:
        state = ProcessState(process_id=self.design.id, inputs=dict(inputs))
        state.trust_level = self.trust.score(self.task_agent.name)
        result = CaseResult(case_id=state.case_id, status="completed")
        remaining = list(self.design.steps)

        while remaining:
            step = remaining[0]
            novelty = 1.0 if not self.memory.exceptions_for(step.name) else 0.0
            if novelty:
                state.stage = "novel"

            # 1) حدود الاستقلالية: ثقة × مخاطر × سياق × سياسات
            ad = self.autonomy.decide(
                step, state, policies=self.design.policies,
                agent_history=self.trust.score(self.task_agent.name))

            # 2) موجّه الانتباه: هل يحتاج القرار حكماً بشرياً فعلاً؟
            rd = self.attention.route(step, state, novelty=novelty)

            need_human = (
                ad.level in (AutonomyLevel.FORBIDDEN,
                             AutonomyLevel.SUPERVISED,
                             AutonomyLevel.ASSISTED)
                or rd.route == "human"
                or (step.requires_approval
                    and step.name not in self.approved_steps))

            if ad.level == AutonomyLevel.FORBIDDEN:
                self.flow.emit(state, step.name, "blocked",
                               self.task_agent.name, reasons=ad.reasons)
                exc = ExceptionCase(
                    kind="policy_forbidden",
                    description=f"حظرت السياسة تنفيذ «{step.name}»",
                    step=step.name, severity=0.9)
                state.open_exceptions.append(exc)
                result.status = "failed"
                break

            # 3) تصعيد للإنسان مع السياق وسبب التصعيد
            if need_human:
                reason = "; ".join(ad.reasons + rd.reasons)
                self.coordination.handoff(state, step, self.task_agent.name,
                                          "human", reason, self.flow)
                ok, note = self.human_approval(state, step, reason)
                result.human_reviews += 1
                self.flow.emit(state, step.name,
                               "approve" if ok else "reject",
                               "human", note=note)
                if ok:
                    self.approved_steps.add(step.name)
                else:
                    exc = ExceptionCase(
                        kind="human_rejected",
                        description=f"رفض الإنسان «{step.name}»: {note}",
                        step=step.name, severity=0.7)
                    state.open_exceptions.append(exc)
                    result.status = "failed"
                    break

            # 4) تنفيذ الوكيل ضمن الحدود — أو تنفيذ بشري مباشر إذا كانت
            # الخطوة مملوكة للإنسان ولا قدرة للوكيل عليها
            human_owned = (step.owner or "").startswith("human")
            if human_owned and not self.task_agent.can_handle(step):
                self.flow.emit(state, step.name, "execute", "human",
                               active_min=step.active_time_min or 1.0,
                               systems=step.systems)
            else:
                outcome = self.task_agent.execute(state, step)
                active = step.active_time_min * 0.1 or 0.5
                if outcome["status"] == "done":
                    self.flow.emit(state, step.name, "execute",
                                   self.task_agent.name, active_min=active,
                                   confidence=outcome.get("confidence", 1.0),
                                   systems=step.systems)
                    result.executed_by_agent += 1
                    self.trust.update(self.task_agent.name, success=True)
                else:
                    exc = outcome.get("exception") or ExceptionCase(
                        kind="agent_failure",
                        description=outcome.get("reason", "فشل غير معروف"),
                        step=step.name)
                    self.exceptions.ingest(exc)
                    self.flow.emit(state, step.name, "exception",
                                   self.task_agent.name, kind=exc.kind,
                                   justified=False, active_min=active)
                    self.trust.update(self.task_agent.name, success=False,
                                      exception=True)
                    result.exceptions += 1
                    # تصعيد الاستثناء للإنسان
                    ok, note = self.human_approval(state, step, exc.description)
                    result.human_reviews += 1
                    self.flow.emit(state, step.name,
                                   "approve" if ok else "reject",
                                   "human", note=note)
                    if not ok:
                        result.status = "failed"
                        break
                    result.status = "completed_with_review"

            # 5) تسجيل القرار والأدلة في الذاكرة
            last_decision = self.decision_agent.decide_next(state,
                                                            remaining[1:])
            self.memory.store_decision(last_decision)
            remaining = remaining[1:]
            state.trust_level = self.trust.score(self.task_agent.name)

        # 6) تدقيق مستمر على كامل سجل الحالة
        report = self.audit.check_log(self.flow.events, self.design,
                                      self.design.autonomy_bounds,
                                      self.approved_steps)
        for e in self.flow.events:
            self.memory.store_event(e)
        if result.exceptions:
            self.memory.store_lesson(
                topic=self.design.name,
                lesson=f"الحالة {state.case_id}: {result.exceptions} استثناء "
                       f"و {result.human_reviews} مراجعة بشرية.",
                change_result=result.status)

        result.events = list(self.flow.events)
        result.audit_alerts = len(report.alerts)
        result.final_trust = state.trust_level
        return result
