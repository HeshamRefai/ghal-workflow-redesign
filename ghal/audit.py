"""وقت تشغيل التدقيق المستمر — Continuous Audit Runtime (القسم 9.8).

    وقت تشغيل التدقيق = تدفق أحداث + محرك قواعد + اكتشاف شذوذ

يراقب كل حدث ويقارنه بالتصميم وبالسياسات، ويتحقق من:
مطابقة التنفيذ للتصميم، تطبيق السياسة، وجود استثناءات غير مبررة،
ظهور نمط غير طبيعي، واحترام حدود الصلاحية.

المخرجات: تنبيه، درجة امتثال، وسجل قابل للتدقيق.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from statistics import mean, pstdev

from .models import AutonomyLevel, Event, ProcessVersion


@dataclass
class AuditAlert:
    kind: str               # deviation / policy_violation / unauthorized / anomaly
    message: str
    event_id: str = ""
    severity: float = 0.5
    timestamp: float = field(default_factory=time.time)


@dataclass
class AuditReport:
    events_checked: int = 0
    compliant: int = 0
    alerts: list[AuditAlert] = field(default_factory=list)

    @property
    def compliance_score(self) -> float:
        if self.events_checked == 0:
            return 1.0
        return round(self.compliant / self.events_checked, 3)


class ContinuousAuditRuntime:
    """يفحص التنفيذ والأحداث والسياسات باستمرار."""

    def __init__(self, anomaly_z: float = 3.0):
        self.anomaly_z = anomaly_z
        self._active_durations: list[float] = []

    # --------------------------------------------------------------
    def check_event(self, event: Event,
                    design: ProcessVersion,
                    autonomy_bounds: dict[str, AutonomyLevel],
                    approved_steps: set[str] | None = None) -> list[AuditAlert]:
        """يفحص حدثاً واحداً مقابل التصميم والسياسات وحدود الصلاحية."""
        alerts: list[AuditAlert] = []
        step = design.step(event.step)
        approved_steps = approved_steps or set()

        # 1) مطابقة التنفيذ للتصميم — خطوة غير موجودة في التصميم
        if step is None:
            alerts.append(AuditAlert(
                "deviation",
                f"الخطوة «{event.step}» غير موجودة في إصدار التصميم "
                f"{design.version} — انحراف عن التصميم.",
                event_id=event.id, severity=0.8))
            return alerts

        # 2) تطبيق السياسة — موافقة مطلوبة لم تُنفَّذ
        if step.requires_approval and event.action == "execute" \
                and event.step not in approved_steps:
            alerts.append(AuditAlert(
                "policy_violation",
                f"الخطوة «{event.step}» تتطلب موافقة ولم يُسجَّل اعتمادها.",
                event_id=event.id, severity=0.9))

        # 3) حدود الصلاحية — فاعل بشري في خطوة مفوَّضة بالكامل أو العكس
        bound = autonomy_bounds.get(event.step)
        actor_is_agent = event.actor.startswith("agent")
        if bound == AutonomyLevel.FORBIDDEN and actor_is_agent:
            alerts.append(AuditAlert(
                "unauthorized",
                f"وكيل نفّذ خطوة محظورة الاستقلالية «{event.step}».",
                event_id=event.id, severity=1.0))
        if bound in (AutonomyLevel.SUPERVISED,) and actor_is_agent \
                and event.action == "execute" \
                and event.step not in approved_steps:
            alerts.append(AuditAlert(
                "unauthorized",
                f"وكيل نفّذ «{event.step}» في وضع المراقبة دون إشراف موثّق.",
                event_id=event.id, severity=0.85))

        # 4) نمط غير طبيعي — زمن نشط شاذ إحصائياً
        dur = float(event.payload.get("active_min", 0.0))
        if dur > 0:
            if len(self._active_durations) >= 20:
                mu, sd = mean(self._active_durations), \
                    pstdev(self._active_durations) or 1e-6
                if abs(dur - mu) / sd > self.anomaly_z:
                    alerts.append(AuditAlert(
                        "anomaly",
                        f"زمن تنفيذ شاذ في «{event.step}»: "
                        f"{dur:.1f} دقيقة مقابل متوسط {mu:.1f}.",
                        event_id=event.id, severity=0.6))
            self._active_durations.append(dur)

        # 5) استثناء غير مبرر
        if event.action == "exception" and not event.payload.get("justified", True):
            alerts.append(AuditAlert(
                "deviation",
                f"استثناء غير مبرر في «{event.step}».",
                event_id=event.id, severity=0.7))

        return alerts

    # --------------------------------------------------------------
    def check_log(self, events: list[Event], design: ProcessVersion,
                  autonomy_bounds: dict[str, AutonomyLevel],
                  approved_steps: set[str] | None = None) -> AuditReport:
        report = AuditReport()
        for e in events:
            report.events_checked += 1
            alerts = self.check_event(e, design, autonomy_bounds,
                                      approved_steps)
            if alerts:
                report.alerts.extend(alerts)
            else:
                report.compliant += 1
        return report
