"""بروتوكول تطوّر العملية — Process Evolution Protocol (القسم 9.9).

العملية لا تتجمد بعد إطلاقها. يستقبل البروتوكول بيانات الأداء
والتغذية الراجعة والاستثناءات، يقترح تغييراً، يقيّم أثره، ويوجّهه
للموافقة وينشر إصداراً جديداً. التغيير ثلاثة أنواع:

- تطوير صغير (minor): تعديل محدود قد يمر بموافقة مبسطة.
- تطوير كبير (major): إعادة تصميم جوهرية تحتاج اعتماداً بشرياً.
- تطوير طارئ (emergency): تغيير فوري بسبب حادثة أو خطر أو تغيير تنظيمي.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .models import ChangeKind, ProcessVersion


@dataclass
class ChangeProposal:
    title: str
    kind: ChangeKind
    description: str
    rationale: str
    impact_estimate: str = ""
    apply: Optional[Callable[[ProcessVersion], ProcessVersion]] = None
    approved: bool = False
    approved_by: str = ""
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: f"chg-{int(time.time()*1000)}")


@dataclass
class EvolutionResult:
    proposal: ChangeProposal
    new_version: Optional[ProcessVersion]
    status: str            # applied / pending_approval / rejected


class ProcessEvolutionProtocol:
    """يدير دورة: اقتراح → تقييم أثر → موافقة → نشر إصدار جديد."""

    # محفز إعادة التصميم — Redesign Trigger (20.2): مؤشرات → عتبات → تنبيه
    def __init__(self,
                 cycle_time_threshold: float = 1.25,   # +25% زمن دورة
                 exception_threshold: float = 0.15,
                 rework_threshold: float = 0.10,
                 human_ratio_threshold: float = 0.40,
                 require_human_for_major: bool = True):
        self.cycle_time_threshold = cycle_time_threshold
        self.exception_threshold = exception_threshold
        self.rework_threshold = rework_threshold
        self.human_ratio_threshold = human_ratio_threshold
        self.require_human_for_major = require_human_for_major
        self.history: list[EvolutionResult] = []

    # --------------------------------------------------------------
    def redesign_trigger(self, metrics: dict,
                         baseline: dict) -> tuple[bool, list[str], float]:
        """يراقب مؤشرات العملية ويطلق تنبيهاً عند تجاوز العتبات.
        التنبيه لا يعني أن التغيير يجب أن يحدث آلياً، بل أن العملية
        تستحق تحليلاً جديداً. يعيد (يستحق؟, أسباب, درجة أولوية)."""
        reasons: list[str] = []
        score = 0.0
        base_cycle = baseline.get("cycle_time_min", 0.0) or 1.0
        cur_cycle = metrics.get("cycle_time_min", 0.0)
        if cur_cycle / base_cycle >= self.cycle_time_threshold:
            reasons.append(f"زمن الدورة ارتفع إلى {cur_cycle:.1f} "
                           f"(+{(cur_cycle/base_cycle-1)*100:.0f}%).")
            score += 0.35
        if metrics.get("exception_rate", 0.0) >= self.exception_threshold:
            reasons.append("معدل الاستثناءات تجاوز العتبة.")
            score += 0.25
        if metrics.get("rework_rate", 0.0) >= self.rework_threshold:
            reasons.append("معدل إعادة العمل تجاوز العتبة.")
            score += 0.2
        if metrics.get("human_ratio", 0.0) >= self.human_ratio_threshold:
            reasons.append("نسبة التدخل البشري مرتفعة — الانتباه يُستنزف.")
            score += 0.2
        return (len(reasons) > 0, reasons, min(score, 1.0))

    # --------------------------------------------------------------
    def submit(self, proposal: ChangeProposal,
               current: ProcessVersion) -> EvolutionResult:
        """يقيّم الاقتراح ويوجّهه حسب نوعه."""
        if proposal.kind == ChangeKind.MINOR and not self.require_human_for_major:
            proposal.approved = True
            proposal.approved_by = "policy:simplified"
        elif proposal.kind == ChangeKind.EMERGENCY:
            # تغيير فوري — يُطبَّق ثم يُراجَع بأثر رجعي
            proposal.approved = True
            proposal.approved_by = "emergency:post-review-required"

        if not proposal.approved:
            result = EvolutionResult(proposal, None, "pending_approval")
            self.history.append(result)
            return result

        if proposal.apply is None:
            result = EvolutionResult(proposal, None, "rejected")
        else:
            new_version = proposal.apply(current)
            new_version.version = self._bump(current.version, proposal.kind)
            result = EvolutionResult(proposal, new_version, "applied")
        self.history.append(result)
        return result

    # --------------------------------------------------------------
    def approve(self, proposal: ChangeProposal, approver: str,
                current: ProcessVersion) -> EvolutionResult:
        """اعتماد بشري لاقتراح معلّق."""
        proposal.approved = True
        proposal.approved_by = approver
        if proposal.apply is None:
            result = EvolutionResult(proposal, None, "rejected")
        else:
            new_version = proposal.apply(current)
            new_version.version = self._bump(current.version, proposal.kind)
            result = EvolutionResult(proposal, new_version, "applied")
        self.history.append(result)
        return result

    # --------------------------------------------------------------
    @staticmethod
    def _bump(version: str, kind: ChangeKind) -> str:
        try:
            major, minor = version.replace("to-be-", "").split(".")
            major, minor = int(major), int(minor)
        except Exception:
            return f"{version}+1"
        if kind == ChangeKind.MAJOR:
            return f"{major + 1}.0"
        return f"{major}.{minor + 1}"
