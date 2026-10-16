"""حالة الاستخدام المرجعية: معالجة الفواتير ودعمها (القسم 11).

يعرض هذا السكربت الدورة الكاملة للمنصة على عملية:

    استلام الفاتورة → استخراج البيانات → التحقق → مطابقة أمر الشراء
    → فحص التكرار → موافقة المدير → موافقة المالية → الدفع

المسار: اكتشاف ← تحليل ← إعادة تصميم من الصفر ← توزيع إنسان/وكيل
← محاكاة سيناريوهات ← تنفيذ مراقَب ← تدقيق مستمر ← ذكاء استثناءات
← ذاكرة ← محفز تطوّر.

التشغيل:  python demo/invoice_demo.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghal import (AutonomyLevel, Event, Evidence, ExceptionCase,
                  HumanAgentAllocator, Policy, ProcessAnalyzer,
                  ProcessDiscovery, ProcessEvolutionProtocol, ProcessHarness,
                  ProcessMemory, ProcessSimulationEngine, RedesignEngine,
                  Scenario, Step, TaskAgent)
from ghal.models import ProcessVersion, StepNature

R = "\033[0m"; B = "\033[1m"; C = "\033[96m"; G = "\033[92m"; Y = "\033[93m"


def h(title: str) -> None:
    print(f"\n{B}{C}{'═' * 62}{R}")
    print(f"{B}{C}  {title}{R}")
    print(f"{B}{C}{'═' * 62}{R}")


# ---------------------------------------------------------------
# 1) توليد سجل أحداث فعلي للوضع الحالي (As-Is)
# ---------------------------------------------------------------
AS_IS_STEPS = [
    # (الخطوة، الفاعل، زمن نشط، انتظار بعدها بالدقائق، معدل استثناء، نوع الاستثناء)
    ("استلام الفاتورة", "clerk:ap", 5, 30, 0.00, ""),
    ("استخراج البيانات", "clerk:ap", 15, 240, 0.12, "بيانات ناقصة في الفاتورة"),
    ("التحقق", "clerk:ap", 10, 180, 0.05, "بيانات غير مكتملة"),
    ("مطابقة أمر الشراء", "clerk:ap", 12, 300, 0.18, "عدم تطابق أمر الشراء"),
    ("فحص التكرار", "clerk:ap", 4, 60, 0.04, "فاتورة مكررة"),
    ("موافقة المدير", "human:manager", 3, 1440, 0.00, ""),
    ("موافقة المالية", "human:finance", 4, 960, 0.00, ""),
    ("الدفع", "human:finance", 6, 0, 0.00, ""),
]


def generate_event_log(cases: int = 60, seed: int = 7) -> list[Event]:
    rng = random.Random(seed)
    events: list[Event] = []
    base = time.time() - 90 * 24 * 3600
    systems = {"استلام الفاتورة": ["email", "erp"],
               "استخراج البيانات": ["ocr", "erp"],
               "التحقق": ["erp"], "مطابقة أمر الشراء": ["erp", "procurement"],
               "فحص التكرار": ["erp"], "موافقة المدير": ["workflow"],
               "موافقة المالية": ["workflow"], "الدفع": ["erp", "bank"]}
    for i in range(cases):
        ts = base + i * 3600 * 11
        cid = f"INV-{1000 + i}"
        rework_once = rng.random() < 0.15
        for name, actor, active, wait, exc_rate, exc_kind in AS_IS_STEPS:
            action = "execute"
            if rng.random() < exc_rate:
                action = "exception"
            if actor.startswith("human") and "موافقة" in name:
                action = "approve"
            events.append(Event(
                step=name, actor=actor, action=action, case_id=cid,
                timestamp=ts,
                payload={"active_min": active * rng.uniform(0.7, 1.4),
                         "systems": systems.get(name, []),
                         "kind": exc_kind if action == "exception" else ""}))
            if rework_once and name == "التحقق" and rng.random() < 0.5:
                events.append(Event(step="استخراج البيانات", actor=actor,
                                    action="rework", case_id=cid, timestamp=ts + 300,
                                    payload={"active_min": 8, "systems": ["ocr"]}))
            ts += wait * 60
    return events


# ---------------------------------------------------------------
# 2) قدرات الوكيل للتصميم المستقبلي (To-Be)
# ---------------------------------------------------------------
def make_task_agent(threshold: float = 10_000.0) -> TaskAgent:
    agent = TaskAgent(name="agent:invoice", confidence_threshold=0.6)

    def extract(state, step):
        inv = state.inputs.get("invoice", {})
        complete = all(k in inv for k in ("amount", "vendor", "po_number"))
        conf = 0.93 if complete else 0.45
        ev = [Evidence("extraction", dict(inv), source="ocr")]
        return ({"extracted": inv}, conf, ev)

    def verify(state, step):
        inv = state.inputs.get("invoice", {})
        ok = inv.get("amount", 0) > 0 and bool(inv.get("vendor"))
        return ({"valid": ok}, 0.95 if ok else 0.4,
                [Evidence("validation", {"valid": ok})])

    def match_po(state, step):
        inv = state.inputs.get("invoice", {})
        po = state.inputs.get("purchase_order", {})
        match = inv.get("po_number") == po.get("number") and \
            abs(inv.get("amount", 0) - po.get("amount", -1)) < 0.01
        return ({"matched": match}, 0.92 if match else 0.35,
                [Evidence("matching", {"po": po.get("number"),
                                       "matched": match})])

    def dup_check(state, step):
        dup = state.inputs.get("duplicate", False)
        return ({"duplicate": dup}, 0.9 if not dup else 0.3,
                [Evidence("duplicate_check", {"duplicate": dup})])

    def receive(state, step):
        return ({"received": True}, 0.99,
                [Evidence("receipt", state.inputs.get("invoice", {}))])

    for name, fn in {
        "استلام الفاتورة": receive,
        "استخراج البيانات": extract,
        "التحقق": verify,
        "مطابقة أمر الشراء": match_po,
        "فحص التكرار": dup_check,
    }.items():
        agent.register(name, fn)
    return agent


# ---------------------------------------------------------------
# 3) محاكاة الإنسان المعتمِد
# ---------------------------------------------------------------
def human_approval(threshold: float):
    def approve(state, step, reason) -> tuple[bool, str]:
        amount = state.inputs.get("invoice", {}).get("amount", 0)
        fraud = state.inputs.get("fraud_suspected", False)
        if fraud:
            return False, "اشتباه احتيال — مرفوضة"
        if "الدفع" in step.name and amount > threshold * 5:
            return False, f"مبلغ {amount} يتجاوز حد التفويض الأعلى"
        return True, "معتمدة"
    return approve


# ---------------------------------------------------------------
def main() -> None:
    THRESHOLD = 10_000.0

    h("A — التدقيق: اكتشاف الوضع الحالي من سجل الأحداث الفعلي")
    discovery = ProcessDiscovery(hourly_cost=60.0)
    log = generate_event_log()
    found = discovery.from_event_log("معالجة الفواتير", log)
    b = found.baseline
    print(f"الحالات المكتشفة: {b.case_count}   التسليمات: {b.handoffs}   "
          f"الموافقات: {b.approvals}   الأنظمة: {b.systems_touched}")
    print(f"زمن الدورة الكلي: {b.cycle_time_min/60:.1f} ساعة   "
          f"النشط: {b.active_time_min:.0f} د   الانتظار: {b.wait_time_min:.0f} د")
    print(f"معدل الاحتكاك: {b.friction_rate:.0f}%   "
          f"إعادة العمل: {b.rework_rate:.1%}   "
          f"الاستثناء: {b.exception_rate:.1%}   "
          f"الاكتمال من أول محاولة: {b.first_pass_yield:.0%}")
    print(f"تكلفة الحالة: {b.cost_per_case:.0f}   "
          f"الاستثناءات المرصودة: {', '.join(found.observed_exceptions[:4])}")
    # ضبط درجات القيمة/المخاطر للخطوات المكتشفة (معرفة مجال)
    value = {"استلام الفاتورة": 0.4, "استخراج البيانات": 0.5, "التحقق": 0.7,
             "مطابقة أمر الشراء": 0.85, "فحص التكرار": 0.6,
             "موافقة المدير": 0.35, "موافقة المالية": 0.45, "الدفع": 0.95}
    risk = {"مطابقة أمر الشراء": 0.4, "الدفع": 0.85,
            "موافقة المدير": 0.3, "موافقة المالية": 0.35}
    nature = {"موافقة المدير": StepNature.JUDGMENT,
              "موافقة المالية": StepNature.JUDGMENT,
              "الدفع": StepNature.HIGH_RISK}
    for s in found.as_is.steps:
        s.value_score = value.get(s.name, 0.4)
        s.risk_score = risk.get(s.name, 0.2)
        s.nature = nature.get(s.name, StepNature.RULE)
        s.reversible = s.name != "الدفع"
        if "موافقة" in s.name or s.name == "الدفع":
            s.owner = "human:finance"
        s.inputs = ["invoice"]; s.outputs = ["evidence"]

    h("G — التقييم: أرباع القيمة/الاحتكاك وخريطة الحرارة")
    analyzer = ProcessAnalyzer(cases_per_year=15000, hourly_cost=60.0)
    analysis = analyzer.analyze(found.as_is, b)
    for a in analysis.assessments:
        print(f"  {a.step:22s} {a.quadrant.value:9s} "
              f"احتكاك={a.friction_rate:7.0f}% قيمة={a.value_score:.2f} "
              f"توفير سنوي محتمل={a.annual_savings:10,.0f}")
    print(f"\nعنق الزجاجة الحقيقي: {Y}{analysis.bottleneck}{R}")
    print(f"خطوات الأولوية (لا دفعة واحدة): {', '.join(analysis.priority_steps)}")
    print(f"{G}إجمالي التوفير السنوي المقدّر: {analysis.total_annual_savings:,.0f}{R}")

    h("E — الهندسة: إعادة تصميم من الصفر (ZBPR) مع المبررات")
    engine = RedesignEngine(desired_outcome="دفع صحيح في وقته بأقل لمس بشري",
                            risk_appetite=0.4)
    spec = engine.redesign(found.as_is, analysis)
    for d in spec.dispositions:
        print(f"  [{d.action:9s}] {d.step:24s} ← {d.reason}")
    print(f"\nالاستقلالية المبدئية: "
          + ", ".join(f"{k}={v.value}" for k, v in list(spec.autonomy_bounds.items())[:5]))
    print(f"سياسة التصعيد: {spec.escalation_policy[:90]}…")

    h("توزيع العمل بين الإنسان والوكيل (Human-Agent Allocation)")
    allocator = HumanAgentAllocator()
    for al in allocator.allocate_process(spec.to_be.steps, trust=0.65):
        print(f"  {al.step:24s} → {al.owner.value:7s} ({al.actor_kind.value}) "
              f"— {al.reason}")

    h("N — التوجيه: محاكاة سيناريوهات قبل الإنتاج")
    sim = ProcessSimulationEngine(hourly_cost=60.0)
    scenarios = [
        Scenario("خط الأساس (As-Is)"),
        Scenario("التصميم المستقبلي (To-Be)",
                 delegate_to_agent=[s.name for s in spec.to_be.steps
                                    if (s.owner or "").startswith("agent")]),
        Scenario("To-Be + حذف موافقة المدير",
                 delegate_to_agent=[s.name for s in spec.to_be.steps
                                    if (s.owner or "").startswith("agent")],
                 remove_approvals=["موافقة المدير"]),
        Scenario("To-Be + ضغط استثناءات أعلى",
                 delegate_to_agent=[s.name for s in spec.to_be.steps
                                    if (s.owner or "").startswith("agent")],
                 exception_rate_delta=0.15),
    ]
    results = sim.compare(found.as_is, scenarios, runs=800)
    print(f"  {'السيناريو':34s} {'الدورة(د)':>9s} {'P95':>7s} {'التكلفة':>8s} "
          f"{'لمس بشري':>8s} {'Δالدورة':>8s}")
    for r in results:
        print(f"  {r.scenario:34s} {r.expected_cycle_time_min:9.1f} "
              f"{r.p95_cycle_time_min:7.1f} {r.expected_cost_per_case:8.1f} "
              f"{r.human_touchpoints:8.1f} {r.vs_baseline_cycle:8.1%}")

    h("T — التتبع: تنفيذ مراقَب عبر Process Harness")
    memory = ProcessMemory()
    agent = make_task_agent(THRESHOLD)
    harness = ProcessHarness(
        design=spec.to_be, task_agent=agent,
        human_approval=human_approval(THRESHOLD), memory=memory)

    test_cases = [
        {"invoice": {"amount": 4_500, "vendor": "شركة الأفق",
                     "po_number": "PO-1"},
         "purchase_order": {"number": "PO-1", "amount": 4_500},
         "approval_threshold": THRESHOLD},
        {"invoice": {"amount": 12_800, "vendor": "مؤسسة النور",
                     "po_number": "PO-2"},
         "purchase_order": {"number": "PO-2", "amount": 12_800},
         "approval_threshold": THRESHOLD},
        {"invoice": {"amount": 7_300, "vendor": "شركة الرياد"},  # ناقص po_number
         "purchase_order": {"number": "PO-3", "amount": 7_300},
         "approval_threshold": THRESHOLD},
        {"invoice": {"amount": 3_100, "vendor": "وهمية",
                     "po_number": "PO-9"},
         "purchase_order": {"number": "PO-4", "amount": 3_100},
         "approval_threshold": THRESHOLD, "fraud_suspected": True},
    ]
    for i, case in enumerate(test_cases, 1):
        res = harness.run_case(case)
        print(f"  حالة {i}: {res.status:22s} وكيل={res.executed_by_agent} "
              f"مراجعات بشرية={res.human_reviews} استثناءات={res.exceptions} "
              f"تنبيهات تدقيق={res.audit_alerts} ثقة={res.final_trust:.2f}")

    h("ذكاء الاستثناءات (Exception Intelligence)")
    report = harness.exceptions.report(
        [exc for case in [ExceptionCase(kind="", description=d, step=s,
                                        impact_cost=120.0)
                          for d, s in
                          [("بيانات ناقصة في الفاتورة", "استخراج البيانات"),
                           ("عدم تطابق أمر الشراء", "مطابقة أمر الشراء"),
                           ("عدم تطابق أمر الشراء", "مطابقة أمر الشراء"),
                           ("فاتورة مكررة", "فحص التكرار")]]
         for exc in [case]])
    print(f"  إجمالي الاستثناءات: {report.total}   المجموعات: {len(report.clusters)}")
    for cl in report.clusters:
        print(f"  • {cl.signature}: {len(cl.cases)} حالة، كلفة={cl.total_cost:.0f}")
        print(f"    السبب الجذري المقترح: {cl.suggested_root_cause}")
        print(f"    مقترح التحسين: {cl.redesign_proposal}")
    print(f"  {Y}ملاحظة: التوصيات ليست نهائية — تتطلب تحققاً بشرياً.{R}")

    h("الذاكرة وأصل القرار (Process Memory / Decision Provenance)")
    print(f"  {memory.stats()}")
    why = memory.why("الخطوة التالية")
    if why:
        print(f"  مثال استعلام «لماذا؟»: {why[0]['subject']} ← {why[0]['rationale']}")

    h("محفز إعادة التصميم (Redesign Trigger)")
    evo = ProcessEvolutionProtocol()
    current_metrics = {"cycle_time_min": b.cycle_time_min * 1.3,
                       "exception_rate": 0.18, "rework_rate": 0.12,
                       "human_ratio": 0.45}
    triggered, reasons, priority = evo.redesign_trigger(
        current_metrics, b.as_dict())
    print(f"  يستحق تحليلاً جديداً؟ {triggered}   درجة الأولوية: {priority:.2f}")
    for r_ in reasons:
        print(f"    - {r_}")

    h("مواصفة Process-as-Code (مقتطف)")
    pac = spec.to_process_as_code()
    print(f"  العملية: {pac['process']}   الإصدار: {pac['version']}")
    print(f"  الخطوات: {len(pac['steps'])}   السياسات: {len(pac['policies'])}")
    print(f"  مبررات موثقة: {len(pac['rationale'])}")

    print(f"\n{G}{B}اكتملت الدورة الكاملة: اكتشاف ← تحليل ← إعادة تصميم ← توزيع "
          f"← محاكاة ← تنفيذ مراقَب ← تدقيق ← استثناءات ← ذاكرة ← تطوّر.{R}\n")


if __name__ == "__main__":
    main()
