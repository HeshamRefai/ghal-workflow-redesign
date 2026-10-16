"""اختبارات النواة — تشغيل: python -m pytest tests/ أو python tests/test_core.py"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghal import (AutonomyBoundaryEngine, AutonomyLevel, Event,
                  ExceptionCase, ExceptionIntelligenceEngine,
                  HumanAgentAllocator, HumanAttentionRouter, OwnerKind,
                  Policy, ProcessAnalyzer, ProcessDiscovery,
                  ProcessEvolutionProtocol, ProcessMemory, ProcessState,
                  ProcessVersion, RedesignEngine, Scenario, Step, StepNature,
                  TrustEngine)
from ghal.models import ChangeKind
from ghal.simulation import ProcessSimulationEngine
from ghal.audit import ContinuousAuditRuntime


def _simple_process() -> ProcessVersion:
    return ProcessVersion(name="p", version="1.0", steps=[
        Step("استخراج", active_time_min=10, wait_time_min=100,
             value_score=0.4, risk_score=0.2),
        Step("مراجعة", active_time_min=5, wait_time_min=500,
             value_score=0.8, risk_score=0.3, nature=StepNature.JUDGMENT),
        Step("اعتماد", active_time_min=2, wait_time_min=900,
             value_score=0.35, risk_score=0.9, reversible=False,
             requires_approval=True),
    ])


# ------------------------------------------------------------- discovery
def test_discovery_builds_baseline():
    evs, ts = [], time.time()
    for i in range(10):
        for j, s in enumerate(["a", "b", "c"]):
            evs.append(Event(step=s, actor="clerk", action="execute",
                             case_id=f"c{i}", timestamp=ts + i * 5000 + j * 900,
                             payload={"active_min": 5.0}))
    res = ProcessDiscovery().from_event_log("p", evs)
    assert res.baseline.case_count == 10
    assert len(res.as_is.steps) == 3
    assert res.baseline.friction_rate > 0


# ------------------------------------------------------------- analysis
def test_friction_quadrants():
    p = _simple_process()
    res = ProcessAnalyzer().analyze(p)
    q = {a.step: a.quadrant.value for a in res.assessments}
    assert q["اعتماد"] == "automate"      # قيمة منخفضة + احتكاك عالٍ
    assert q["مراجعة"] == "redesign"      # قيمة عالية + احتكاك عالٍ
    assert res.bottleneck == "اعتماد"      # أعلى انتظار


def test_annual_savings_formula():
    p = _simple_process()
    an = ProcessAnalyzer(cases_per_year=1000, hourly_cost=100)
    res = an.analyze(p)
    assert res.total_annual_savings > 0


# ------------------------------------------------------------- redesign
def test_redesign_justifies_every_disposition():
    p = _simple_process()
    res = ProcessAnalyzer().analyze(p)
    spec = RedesignEngine().redesign(p, res)
    for d in spec.dispositions:
        assert d.reason, f"خطوة بلا مبرر: {d.step}"
    # الخطوة غير القابلة للعكس تبقى بشرية
    pay = next(d for d in spec.dispositions if d.step == "اعتماد")
    assert pay.action == "keep"
    # المواصفة تتحول إلى Process-as-Code
    pac = spec.to_process_as_code()
    assert pac["steps"] and pac["policies"] and pac["rationale"]


def test_no_sacred_cows_delete():
    p = ProcessVersion(name="p", version="1", steps=[
        Step("حركة بلا قيمة", active_time_min=5, wait_time_min=200,
             value_score=0.1, risk_score=0.1),
        Step("جوهرية", active_time_min=5, wait_time_min=0,
             value_score=0.9, risk_score=0.1),
    ])
    res = ProcessAnalyzer().analyze(p)
    spec = RedesignEngine().redesign(p, res)
    actions = {d.step: d.action for d in spec.dispositions}
    assert actions["حركة بلا قيمة"] == "delete"
    assert "حركة بلا قيمة" not in [s.name for s in spec.to_be.steps]


# ------------------------------------------------------------- allocation
def test_allocation_rules():
    alloc = HumanAgentAllocator()
    irreversible = Step("دفع", reversible=False, risk_score=0.9)
    assert alloc.allocate(irreversible).owner == OwnerKind.HUMAN
    rule = Step("مطابقة", nature=StepNature.RULE, risk_score=0.2)
    assert alloc.allocate(rule, trust=0.8).owner == OwnerKind.AGENT
    judgment = Step("تقدير", nature=StepNature.JUDGMENT)
    assert alloc.allocate(judgment).owner == OwnerKind.HYBRID


# ------------------------------------------------------------- trust
def test_trust_rises_and_falls():
    t = TrustEngine(initial=0.5)
    for _ in range(10):
        t.update("a", success=True)
    high = t.score("a")
    assert high > 0.7
    for _ in range(5):
        t.update("a", success=False, audit_finding=True)
    assert t.score("a") < high


# ------------------------------------------------------------- autonomy
def test_autonomy_matrix():
    eng = AutonomyBoundaryEngine()
    step = Step("x", risk_score=0.2, reversible=True)
    state = ProcessState(process_id="p", inputs={"amount": 100})
    state.trust_level = 0.95
    assert eng.decide(step, state).level == AutonomyLevel.FULL
    state.trust_level = 0.65
    assert eng.decide(step, state).level == AutonomyLevel.BOUNDED
    state.trust_level = 0.2
    assert eng.decide(step, state).level == AutonomyLevel.SUPERVISED


def test_autonomy_policy_overrides():
    eng = AutonomyBoundaryEngine()
    step = Step("x", risk_score=0.1)
    state = ProcessState(process_id="p",
                         inputs={"amount": 999_999,
                                 "approval_threshold": 10_000})
    state.trust_level = 0.99
    pol = Policy(name="حد", rule="فوق العتبة اعتماد",
                 condition="amount > approval_threshold",
                 effect="require_approval")
    d = eng.decide(step, state, policies=[pol])
    assert d.level == AutonomyLevel.ASSISTED
    assert "حد" in d.triggered_policies


def test_irreversible_never_full():
    eng = AutonomyBoundaryEngine()
    step = Step("x", risk_score=0.0, reversible=False)
    state = ProcessState(process_id="p")
    state.trust_level = 1.0
    assert eng.decide(step, state).level == AutonomyLevel.SUPERVISED


# ------------------------------------------------------------- attention
def test_attention_router():
    router = HumanAttentionRouter()
    easy = Step("x", risk_score=0.05, reversible=True)
    state = ProcessState(process_id="p")
    state.trust_level = 0.95
    assert router.route(easy, state, novelty=0.0).route == "agent"
    hard = Step("y", risk_score=0.9, reversible=False)
    state.trust_level = 0.3
    assert router.route(hard, state, novelty=0.8).route == "human"


# ------------------------------------------------------------- simulation
def test_simulation_improves_with_delegation():
    p = _simple_process()
    sim = ProcessSimulationEngine()
    results = sim.compare(p, [
        Scenario("base"),
        Scenario("agents", delegate_to_agent=["استخراج", "مراجعة"]),
    ], runs=300)
    assert results[1].expected_cycle_time_min < results[0].expected_cycle_time_min
    assert results[1].vs_baseline_cycle < 0


# ------------------------------------------------------------- audit
def test_audit_catches_unapproved_and_deviation():
    p = _simple_process()
    p.step("اعتماد").requires_approval = True
    runtime = ContinuousAuditRuntime()
    evs = [
        Event(step="اعتماد", actor="agent:x", action="execute",
              case_id="c1", payload={"active_min": 1}),
        Event(step="غير موجودة", actor="agent:x", action="execute",
              case_id="c1", payload={"active_min": 1}),
    ]
    rep = runtime.check_log(evs, p, {"اعتماد": AutonomyLevel.SUPERVISED})
    kinds = {a.kind for a in rep.alerts}
    assert "policy_violation" in kinds
    assert "deviation" in kinds
    assert rep.compliance_score < 1.0


# ------------------------------------------------------------- exceptions
def test_exception_intelligence_clusters_and_proposes():
    eng = ExceptionIntelligenceEngine()
    cases = [ExceptionCase(kind="", description="عدم تطابق أمر الشراء",
                           step="مطابقة", impact_cost=100),
             ExceptionCase(kind="", description="عدم تطابق في المبلغ",
                           step="مطابقة", impact_cost=100),
             ExceptionCase(kind="", description="بيانات ناقصة",
                           step="استخراج", impact_cost=50)]
    rep = eng.report(cases)
    assert rep.total == 3
    assert len(rep.clusters) == 2
    assert rep.clusters[0].signature.startswith("matching_failure")
    assert rep.proposals
    assert rep.requires_human_review


# ------------------------------------------------------------- memory
def test_memory_hash_chain_integrity():
    from ghal.models import Decision
    mem = ProcessMemory()
    mem.store_event(Event(step="a", actor="x", action="execute", case_id="c"))
    mem.store_decision(Decision(subject="لماذا", outcome="ok", actor="agent"))
    assert mem.verify_integrity()
    # عبث مباشر يكسر السلسلة
    mem.conn.execute("UPDATE events SET payload = 'tampered' WHERE seq = 1")
    mem.conn.commit()
    assert not mem.verify_integrity()


def test_memory_why_query():
    from ghal.models import Decision
    mem = ProcessMemory()
    mem.store_decision(Decision(subject="إضافة موافقة مالية",
                                rationale="حادثة احتيال 2023",
                                outcome="added", actor="human:cfo"))
    rows = mem.why("موافقة")
    assert rows and "احتيال" in rows[0]["rationale"]


# ------------------------------------------------------------- evolution
def test_redesign_trigger_thresholds():
    evo = ProcessEvolutionProtocol()
    trig, reasons, score = evo.redesign_trigger(
        {"cycle_time_min": 130, "exception_rate": 0.2},
        {"cycle_time_min": 100})
    assert trig and score > 0.4
    trig2, _, _ = evo.redesign_trigger(
        {"cycle_time_min": 100, "exception_rate": 0.01},
        {"cycle_time_min": 100})
    assert not trig2


def test_evolution_minor_major_emergency():
    evo = ProcessEvolutionProtocol()
    cur = ProcessVersion(name="p", version="1.0")

    def apply(v: ProcessVersion) -> ProcessVersion:
        return v

    from ghal.evolution import ChangeProposal
    minor = ChangeProposal("تعديل عتبة", ChangeKind.MINOR, "وصف", "مبرر",
                           apply=apply)
    res = evo.submit(minor, cur)
    assert res.status == "pending_approval"      # الافتراضي: يتطلب بشراً
    res2 = evo.approve(minor, "human:owner", cur)
    assert res2.status == "applied"
    assert res2.new_version.version == "1.1"

    emerg = ChangeProposal("إصلاح عاجل", ChangeKind.EMERGENCY, "وصف",
                           "خطر", apply=apply)
    res3 = evo.submit(emerg, cur)
    assert res3.status == "applied"              # فوري مع مراجعة لاحقة


# ------------------------------------------------------------- runner
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} اختباراً ناجحاً")
    sys.exit(1 if failed else 0)
