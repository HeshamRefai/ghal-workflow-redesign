"""محرك محاكاة العملية — Process Simulation Engine (القسم 9.2).

يسمح باختبار التصميم قبل الإنتاج: حذف موافقة، تغيير حد الاستقلالية،
إضافة وكيل متخصص، تحويل خطوة من إنسان إلى وكيل، تغيير ترتيب الخطوات،
زيادة حجم الحالات، ارتفاع معدل الاستثناءات، تغيير مستوى المخاطر.

المخرجات: زمن الدورة المتوقع، الاختناقات، التكلفة، عدد نقاط التدخل
البشري، معدل الفشل، وحجم الاستثناءات — بمحاكاة مونت كارلو.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .models import ProcessVersion, Step


@dataclass
class Scenario:
    """سيناريو محاكاة — تعديلات على التصميم الأساسي."""
    name: str
    remove_approvals: list[str] = field(default_factory=list)
    delegate_to_agent: list[str] = field(default_factory=list)   # إنسان → وكيل
    add_specialist_agent: Optional[str] = None                   # اسم خطوة
    volume_multiplier: float = 1.0
    exception_rate_delta: float = 0.0
    risk_delta: float = 0.0
    autonomy_trust: float = 0.7          # ثقة مفترضة للاستقلالية


@dataclass
class SimulationResult:
    scenario: str
    runs: int
    expected_cycle_time_min: float
    p95_cycle_time_min: float
    expected_cost_per_case: float
    bottleneck: str
    human_touchpoints: float
    failure_rate: float
    exception_volume: float
    vs_baseline_cycle: float = 0.0       # نسبة التغيّر مقابل خط الأساس
    vs_baseline_cost: float = 0.0


class ProcessSimulationEngine:
    """يحاكي التصميم قبل الإنتاج ويقارن السيناريوهات."""

    def __init__(self, hourly_cost: float = 50.0,
                 agent_speed_factor: float = 0.1,
                 agent_wait_factor: float = 0.0,
                 seed: int = 42):
        self.hourly_cost = hourly_cost
        self.agent_speed_factor = agent_speed_factor   # الوكيل أسرع ~10×
        self.agent_wait_factor = agent_wait_factor     # بلا طوابير بشرية
        self.seed = seed

    # --------------------------------------------------------------
    def _apply(self, process: ProcessVersion, sc: Scenario) -> list[Step]:
        steps: list[Step] = []
        for s in process.steps:
            cp = Step(**{**s.__dict__})
            if cp.name in sc.remove_approvals:
                cp.requires_approval = False
                cp.wait_time_min *= 0.2
            if cp.name in sc.delegate_to_agent or \
                    (cp.owner or "").startswith("agent"):
                cp.active_time_min *= self.agent_speed_factor
                cp.wait_time_min *= self.agent_wait_factor
            if sc.add_specialist_agent and cp.name == sc.add_specialist_agent:
                cp.active_time_min *= 0.5
                cp.error_rate *= 0.5
            cp.exception_rate = max(0.0, min(1.0,
                                             cp.exception_rate + sc.exception_rate_delta))
            cp.risk_score = max(0.0, min(1.0, cp.risk_score + sc.risk_delta))
            steps.append(cp)
        return steps

    # --------------------------------------------------------------
    def simulate(self, process: ProcessVersion, scenario: Scenario,
                 runs: int = 1000) -> SimulationResult:
        rng = random.Random(self.seed)
        steps = self._apply(process, scenario)
        cycles, costs, human_touches, failures, exceptions = [], [], 0, 0, 0.0
        wait_by_step: dict[str, float] = {s.name: 0.0 for s in steps}

        for _ in range(runs):
            cycle = 0.0
            for s in steps:
                exc = rng.random() < s.exception_rate
                fail = rng.random() < s.error_rate
                active = max(0.1, rng.gauss(s.active_time_min,
                                            max(s.active_time_min * 0.2, 0.05)))
                wait = max(0.0, rng.gauss(s.wait_time_min,
                                          max(s.wait_time_min * 0.3, 0.01)))
                wait_by_step[s.name] += wait
                if s.requires_approval or (s.owner or "").startswith("human"):
                    human_touches += 1
                if exc:
                    exceptions += 1
                    cycle += active * 2.0 + wait       # معالجة الاستثناء تضيف وقتاً
                if fail:
                    failures += 1
                    cycle += active                    # إعادة العمل
                cycle += active + wait
            cycles.append(cycle)
            costs.append(cycle / 60.0 * self.hourly_cost)

        cycles.sort()
        n = max(runs, 1)
        total_step_events = n * max(len(steps), 1)
        bottleneck = max(wait_by_step, key=wait_by_step.get) if wait_by_step else ""
        return SimulationResult(
            scenario=scenario.name, runs=runs,
            expected_cycle_time_min=round(sum(cycles) / n, 2),
            p95_cycle_time_min=round(cycles[int(0.95 * (n - 1))], 2),
            expected_cost_per_case=round(sum(costs) / n, 2),
            bottleneck=bottleneck,
            human_touchpoints=round(human_touches / n, 2),
            failure_rate=round(failures / total_step_events, 4),
            exception_volume=round(exceptions / n * scenario.volume_multiplier, 2),
        )

    # --------------------------------------------------------------
    def compare(self, process: ProcessVersion,
                scenarios: list[Scenario],
                runs: int = 1000) -> list[SimulationResult]:
        """يقارن عدة سيناريوهات مع خط أساس (السيناريو الأول بلا تعديل)."""
        results = [self.simulate(process, sc, runs) for sc in scenarios]
        if results:
            base_cycle = results[0].expected_cycle_time_min or 1.0
            base_cost = results[0].expected_cost_per_case or 1.0
            for r in results[1:]:
                r.vs_baseline_cycle = round(
                    (r.expected_cycle_time_min - base_cycle) / base_cycle, 3)
                r.vs_baseline_cost = round(
                    (r.expected_cost_per_case - base_cost) / base_cost, 3)
        return results
