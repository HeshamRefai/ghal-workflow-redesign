"""نموذج البيانات الأساسي — Data Model (القسم 8.3 / 20.8 من الوثيقة).

يمثّل الكيانات: Process, Step, Decision, Actor, Agent, Human,
Policy, Risk, Exception, Outcome, Evidence, Approval, Audit Event,
Trust Score, Change Proposal — إضافة إلى Process State (8.4).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------- enums

class ActorKind(str, Enum):
    HUMAN = "human"                    # الإنسان
    SPECIALIST_AGENT = "specialist"    # الوكيل المتخصص
    DECISION_AGENT = "decision_agent"  # وكيل القرار
    FLOW_AGENT = "flow_agent"          # وكيل التدفق
    COORDINATION_AGENT = "coordination"  # وكيل التنسيق
    DETERMINISTIC_SYSTEM = "system"    # النظام الحتمي
    POLICY_ENGINE = "policy_engine"    # محرك السياسات
    RISK_ENGINE = "risk_engine"        # محرك المخاطر
    AUDIT_ENGINE = "audit_engine"      # محرك التدقيق
    PROCESS_OWNER = "process_owner"    # صاحب العملية


class StepNature(str, Enum):
    """تصنيف النشاط: قاعدة حتمية / حكم بشري / معرفة ضمنية (القسم 5)."""
    RULE = "rule"                # قاعدة قابلة للصياغة «إذا‒فإن»
    JUDGMENT = "judgment"        # يتطلب خبرة أو تفسيراً أو سياقاً
    TACIT = "tacit"              # معرفة ضمنية غير مكتوبة
    HIGH_RISK = "high_risk"      # قرار عالي المخاطر أو غير قابل للعكس


class DecisionKind(str, Enum):
    DETERMINISTIC = "deterministic"  # قرار حتمي
    PROBABILISTIC = "probabilistic"  # يحتاج أدلة
    CONTEXTUAL = "contextual"        # يحتاج سياقاً
    EXPERT = "expert"                # يحتاج خبرة عالية
    HIGH_RISK = "high_risk"          # يحتاج اعتماداً بشرياً
    IRREVERSIBLE = "irreversible"    # يصعب التراجع عنه


class AutonomyLevel(str, Enum):
    """مستويات الحوكمة الأربعة (القسم 7.1)."""
    SUPERVISED = "supervised"    # 1 — المراقبة: يقترح أو ينفذ في وضع الظل
    ASSISTED = "assisted"        # 2 — المساعدة: ينفذ أجزاء ويطلب اعتماداً
    BOUNDED = "bounded"          # 3 — استقلالية مقيدة: ضمن حدود مبلغ/حالة/مخاطر
    FULL = "full"                # 4 — استقلالية مسموح بها: تنفيذ آلي كامل مع تدقيق مستمر
    FORBIDDEN = "forbidden"      # حظر — خارج أي تفويض


class ChangeKind(str, Enum):
    MINOR = "minor"          # تطوير صغير — موافقة مبسطة
    MAJOR = "major"          # تطوير كبير — اعتماد بشري
    EMERGENCY = "emergency"  # تطوير طارئ — تغيير فوري (حادثة/خطر/تنظيم)


# ---------------------------------------------------------------- entities

@dataclass
class Actor:
    name: str
    kind: ActorKind
    capabilities: list[str] = field(default_factory=list)
    id: str = field(default_factory=_uid)


@dataclass
class Policy:
    """سياسة قابلة للتنفيذ والاختبار والإصدار (Policy as Code)."""
    name: str
    rule: str                       # وصف القاعدة بلغة طبيعية
    condition: str = ""             # شرط قابل للتقييم (تعبير بايثون على سياق الحالة)
    effect: str = "require_approval"  # require_approval / forbid / allow / escalate
    version: str = "1.0"
    id: str = field(default_factory=_uid)

    def evaluate(self, context: dict[str, Any]) -> bool:
        """يعيد True إذا انطبق الشرط على السياق."""
        if not self.condition:
            return False
        try:
            return bool(eval(self.condition, {"__builtins__": {}}, dict(context)))
        except Exception:
            return False


@dataclass
class Evidence:
    """دليل متراكم في الحالة — التصميم القائم على الأدلة (3.1)."""
    kind: str                       # document / log / extraction / approval / ...
    content: Any
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=_uid)


@dataclass
class Step:
    name: str
    nature: StepNature = StepNature.RULE
    owner: Optional[str] = None          # اسم الفاعل المقترح/المعيّن
    owner_kind: Optional[ActorKind] = None
    active_time_min: float = 0.0         # الزمن النشط لكل حالة
    wait_time_min: float = 0.0           # زمن الانتظار قبل الخطوة
    error_rate: float = 0.0              # معدل الأخطاء (0..1)
    rework_rate: float = 0.0             # معدل إعادة العمل
    exception_rate: float = 0.0          # معدل الاستثناءات
    value_score: float = 0.5             # مساهمة الخطوة في القيمة (0..1)
    risk_score: float = 0.2              # درجة مخاطر الخطوة (0..1)
    reversible: bool = True              # قابلية التراجع عن الفعل
    requires_approval: bool = False
    systems: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    id: str = field(default_factory=_uid)

    @property
    def friction_rate(self) -> float:
        """معدل الاحتكاك = زمن الانتظار ÷ الزمن النشط × 100 (القسم G)."""
        if self.active_time_min <= 0:
            return float("inf") if self.wait_time_min > 0 else 0.0
        return (self.wait_time_min / self.active_time_min) * 100.0


@dataclass
class Decision:
    """قرار مع أصله (Decision Provenance — 9.12)."""
    subject: str
    outcome: Any
    kind: DecisionKind = DecisionKind.DETERMINISTIC
    actor: str = ""
    rationale: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    policies: list[str] = field(default_factory=list)
    model: str = ""
    alternatives: list[Any] = field(default_factory=list)
    confidence: float = 1.0
    approved_by: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=_uid)


@dataclass
class ExceptionCase:
    """استثناء — معلومة يمكن أن تؤدي إلى تحسين (9.5)."""
    kind: str
    description: str
    step: str = ""
    severity: float = 0.5
    root_cause: str = ""
    impact_cost: float = 0.0
    resolved: bool = False
    resolution: str = ""
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=_uid)


@dataclass
class Event:
    """حدث تنفيذ — يغذّي Process Genome والتدقيق المستمر."""
    step: str
    actor: str
    action: str
    case_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=_uid)


@dataclass
class ProcessVersion:
    """إصدار عملية — Process-as-Code (2.4)."""
    name: str
    version: str
    steps: list[Step] = field(default_factory=list)
    policies: list[Policy] = field(default_factory=list)
    autonomy_bounds: dict[str, AutonomyLevel] = field(default_factory=dict)
    rationale: dict[str, str] = field(default_factory=dict)  # مبررات التصميم (سجل)
    id: str = field(default_factory=_uid)

    def step(self, name: str) -> Optional[Step]:
        return next((s for s in self.steps if s.name == name), None)


@dataclass
class ProcessState:
    """حالة العملية لحظة معيّنة — Process State (8.4 / 10.1)."""
    process_id: str
    case_id: str = field(default_factory=_uid)
    inputs: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    current_decision: Optional[str] = None
    current_owner: Optional[str] = None
    trust_level: float = 0.5
    risk_level: float = 0.2
    open_exceptions: list[ExceptionCase] = field(default_factory=list)
    next_step: Optional[str] = None
    policy_version: str = "1.0"
    process_version: str = "1.0"
    stage: str = "init"

    def context(self) -> dict[str, Any]:
        """سياق قابل للتقييم في السياسات والشروط."""
        return {
            "case_id": self.case_id,
            "trust": self.trust_level,
            "risk": self.risk_level,
            "stage": self.stage,
            "exceptions": len(self.open_exceptions),
            **self.inputs,
        }
