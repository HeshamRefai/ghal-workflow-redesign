"""محرك حدود الاستقلالية — Autonomy Boundary Engine (القسم 7.3).

لا يسأل فقط «هل الوكيل مستقل أو غير مستقل» بل يحدد مستوى الاستقلالية
في كل حالة. الصيغة المفاهيمية:

    محرك الاستقلالية = نموذج الثقة + نموذج المخاطر + نموذج السياق + محرك السياسات

المخرجات الممكنة: تنفيذ كامل / تنفيذ تحت إشراف / اعتماد مطلوب / حظر.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import AutonomyLevel, Policy, ProcessState, Step


@dataclass
class AutonomyDecision:
    level: AutonomyLevel
    reasons: list[str] = field(default_factory=list)
    triggered_policies: list[str] = field(default_factory=list)

    @property
    def allows_execution(self) -> bool:
        return self.level in (AutonomyLevel.FULL, AutonomyLevel.BOUNDED,
                              AutonomyLevel.ASSISTED)


class AutonomyBoundaryEngine:
    """يحسم مستوى الاستقلالية لكل خطوة في كل حالة على حدة."""

    # عتبات قابلة للتعديل دون إعادة بناء العملية (فصل المعاملات عن المنطق)
    def __init__(self,
                 full_trust: float = 0.85,
                 bounded_trust: float = 0.6,
                 assisted_trust: float = 0.4,
                 high_risk: float = 0.7):
        self.full_trust = full_trust
        self.bounded_trust = bounded_trust
        self.assisted_trust = assisted_trust
        self.high_risk = high_risk

    # --------------------------------------------------------------
    def decide(self, step: Step, state: ProcessState,
               policies: list[Policy] | None = None,
               agent_history: float | None = None) -> AutonomyDecision:
        reasons: list[str] = []
        triggered: list[str] = []
        ctx = state.context()
        ctx.setdefault("amount", state.inputs.get("amount", 0))
        ctx.setdefault("approval_threshold",
                       state.inputs.get("approval_threshold", 10_000))
        ctx.setdefault("missing_evidence",
                       state.inputs.get("missing_evidence", 0))

        # 1) السياسات أولاً — قد تفرض اعتماداً أو حظراً
        for p in (policies or []):
            if p.evaluate(ctx):
                triggered.append(p.name)
                if p.effect == "forbid":
                    return AutonomyDecision(
                        AutonomyLevel.FORBIDDEN,
                        [f"السياسة «{p.name}» تحظر التنفيذ: {p.rule}"],
                        triggered)
                if p.effect == "require_approval":
                    return AutonomyDecision(
                        AutonomyLevel.ASSISTED,
                        [f"السياسة «{p.name}» تشترط اعتماداً بشرياً: {p.rule}"],
                        triggered)
                if p.effect == "escalate":
                    reasons.append(f"السياسة «{p.name}» تطلب تصعيداً: {p.rule}")

        # 2) فعل غير قابل للعكس → لا استقلالية كاملة أبداً
        if not step.reversible:
            return AutonomyDecision(
                AutonomyLevel.SUPERVISED,
                reasons + ["الفعل غير قابل للعكس — تنفيذ تحت إشراف فقط."],
                triggered)

        # 3) مخاطر مرتفعة → اعتماد مطلوب
        risk = max(step.risk_score, state.risk_level)
        if risk >= self.high_risk:
            return AutonomyDecision(
                AutonomyLevel.ASSISTED,
                reasons + [f"درجة المخاطر {risk:.2f} ≥ {self.high_risk} "
                           "— اعتماد بشري مطلوب."],
                triggered)

        # 4) مصفوفة الثقة × المخاطر
        trust = state.trust_level
        if trust >= self.full_trust and risk < 0.4 and state.stage != "novel":
            level = AutonomyLevel.FULL
            reasons.append(f"ثقة مرتفعة ({trust:.2f}) ومخاطر منخفضة "
                           f"({risk:.2f}) — تنفيذ كامل مع تدقيق مستمر.")
        elif trust >= self.bounded_trust and risk < 0.6:
            level = AutonomyLevel.BOUNDED
            reasons.append(f"ثقة جيدة ({trust:.2f}) — استقلالية مقيدة "
                           "ضمن حدود المبلغ ونوع الحالة.")
        elif trust >= self.assisted_trust:
            level = AutonomyLevel.ASSISTED
            reasons.append(f"ثقة متوسطة ({trust:.2f}) — تنفيذ أجزاء "
                           "مع طلب اعتماد عند النقاط المحددة.")
        else:
            level = AutonomyLevel.SUPERVISED
            reasons.append(f"ثقة منخفضة ({trust:.2f}) — وضع الظل: "
                           "يقترح الوكيل والإنسان ينفذ/يراقب.")

        if state.stage == "novel" and level == AutonomyLevel.FULL:
            level = AutonomyLevel.BOUNDED
            reasons.append("حالة جديدة — خُفّضت الاستقلالية درجة.")

        if agent_history is not None and agent_history < 0.5 \
                and level in (AutonomyLevel.FULL, AutonomyLevel.BOUNDED):
            level = AutonomyLevel.ASSISTED
            reasons.append("سجل أداء الوكيل دون العتبة — خُفّضت الاستقلالية.")

        return AutonomyDecision(level, reasons, triggered)
