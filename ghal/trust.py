"""محرك الثقة — Process Trust Score (القسمان 7.4 و9.7).

درجة ثقة ديناميكية للوكيل وللعملية معاً، تتغير بناءً على:
الدقة، نسبة النجاح، عدد التصحيحات، معدل الاستثناء، ونتائج التدقيق.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrustRecord:
    subject: str                  # وكيل أو عملية
    score: float = 0.5            # درجة الثقة الحالية (0..1)
    attempts: int = 0
    successes: int = 0
    corrections: int = 0
    exceptions: int = 0
    audit_findings: int = 0
    history: list[float] = field(default_factory=list)

    @property
    def trend(self) -> str:
        if len(self.history) < 2:
            return "stable"
        return "rising" if self.history[-1] >= self.history[-2] else "falling"


class TrustEngine:
    """يحسب درجة الثقة ويحدّثها من بيانات التنفيذ والتدقيق."""

    def __init__(self, learning_rate: float = 0.15,
                 initial: float = 0.5):
        self.learning_rate = learning_rate
        self.initial = initial
        self._records: dict[str, TrustRecord] = {}

    def record(self, subject: str) -> TrustRecord:
        if subject not in self._records:
            self._records[subject] = TrustRecord(subject=subject,
                                                 score=self.initial)
        return self._records[subject]

    # --------------------------------------------------------------
    def update(self, subject: str, *, success: bool,
               corrected: bool = False, exception: bool = False,
               audit_finding: bool = False) -> TrustRecord:
        """يحدّث الثقة بعد كل نتيجة تنفيذ."""
        r = self.record(subject)
        r.attempts += 1
        r.successes += int(success)
        r.corrections += int(corrected)
        r.exceptions += int(exception)
        r.audit_findings += int(audit_finding)

        # الهدف اللحظي: نجاح نظيف = 1 ، فشل أو تدقيق سلبي = 0
        target = 1.0 if success else 0.0
        if corrected:
            target -= 0.3
        if exception:
            target -= 0.15
        if audit_finding:
            target -= 0.25
        target = max(0.0, min(1.0, target))

        r.score = round(r.score + self.learning_rate * (target - r.score), 4)
        r.history.append(r.score)
        return r

    # --------------------------------------------------------------
    def score(self, subject: str) -> float:
        return self.record(subject).score

    def snapshot(self, subject: str) -> dict:
        r = self.record(subject)
        accuracy = r.successes / r.attempts if r.attempts else 0.0
        return {
            "subject": r.subject,
            "trust_score": r.score,
            "trend": r.trend,
            "attempts": r.attempts,
            "accuracy": round(accuracy, 3),
            "correction_rate": round(r.corrections / max(r.attempts, 1), 3),
            "exception_rate": round(r.exceptions / max(r.attempts, 1), 3),
            "audit_findings": r.audit_findings,
        }
