# Commercial Hypotheses

## 1. How to test these hypotheses

These are questions to validate with prospective buyers. None is a market fact or a pricing commitment. Record the interview role, company context, current workflow, evidence, and decision for each interview. Seek disconfirming evidence as well as positive feedback.

Use problem interviews before presenting proposed prices. Follow them with a small, time-boxed pilot using agreed tasks and a baseline from the customer's existing workflow. Do not infer willingness to pay from stated interest alone; ask for a concrete next step such as access to a pilot, procurement review, or budget-owner meeting.

## 2. Testable hypotheses

### H1 — Initial customer segment

**Hypothesis:** Independent panel builders and mid-sized EPC engineering teams with recurring LV panel work have a frequent enough calculation/reporting problem to evaluate this desktop product.

**Evidence to collect:** 12–15 interviews across panel builders, EPC teams, and engineering consultants; current project volume; roles involved; existing tools; time spent on calculation, BOM, and report preparation; buying authority.

**Decision signal:** A segment repeatedly describes the same costly workflow and agrees to test a representative project. If pain is rare or owned by another buyer, revise the segment before pricing.

### H2 — Licensing model

**Hypothesis:** Buyers will prefer one of per-seat, per-project, or organization-wide licensing based on how many engineers contribute and how often projects are delivered.

**Evidence to collect:** Interview users and budget owners separately. Present comparable licensing structures only after understanding procurement, project cadence, seat sharing, and offline/deployment constraints. Record which structure advances to procurement review.

**Decision signal:** Select a model only after a buyer can explain how it maps to their budget and usage. No price point is assumed in this document.

### H3 — Primary value proposition

**Hypothesis:** Reducing repeated engineering entry and report/BOM preparation is a stronger purchase driver than adding another calculation screen.

**Evidence to collect:** In a pilot, time the same agreed task in the customer's current workflow and in the application; record corrections, omitted inputs, review time, and export rework. Include representative projects rather than a hand-picked easy case.

**Decision signal:** The value proposition is supported if measured workflow improvements are repeatable and customers consider the result important enough to change their process. No percentage reduction is claimed in advance.

### H4 — Independent oracle and traceability value

**Hypothesis:** Some technical buyers will value an independent cable-selection cross-check and report provenance enough to include them in evaluation or procurement criteria.

**Evidence to collect:** Ask engineering reviewers to compare the engine, F-031a oracle, and their current checks; note discrepancies, review effort, trust concerns, and whether the missing F-031b fault-energy layer changes their acceptance.

**Decision signal:** Treat the feature as a differentiator only if reviewers use the evidence in a real review and can state what additional validation they require. F-031a is not a complete independent reproduction of the full engine.

### H5 — Initial geography and buying route

**Hypothesis:** One of Germany or Iran will provide a more practical first customer group based on language, local support, standards workflow, procurement, and deployment requirements.

**Evidence to collect:** Interviews in both markets with engineers and budget owners; required languages and standards evidence; local data/privacy expectations; payment/procurement route; support expectations; willingness to pilot.

**Decision signal:** Choose a first geography based on access to qualified pilot customers and ability to meet their requirements, not on assumed market size. Reassess if localization, support, or security requirements exceed current product capacity.

## 3. Validation plan

1. Conduct 12–15 discovery interviews across at least two candidate segments and both candidate geographies where access permits.
2. Select 2–3 pilot organizations only after a workflow baseline and data-handling expectations are documented.
3. Use a common pilot protocol: same project inputs, defined outputs, task timing, defect/correction log, reviewer feedback, and explicit limitations.
4. Track measures such as completion time, manual corrections, missing-input detection, review time, export rework, repeated use, and willingness to enter procurement review.
5. Review findings with the product owner; preserve negative results and update or reject hypotheses rather than changing thresholds after seeing outcomes.

The sample sizes above are proposed discovery targets, not statistically representative market research.

## 4. Risks and open decisions

- Which role owns the budget: engineering manager, panel-builder owner, project manager, or IT/procurement?
- Is local desktop deployment sufficient, or will buyers require managed multi-user storage and identity controls?
- What independent validation is required before a buyer relies on calculations in production?
- Which catalog/manufacturer evidence and local standards workflows are essential for the first market?
- Can the team support the security review, update process, and service expectations requested by the first pilot customers?
- Which pricing model best fits real procurement behavior? Keep pricing undecided until buyer evidence exists.
- Does the reported 47 ms result hold under a reproducible benchmark protocol and customer-scale input mix? R-16b contains cache implementation/tests, but no checked-in timing artifact.
