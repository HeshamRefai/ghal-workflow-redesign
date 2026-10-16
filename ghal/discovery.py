"""اكتشاف العملية — Process Discovery (إطار A.G.E.N.T / مرحلة A «التدقيق»).

يجمع حالات فعلية حديثة (ناجحة واستثناءات وفشل وحالات نادرة) من سجلات
الأحداث، ويبني خريطة الوضع الحالي As-Is: المشغّل، الأنظمة، التسليمات،
القرارات، الاستثناءات، الضوابط، المخرجات النهائية — ويقيس خط الأساس:
الحجم، زمن الدورة، الزمن النشط، الانتظار، إعادة العمل، الاستثناءات، التكلفة.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import Event, Step, ProcessVersion


@dataclass
class BaselineMetrics:
    """قياسات خط الأساس للوضع الحالي (القسم 12.1)."""
    case_count: int = 0
    cycle_time_min: float = 0.0       # متوسط زمن الدورة الكلي
    active_time_min: float = 0.0      # متوسط الزمن النشط
    wait_time_min: float = 0.0        # متوسط زمن الانتظار
    friction_rate: float = 0.0        # معدل الاحتكاك الكلي
    rework_rate: float = 0.0
    exception_rate: float = 0.0
    first_pass_yield: float = 1.0     # نسبة الحالات المكتملة من المحاولة الأولى
    cost_per_case: float = 0.0
    handoffs: int = 0
    approvals: int = 0
    systems_touched: int = 0

    def as_dict(self) -> dict:
        return {k: round(v, 3) if isinstance(v, float) else v
                for k, v in self.__dict__.items()}


@dataclass
class DiscoveryResult:
    """مخرجات الاكتشاف: وصف موثّق للوضع الحالي + خط الأساس."""
    as_is: ProcessVersion
    baseline: BaselineMetrics
    triggers: list[str] = field(default_factory=list)   # ما الذي يبدأ العملية
    handoffs: list[tuple[str, str]] = field(default_factory=list)
    observed_exceptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ProcessDiscovery:
    """يكتشف العملية من الأحداث الفعلية، لا من الوثائق الرسمية."""

    def __init__(self, hourly_cost: float = 50.0):
        self.hourly_cost = hourly_cost

    # --------------------------------------------------------------
    def from_event_log(self, name: str, events: list[Event]) -> DiscoveryResult:
        """يبني خريطة As-Is من سجل أحداث تنفيذ فعلي."""
        by_case: dict[str, list[Event]] = defaultdict(list)
        for e in sorted(events, key=lambda x: x.timestamp):
            by_case[e.case_id].append(e)

        step_stats: dict[str, dict] = defaultdict(
            lambda: {"active": [], "wait": [], "errors": 0, "reworks": 0,
                     "exceptions": 0, "occurrences": 0, "actors": set(),
                     "systems": set(), "approvals": 0})

        triggers, exceptions_seen, handoffs = set(), [], []
        cycle_times, first_pass = [], 0

        for case_id, evs in by_case.items():
            if evs:
                triggers.add(evs[0].step)
                cycle_times.append(evs[-1].timestamp - evs[0].timestamp)
            reworked_steps = set()
            prev_actor, prev_step, prev_ts = None, None, None
            for e in evs:
                st = step_stats[e.step]
                st["occurrences"] += 1
                st["actors"].add(e.actor)
                st["systems"].update(e.payload.get("systems", []))
                active = float(e.payload.get("active_min", 0.0))
                st["active"].append(active)
                if prev_ts is not None:
                    st["wait"].append(max(0.0, (e.timestamp - prev_ts) / 60.0 - active))
                if prev_actor and prev_actor != e.actor:
                    handoffs.append((prev_step or "?", e.step))
                if e.action == "error":
                    st["errors"] += 1
                if e.action == "exception":
                    st["exceptions"] += 1
                    exceptions_seen.append(e.payload.get("kind", e.step))
                if e.action == "approve":
                    st["approvals"] += 1
                if e.step in reworked_steps:
                    st["reworks"] += 1
                if e.action == "rework":
                    reworked_steps.add(e.step)
                prev_actor, prev_step, prev_ts = e.actor, e.step, e.timestamp
            if not reworked_steps:
                first_pass += 1

        steps: list[Step] = []
        seen_order: list[str] = []
        for e in events:
            if e.step not in seen_order:
                seen_order.append(e.step)
        for sname in seen_order:
            st = step_stats[sname]
            occ = max(st["occurrences"], 1)
            steps.append(Step(
                name=sname,
                active_time_min=sum(st["active"]) / occ,
                wait_time_min=sum(st["wait"]) / max(len(st["wait"]), 1),
                error_rate=st["errors"] / occ,
                rework_rate=st["reworks"] / occ,
                exception_rate=st["exceptions"] / occ,
                requires_approval=st["approvals"] > 0,
                systems=sorted(st["systems"]),
            ))

        n_cases = max(len(by_case), 1)
        total_active = sum(s.active_time_min for s in steps)
        total_wait = sum(s.wait_time_min for s in steps)
        baseline = BaselineMetrics(
            case_count=len(by_case),
            cycle_time_min=sum(cycle_times) / n_cases / 60.0 if cycle_times else 0.0,
            active_time_min=total_active,
            wait_time_min=total_wait,
            friction_rate=(total_wait / total_active * 100.0) if total_active > 0 else 0.0,
            rework_rate=sum(s.rework_rate for s in steps) / max(len(steps), 1),
            exception_rate=sum(s.exception_rate for s in steps) / max(len(steps), 1),
            first_pass_yield=first_pass / n_cases,
            cost_per_case=(total_active + total_wait) / 60.0 * self.hourly_cost,
            handoffs=len(handoffs),
            approvals=sum(1 for s in steps if s.requires_approval),
            systems_touched=len({sys for s in steps for sys in s.systems}),
        )

        return DiscoveryResult(
            as_is=ProcessVersion(name=name, version="as-is", steps=steps),
            baseline=baseline,
            triggers=sorted(triggers),
            handoffs=handoffs,
            observed_exceptions=sorted(set(exceptions_seen)),
            notes=["خريطة مبنية من سجل الأحداث الفعلي، وليست توصيفاً رسمياً."],
        )
