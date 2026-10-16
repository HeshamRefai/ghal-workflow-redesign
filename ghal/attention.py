"""موجّه الانتباه البشري — Human Attention Router (القسم 9.4).

بدلاً من إرسال كل شيء إلى الإنسان، يرسل إليه فقط القرارات التي تحتاج
حكمه فعلاً. الصيغة المفاهيمية:

    موجّه الانتباه = الثقة + المخاطر + الجِدّة + قابلية التراجع
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ProcessState, Step


@dataclass
class RoutingDecision:
    route: str                 # "agent" (تنفيذ آلي) أو "human" (إلى الإنسان)
    attention_score: float     # درجة الحاجة إلى الانتباه البشري (0..1)
    reasons: list[str] = field(default_factory=list)


class HumanAttentionRouter:
    """يوجّه القرارات: آلي للنمطية عالية الثقة منخفضة المخاطر،
    وإلى الإنسان لغير النمطية أو عالية المخاطر."""

    def __init__(self, human_threshold: float = 0.5):
        self.human_threshold = human_threshold

    def route(self, step: Step, state: ProcessState,
              novelty: float = 0.0) -> RoutingDecision:
        """يحسب درجة الانتباه = مزيج مرجّح من المخاطر والجِدّة
        وانخفاض الثقة وعدم قابلية التراجع."""
        risk = max(step.risk_score, state.risk_level)
        distrust = 1.0 - state.trust_level
        irreversibility = 0.0 if step.reversible else 1.0

        score = (0.35 * risk
                 + 0.30 * distrust
                 + 0.20 * novelty
                 + 0.15 * irreversibility)

        reasons = [
            f"مخاطر={risk:.2f}", f"انخفاض الثقة={distrust:.2f}",
            f"جِدّة={novelty:.2f}", f"عدم قابلية التراجع={irreversibility:.0f}",
        ]
        if score >= self.human_threshold:
            return RoutingDecision(
                "human", round(score, 3),
                reasons + ["الدرجة ≥ العتبة — يُوجَّه إلى الإنسان مع "
                           "تلخيص الأدلة وسبب التصعيد."])
        return RoutingDecision(
            "agent", round(score, 3),
            reasons + ["الدرجة < العتبة — تمرير آلي مع تسجيل القرار."])
