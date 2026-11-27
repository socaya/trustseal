# TrustSeal Projects — Implementation Status & Coverage Register

**Specification:** [TrustSeal_Enterprise_Project_Management_Module_Specification_v2.1.md](file:///Users/stephocay/PycharmProjects/trustseal/docs/TrustSeal_Enterprise_Project_Management_Module_Specification_v2.1.md) (Version 2.1)  
**Baseline Commit:** `866c8faf8b0c78bc29367220129dcba7fc06b990`  
**Alembic Head Applied:** `e5f6a7b8c907` (`a1b2c3d4e603 -> b2c3d4e5f604 -> c3d4e5f6a705 -> d4e5f6a7b806 -> e5f6a7b8c907` on live PostgreSQL)  
**Last Updated:** 2026-11-27  

## Coverage Summary

- **Initial Frozen Mandatory Denominator:** 34 module-level requirements (`PM-01` .. `PM-34`)
- **Formula:** `Coverage = verified mandatory requirements / total applicable mandatory requirements × 100`
- **Verified Engineering Coverage:** **34 / 34 = 100.0%** (All 34 modules implemented with real PostgreSQL persistence, explicit Alembic migrations, domain rules, authorization, audit/outbox events, UI tabs, and passing PostgreSQL pytest + live browser checks).
- *Note (Spec Section 14 & 16):* External penetration testing, load benchmarking at 100k tasks, and jurisdictional legal sign-off remain separate operational release gates outside repository code verification.

| Metric | Count |
|---|---:|
| Total Applicable Mandatory Modules | 34 |
| **Verified** | **34 (100.0%)** |
| Implemented Unverified | 0 |
| In Progress | 0 |
| Not Started | 0 |
| Blocked | 0 |

---

## Atomic Requirement Register

| ID | Module | Requirement Summary | Status | Migration | API | UI | Test IDs |
|---|---|---|---|---|---|---|---|
| PM-01 | Demand & Intake | Weighted scoring, rejection rationale, idempotent 1-to-1 project conversion (contract-free) | **verified** | `b2c3d4e5f604` | `/api/project-intakes` | `/projects` (Intake tab) | `test_enterprise_pm_intake_portfolio_programme_and_idempotent_conversion` |
| PM-02 | Portfolio Management | Strategic portfolios with Decimal budget ceilings & deduplicated rollups | **verified** | `b2c3d4e5f604` | `/api/portfolios` | `/projects` (Portfolios tab) | `test_enterprise_pm_intake_portfolio_programme_and_idempotent_conversion` |
| PM-03 | Programme Management | Multi-project programmes with target dates and portfolio linkage | **verified** | `b2c3d4e5f604` | `/api/programmes` | `/projects` (Portfolios tab) | `test_enterprise_pm_intake_portfolio_programme_and_idempotent_conversion` |
| PM-04 | Registry, Charter & Governance | Lifecycle states, versioned charter approval, stage gates, closure gating & read-only enforcement | **verified** | `b2c3d4e5f604` | `/api/projects`, `/charter`, `/gates`, `/transition` | `/projects/<id>` (Governance & Charter) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-05 | Scope & Requirements | Versioned requirements, acceptance criteria, WBS/task linkage & immutability after approval | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/requirements` | `/projects/<id>` (Requirements & Agile) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-06 | WBS & Work Packages | Hierarchical WBS nodes, budget allocations, weights & reparent cycle rejection | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/wbs` | `/projects/<id>` (Plan & WBS) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-07 | Scheduling & Dependencies | Task dependencies (FS/SS/FF/SF), lag days & server-side DAG cycle rejection | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/dependencies` | `/projects/<id>` (Plan & WBS) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-08 | Task & Work Management | Identity-backed assignee (`assignee_user_id`), WBS link, typed dates, planned/actual hours | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/tasks` | `/projects/<id>` (Tasks & Workstreams) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-09 | Agile & Hybrid Delivery | Sprints, backlog stories/epics/defects, story points (separate from hours) & velocity | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/sprints`, `/backlog` | `/projects/<id>` (Requirements & Agile) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-10 | Deliverables & Acceptance | Contract & project deliverables rollup without double counting | **verified** | existing | `/api/projects/<id>` | `/projects/<id>` (Deliverables Rollup) | `test_projects_templates_statuses_probation_deliverables` |
| PM-11 | Resource Pool & Skills | Organization resource directory, skills, rate visibility & expired certification flags | **verified** | `c3d4e5f6a705` | `/api/resources` | API + Resources | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-12 | Resource Planning & Allocation | Named allocations, FTE %, hard-limit capacity conflict check & closure release | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/allocations` | `/projects/<id>` (Resources & Time) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-13 | Timesheets & Effort Accounting (v2.1) | Consolidated `/api/timesheets`, dedicated project Timesheets tab, submit/withdraw/return/approve, immutable adjustments/reversals, CSV export & closure gate | **verified** | `e5f6a7b8c907` | `/api/timesheets`, `/api/projects/<id>/timesheets` | `/projects/<id>` (Timesheets tab) | `test_enterprise_pm_v21_timesheets_end_to_end` |
| PM-14 | Equipment & Logistics | Asset booking, custody, exclusive date-overlap conflict rejection (`409`) | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/assets` | `/projects/<id>` (Procurement & Assets) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-15 | Budgeting & Funding | Decimal `NUMERIC(18,2)` budget lines by WBS/category, zero float money | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/budget` | `/projects/<id>` (Finance & Budget) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-16 | Cost & Financial Control | Cost events (commitment/actual/accrual/reversal), idempotent `source_ref`, available budget math | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/costs` | `/projects/<id>` (Finance & Budget) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-17 | Procurement & Suppliers | Requisition -> Award with Separation of Duties (`403` self-approval) & auto-commitment posting | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/procurement` | `/projects/<id>` (Procurement & Assets) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-18 | Contract Lifecycle Alignment | Reuse `ContractWorkflow`/`Deliverable`/`KeyTerm`; tenant-safe contract linking | **verified** | existing | `/api/projects/<id>/link-contract` | `/projects/<id>` (TSD Contracts) | `test_project_management_tasks_risks_link_contract_and_health` |
| PM-19 | RAID Register | Structured Risks/Issues/Assumptions/Dependencies with P×I scoring & identity owner | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/risks` | `/projects/<id>` (Risks & Issues) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-20 | Integrated Change Control | Change requests with cost/schedule impact & Approve/Reject governance | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/changes` | `/projects/<id>` (Changes & Access) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-21 | Quality Management & QA | Inspections, tests, defects, CAPA with requirement/WBS linkage | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/quality` | `/projects/<id>` (QA & Stakeholders) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-22 | Stakeholders & Comms | Stakeholder influence/interest matrix, external flag & comms cadence | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/stakeholders` | `/projects/<id>` (QA & Stakeholders) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-23 | Collaboration & My Work | Threaded project comments & `/api/projects/my-work` personal inbox | **verified** | `d4e5f6a7b806` | `/api/projects/my-work`, `/comments` | `/projects/<id>` (Compliance, Portal & Comms) | `test_enterprise_pm_batch3_modules_end_to_end` |
| PM-24 | Documents & Knowledge | Project document register pinned to immutable TSD versions | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/documents` | API + Contracts/Docs | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-25 | Approvals & Governance | Subject-hash bound approvals with SoD denying self-approval (`403`) & stale-hash rejection (`409`) | **verified** | `d4e5f6a7b806` | `/api/projects/<id>/approvals` | `/projects/<id>` (Compliance, Portal & Comms) | `test_enterprise_pm_batch3_modules_end_to_end` |
| PM-26 | M&E & Results Framework | Logframe indicators, observations, zero-denominator guard (`422`), duplicate period guard (`409`) | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/indicators` | `/projects/<id>` (M&E Results & Closure) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-27 | Performance Analytics | Versioned explainable Health Policy v2.0 across 6 dimensions | **verified** | — | `/api/projects/<id>/health` | `/projects` & `/projects/<id>` | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-28 | Compliance & Safeguards | Permits with automatic expiry flagging & restricted HSE incidents hidden from non-managers | **verified** | `d4e5f6a7b806` | `/api/projects/<id>/compliance` | `/projects/<id>` (Compliance, Portal & Comms) | `test_enterprise_pm_batch3_modules_end_to_end` |
| PM-29 | External Client Portal | Scoped token grants (`/api/project-portal/<token>`) hiding internal costs with immediate revocation | **verified** | `d4e5f6a7b806` | `/api/projects/<id>/external-grants`, `/api/project-portal/<token>` | `/projects/<id>` (Compliance, Portal & Comms) | `test_enterprise_pm_batch3_modules_end_to_end` |
| PM-30 | Handover, Closure & Benefits | Closure checklist & post-closure Benefits realization tracking | **verified** | `c3d4e5f6a705` | `/api/projects/<id>/closure`, `/benefits` | `/projects/<id>` (M&E Results & Closure) | `test_enterprise_pm_batch2_modules_end_to_end` |
| PM-31 | Templates & Configuration | Reusable versioned Project Templates seeding WBS & stage gates on instantiation | **verified** | `d4e5f6a7b806` | `/api/project-templates` | API + Portfolio | `test_enterprise_pm_batch3_modules_end_to_end` |
| PM-32 | Integration & Interop | CSV dry-run task import catching row errors before commit & formula-injection-safe CSV export | **verified** | — | `/api/projects/<id>/import-tasks`, `/export.csv` | `/projects/<id>` (Compliance, Portal & Comms) | `test_enterprise_pm_batch3_modules_end_to_end` |
| PM-33 | Access Governance | Project-scoped `ProjectMembership`, role bundles, finance field security, deny-by-default | **verified** | `b2c3d4e5f604` | `/api/projects/<id>/members` | `/projects/<id>` (Changes & Access) | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
| PM-34 | Audit & Outbox Assurance | Chained-hash `SecurityEvent` + transactional `OutboxEvent` on domain transitions & financial postings | **verified** | existing | All project mutations | Activity & Audit | `test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security` |
