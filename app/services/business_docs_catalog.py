"""Business-in-a-Box Complete Company Document Templates Catalog (1,080+ Full Documents).

Covers all 12 core corporate departments (180 distinct company document archetypes
× 6 corporate editions = 1,080 full-length, ready-to-use company documents) for
TrustSeal Documents (TSD) with structured document control headers, complete
operational sections, tables/checklists, and sign-off blocks.
"""
from __future__ import annotations

import html as _html
from functools import lru_cache
from typing import Any


_ATAG = (
    '<span style="background:#eef3fa;color:#0f3b82;border:1px solid #cfdcef;'
    'padding:1px 6px;border-radius:3px;font-family:monospace;font-size:10pt;">'
)


def _field(name: str) -> str:
    return f"{_ATAG}{{{{{name}}}}}</span>"


# 12 Departments × 15 Document Archetypes = 180 Archetypes × 6 Editions = 1,080 Full Company Documents
BUSINESS_DOC_DEPARTMENTS: list[tuple[str, str, list[tuple[str, str, str, str]]]] = [
    (
        "Business Planning & Strategy",
        "strategy, business-plan",
        [
            ("executive_business_plan", "Comprehensive Executive Business Plan", "Full investor-ready business plan covering executive summary, market opportunity, operations, financial model, and milestones.", "strategic business planning and investor presentation"),
            ("annual_strategic_roadmap", "Annual Strategic Plan & OKR Roadmap", "Company-wide annual objectives, key results, departmental priorities, resource budgets, and quarterly review cadence.", "annual strategic execution and OKR alignment"),
            ("swot_pestel_analysis", "SWOT & PESTEL Strategic Analysis", "Structured internal strengths/weaknesses and external macro-environmental opportunity and threat assessment.", "strategic market and competitive assessment"),
            ("feasibility_study_report", "Project & Venture Feasibility Study", "Technical, commercial, operational, legal, and financial viability evaluation prior to capital commitment.", "capital venture feasibility evaluation"),
            ("market_entry_strategy", "New Market Entry & Expansion Plan", "Go-to-market blueprint detailing regulatory licensing, channel partnerships, localization, and break-even timeline.", "geographic and segment market expansion"),
            ("business_continuity_plan", "Business Continuity & Resilience Plan (BCP)", "Enterprise continuity framework defining critical functions, RTO/RPO targets, crisis command, and recovery playbooks.", "operational resilience and crisis continuity"),
            ("enterprise_risk_framework", "Enterprise Risk Management (ERM) Charter", "Board-level risk appetite, risk scoring matrix, mitigation ownership, and quarterly risk committee reporting.", "enterprise risk identification and governance"),
            ("investor_pitch_narrative", "Investor Memo & Fundraising Brief", "Structured investment memorandum covering problem/solution, traction metrics, unit economics, and use of proceeds.", "institutional fundraising and investor communications"),
            ("competitive_intelligence", "Competitive Landscape & Positioning Brief", "Systematic analysis of key competitors, pricing tiers, differentiation moats, and win/loss battlecards.", "competitive intelligence and market positioning"),
            ("mission_vision_charter", "Corporate Mission, Vision & Values Charter", "Foundational cultural and purpose charter guiding leadership decisions, hiring standards, and brand identity.", "organizational purpose and cultural alignment"),
            ("kpi_executive_scorecard", "Executive Balanced Scorecard & KPI Framework", "Financial, customer, operational, and learning KPI definitions with baseline targets and executive owners.", "executive performance measurement"),
            ("annual_operating_plan", "Annual Operating Plan (AOP) & Budget Brief", "Departmental operating plan linking headcount, CapEx/OpEx budgets, and quarterly revenue milestones.", "annual operational budgeting and execution"),
            ("merger_integration_plan", "Post-Merger Integration (PMI) Playbook", "100-day acquisition integration plan covering legal, finance, HR, IT systems, and customer retention.", "post-acquisition corporate integration"),
            ("sustainability_esg_report", "Corporate ESG & Sustainability Report", "Environmental, social, and governance disclosures, carbon targets, diversity metrics, and stakeholder impact.", "ESG governance and sustainability reporting"),
            ("exit_succession_plan", "Business Succession & Exit Readiness Plan", "Long-term leadership continuity, valuation enhancement levers, and strategic exit transaction readiness.", "corporate succession and exit planning"),
        ],
    ),
    (
        "Board & Corporate Governance",
        "governance, board, resolution",
        [
            ("board_meeting_minutes", "Official Board of Directors Meeting Minutes", "Formal statutory minutes recording attendance, quorum, resolutions passed, dissenting notes, and chair sign-off.", "board of directors statutory minutes"),
            ("agm_notice_agenda", "Notice & Agenda of Annual General Meeting (AGM)", "Statutory shareholder notice detailing ordinary/special business, financial statements review, and proxy rights.", "annual general meeting statutory notice"),
            ("board_resolution_bank", "Board Resolution — Bank Account & Signatories", "Certified corporate resolution authorizing opening of bank facilities and designating authorized signing mandates.", "corporate banking authority resolution"),
            ("board_resolution_loan", "Board Resolution — Borrowing & Credit Facility", "Formal board approval authorizing execution of loan agreements, debentures, and corporate security charges.", "corporate borrowing and security authorization"),
            ("board_resolution_shares", "Board Resolution — Allotment & Transfer of Shares", "Official resolution approving new share issuance, capital register updates, and share certificate sealing.", "share allotment and cap-table governance"),
            ("board_resolution_dividend", "Board Resolution — Dividend Declaration", "Formal solvency confirmation and dividend distribution resolution specifying record date and payment date.", "dividend declaration and solvency governance"),
            ("director_appointment_letter", "Non-Executive Director Appointment Letter", "Formal terms of appointment detailing fiduciary duties, board committee roles, fees, and independence standards.", "board director appointment and fiduciary terms"),
            ("director_resignation_letter", "Formal Letter of Resignation as Director", "Clean statutory resignation letter confirming effective date, waiver of claims, and company registry filing.", "director resignation and statutory handoff"),
            ("corporate_bylaws_charter", "Corporate Bylaws & Governance Manual", "Comprehensive internal corporate governance rules covering board committees, voting thresholds, and seal custody.", "internal corporate governance and bylaws"),
            ("audit_committee_charter", "Board Audit & Risk Committee Charter", "Terms of reference governing financial reporting oversight, external auditor independence, and internal controls.", "board audit committee oversight"),
            ("conflict_of_interest_decl", "Annual Conflict of Interest Disclosure Form", "Mandatory director and executive disclosure of related-party interests, external directorships, and gifts.", "conflict of interest and related-party disclosure"),
            ("shareholder_proxy_form", "Instrument of Proxy (Shareholder Voting)", "Formal proxy appointment instrument authorizing an alternate representative to attend and vote at general meetings.", "shareholder proxy representation"),
            ("unanimous_written_consent", "Unanimous Written Resolution of Directors", "Circulated written resolution carrying the same legal force as a resolution passed at a convened board meeting.", "written board resolution in lieu of meeting"),
            ("statutory_register_template", "Statutory Register of Directors & Shareholders", "Compliant corporate secretarial register tracking shareholdings, transfers, beneficial ownership, and officers.", "statutory corporate secretarial recordkeeping"),
            ("corporate_seal_custody_policy", "Company Seal & Digital Stamp Custody Policy", "Governance policy controlling physical and TrustSeal cryptographic seal authorization, logging, and audit.", "official corporate seal custody and governance"),
        ],
    ),
    (
        "Human Resources & People Ops",
        "hr, people, policy",
        [
            ("formal_job_offer_letter", "Formal Offer of Employment Letter", "Executive offer letter detailing role, reporting line, compensation, probation period, start date, and acceptance.", "candidate employment offer and onboarding"),
            ("probation_review_evaluation", "30/60/90-Day Probation Performance Review", "Structured probationary evaluation rubric covering core competencies, deliverables, feedback, and recommendation.", "employee probation performance evaluation"),
            ("probation_confirmation_letter", "Letter of Confirmation of Permanent Employment", "Official HR letter confirming successful completion of probation and transition to permanent staff status.", "probation completion and permanent confirmation"),
            ("probation_extension_notice", "Notice of Probation Period Extension", "Formal notice extending probation with documented performance objectives, support plan, and review date.", "structured probation extension and coaching"),
            ("annual_performance_appraisal", "Annual Performance Appraisal & Development Plan", "Comprehensive yearly employee review measuring KPIs, leadership values, career goals, and merit review.", "annual employee performance management"),
            ("performance_improvement_plan", "Performance Improvement Plan (PIP)", "Documented 30/60/90-day corrective performance roadmap with measurable milestones and weekly check-ins.", "structured employee performance remediation"),
            ("disciplinary_warning_letter", "Formal Written Disciplinary Warning", "Compliant HR disciplinary notice documenting policy breach, employee hearing record, and expected conduct.", "formal workplace disciplinary governance"),
            ("employee_handbook_master", "Comprehensive Employee Handbook & HR Manual", "Master workplace guide covering working hours, leave, benefits, conduct, grievance procedures, and IT rules.", "company-wide HR policies and workplace standards"),
            ("remote_hybrid_work_policy", "Remote & Hybrid Work Policy", "Clear standards for flexible work schedules, home-office ergonomics, cybersecurity, and collaboration.", "hybrid and remote workforce governance"),
            ("code_of_conduct_ethics", "Corporate Code of Business Conduct & Ethics", "Mandatory integrity charter covering anti-harassment, anti-bribery, confidentiality, and fair dealing.", "workplace ethics and corporate integrity"),
            ("whistleblower_speakup_policy", "Whistleblower & Speak-Up Protection Policy", "Confidential reporting channels, non-retaliation guarantees, and independent investigation protocols.", "confidential ethics reporting and non-retaliation"),
            ("leave_absence_policy", "Annual, Sick, Parental & Study Leave Policy", "Clear statutory and company leave entitlements, approval workflows, accrual rules, and handover standards.", "employee leave administration"),
            ("onboarding_checklist_pack", "New Hire 30-Day Onboarding Checklist", "Cross-functional HR, IT, security, and manager onboarding checklist for seamless new employee ramp-up.", "structured new employee onboarding"),
            ("exit_interview_guide", "Employee Exit Interview & Offboarding Form", "Structured departure feedback questionnaire, asset return verification, access revocation, and final dues.", "employee offboarding and knowledge retention"),
            ("employment_verification_ltr", "Official Letter of Employment & Reference", "Formal HR confirmation of employment dates, role, and standing for embassies, banks, or landlords.", "official employment confirmation letter"),
        ],
    ),
    (
        "Finance, Accounting & Credit",
        "finance, accounting, billing",
        [
            ("commercial_tax_invoice", "Official Commercial & Tax Invoice", "Compliant VAT/tax invoice template with itemized line items, tax registration, bank remittance, and due date.", "commercial invoicing and revenue collection"),
            ("proforma_invoice_quote", "Commercial Proforma Invoice", "Pre-shipment / pre-engagement proforma invoice detailing scope, currency, taxes, and payment instructions.", "commercial proforma billing"),
            ("payment_reminder_notice", "Account Receivable Payment Reminder (1st / 2nd / Final)", "Escalating professional credit-control collection letters preserving client goodwill while securing settlement.", "accounts receivable credit control"),
            ("formal_demand_letter", "Formal Final Demand for Overdue Debt", "Pre-litigation statutory demand letter setting final 7/14-day settlement deadline before legal recovery.", "overdue commercial debt recovery"),
            ("purchase_order_standard", "Official Company Purchase Order (PO)", "Authorized procurement purchase order specifying SKU/deliverables, pricing, delivery terms, and PO conditions.", "authorized corporate procurement"),
            ("expense_reimbursement_policy", "Travel & Expense Reimbursement Policy", "Clear per-diem caps, receipt requirements, approval thresholds, and non-reimbursable expense rules.", "corporate travel and expense controls"),
            ("capex_business_case", "Capital Expenditure (CapEx) Approval Request", "Investment justification memo detailing ROI, payback period, vendor quotes, and CFO/Board sign-off.", "capital expenditure authorization"),
            ("monthly_financial_report", "Monthly Management Accounts & Executive Commentary", "Structured CFO narrative covering P&L variance, cash runway, AR/AP aging, and balance sheet highlights.", "monthly executive financial reporting"),
            ("internal_financial_controls", "Internal Financial Controls & Treasury Policy", "Segregation of duties, dual payment approval matrices, bank reconciliation cadence, and fraud prevention.", "treasury and internal financial controls"),
            ("vendor_kyc_onboarding_form", "Supplier Onboarding, KYC & Bank Verification Form", "Structured vendor due diligence form capturing tax PIN, incorporation docs, beneficial owners, and bank details.", "supplier KYC and anti-fraud onboarding"),
            ("credit_application_form", "Commercial Customer Credit Application", "Trade credit vetting form capturing trade references, financial statements, credit limit, and guarantee.", "commercial trade credit underwriting"),
            ("credit_note_adjustment", "Official Commercial Credit Note", "Formal billing adjustment document referencing original invoice, credit reason, and VAT adjustment.", "commercial billing adjustment"),
            ("petty_cash_policy_log", "Petty Cash Imprest Policy & Reconciliation", "Cash float limits, voucher authorization rules, surprise count procedures, and monthly replenishment.", "petty cash custody and reconciliation"),
            ("annual_audit_readiness_pack", "Year-End Statutory Audit Readiness Checklist", "Comprehensive PBC (Prepared by Client) schedule for smooth external statutory financial audits.", "year-end statutory audit preparation"),
            ("debt_restructuring_proposal", "Commercial Debt Settlement & Payment Plan", "Structured installment repayment proposal with default acceleration and release upon final settlement.", "commercial payment restructuring"),
        ],
    ),
    (
        "Sales, Proposals & Client Success",
        "sales, proposal, commercial",
        [
            ("executive_sales_proposal", "Comprehensive Enterprise Sales Proposal", "Persuasive commercial proposal covering client pain points, proposed architecture, timeline, investment, and ROI.", "enterprise commercial sales proposals"),
            ("rfp_tender_response", "Formal RFP / Public Tender Response Document", "Structured tender submission addressing compliance matrix, technical methodology, team CVs, and pricing.", "formal RFP and tender submissions"),
            ("commercial_quotation", "Official Commercial Quotation & Pricing Schedule", "Itemized validity-bound commercial quote with optional add-ons, delivery lead times, and terms.", "commercial pricing and quotations"),
            ("client_onboarding_playbook", "Enterprise Customer Onboarding Playbook", "Structured implementation kickoff guide covering governance roles, training milestones, and go-live criteria.", "enterprise customer onboarding"),
            ("quarterly_business_review", "Quarterly Business Review (QBR) Executive Report", "Account health deck narrative covering usage metrics, SLA attainment, ROI realized, and next-quarter roadmap.", "strategic account management and QBRs"),
            ("contract_renewal_proposal", "Annual Account Renewal & Expansion Proposal", "Proactive renewal brief highlighting delivered value, upgraded tier benefits, and multi-year loyalty pricing.", "commercial subscription and contract renewals"),
            ("price_adjustment_notice", "Official Annual Price Adjustment Notice", "Transparent, relationship-preserving customer notice communicating CPI/tier pricing updates ahead of renewal.", "commercial pricing communication"),
            ("company_capability_profile", "Corporate Capability Statement & Company Profile", "Executive overview of company credentials, certifications, flagship projects, leadership, and client roster.", "corporate credentials and sales collateral"),
            ("partnership_pitch_letter", "Strategic Alliance & Partnership Proposal", "Formal outreach proposing co-selling, integration, or regional distribution collaboration.", "strategic partner acquisition"),
            ("customer_welcome_letter", "New Client Executive Welcome & Kickoff Letter", "Warm executive welcome introducing the delivery team, escalation contacts, and first-week milestones.", "new client welcome and relationship kickoff"),
            ("service_recovery_apology", "Executive Service Incident & Apology Letter", "Accountable customer communication detailing incident root cause, remediation actions, and service credit.", "executive customer service recovery"),
            ("client_case_study_brief", "Customer Success Case Study Template", "Structured challenge-solution-results narrative with quantified business metrics and client quote approval.", "customer success marketing proof"),
            ("sla_monthly_performance", "Monthly SLA & Service Performance Report", "Transparent operational report tracking uptime, response times, ticket resolution, and continuous improvement.", "monthly customer SLA reporting"),
            ("customer_feedback_survey", "Enterprise NPS & Client Satisfaction Survey", "Structured annual client experience questionnaire measuring delivery quality, responsiveness, and value.", "customer experience measurement"),
            ("account_closure_notice", "Formal Notice of Account Closure & Data Export", "Clear offboarding notice detailing final billing reconciliation, data export window, and archive deletion.", "orderly customer offboarding"),
        ],
    ),
    (
        "Marketing, PR & Communications",
        "marketing, pr, brand",
        [
            ("annual_marketing_plan", "Annual Marketing & Demand Generation Plan", "Comprehensive campaign calendar, ICP personas, channel mix, budget allocation, and pipeline attribution KPIs.", "annual marketing and pipeline strategy"),
            ("official_press_release", "Official Corporate Press Release", "AP-style media announcement with headline, dateline, executive quotes, boilerplate, and media contact.", "media and public relations announcements"),
            ("product_launch_playbook", "Product & Service Go-To-Market Launch Plan", "Cross-functional launch checklist spanning positioning, sales enablement, PR, webinars, and launch metrics.", "product go-to-market execution"),
            ("brand_identity_guidelines", "Corporate Brand Identity & Style Guidelines", "Authoritative brand book covering logo usage, typography, color tokens, tone of voice, and stationery rules.", "brand consistency and visual identity"),
            ("crisis_communications_plan", "Corporate Crisis Communications Playbook", "Rapid-response media protocol, designated spokespersons, holding statements, and stakeholder escalation.", "reputation management and crisis PR"),
            ("social_media_policy", "Corporate Social Media & Employee Advocacy Policy", "Clear guardrails for official brand accounts, employee disclosures, confidentiality, and moderation.", "social media governance and brand safety"),
            ("event_sponsorship_deck", "Corporate Event Sponsorship Prospectus", "Structured sponsorship tiers (Platinum/Gold/Silver), audience demographics, brand exposure, and ROI.", "event sponsorship monetization"),
            ("internal_all_hands_memo", "Executive All-Hands & Quarterly Update Memo", "Transparent leadership communication covering company performance, strategic wins, and upcoming priorities.", "internal executive communications"),
            ("rebranding_announcement", "Official Corporate Rebranding Announcement", "Stakeholder communication explaining brand evolution, visual identity updates, and continuity of service.", "brand transition communications"),
            ("media_kit_fact_sheet", "Corporate Media Kit & Press Fact Sheet", "Journalist-ready company overview, executive bios, key milestones, high-res asset links, and press contacts.", "media relations and press outreach"),
            ("webinar_event_brief", "Executive Webinar & Roundtable Production Brief", "End-to-end event blueprint covering topic agenda, speaker briefing, promotion schedule, and lead follow-up.", "B2B thought leadership events"),
            ("testimonial_release_form", "Client Logo & Testimonial Publication Release", "Formal written authorization to publish customer name, logo, quotes, and case study metrics.", "marketing rights and client approvals"),
            ("editorial_content_calendar", "Thought Leadership & Content Strategy Brief", "SEO pillars, whitepaper schedule, executive bylines, and distribution workflow across digital channels.", "content marketing and thought leadership"),
            ("public_statement_template", "Official Corporate Public Statement", "Measured executive statement template for regulatory updates, industry positions, or community initiatives.", "official public affairs communication"),
            ("trade_show_execution_plan", "Trade Show & Exhibition Execution Plan", "Booth logistics, staffing roster, demo scripts, lead capture workflow, and post-event ROI tracking.", "exhibition and field marketing"),
        ],
    ),
    (
        "Operations, SOPs & Quality",
        "operations, sop, quality",
        [
            ("master_sop_template", "Standard Operating Procedure (SOP) Master", "ISO-ready SOP format with purpose, scope, RACI roles, step-by-step instructions, exceptions, and revision log.", "standardized operational procedures"),
            ("iso9001_quality_manual", "ISO 9001 Quality Management Manual", "Comprehensive QMS manual defining quality policy, process interactions, document control, and continual improvement.", "ISO 9001 quality management"),
            ("incident_rca_report", "Operational Incident & Root Cause Analysis (RCA)", "Structured 5-Whys / fishbone post-mortem detailing timeline, customer impact, root cause, and CAPA actions.", "incident investigation and CAPA"),
            ("change_management_rfc", "Operational Change Management Request (RFC)", "Formal change control form documenting impact analysis, rollback plan, risk level, and CAB approval.", "controlled operational change management"),
            ("procurement_tendering_policy", "Corporate Procurement & Tendering Policy", "Competitive bidding thresholds, conflict checks, evaluation committees, and vendor award governance.", "transparent corporate procurement"),
            ("vendor_performance_scorecard", "Quarterly Vendor Performance Scorecard", "Objective supplier evaluation rubric measuring on-time delivery, defect rate, SLA adherence, and responsiveness.", "supplier quality and performance management"),
            ("occupational_health_safety", "Occupational Health & Safety (OSH) Policy", "Workplace safety standards, hazard reporting, PPE compliance, emergency drills, and statutory injury logging.", "workplace health and safety compliance"),
            ("inventory_audit_sop", "Inventory Control & Cycle Count SOP", "Warehouse stock-take procedures, variance investigation thresholds, shrinkage reporting, and ERP reconciliation.", "inventory accuracy and warehouse controls"),
            ("fleet_dispatch_manual", "Fleet Management & Dispatch Operations Manual", "Vehicle inspection checklists, driver safety rules, fuel monitoring, GPS compliance, and accident protocols.", "commercial fleet and logistics operations"),
            ("quality_assurance_signoff", "Quality Assurance Inspection & Release Certificate", "Formal QA verification record confirming batch/deliverable conformity against technical specifications.", "quality inspection and release control"),
            ("facility_safety_checklist", "Monthly Facility & Fire Safety Inspection", "Structured premises audit covering fire extinguishers, exits, electrical panels, first-aid, and hygiene.", "premises safety compliance"),
            ("operational_handover_doc", "Operational Shift & Role Handover Document", "Clear continuity brief transferring active tasks, pending escalations, credentials, and key contacts.", "seamless operational handover"),
            ("corrective_action_capa", "Corrective & Preventive Action (CAPA) Plan", "Formal non-conformance tracking document assigning root-cause fixes, verification dates, and effectiveness audit.", "ISO non-conformance and CAPA tracking"),
            ("document_control_policy", "Enterprise Document Control & Retention Policy", "Naming conventions, version numbering, approval workflows, archival schedules, and TrustSeal vault rules.", "enterprise document lifecycle governance"),
            ("supply_chain_contingency", "Supply Chain Disruption & Alternate Sourcing Plan", "Critical component mapping, safety stock buffers, pre-qualified backup vendors, and rapid switchover SOP.", "supply chain risk mitigation"),
        ],
    ),
    (
        "IT, Cybersecurity & Privacy",
        "it, security, privacy",
        [
            ("infosec_policy_iso27001", "Information Security Policy (ISO 27001)", "Master ISMS policy governing asset classification, encryption, access control, incident reporting, and audits.", "enterprise information security governance"),
            ("data_protection_privacy", "Corporate Data Protection & Privacy Policy", "GDPR and regional Data Protection Act compliant policy covering lawful basis, DSARs, retention, and DPO duties.", "statutory personal data privacy compliance"),
            ("acceptable_use_policy", "IT Acceptable Use Policy (AUP)", "Clear rules governing corporate laptops, email, cloud apps, software installation, and prohibited activities.", "workplace IT acceptable use"),
            ("data_breach_response_plan", "Cybersecurity & Data Breach Response Plan", "Step-by-step containment, forensic preservation, 72-hour regulator notification, and affected-party notice.", "cyber incident and breach response"),
            ("access_control_policy", "Identity, Access Control & MFA Policy", "Least-privilege RBAC, mandatory MFA, privileged session logging, quarterly access reviews, and offboarding.", "identity and access management"),
            ("byod_endpoint_policy", "BYOD & Mobile Endpoint Security Policy", "MDM enrollment, full-disk encryption, remote wipe authorization, and corporate data containerization rules.", "mobile and endpoint security"),
            ("ai_governance_policy", "Enterprise AI & Generative AI Acceptable Use Policy", "Safe corporate AI adoption guardrails prohibiting confidential data leakage, requiring human review and audit.", "responsible enterprise AI governance"),
            ("disaster_recovery_plan", "IT Disaster Recovery & Backup Plan (DRP)", "Automated backup schedules, off-site replication, failover runbooks, RPO/RTO targets, and annual DR drills.", "IT disaster recovery and backup resilience"),
            ("software_release_sop", "Software Release, CI/CD & Deployment SOP", "Code review gates, security scanning, staging validation, change approval, and production rollback runbook.", "controlled software release engineering"),
            ("vendor_security_assessment", "Third-Party Vendor Security Questionnaire", "Comprehensive SaaS/vendor due diligence checklist covering SOC 2, encryption, pentests, and sub-processors.", "third-party cyber risk assessment"),
            ("website_privacy_cookies", "Website Privacy & Cookie Notice", "Transparent public-facing privacy disclosure detailing analytics cookies, consent management, and user rights.", "public digital privacy transparency"),
            ("it_asset_handover_form", "IT Equipment Issue & Return Custody Form", "Employee acknowledgment of issued laptops, phones, serial numbers, security duties, and return condition.", "IT hardware asset custody"),
            ("system_architecture_spec", "Technical System Architecture Specification", "Structured engineering design document covering components, data flows, security boundaries, and scalability.", "technical architecture documentation"),
            ("business_impact_analysis", "IT Business Impact Analysis (BIA)", "Critical application inventory mapping downtime financial impact, dependencies, and recovery priority tiers.", "IT criticality and impact analysis"),
            ("vulnerability_remediation", "Vulnerability & Penetration Test Remediation Report", "Executive tracking report classifying findings by CVSS severity, remediation owners, SLAs, and retest proof.", "cybersecurity remediation tracking"),
        ],
    ),
    (
        "Project Management & Delivery",
        "project, delivery, pmo",
        [
            ("project_charter_master", "Executive Project Charter", "Formal project authorization defining business case, objectives, scope boundaries, budget, sponsor, and PM authority.", "project initiation and executive authorization"),
            ("project_scope_statement", "Detailed Project Scope & Deliverables Statement", "Explicit in-scope deliverables, out-of-scope exclusions, assumptions, constraints, and acceptance criteria.", "project scope baseline governance"),
            ("project_kickoff_brief", "Project Kickoff & Governance Brief", "Stakeholder alignment pack detailing communication cadence, RACI matrix, tools, and first 30-day plan.", "project kickoff and team alignment"),
            ("weekly_project_status", "Executive Weekly Project Status Report", "RAG status summary covering accomplishments, upcoming milestones, budget burn, blockers, and decisions needed.", "executive project status reporting"),
            ("raid_risk_issue_register", "Project RAID Log (Risks, Assumptions, Issues, Dependencies)", "Structured governance register tracking severity, probability, mitigation plans, owners, and target closure dates.", "project risk and issue management"),
            ("project_change_request", "Formal Project Change Request (CR)", "Documented scope, schedule, or budget change evaluation requiring sponsor and counterparty sign-off.", "formal project change control"),
            ("milestone_acceptance_cert", "Official Milestone Acceptance Certificate", "Sign-off certificate confirming deliverable inspection, defect clearance, and authorization for tranche invoicing.", "formal deliverable acceptance sign-off"),
            ("uat_signoff_certificate", "User Acceptance Testing (UAT) Sign-Off Report", "Structured UAT test summary, pass/fail defect tally, open waivers, and formal production go-live approval.", "software and system UAT acceptance"),
            ("stakeholder_comm_plan", "Stakeholder Engagement & Communication Plan", "Stakeholder power/interest mapping, reporting channels, frequency, and executive escalation matrix.", "stakeholder communication governance"),
            ("resource_capacity_plan", "Project Resource Allocation & Capacity Plan", "Role-by-role staffing forecast, allocation percentages, skill requirements, and external contractor plan.", "project workforce and capacity planning"),
            ("wbs_schedule_baseline", "Work Breakdown Structure (WBS) & Schedule Baseline", "Phased work packages, task dependencies, critical path milestones, and baseline target completion dates.", "project work breakdown and scheduling"),
            ("project_closure_report", "Project Closure & Lessons Learned Report", "Formal project wrap-up summarizing final budget vs actuals, benefits realized, archived artifacts, and lessons.", "formal project closeout and handover"),
            ("post_implementation_review", "Post-Implementation Benefits Realization Review", "90-day post-launch audit measuring actual ROI, adoption metrics, operational stability, and optimization actions.", "post-launch benefits verification"),
            ("deliverable_transmittal", "Official Deliverable Transmittal Memo", "Formal cover note accompanying submitted contract milestones, enumerating files, versions, and SHA-256 hashes.", "formal deliverable submission"),
            ("pmo_governance_standard", "PMO Project Governance & Stage-Gate Standard", "Enterprise project lifecycle methodology defining Gate 0–5 approval criteria and portfolio reporting rules.", "PMO portfolio governance"),
        ],
    ),
    (
        "Executive Letters, Memos & Notices",
        "correspondence, memo, notice",
        [
            ("executive_memorandum", "Official Executive Memorandum", "Crisp internal/external executive memo covering subject, background, analysis, decision, and action owners.", "formal executive memoranda"),
            ("company_announcement_ltr", "Official Corporate Announcement Letter", "Polished leadership letter announcing executive appointments, acquisitions, office openings, or strategic milestones.", "official corporate announcements"),
            ("letter_of_introduction", "Formal Corporate Letter of Introduction", "Executive introduction establishing corporate credentials, authorized representative identity, and engagement purpose.", "corporate introductions and representation"),
            ("letter_of_authorization", "Official Letter of Authorization & Representation", "Formal mandate empowering a named officer or agent to act, collect documents, or represent the company.", "corporate agent authorization"),
            ("cease_and_desist_notice", "Formal Cease & Desist Notice", "Assertive pre-action legal notice demanding immediate cessation of IP infringement, defamation, or breach.", "IP and commercial rights enforcement"),
            ("notice_of_breach_cure", "Formal Notice of Material Breach & Cure Window", "Contractual notice specifying breach particulars, citing clauses, and triggering the mandatory 30-day cure period.", "contractual breach enforcement"),
            ("notice_contract_renewal", "Formal Notice of Contract Renewal", "Timely written notice exercising renewal rights under an existing agreement prior to the notice-period deadline.", "contract renewal exercise"),
            ("notice_contract_suspension", "Formal Notice of Contract Suspension", "Official notice placing a contract in SUSPENDED status and pausing deliverable/SLA timers pending resumption.", "formal contract suspension notice"),
            ("notice_contract_termination", "Formal Notice of Contract Termination", "Clear statutory/contractual termination notice specifying effective date, basis, final invoicing, and handover.", "formal contract termination notice"),
            ("invitation_to_tender_itt", "Official Invitation to Tender (ITT) Letter", "Formal procurement invitation outlining tender scope, eligibility criteria, submission deadline, and evaluation.", "competitive tender invitation"),
            ("letter_of_recommendation", "Executive Letter of Recommendation", "Endorsement letter highlighting verified achievements, character, leadership impact, and contact verification.", "executive professional endorsement"),
            ("regulatory_cover_letter", "Official Regulatory Filing Cover Letter", "Formal transmittal letter accompanying statutory returns, license renewals, or compliance filings to regulators.", "regulatory authority correspondence"),
            ("statutory_declaration", "Statutory Declaration & Corporate Affidavit", "Sworn declaration template verifying corporate facts, compliance standing, or document authenticity.", "sworn corporate statutory declaration"),
            ("thank_you_executive_ltr", "Executive Appreciation & Partnership Letter", "Refined post-closing or milestone appreciation letter reinforcing long-term institutional relationships.", "executive relationship stewardship"),
            ("notice_address_change", "Official Notice of Registered Office / Bank Change", "Formal notification to clients, vendors, and regulators regarding updated registered address or banking details.", "corporate administrative notifications"),
        ],
    ),
    (
        "Real Estate & Office Admin",
        "real-estate, admin, facilities",
        [
            ("notice_to_vacate_premises", "Formal Notice to Vacate Commercial Premises", "Clear tenancy notice confirming vacation date, make-good obligations, key handover, and deposit refund.", "commercial lease exit notice"),
            ("rent_escalation_notice", "Official Notice of Scheduled Rent Adjustment", "Contract-aligned landlord notice communicating scheduled annual lease escalation and updated invoice schedule.", "commercial rent adjustment notice"),
            ("lease_renewal_request", "Formal Commercial Lease Renewal Request", "Tenant notice exercising option to renew commercial lease and proposing updated terms or fit-out allowance.", "commercial lease renewal exercise"),
            ("premises_handover_report", "Premises Handover, Meter & Snagging Report", "Joint move-in/move-out inspection schedule recording utility readings, fixtures, defects, and key inventory.", "property handover inspection"),
            ("office_relocation_plan", "Corporate Office Relocation & Move Plan", "Comprehensive office move checklist covering IT cabling, lease exit, movers, regulatory updates, and comms.", "corporate office relocation"),
            ("visitor_access_security", "Premises Security & Visitor Access Policy", "Reception sign-in rules, NDA badges, server room escort rules, CCTV notice, and after-hours access logs.", "physical premises security"),
            ("asset_disposal_form", "Fixed Asset Write-Off & Disposal Authorization", "Audit-ready form recording asset tag, net book value, disposal method (sale/recycle), and CFO approval.", "fixed asset disposal governance"),
            ("meeting_agenda_actions", "Executive Meeting Agenda & Action Tracker", "Structured meeting template with timed topics, pre-reads, decisions logged, and accountable action owners.", "effective executive meeting management"),
            ("emergency_evacuation_plan", "Office Fire & Emergency Evacuation Plan", "Floor warden roles, assembly points, emergency contacts, first-aid stations, and semi-annual drill records.", "workplace emergency preparedness"),
            ("maintenance_work_order", "Facility Maintenance & Repair Work Order", "Structured maintenance request logging asset location, priority, vendor quote, completion sign-off, and cost.", "facility maintenance administration"),
            ("equipment_loan_agreement", "Internal Equipment Loan & Return Form", "Custody receipt for cameras, projectors, pool vehicles, or test hardware checked out for field assignments.", "shared equipment custody"),
            ("sublease_consent_request", "Request for Landlord Consent to Sublease / Fit-Out", "Formal tenant application seeking written landlord approval for workspace partitioning, signage, or subletting.", "commercial lease consent application"),
            ("travel_authorization_form", "Corporate International Travel Authorization", "Pre-trip approval form covering business itinerary, estimated budget, travel insurance, and emergency contacts.", "corporate travel pre-approval"),
            ("mailroom_courier_sop", "Reception, Mailroom & Legal Service SOP", "Chain-of-custody procedure for logging incoming legal notices, couriers, cheques, and sensitive parcels.", "mailroom and legal notice custody"),
            ("parking_access_policy", "Corporate Parking & Access Card Policy", "Allocation rules, lost-card replacement procedures, EV charging etiquette, and visitor bay reservations.", "office administrative operations"),
        ],
    ),
    (
        "VitalWorks, VitalWills & VitalReturns Docs",
        "vitalworks, vitalwills, vitalreturns",
        [
            ("vitalworks_project_brief", "VitalWorks Executive Project Governance Brief", "Flagship VitalWorks project initiation brief aligning scope, milestone payments, SLA metrics, and risk controls.", "VitalWorks enterprise project governance"),
            ("vitalworks_clinical_sop", "VitalWorks Clinical Operations & Compliance SOP", "VitalWorks healthcare delivery standard operating procedure covering patient privacy, audit logs, and QA.", "VitalWorks clinical systems operations"),
            ("vitalworks_iso_manual", "VitalWorks ISO 27001 & Quality Compliance Policy", "Master VitalWorks security and quality assurance policy for enterprise and regulated client deployments.", "VitalWorks ISO security and quality"),
            ("vitalworks_vendor_charter", "VitalWorks Approved Supplier Governance Charter", "Standards for VitalWorks subcontractors covering ethics, safety, delivery SLAs, and cryptographic billing.", "VitalWorks supply chain governance"),
            ("vitalworks_board_pack", "VitalWorks Quarterly Board & Operations Report", "Executive summary of VitalWorks portfolio revenue, active project deliverables, probation cohorts, and risks.", "VitalWorks executive board reporting"),
            ("vitalwills_estate_intake", "VitalWills Comprehensive Estate Planning Intake Form", "Structured client questionnaire capturing family tree, assets, liabilities, guardians, executors, and wishes.", "VitalWills estate planning discovery"),
            ("vitalwills_asset_inventory", "VitalWills Schedule of Assets & Beneficiaries", "Detailed inventory of real property, bank accounts, investments, digital assets, and beneficiary allocations.", "VitalWills estate asset scheduling"),
            ("vitalwills_executor_checklist", "VitalWills Executor Probate & Administration Checklist", "Step-by-step fiduciary roadmap from death certificate and will custody release to probate grant and distribution.", "VitalWills probate administration"),
            ("vitalwills_beneficiary_notice", "VitalWills Official Notice to Estate Beneficiaries", "Formal fiduciary letter notifying beneficiaries of testamentary entitlements, timelines, and tax clearance.", "VitalWills beneficiary communications"),
            ("vitalwills_custody_receipt", "VitalWills Official Will Custody & Vault Receipt", "Certified receipt confirming physical and TrustSeal cryptographic preservation of an executed Last Will.", "VitalWills testamentary vault custody"),
            ("vitalreturns_tax_checklist", "VitalReturns Annual Corporate Tax Compliance Checklist", "End-to-end statutory tax preparation checklist covering CIT, VAT, WHT, PAYE, and transfer pricing schedules.", "VitalReturns annual tax readiness"),
            ("vitalreturns_audit_rep_ltr", "VitalReturns Management Representation Letter", "Formal ISA-aligned management representation letter confirming completeness of financial records for audit.", "VitalReturns statutory audit representations"),
            ("vitalreturns_vat_memo", "VitalReturns VAT Reconciliation & Refund Memo", "Technical memorandum supporting input/output VAT reconciliation, exempt supplies, and revenue refund claims.", "VitalReturns indirect tax advisory"),
            ("vitalreturns_payroll_summary", "VitalReturns Monthly Payroll & Statutory Remittance Pack", "Executive payroll sign-off summary detailing gross pay, PAYE, social security, pension, and net disbursements.", "VitalReturns managed payroll reporting"),
            ("vitalreturns_objection_cover", "VitalReturns Notice of Tax Objection Cover Letter", "Formal revenue authority submission letter setting out statutory grounds of objection and supporting schedules.", "VitalReturns tax controversy representation"),
        ],
    ),
]


DOC_EDITIONS: list[tuple[str, str, str]] = [
    ("standard", "Standard Corporate", "Balanced institutional format ready for immediate corporate use across all departments."),
    ("executive", "Executive Boardroom Edition", "Elevated C-suite and board-ready edition with formal governance sign-off and KPI tables."),
    ("enterprise_iso", "Enterprise ISO / Audit-Ready", "Includes full ISO document control table, compliance attestation, and 7-year TrustSeal archival rules."),
    ("sme_lean", "SME Rapid-Deploy Edition", "Streamlined, practical format tailored for agile SMEs and fast-growing teams."),
    ("regional_eac", "East Africa / Regional Statutory", "Aligned with regional East African corporate, tax, labor, and data protection practices."),
    ("international", "International / Global Standard", "Cross-border corporate edition aligned with UK/EU/US multinational governance standards."),
]


def _department_deep_module(dept: str, focus: str) -> str:
    """Return rich, department-tailored substantive clauses so every document is multi-page & domain-specific."""
    dl = (dept or "").lower()
    if "board" in dl or "governance" in dl:
        return (
            "<h2>5. Corporate Governance, Board Quorum &amp; Statutory Compliance</h2>"
            "<p>5.1 <strong>Board Authority &amp; Fiduciary Duty.</strong> All resolutions, charters, and delegations recorded herein are exercised pursuant to the Articles of Association of " + _field("organization_name") + " and applicable Companies Act fiduciary duties of care, skill, and loyalty.</p>"
            "<p>5.2 <strong>Quorum, Voting &amp; Conflict of Interest.</strong> A duly constituted quorum of at least fifty percent (50%) of eligible Directors (minimum two Directors, or the Sole Member in an SMC) shall be present. Any Director holding a direct or indirect material interest in a matter under consideration shall declare the nature of such interest prior to deliberation and abstain from voting.</p>"
            "<p>5.3 <strong>Statutory Filing Obligations.</strong> The Company Secretary (" + _field("company_secretary") + ") shall record finalized minutes in the Statutory Minute Book within fourteen (14) days and lodge any registrable Special or Ordinary Resolutions with the Registrar of Companies within statutory timelines.</p>"
        )
    if "human resources" in dl or "hr" in dl:
        return (
            "<h2>5. Employment Standards, Probation, Welfare &amp; Statutory Deductions</h2>"
            "<p>5.1 <strong>Fair Labor &amp; Equal Opportunity.</strong> " + _field("organization_name") + " upholds non-discrimination, workplace dignity, occupational health and safety, and full compliance with national Employment Act standards.</p>"
            "<p>5.2 <strong>Probation, Performance &amp; Disciplinary Fairness.</strong> Appointments subject to probation shall receive documented 30-, 60-, and pre-confirmation reviews. Any disciplinary or grievance proceeding shall observe natural justice: written notice of allegations, fair hearing opportunity, right of representation, and documented appeal channel.</p>"
            "<p>5.3 <strong>Statutory Remittances &amp; Privacy.</strong> Payroll, PAYE income tax, social security/NSSF contributions, and medical/leave entitlements shall be administered accurately, with employee personal records safeguarded under strict data protection controls.</p>"
        )
    if "finance" in dl or "accounting" in dl:
        return (
            "<h2>5. Financial Controls, IFRS Reporting, Taxation &amp; Audit Trail</h2>"
            "<p>5.1 <strong>Accounting Standards &amp; Segregation of Duties.</strong> All financial entries, budgets, and treasury disbursements associated with " + focus + " shall conform to International Financial Reporting Standards (IFRS) and enforce strict segregation between initiation, verification, approval, and payment release.</p>"
            "<p>5.2 <strong>Delegated Financial Authority Matrix.</strong></p>"
            "<ul>"
            "  <li><strong>Tier 1 (Department Head):</strong> Operational expenditure up to " + _field("tier1_limit") + " within approved departmental budget.</li>"
            "  <li><strong>Tier 2 (Chief Financial Officer / Finance Director):</strong> Commitments between Tier 1 ceiling and " + _field("tier2_limit") + ", including tax and supplier credit terms.</li>"
            "  <li><strong>Tier 3 (Managing Director / Board Finance Committee):</strong> Capital expenditure, unbudgeted variances exceeding 10%, and credit facilities above Tier 2 limits.</li>"
            "</ul>"
            "<p>5.3 <strong>Tax &amp; Statutory Compliance.</strong> All invoices, credit notes, VAT/WHT schedules, and supporting vouchers shall be reconciled monthly and archived for a minimum of seven (7) statutory years.</p>"
        )
    if "it" in dl or "cybersecurity" in dl or "data" in dl:
        return (
            "<h2>5. Information Security, ISO 27001 Controls &amp; Incident Response</h2>"
            "<p>5.1 <strong>Zero-Trust &amp; Least Privilege.</strong> Systems, repositories, and endpoints supporting " + focus + " shall enforce Multi-Factor Authentication (MFA), Role-Based Access Control (RBAC), AES-256 encryption at rest, and TLS 1.3 encryption in transit.</p>"
            "<p>5.2 <strong>Data Classification &amp; Breach Notification.</strong> Information assets shall be classified as Public, Internal, Confidential, or Restricted. Any suspected personal data breach or security incident shall be triaged within two (2) hours, contained immediately, and reported to the Data Protection Officer and relevant supervisory authority within seventy-two (72) hours where legally required.</p>"
            "<p>5.3 <strong>Business Continuity &amp; Backups.</strong> Critical databases and TrustSeal vaults shall maintain automated encrypted daily backups with quarterly disaster-recovery restoration testing (RPO &lt;= 4 hours, RTO &lt;= 8 hours).</p>"
        )
    if "vitalworks" in dl or "vitalwills" in dl or "vitalreturns" in dl:
        return (
            "<h2>5. Institutional Practice Standards, Fiduciary Care &amp; Quality Assurance</h2>"
            "<p>5.1 <strong>Practice Domain Excellence.</strong> This document governs flagship institutional delivery across " + focus + ", adhering to ISO 27001 security controls, statutory fiduciary duties, client confidentiality, and verifiable audit trails.</p>"
            "<p>5.2 <strong>Client Intake, Verification &amp; Custody Controls.</strong> All client instructions, identity documents, asset schedules, tax filings, or project deliverables shall undergo dual-partner quality review prior to external release or statutory submission.</p>"
            "<p>5.3 <strong>Cryptographic Vault Preservation.</strong> Executed originals, client acknowledgments, and regulatory receipts shall be sealed with TrustSeal SHA-256 integrity hashes and retained in tamper-evident evidence storage for statutory audit inspection.</p>"
        )
    return (
        "<h2>5. Operational Governance, Quality Standards &amp; Service Delivery Controls</h2>"
        "<p>5.1 <strong>Institutional Execution Standard.</strong> All teams, vendors, and stakeholders executing " + focus + " shall adhere to documented quality benchmarks, transparent milestone tracking, and ethical business conduct policies of " + _field("organization_name") + ".</p>"
        "<p>5.2 <strong>Resource Allocation &amp; Budget Governance.</strong> Approved resources, timelines, and operational budgets (" + _field("budget_amount") + ") shall be monitored monthly against baseline forecasts. Variances exceeding ten percent (10%) require documented corrective action plans signed off by the Executive Sponsor.</p>"
        "<p>5.3 <strong>Stakeholder Communication &amp; Escalation Protocol.</strong> Routine operational updates shall be issued bi-weekly; high-severity risks, regulatory blockers, or commercial disputes shall be escalated within twenty-four (24) hours through the designated Governance Lead.</p>"
    )


def render_business_doc_html(entry: dict[str, Any]) -> str:
    """Generate a comprehensive, multi-page (4–5 page) ready-to-use company document HTML."""
    if entry.get("is_ursb_obrs"):
        from app.services.ursb_uganda_catalog import render_ursb_obrs_html

        return render_ursb_obrs_html(entry)
    if entry.get("is_policy_guideline"):
        from app.services.policies_guidelines_catalog import render_policy_guideline_html

        return render_policy_guideline_html(entry)

    title_u = _html.escape(entry["name"].upper())
    dept = _html.escape(entry["category"])
    ed = _html.escape(entry["edition"])
    focus = _html.escape(entry["focus"])
    ed_note = _html.escape(entry["edition_note"])
    summary = _html.escape(entry["summary"])
    dept_mod = _department_deep_module(entry["category"], focus)

    return f"""<h1>{title_u}</h1>
<blockquote>
  <p><strong>Document Ref:</strong> {_field('document_ref')} &nbsp;·&nbsp; <strong>Version:</strong> 1.0 (Master Institutional Edition) &nbsp;·&nbsp; <strong>Effective Date:</strong> {_field('effective_date')}</p>
  <p><strong>Organization:</strong> {_field('organization_name')} &nbsp;·&nbsp; <strong>Department:</strong> {dept} &nbsp;·&nbsp; <strong>Document Owner:</strong> {_field('owner_name')}</p>
  <p><strong>Edition / Standard:</strong> {ed} &nbsp;·&nbsp; <strong>Next Review Date:</strong> {_field('review_date')} &nbsp;·&nbsp; <strong>Classification:</strong> Confidential — Authorized Use</p>
</blockquote>

<h2>1. Executive Summary &amp; Strategic Mandate</h2>
<p>1.1 <strong>Institutional Purpose.</strong> This document establishes the comprehensive, authoritative corporate framework, operational standard, and governance record for <strong>{focus}</strong> across {_field('organization_name')}. {summary}</p>
<p>1.2 <strong>Edition Governance Benchmark.</strong> {ed_note} All officers, department heads, project leads, and external advisers engaging with this subject matter are required to apply the standards, workflows, and compliance controls set forth herein.</p>
<p>1.3 <strong>Strategic Alignment.</strong> The provisions of this document align directly with {_field('organization_name')}&rsquo;s strategic plan, enterprise risk appetite, regulatory compliance register, and Project/Initiative {_field('project_name')} ({_field('project_code')}).</p>

<h2>2. Scope, Applicability &amp; Definitions</h2>
<p>2.1 <strong>Organizational Scope.</strong> This document applies across all operating divisions, wholly owned subsidiaries, branch offices, project teams, permanent and probationary staff, consultants, and authorized third-party partners acting on behalf of {_field('organization_name')}.</p>
<p>2.2 <strong>Key Institutional Definitions.</strong></p>
<ul>
  <li><strong>&ldquo;Authorized Approver&rdquo;</strong> means the executive officer, Board committee, or delegated manager ({_field('approver_name')}) empowered to grant binding approval under the Delegated Authority Matrix.</li>
  <li><strong>&ldquo;Control Owner&rdquo;</strong> means the operational lead ({_field('owner_name')}) accountable for day-to-day execution, evidence capture, and periodic effectiveness testing.</li>
  <li><strong>&ldquo;Evidence Record&rdquo;</strong> means any signed resolution, financial schedule, inspection report, audit log, or TrustSeal cryptographically sealed artifact demonstrating compliance.</li>
  <li><strong>&ldquo;Material Exception&rdquo;</strong> means any deviation from mandatory timelines, financial thresholds, or statutory rules exceeding approved tolerance limits.</li>
</ul>
<p>2.3 <strong>Exceptions &amp; Waivers.</strong> No permanent waiver of any mandatory control in this document is valid unless documented in writing, risk-assessed by Compliance ({_field('compliance_officer')}), and countersigned by {_field('approver_name')} prior to implementation.</p>

<h2>3. Governance Structure, Roles &amp; RACI Matrix</h2>
<p>3.1 <strong>Clear Accountability.</strong> To eliminate ambiguity during execution, oversight responsibilities for {focus} are allocated as follows:</p>
<ul>
  <li><strong>Executive Sponsor ({_field('sponsor_name')} — Accountable):</strong> Sets strategic direction, approves funding allocations ({_field('budget_amount')}), resolves cross-functional escalations, and signs off final institutional outputs.</li>
  <li><strong>Document &amp; Process Owner ({_field('owner_name')} — Responsible):</strong> Leads operational delivery, maintains accurate templates and records, coordinates stakeholder reviews, and tracks milestone completion.</li>
  <li><strong>Departmental &amp; Operational Leads ({_field('department_lead')} — Consulted):</strong> Provide domain input, validate resource capacity, verify technical or commercial feasibility, and enforce team compliance.</li>
  <li><strong>Compliance, Legal &amp; Internal Audit ({_field('compliance_officer')} — Informed / Assurance):</strong> Conducts independent compliance verification, validates statutory alignment, monitors TrustSeal evidence retention, and reports exceptions to the Audit &amp; Risk Committee.</li>
</ul>
<p>3.2 <strong>Governance Cadence.</strong> Operational progress shall be reviewed monthly by the Process Owner, quarterly by Executive Management, and annually by the Board or designated Oversight Committee.</p>

<h2>4. Detailed Operating Procedures, Specifications &amp; Workflow</h2>
<p>4.1 <strong>End-to-End Execution Lifecycle.</strong> All activities under {focus} shall follow four disciplined, auditable operational phases:</p>
<ol>
  <li><strong>Phase 1 — Initiation, Intake &amp; Prerequisite Verification:</strong> Confirm business justification, stakeholder mandate, statutory/regulatory prerequisites, counterparty due diligence, and approved budget envelope ({_field('budget_amount')}). Assign a unique reference code ({_field('document_ref')}) in the central register.</li>
  <li><strong>Phase 2 — Planning, Drafting &amp; Technical Execution:</strong> Assemble required source data, financial projections, legal/operational schedules, and work product in accordance with institutional templates. Document all assumptions, dependencies, and open risks transparently.</li>
  <li><strong>Phase 3 — Quality Assurance, Peer Review &amp; Formal Approval:</strong> Route completed outputs for mandatory technical, financial, and compliance review. Address all review comments, verify calculation and legal accuracy, and obtain formal sign-off from {_field('approver_name')} prior to external release or execution.</li>
  <li><strong>Phase 4 — Release, Archival &amp; Continuous Monitoring:</strong> Distribute finalized documents via authorized channels, seal the master copy in TrustSeal with cryptographic SHA-256 verification and official corporate stamp where applicable, and track post-execution obligations.</li>
</ol>
<p>4.2 <strong>Specific Operational Requirements &amp; Custom Provisions.</strong> {_field('custom_details')}</p>
<p>4.3 <strong>Documentation &amp; Record-Keeping Standards.</strong> Every action taken under this procedure must leave a clear, dated audit trail identifying the actor, decision rationale, supporting annexures, and approval timestamp.</p>

{dept_mod}

<h2>6. Key Performance Indicators (KPIs), Milestones &amp; Implementation Roadmap</h2>
<p>6.1 <strong>Target Performance Benchmarks.</strong> Effectiveness of {focus} shall be measured continuously against the following institutional KPIs:</p>
<ul>
  <li><strong>Schedule Adherence:</strong> &gt;= 95% of scheduled milestones and statutory submissions completed on or before target due dates.</li>
  <li><strong>Quality &amp; First-Time Approval Rate:</strong> &gt;= 90% of submissions passing executive/compliance review without material rework.</li>
  <li><strong>Audit &amp; Compliance Standing:</strong> Zero critical regulatory findings, late filing penalties, or undocumented policy exceptions.</li>
  <li><strong>Budget &amp; Cost Discipline:</strong> Actual expenditure maintained within &plusmn;5% of approved baseline budget ({_field('budget_amount')}).</li>
</ul>
<p>6.2 <strong>Implementation &amp; Delivery Schedule.</strong></p>
<ul>
  <li><strong>Milestone 1 — Baseline Charter &amp; Stakeholder Alignment:</strong> Target Date: {_field('milestone_1_date')} · Deliverable: Signed scope, roles, and resource plan · Owner: {_field('owner_name')}.</li>
  <li><strong>Milestone 2 — Operational Rollout &amp; Mid-Point Assurance Review:</strong> Target Date: {_field('milestone_2_date')} · Deliverable: Operational execution evidence &amp; QA checklist · Owner: {_field('department_lead')}.</li>
  <li><strong>Milestone 3 — Final Executive Sign-Off &amp; TrustSeal Vault Archival:</strong> Target Date: {_field('milestone_3_date')} · Deliverable: Executed final record sealed in Evidence Vault · Owner: {_field('approver_name')}.</li>
</ul>

<h2>7. Enterprise Risk Register &amp; Mitigation Controls</h2>
<p>7.1 <strong>Proactive Risk Management.</strong> The following primary operational, financial, and compliance risks have been identified and assigned standing mitigation controls:</p>
<ul>
  <li><strong>Regulatory &amp; Statutory Non-Compliance Risk:</strong> Mitigated through mandatory legal/compliance pre-release checks, automated calendar reminders for statutory deadlines, and annual external audit verification.</li>
  <li><strong>Operational Delay or Resource Bottleneck Risk:</strong> Mitigated through clear RACI ownership, bi-weekly milestone tracking, documented backup signatories, and early 14-day escalation triggers.</li>
  <li><strong>Financial Leakage or Unauthorized Commitment Risk:</strong> Mitigated through strict Delegated Authority limits, dual-signatory banking/contract controls, and monthly variance reconciliation.</li>
  <li><strong>Data Loss, Tampering or Confidentiality Breach Risk:</strong> Mitigated through TrustSeal AES-256 document encryption, RBAC access controls, cryptographic signature/stamp attestation, and encrypted offsite backups.</li>
</ul>

<h2>8. Confidentiality, Data Protection &amp; Intellectual Property</h2>
<p>8.1 <strong>Confidential Information Protection.</strong> All proprietary commercial data, financial models, client records, personal data, pricing schedules, and strategic plans contained in or generated under this document are strictly confidential assets of {_field('organization_name')}.</p>
<p>8.2 <strong>Personal Data Protection Compliance.</strong> Any personal data processed in connection with {focus} shall be collected lawfully for explicit purposes, minimized to strict operational necessity, secured against unauthorized access, and retained only for lawful statutory periods.</p>
<p>8.3 <strong>Intellectual Property Ownership.</strong> All templates, methodologies, work product, and institutional know-how developed under this framework remain the exclusive intellectual property of {_field('organization_name')}.</p>

<h2>9. Training, Communication &amp; Change Management</h2>
<p>9.1 <strong>Stakeholder Rollout.</strong> Upon approval, the Document Owner shall circulate this document to all impacted personnel via official internal channels and conduct a structured briefing for newly onboarded staff and operational leads.</p>
<p>9.2 <strong>Continuous Improvement.</strong> Feedback, lessons learned, and regulatory updates shall be logged in the Document Change Register and incorporated during scheduled reviews.</p>

<h2>10. Archival, Retention &amp; Cryptographic Evidence Preservation</h2>
<p>10.1 <strong>Minimum Retention Schedule.</strong> Executed copies, supporting annexures, approval logs, and audit trails shall be retained in the TrustSeal Evidence Vault for a minimum of <strong>seven (7) years</strong> (or longer where mandated by tax, corporate, employment, or sector-specific legislation).</p>
<p>10.2 <strong>Cryptographic Integrity.</strong> Every saved revision is hashed with SHA-256 and logged in an append-only tamper-evident audit chain, ensuring full evidentiary admissibility in regulatory inspections, internal audits, or dispute proceedings.</p>

<h2>11. Document Control &amp; Revision History</h2>
<ul>
  <li><strong>Version 1.0 ({_field('effective_date')}):</strong> Initial master institutional issue prepared by {_field('author_name')} and reviewed by {_field('reviewer_name')} — Status: Approved for Operational Use.</li>
  <li><strong>Scheduled Annual Review ({_field('review_date')}):</strong> Mandatory compliance &amp; operational effectiveness review coordinated by {_field('owner_name')}.</li>
</ul>

<h2>12. Formal Institutional Authorization &amp; Executive Sign-Off</h2>
<p>By signing below, the undersigned authorized officers confirm that this document has been duly reviewed, verified for operational and statutory compliance, and formally adopted for institutional execution across {_field('organization_name')}.</p>
<p><strong>Prepared &amp; Verified By (Document Owner):</strong> {_field('author_name')} &nbsp;·&nbsp; Title: {_field('author_title')} &nbsp;—&nbsp; Signature &amp; Date: ___________________________</p>
<p><strong>Reviewed By (Compliance / Finance / Legal):</strong> {_field('reviewer_name')} &nbsp;·&nbsp; Title: {_field('reviewer_title')} &nbsp;—&nbsp; Signature &amp; Date: ___________________________</p>
<p><strong>Approved &amp; Adopted By (Executive Approver):</strong> {_field('approver_name')} &nbsp;·&nbsp; Title: {_field('approver_title')} &nbsp;—&nbsp; Signature &amp; Date: ___________________________</p>
""".strip()


@lru_cache(maxsize=1)
def get_business_docs_catalog() -> list[dict[str, Any]]:
    """Build and cache 1,080 full-length Business-in-a-Box company document templates."""
    items: list[dict[str, Any]] = []
    idx = 0
    for dept, base_tags, archetypes in BUSINESS_DOC_DEPARTMENTS:
        for slug_base, title_base, summary, focus in archetypes:
            for ed_slug, ed_label, ed_note in DOC_EDITIONS:
                idx += 1
                slug = f"bib-{slug_base}__{ed_slug}"
                full_name = title_base if ed_slug == "standard" else f"{title_base} — {ed_label}"
                items.append({
                    "slug": slug,
                    "index": idx,
                    "name": full_name,
                    "title": full_name,
                    "category": dept,
                    "edition": ed_label,
                    "description": f"{summary} ({ed_label}).",
                    "summary": summary,
                    "focus": focus,
                    "edition_note": ed_note,
                    "tags": f"{base_tags}, {ed_slug}",
                    "sections": 8,
                    "is_business_box": True,
                })
    from app.services.ursb_uganda_catalog import build_ursb_obrs_entries
    from app.services.policies_guidelines_catalog import build_policies_guidelines_entries
    from app.services.sacco_policies_catalog import build_sacco_policies_entries

    items.extend(build_ursb_obrs_entries(start_index=idx + 1))
    items.extend(build_policies_guidelines_entries(start_index=len(items)))
    items.extend(build_sacco_policies_entries(start_index=len(items)))
    return items


@lru_cache(maxsize=1)
def get_business_doc_by_slug() -> dict[str, dict[str, Any]]:
    return {it["slug"]: it for it in get_business_docs_catalog()}


def get_business_doc_categories() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for it in get_business_docs_catalog():
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    return [{"category": k, "count": v} for k, v in counts.items()]


def search_business_docs_catalog(
    *,
    q: str = "",
    category: str = "",
    page: int = 1,
    per_page: int = 24,
) -> dict[str, Any]:
    """Fast in-memory search & pagination across all 1,080+ Business-in-a-Box documents."""
    all_items = get_business_docs_catalog()
    ql = (q or "").strip().lower()
    cat_f = (category or "").strip()

    tokens = [t for t in ql.split() if t]
    filtered = []
    for it in all_items:
        if cat_f and cat_f.upper() != "ALL" and it["category"] != cat_f:
            continue
        if tokens:
            hay = f"{it['name']} {it['category']} {it['edition']} {it['description']} {it['tags']}".lower()
            if not all(tok in hay for tok in tokens):
                continue
        filtered.append(it)

    total = len(filtered)
    per_page = max(6, min(100, int(per_page or 24)))
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(total_pages, int(page or 1)))
    start = (page - 1) * per_page

    return {
        "total": total,
        "catalog_total": len(all_items),
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": get_business_doc_categories(),
        "items": [
            {
                "slug": it["slug"],
                "name": it["name"],
                "category": it["category"],
                "edition": it["edition"],
                "description": it["description"],
                "tags": it["tags"],
                "sections": it["sections"],
                "preview_html": render_business_doc_html(it),
            }
            for it in filtered[start : start + per_page]
        ],
    }
