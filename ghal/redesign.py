"""محرك إعادة التصميم — Redesign Engine (القسم 9.1، إطار ZBPR).

يستقبل الوضع الحالي والنتيجة المطلوبة والبيانات والسياسات والمخاطر
والقدرات المتاحة، ثم: يكتشف الخطوات والقرارات والأدوار → يميّز القيمة
عن الحركة والانتظار → يحدد الاختناقات والتكرار والاستثناءات → يصنّف
العمل بين قواعد وحكم ومعرفة ضمنية → يحدد فرص الحذف والتجميع والتفويض
والأتمتة → يبني بدائل مستقبلية → يقارنها بالقيمة والمخاطر والجدوى →
يوزّع الأدوار → يحدد الأدلة والسياسات والحدود → ينتج تصميماً مبرراً
قابلاً للمحاكاة والتنفيذ.

المبادئ الحاكمة:
- الاستثناء جزء من التصميم — صمّم للكشف عن الاستثناء وتوجيهه وحلّه فقط.
- تغيّر ملكية العملية — مالك واحد مسؤول عن النتيجة كاملة.
- النتيجة قبل العملية — لا تُقدَّس الخريطة الحالية لمجرد أنها قائمة.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import AnalysisResult, FrictionQuadrant
from .models import (AutonomyLevel, Policy, ProcessVersion, Step, StepNature)


@dataclass
class StepDisposition:
    """مصير الخطوة في التصميم المستقبلي مع مبرّره."""
    step: str
    action: str          # keep / delete / merge / delegate / automate
    new_owner: str
    reason: str          # سبب الحذف / التفويض / الإبقاء — إلزامي (6.1)


@dataclass
class RedesignSpec:
    """مواصفة التصميم المستقبلي To-Be — قابلة للتحويل إلى Process-as-Code."""
    to_be: ProcessVersion
    dispositions: list[StepDisposition] = field(default_factory=list)
    autonomy_bounds: dict[str, AutonomyLevel] = field(default_factory=dict)
    escalation_policy: str = ""
    evidence_requirements: dict[str, list[str]] = field(default_factory=dict)
    metrics_plan: list[str] = field(default_factory=list)
    expected_savings: float = 0.0

    def to_process_as_code(self) -> dict:
        """تصدير المواصفة كوثيقة Process-as-Code قابلة للتنفيذ والتحقق."""
        tb = self.to_be
        return {
            "process": tb.name,
            "version": tb.version,
            "steps": [{
                "name": s.name,
                "nature": s.nature.value,
                "owner": s.owner,
                "owner_kind": s.owner_kind.value if s.owner_kind else None,
                "requires_approval": s.requires_approval,
                "risk_score": s.risk_score,
                "reversible": s.reversible,
                "systems": s.systems,
                "inputs": s.inputs,
                "outputs": s.outputs,
            } for s in tb.steps],
            "policies": [{
                "name": p.name, "rule": p.rule,
                "condition": p.condition, "effect": p.effect,
                "version": p.version,
            } for p in tb.policies],
            "autonomy_bounds": {k: v.value for k, v in self.autonomy_bounds.items()},
            "rationale": tb.rationale,
            "evidence_requirements": self.evidence_requirements,
            "escalation_policy": self.escalation_policy,
        }


class RedesignEngine:
    """محرك إعادة التصميم من الصفر (Zero-Based Process Redesign)."""

    AGENT_CAPABILITIES = {
        # قدرات الوكلاء الافتراضية (Agentic-Native Design — 2.3)
        "read_extract": "قراءة المعلومات واستخراجها",
        "retrieve": "استرجاع المعرفة والسياق",
        "summarize": "تلخيص المستندات وصياغة المخرجات",
        "route": "توجيه الحالات واتخاذ القرارات المحدودة",
        "coordinate": "التنسيق بين الأنظمة والفرق والوكلاء",
        "monitor": "مراقبة التنفيذ والتقاط الأدلة",
        "handle_exceptions": "التعامل مع الاستثناءات وإرسالها للجهة المناسبة",
    }

    def __init__(self, desired_outcome: str = "",
                 risk_appetite: float = 0.4):
        self.desired_outcome = desired_outcome
        self.risk_appetite = risk_appetite   # 0 متحفظ — 1 جريء

    # --------------------------------------------------------------
    def _nature_of(self, step: Step) -> StepNature:
        if step.nature != StepNature.RULE:
            return step.nature
        if step.risk_score >= 0.75 or not step.reversible:
            return StepNature.HIGH_RISK
        if step.requires_approval and step.value_score >= 0.6:
            return StepNature.JUDGMENT
        return StepNature.RULE

    # --------------------------------------------------------------
    def redesign(self, as_is: ProcessVersion,
                 analysis: AnalysisResult) -> RedesignSpec:
        """يبني التصميم المستقبلي من النتيجة إلى الخلف — لا من الخطوات."""
        quadrant_of = {a.step: a.quadrant for a in analysis.assessments}
        savings_of = {a.step: a.annual_savings for a in analysis.assessments}
        dispositions: list[StepDisposition] = []
        new_steps: list[Step] = []
        rationale: dict[str, str] = {}

        for step in as_is.steps:
            q = quadrant_of.get(step.name, FrictionQuadrant.PROTECT)
            nature = self._nature_of(step)

            # 1) الحذف: خطوة لا تخلق قيمة ولا تحقق امتثالاً أو حماية واضحة
            if q == FrictionQuadrant.AUTOMATE and step.value_score < 0.25 \
                    and not step.requires_approval and step.risk_score < 0.4:
                dispositions.append(StepDisposition(
                    step.name, "delete", "-",
                    "لا تخلق قيمة ولا تحقق امتثالاً أو حماية — تُحذف (ZBPR)."))
                rationale[f"delete:{step.name}"] = \
                    "حُذفت لأنها حركة لا قيمة فيها (اختبار «وماذا بعد؟»)."
                continue

            # 2) الإبقاء البشري: حكم أو مخاطر عالية أو فعل غير قابل للعكس
            if nature in (StepNature.JUDGMENT, StepNature.HIGH_RISK,
                          StepNature.TACIT):
                kept = Step(**{**step.__dict__})
                kept.owner = kept.owner or "human:owner"
                dispositions.append(StepDisposition(
                    step.name, "keep", kept.owner,
                    "تتطلب حكماً/سياقاً أو مخاطرها عالية — تبقى بشرية "
                    "مع اقتراح آلي ومراجعة."))
                rationale[f"keep:{step.name}"] = \
                    "أُبقيت لدى الإنسان لحاجتها إلى حكم أو لكونها غير قابلة للعكس."
                new_steps.append(kept)
                continue

            # 3) الدمج: منخفضة القيمة ومنخفضة الاحتكاك
            if q == FrictionQuadrant.MERGE and new_steps \
                    and new_steps[-1].owner_kind == step.owner_kind:
                prev = new_steps[-1]
                prev.name = f"{prev.name}+{step.name}"
                prev.active_time_min += step.active_time_min
                dispositions.append(StepDisposition(
                    step.name, "merge", prev.name,
                    "منخفضة القيمة والاحتكاك — دُمجت مع الخطوة السابقة."))
                rationale[f"merge:{step.name}"] = "دُمجت لتقليل التسليمات."
                continue

            # 4) التفويض إلى وكيل: قاعدة قابلة للتحقق والتكرار
            delegated = Step(**{**step.__dict__})
            delegated.nature = nature
            delegated.owner = "agent:workflow"
            delegated.wait_time_min = 0.0          # الوكيل لا ينتظر طوابير بشرية
            delegated.requires_approval = (
                step.requires_approval and step.risk_score > self.risk_appetite)
            action = "delegate" if not step.requires_approval else "automate"
            dispositions.append(StepDisposition(
                step.name, action, delegated.owner,
                "قاعدة قابلة للصياغة والتحقق والتكرار — تُفوَّض إلى وكيل "
                "ضمن حدود استقلالية."))
            rationale[f"{action}:{step.name}"] = \
                "فُوّضت إلى وكيل لأنها قاعدة حتمية متكررة قابلة للتحقق."
            new_steps.append(delegated)

        # حدود الاستقلالية المبدئية لكل خطوة (تُضبط لاحقاً بمحرك الحدود)
        autonomy: dict[str, AutonomyLevel] = {}
        for s in new_steps:
            if s.owner and s.owner.startswith("agent"):
                if s.risk_score < 0.3 and s.reversible:
                    autonomy[s.name] = AutonomyLevel.BOUNDED
                else:
                    autonomy[s.name] = AutonomyLevel.ASSISTED
            else:
                autonomy[s.name] = AutonomyLevel.SUPERVISED

        # سياسات افتراضية: عتبة مبلغ + فصل واجبات + أدلة قبل الدفع
        policies = [
            Policy(name="approval-threshold",
                   rule="كل حالة تتجاوز عتبة المبلغ تتطلب اعتماداً بشرياً",
                   condition="amount > approval_threshold",
                   effect="require_approval"),
            Policy(name="evidence-before-commit",
                   rule="لا فعل مؤثر قبل اكتمال الأدلة المطلوبة",
                   condition="missing_evidence > 0",
                   effect="escalate"),
        ]

        to_be = ProcessVersion(
            name=as_is.name, version="to-be-0.1",
            steps=new_steps, policies=policies,
            autonomy_bounds=autonomy, rationale=rationale)

        return RedesignSpec(
            to_be=to_be,
            dispositions=dispositions,
            autonomy_bounds=autonomy,
            escalation_policy=(
                "يُصعَّد إلى الإنسان عند: انخفاض الثقة، ارتفاع المخاطر، "
                "حالة جديدة، تعارض الأدلة، تجاوز المبلغ حداً معيناً، "
                "فشل الوكيل، الحاجة إلى حكم، أو فعل غير قابل للعكس."),
            evidence_requirements={
                s.name: list(s.outputs or ["execution-evidence"])
                for s in new_steps},
            metrics_plan=[
                "زمن الدورة", "معدل الاستثناء", "معدل إعادة العمل",
                "نسبة القرارات الموجهة للإنسان", "نسبة التنفيذ الذاتي",
                "درجة الثقة", "درجة الامتثال", "تكلفة الحالة",
            ],
            expected_savings=sum(savings_of.get(d.step, 0.0)
                                 for d in dispositions
                                 if d.action in ("delete", "delegate", "automate")),
        )
