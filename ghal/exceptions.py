"""محرك ذكاء الاستثناءات — Exception Intelligence Engine (القسم 9.5).

يعامل كل استثناء بوصفه معلومة يمكن أن تؤدي إلى تحسين:
تصنيف الاستثناء → تحديد السبب الجذري → تجميع الحالات المتشابهة →
حساب الأثر والتكلفة → اكتشاف الأنماط → اقتراح تغيير في العملية.

ملاحظة الوثيقة: يمكن استخدام التجميع والاستدلال السببي مع ضرورة عدم
اعتبار توصية المحرك نهائية قبل التحقق البشري.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import ExceptionCase


@dataclass
class ExceptionCluster:
    signature: str
    cases: list[ExceptionCase] = field(default_factory=list)
    total_cost: float = 0.0
    suggested_root_cause: str = ""
    redesign_proposal: str = ""


@dataclass
class ExceptionInsightReport:
    total: int
    clusters: list[ExceptionCluster] = field(default_factory=list)
    top_root_causes: list[tuple[str, int]] = field(default_factory=list)
    proposals: list[str] = field(default_factory=list)
    requires_human_review: bool = True     # التوصية ليست نهائية قبل التحقق


# قواعد تصنيف وسبب جذري مبدئية — قابلة للتوسع (Rule-based + قابل للاستبدال بنموذج لغوي)
_CLASSIFIERS: list[tuple[list[str], str, str, str]] = [
    # (كلمات مفتاحية, التصنيف, السبب الجذري المقترح, مقترح إعادة التصميم)
    (["missing", "ناقص", "incomplete", "غير مكتمل"],
     "data_missing", "بيانات ناقصة عند الاستلام",
     "أضف تحققاً آلياً من اكتمال البيانات عند نقطة الاستلام."),
    (["mismatch", "عدم تطابق", "no-match", "تعارض"],
     "matching_failure", "فشل المطابقة بين المصادر",
     "وسّع قواعد المطابقة المتساهلة وحدّد عتبة ثقة للتصعيد."),
    (["duplicate", "مكرر", "تكرار"],
     "duplicate", "ازدواجية في الإدخال أو المصدر",
     "عزّز فحص التكرار الآلي قبل المطابقة بدلاً من بعدها."),
    (["threshold", "عتبة", "exceeds", "يتجاوز"],
     "threshold_exceeded", "تجاوز عتبة مبلغ/مخاطر",
     "راجع مستويات العتبات؛ قد تكون أدنى من اللازم فتُغرق الإنسان."),
    (["timeout", "مهلة", "تأخر", "late"],
     "sla_breach", "تجاوز المهلة الزمنية",
     "أضف تصعيداً آلياً قبل انتهاء المهلة مع بديل عند عدم الاستجابة."),
    (["unknown", "جديد", "novel", "غير معروف"],
     "novel_case", "حالة جديدة لم تُرَ من قبل",
     "سجّل الحالة في ذاكرة العملية وحدّث نموذج التصنيف بعد المراجعة."),
]

_DEFAULT = ("unclassified", "سبب غير مصنّف بعد",
            "اجمع مزيداً من السياق ووجّهه لمراجعة بشرية لتعلّم النمط.")


class ExceptionIntelligenceEngine:
    """يحلل الاستثناءات ويستخرج الأنماط ويقترح تحسينات."""

    # --------------------------------------------------------------
    def classify(self, case: ExceptionCase) -> tuple[str, str, str]:
        """يصنّف الاستثناء ويقترح سبباً جذرياً ومقترح معالجة."""
        text = f"{case.kind} {case.description}".lower()
        for keywords, label, cause, proposal in _CLASSIFIERS:
            if any(k in text for k in keywords):
                return label, cause, proposal
        return _DEFAULT

    # --------------------------------------------------------------
    def ingest(self, case: ExceptionCase) -> ExceptionCase:
        """يستقبل استثناءً ويصنّفه ويحدّد سببه الجذري إن لم يُحدَّد."""
        label, cause, _ = self.classify(case)
        case.kind = label if case.kind in ("", "unknown") else case.kind
        if not case.root_cause:
            case.root_cause = cause
        return case

    # --------------------------------------------------------------
    def cluster(self, cases: list[ExceptionCase]) -> list[ExceptionCluster]:
        """يجمّع الحالات المتشابهة ويحسب أثرها ويقترح تغييرات."""
        groups: dict[str, list[ExceptionCase]] = defaultdict(list)
        for c in cases:
            self.ingest(c)
            signature = f"{c.kind}:{c.step or 'global'}"
            groups[signature].append(c)

        clusters = []
        for sig, members in sorted(groups.items(),
                                   key=lambda x: -len(x[1])):
            _, _, proposal = self.classify(members[0])
            clusters.append(ExceptionCluster(
                signature=sig,
                cases=members,
                total_cost=sum(m.impact_cost for m in members),
                suggested_root_cause=members[0].root_cause,
                redesign_proposal=proposal,
            ))
        return clusters

    # --------------------------------------------------------------
    def report(self, cases: list[ExceptionCase]) -> ExceptionInsightReport:
        clusters = self.cluster(cases)
        causes: dict[str, int] = defaultdict(int)
        for cl in clusters:
            if cl.suggested_root_cause:
                causes[cl.suggested_root_cause] += len(cl.cases)
        proposals = sorted({cl.redesign_proposal for cl in clusters
                            if cl.redesign_proposal})
        return ExceptionInsightReport(
            total=len(cases),
            clusters=clusters,
            top_root_causes=sorted(causes.items(), key=lambda x: -x[1]),
            proposals=proposals,
            requires_human_review=True,
        )
