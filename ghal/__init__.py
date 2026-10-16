"""
G-HAL — منصة إعادة تصميم سير العمل الوكيلية
Agentic Workflow Redesign Platform core.

تنفّذ هذه الحزمة النواة المفاهيمية الموصوفة في وثيقة
«إعادة تصميم سير العمل — المرجع الشامل»:

    Process Discovery → Analysis → Zero-Based Redesign
    → Human-Agent Allocation → Autonomy/Risk/Policy
    → Simulation → Controlled Execution → Continuous Audit
    → Exception Intelligence → Process Memory → Process Evolution
"""

from .models import (
    Actor,
    ActorKind,
    AutonomyLevel,
    Decision,
    DecisionKind,
    Event,
    Evidence,
    ExceptionCase,
    Policy,
    ProcessState,
    ProcessVersion,
    Step,
    StepNature,
)
from .discovery import ProcessDiscovery
from .analysis import ProcessAnalyzer, FrictionQuadrant
from .redesign import RedesignEngine, RedesignSpec
from .allocation import HumanAgentAllocator, OwnerKind
from .trust import TrustEngine
from .autonomy import AutonomyBoundaryEngine, AutonomyDecision
from .attention import HumanAttentionRouter, RoutingDecision
from .simulation import ProcessSimulationEngine, Scenario
from .audit import ContinuousAuditRuntime, AuditReport
from .exceptions import ExceptionIntelligenceEngine
from .memory import ProcessMemory
from .evolution import ProcessEvolutionProtocol, ChangeKind
from .agents import TaskAgent, DecisionAgent, FlowAgent, CoordinationAgent
from .runtime import ProcessHarness

__version__ = "0.1.0"

__all__ = [
    "Actor", "ActorKind", "AutonomyLevel", "Decision", "DecisionKind",
    "Event", "Evidence", "ExceptionCase", "Policy", "ProcessState",
    "ProcessVersion", "Step", "StepNature",
    "ProcessDiscovery", "ProcessAnalyzer", "FrictionQuadrant",
    "RedesignEngine", "RedesignSpec", "HumanAgentAllocator", "OwnerKind",
    "TrustEngine", "AutonomyBoundaryEngine", "AutonomyDecision",
    "HumanAttentionRouter", "RoutingDecision",
    "ProcessSimulationEngine", "Scenario", "ContinuousAuditRuntime",
    "AuditReport", "ExceptionIntelligenceEngine", "ProcessMemory",
    "ProcessEvolutionProtocol", "ChangeKind",
    "TaskAgent", "DecisionAgent", "FlowAgent", "CoordinationAgent",
    "ProcessHarness",
]
