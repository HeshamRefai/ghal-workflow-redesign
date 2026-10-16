"""تحليل العملية — Gauge (إطار A.G.E.N.T / مرحلة G «التقييم»).

يحلّل كل خطوة بمحاور: الزمن النشط، الانتظار، معدل الأخطاء، نوع القيمة،
تكلفة إعادة العمل — ويصنّف الخطوات إلى أرباع القيمة/الاحتكاك الأربعة،
ويحدّد ثلاث قوائم: خطوات عالية القيمة، خطوات عالية الاحتكاك،
خطوات منخفضة القيمة — ثم يحلّل الاستثناءات الأكثر شيوعاً ويبني
خريطة حرارة (الأثر المحتمل × سهولة التنفيذ).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .discovery import BaselineMetrics
from .models import ProcessVersion, Step


class FrictionQuadrant(str, Enum):
    PROTECT = "protect"      # عالية القيمة / منخفض الاحتكاك — تُحافَظ وتُحسَّن بحذر
    REDESIGN = "redesign"    # عالية القيمة / عالٍ الاحتكاك — مرشح قوي لإعادة التصميم
    MERGE = "merge"          # منخفضة القيمة / منخفض الاحتكاك — تُوحَّد أو تُلغى
    AUTOMATE = "automate"    # منخفضة القيمة / عالٍ الاحتكاك — مرشح قوي للأتمتة أو الحذف


@dataclass
class StepAssessment:
    step: str
    quadrant: FrictionQuadrant
    friction_rate: float
    value_score: float
    annual_savings: float       # التوفير السنوي المقدّر إن عولجت
    recommendation: str


@dataclass
class ExceptionInsight:
    kind: str
    frequency: float
    cost: float
    candidate_path: str         # مسار بديل مقترح أو معالجة وكيل
    root_cause_hint: str


@dataclass
class AnalysisResult:
    assessments: list[StepAssessment] = field(default_factory=list)
    high_value: list[str] = field(default_factory=list)
    high_friction: list[str] = field(default_factory=list)
    low_value: list[str] = field(default_factory=list)
    bottleneck: str = ""
    exception_insights: list[ExceptionInsight] = field(default_factory=list)
    heatmap: list[tuple[str, float, float]] = field(default_factory=list)  # (خطوة، أثر، سهولة)
    priority_steps: list[str] = field(default_factory=list)  # خطوة أو خطوتان ذواتا أولوية
    total_annual_savings: float = 0.0


class ProcessAnalyzer:
    """محرك التقييم — لا يبدأ بإضافة الذكاء الاصطناعي بل بتحليل الوقت."""

    def __init__(self, cases_per_year: int = 12000, hourly_cost: float = 50.0,
                 value_threshold: float = 0.5, friction_threshold: float = 100.0):
        self.cases_per_year = cases_per_year
        self.hourly_cost = hourly_cost
        self.value_threshold = value_threshold
        self.friction_threshold = friction_threshold

    # --------------------------------------------------------------
    def annual_savings(self, step: Step) -> float:
        """التوفير السنوي =
        (وقت لكل حالة × عدد الحالات السنوي × تكلفة الساعة)
        + (انخفاض إعادة العمل × تكلفة إعادة العمل) + فوائد أخرى."""
        hours = (step.active_time_min + step.wait_time_min) / 60.0
        time_saving = hours * self.cases_per_year * self.hourly_cost * 0.6
        rework_saving = (step.rework_rate * hours * self.cases_per_year
                         * self.hourly_cost * 0.4)
        return time_saving + rework_saving

    # --------------------------------------------------------------
    def classify(self, step: Step) -> FrictionQuadrant:
        high_value = step.value_score >= self.value_threshold
        fr = step.friction_rate
        high_friction = fr >= self.friction_threshold or fr == float("inf")
        if high_value and not high_friction:
            return FrictionQuadrant.PROTECT
        if high_value and high_friction:
            return FrictionQuadrant.REDESIGN
        if not high_value and not high_friction:
            return FrictionQuadrant.MERGE
        return FrictionQuadrant.AUTOMATE

    _RECOMMEND = {
        FrictionQuadrant.PROTECT: "تُحافَظ عليها وتُحسَّن بحذر",
        FrictionQuadrant.REDESIGN: "مرشح قوي لإعادة التصميم من الصفر",
        FrictionQuadrant.MERGE: "تُوحَّد مع خطوات أخرى أو تُلغى إن لم تكن ضرورية",
        FrictionQuadrant.AUTOMATE: "مرشح قوي للأتمتة أو الحذف",
    }

    # --------------------------------------------------------------
    def analyze(self, process: ProcessVersion,
                baseline: BaselineMetrics | None = None) -> AnalysisResult:
        result = AnalysisResult()
        for s in process.steps:
            q = self.classify(s)
            savings = self.annual_savings(s) if q in (
                FrictionQuadrant.REDESIGN, FrictionQuadrant.AUTOMATE) else 0.0
            result.assessments.append(StepAssessment(
                step=s.name, quadrant=q, friction_rate=s.friction_rate,
                value_score=s.value_score, annual_savings=savings,
                recommendation=self._RECOMMEND[q]))
            result.total_annual_savings += savings
            if s.value_score >= self.value_threshold:
                result.high_value.append(s.name)
            else:
                result.low_value.append(s.name)
            if s.friction_rate >= self.friction_threshold:
                result.high_friction.append(s.name)

        # اختبار «عنق الزجاجة الحقيقي»: أعلى خطوة انتظاراً/احتكاكاً
        if process.steps:
            bottleneck = max(
                process.steps,
                key=lambda s: (s.wait_time_min, s.friction_rate
                               if s.friction_rate != float("inf") else 1e9))
            result.bottleneck = bottleneck.name

        # خريطة الحرارة: الأثر (توفير) × سهولة التنفيذ (عكس المخاطر/الحكم)
        for a in result.assessments:
            step = process.step(a.step)
            ease = 1.0 - ((step.risk_score if step else 0.5) * 0.6
                          + (0.3 if step and step.requires_approval else 0.0))
            impact = a.annual_savings
            result.heatmap.append((a.step, impact, max(ease, 0.05)))

        # أولوية: أعلى أثر×سهولة — خطوة أو خطوتان، لا أتمتة دفعة واحدة
        ranked = sorted(result.heatmap, key=lambda x: x[1] * x[2], reverse=True)
        result.priority_steps = [r[0] for r in ranked[:2] if r[1] > 0]
        return result

    # --------------------------------------------------------------
    def analyze_exceptions(self, kinds: list[str],
                           avg_cost: float = 25.0) -> list[ExceptionInsight]:
        """يحلّل الاستثناءات الأكثر شيوعاً: تكرارها، كلفتها، مسارها البديل."""
        freq: dict[str, int] = {}
        for k in kinds:
            freq[k] = freq.get(k, 0) + 1
        total = max(len(kinds), 1)
        insights = []
        for kind, count in sorted(freq.items(), key=lambda x: -x[1]):
            insights.append(ExceptionInsight(
                kind=kind,
                frequency=count / total,
                cost=count * avg_cost,
                candidate_path="معالجة وكيل مع تصعيد عند انخفاض الثقة",
                root_cause_hint="يُحدَّد الجذر عبر ذكاء الاستثناءات أثناء التشغيل",
            ))
        return insights
