"""مخصّص العمل بين الإنسان والوكيل — Human-Agent Allocation (القسم 9.3).

يقترح لكل خطوة المالك الأنسب وفق: طبيعة العمل، الثقة، المخاطر،
قابلية التحقق، حساسية القرار، وقابلية التراجع.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import ActorKind, Step, StepNature


class OwnerKind(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"        # النظام الحتمي
    HYBRID = "hybrid"        # اقتراح آلي + مراجعة بشرية


@dataclass
class Allocation:
    step: str
    owner: OwnerKind
    actor_kind: ActorKind
    reason: str
    confidence: float


class HumanAgentAllocator:
    """يوزّع العمل: الوكيل يتولى الأعمال المتكررة القابلة للتحقق،
    والإنسان يركز على الاستثناءات والحكم والسياق (مبدأ ZBPR رقم 4)."""

    def allocate(self, step: Step, trust: float = 0.5) -> Allocation:
        # فعل غير قابل للعكس أو مخاطر عالية جداً → إنسان حتماً
        if not step.reversible or step.risk_score >= 0.8:
            return Allocation(
                step.name, OwnerKind.HUMAN, ActorKind.HUMAN,
                "فعل غير قابل للعكس أو مخاطره عالية — اعتماد بشري إلزامي.",
                1.0)

        # حكم أو معرفة ضمنية → هجين: اقتراح آلي مع مراجعة بشرية
        if step.nature in (StepNature.JUDGMENT, StepNature.TACIT):
            return Allocation(
                step.name, OwnerKind.HYBRID, ActorKind.SPECIALIST_AGENT,
                "يتطلب حكماً/سياقاً — وكيل يقترح وإنسان يراجع.",
                0.7)

        # قاعدة + ثقة كافية + مخاطر منخفضة → وكيل
        if step.nature == StepNature.RULE and step.risk_score < 0.5:
            if trust >= 0.6:
                return Allocation(
                    step.name, OwnerKind.AGENT, ActorKind.SPECIALIST_AGENT,
                    "قاعدة قابلة للتحقق مع ثقة كافية ومخاطر منخفضة — وكيل.",
                    trust)
            return Allocation(
                step.name, OwnerKind.HYBRID, ActorKind.SPECIALIST_AGENT,
                "قاعدة لكن الثقة لم تنضج بعد — وكيل بمراجعة بشرية.",
                trust)

        # حسابيات/مطابقات حتمية دقيقة → نظام حتمي
        if step.nature == StepNature.RULE and step.error_rate < 0.01:
            return Allocation(
                step.name, OwnerKind.SYSTEM, ActorKind.DETERMINISTIC_SYSTEM,
                "حتمي تماماً والدقة والامتثال أهم — نظام حتمي.",
                0.95)

        return Allocation(
            step.name, OwnerKind.HUMAN, ActorKind.HUMAN,
            "الافتراضي المتحفظ: إنسان حتى تثبت الأدلة غير ذلك.",
            0.5)

    def allocate_process(self, steps: list[Step],
                         trust: float = 0.5) -> list[Allocation]:
        return [self.allocate(s, trust) for s in steps]
