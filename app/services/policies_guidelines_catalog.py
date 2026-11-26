"""Comprehensive Company Policies & Guidelines Templates Catalog (55 Full Multi-Page Policies).

Covers:
1. Corporate Policies & Guidelines (25 core cross-enterprise governance, HR, finance, IT, risk, ESG & operations policies)
2. Organization-Type Policies & Guidelines (12 governance & operational frameworks for PLCs, SMEs/SMCs, NGOs/NPOs, SACCOs/Cooperatives, FBOs, Public Bodies, Trusts, Partnerships, Trade Associations, CBOs, Startups, and Multinationals)
3. Sector & Industry Policies & Guidelines (18 specialized regulatory & operational frameworks across Banking/FinTech, Insurance, Healthcare, Pharma, Education, IT/SaaS, Manufacturing, Construction, Agriculture, Energy/Mining, Real Estate/Hospitality, Logistics, Retail/E-Commerce, Professional Services, Media, Tourism, WASH, and Humanitarian Relief)

Every policy renders as a structured, ProseMirror-safe, multi-page (4–6 A4 pages)
institutional policy document with 12 complete sections, regulatory alignment,
mandatory directives, operational guidelines, RACI governance, compliance monitoring,
and formal adoption & employee acknowledgment sign-off blocks.
"""
from __future__ import annotations

import html as _html
from typing import Any

CAT_CORPORATE_POLICIES = "Corporate Policies & Guidelines"
CAT_ORGTYPE_POLICIES = "Organization-Type Policies & Guidelines"
CAT_SECTOR_POLICIES = "Sector & Industry Policies & Guidelines"

_ATAG = (
    '<span style="background:#eef3fa;color:#0f3b82;border:1px solid #cfdcef;'
    'padding:1px 6px;border-radius:3px;font-family:monospace;font-size:10pt;">'
)


def _f(name: str) -> str:
    return f"{_ATAG}{{{{{name}}}}}</span>"


# Spec tuple:
# (slug_base, title, category, policy_code, applicability, regulatory_alignment, summary, directives, guidelines, kpis)
PolicySpec = tuple[str, str, str, str, str, str, str, list[str], list[str], list[str]]


CORPORATE_POLICY_SPECS: list[PolicySpec] = [
    (
        "pol_corp_governance_board",
        "Corporate Governance & Board Ethics Policy",
        CAT_CORPORATE_POLICIES,
        "POL-GOV-001",
        "All Board Directors, Company Secretary, Executive Management, and Subsidiary Boards",
        "Companies Act (Cap. 106), King IV / OECD Principles of Corporate Governance, Capital Markets Governance Guidelines",
        "Establishes Board composition, fiduciary duties, committee charters, independent oversight, shareholder rights, and annual Board effectiveness evaluations.",
        [
            "Fiduciary Duty & Care: Every Director shall act honestly, in good faith, and in the best long-term interests of the organization, exercising independent judgment free of undue influence.",
            "Board Structure & Independence: The Board shall maintain an appropriate balance of Executive and Non-Executive Directors, with clear separation between Board Chair and Chief Executive Officer.",
            "Committee Delegation: Audit & Risk, Remuneration & Nominations, and Governance committees shall operate under formal Board-approved Terms of Reference with documented minutes.",
            "Quorum & Decision Integrity: Board decisions require a duly constituted quorum, advance circulation of board packs at least seven (7) days prior, and formal recording in the Statutory Minute Book.",
            "Conflict Disclosure: Directors must declare any direct or indirect material interest at the outset of every meeting and recuse themselves from deliberation and voting.",
        ],
        [
            "Convene at least four (4) scheduled quarterly Board meetings and one (1) Annual General Meeting per financial year.",
            "Conduct formal induction for all newly appointed Directors within thirty (30) days of appointment and annual continuing governance training.",
            "Perform an annual Board and Committee self-evaluation led by the Board Chair and Company Secretary, tracking remediation actions.",
            "Maintain an up-to-date Register of Directors, Beneficial Owners, and Delegated Authority Matrix sealed in TrustSeal.",
        ],
        [
            "100% timely circulation of Board packs (>= 7 days before meeting).",
            "100% annual Conflict of Interest declarations filed by all Directors and Officers.",
            ">= 90% Board attendance across all scheduled meetings and committee sessions.",
        ],
    ),
    (
        "pol_code_of_conduct_ethics",
        "Code of Business Conduct, Ethics & Workplace Integrity Policy",
        CAT_CORPORATE_POLICIES,
        "POL-ETH-002",
        "All Employees, Officers, Directors, Contractors, Interns, and Business Partners",
        "Employment Act, Anti-Corruption Act, UN Global Compact Principles, ILO Core Labour Conventions",
        "Defines mandatory standards of ethical business behavior, workplace respect, zero tolerance for harassment or discrimination, fair competition, and asset stewardship.",
        [
            "Respect & Non-Discrimination: Zero tolerance for harassment, bullying, sexual exploitation, or discrimination based on gender, race, religion, disability, age, or social status.",
            "Honest & Fair Dealing: All marketing, sales, procurement, and financial representations shall be truthful, accurate, and free from deceptive or anti-competitive practices.",
            "Protection of Assets: Company funds, intellectual property, IT systems, vehicles, and confidential data shall be used strictly for authorized organizational purposes.",
            "Zero Tolerance for Retaliation: Any individual reporting an ethical concern in good faith is strictly protected against demotion, dismissal, or harassment.",
            "Alcohol, Drugs & Workplace Safety: Personnel shall report for duty fit for work, free from impairment by alcohol or prohibited substances.",
        ],
        [
            "Require every new employee and contractor to read and sign the Code of Conduct Acknowledgment during onboarding.",
            "Deliver mandatory annual ethics refresher training with scenario-based compliance assessments.",
            "Operate confidential ethics advice and reporting channels overseen by Legal & Compliance.",
            "Investigate all alleged Code breaches promptly, objectively, and in accordance with natural justice.",
        ],
        [
            "100% annual signed Code of Conduct attestation across all active personnel.",
            "100% of reported ethics concerns acknowledged within 48 hours and triaged within 5 business days.",
            "Zero uninvestigated harassment or integrity complaints.",
        ],
    ),
    (
        "pol_anti_bribery_corruption",
        "Anti-Bribery, Anti-Corruption (ABAC) & Gifts Policy",
        CAT_CORPORATE_POLICIES,
        "POL-ABC-003",
        "All Personnel, Directors, Agents, Intermediaries, Joint Venture Partners, and Suppliers",
        "Anti-Corruption Act, UK Bribery Act 2010, US FCPA, ISO 37001 Anti-Bribery Management System",
        "Prohibits bribery, kickbacks, facilitation payments, improper political contributions, and undisclosed hospitality across all public and private sector dealings.",
        [
            "Absolute Prohibition on Bribery: Offering, promising, giving, requesting, or accepting any bribe, kickback, or undue advantage to influence a business or official decision is strictly prohibited.",
            "Ban on Facilitation Payments: Small unofficial payments to expedite routine government or administrative actions are prohibited except where immediate personal safety is threatened (and must be reported immediately).",
            "Gifts & Hospitality Thresholds: Modest, customary corporate hospitality below approved monetary limits must be transparent, proportionate, and logged in the Gifts & Hospitality Register.",
            "Third-Party Due Diligence: Agents, brokers, consultants, and lobbyists acting for the organization must pass risk-based ABAC due diligence and sign contractual anti-bribery clauses.",
            "Accurate Books & Records: No off-book accounts, false invoices, or misclassified disbursements may ever be created or approved.",
        ],
        [
            "Maintain a centralized Gifts, Hospitality & Sponsorship Register reviewed quarterly by Compliance.",
            "Require pre-approval from Compliance before offering any hospitality to a Public Official or Politically Exposed Person (PEP).",
            "Include mandatory ABAC audit and termination clauses in all supplier, distributor, and agency agreements.",
            "Conduct annual bribery risk assessments across high-risk geographies, tenders, and licensing workflows.",
        ],
        [
            "100% of high-risk third parties screened before contract execution.",
            "Zero unexplained cash disbursements or unlogged hospitality entries.",
            "100% ABAC training completion for Procurement, Sales, Finance, and Leadership.",
        ],
    ),
    (
        "pol_whistleblower_speakup",
        "Whistleblower, Speak-Up & Protected Disclosures Policy",
        CAT_CORPORATE_POLICIES,
        "POL-WHB-004",
        "All Current and Former Employees, Directors, Contractors, Volunteers, Vendors, and Beneficiaries",
        "Whistleblowers Protection Act, ISO 37002 Whistleblowing Management Systems, EU Whistleblowing Directive",
        "Provides secure, confidential, and anonymous reporting channels for suspected fraud, misconduct, safety hazards, or legal breaches with strict anti-retaliation safeguards.",
        [
            "Protected Disclosures: Covers suspected fraud, corruption, financial misstatement, data breaches, safeguarding violations, environmental harm, and abuse of authority.",
            "Confidentiality & Anonymity: Reporters may submit disclosures anonymously; the identity of named whistleblowers shall be strictly protected on a need-to-know basis.",
            "Absolute Non-Retaliation: Any act of retaliation against a good-faith reporter constitutes gross misconduct subject to summary dismissal.",
            "Independent Investigation: Disclosures involving senior executives or Board members shall escalate directly to the Chair of the Audit & Risk Committee.",
            "Good-Faith Standard: Protection applies even if an investigation finds no misconduct, provided the report was made in honest good faith.",
        ],
        [
            "Provide multiple intake channels: dedicated confidential email, encrypted ethics hotline, direct Audit Committee Chair access, and physical drop-box.",
            "Acknowledge receipt of every report within two (2) business days and issue status updates every thirty (30) days.",
            "Assign independent investigators with zero conflict of interest to preserve evidence and document findings.",
            "Report anonymized whistleblowing trends and closure rates quarterly to the Audit & Risk Committee.",
        ],
        [
            "100% of disclosures acknowledged within 48 hours.",
            "Average investigation closure time <= 45 calendar days.",
            "Zero substantiated incidents of retaliation against whistleblowers.",
        ],
    ),
    (
        "pol_conflict_of_interest",
        "Conflict of Interest & Related-Party Transactions Policy",
        CAT_CORPORATE_POLICIES,
        "POL-COI-005",
        "All Directors, Executive Officers, Procurement Staff, Finance Personnel, and All Employees",
        "Companies Act (Cap. 106), IAS 24 Related Party Disclosures, Public Ethics & Leadership Codes",
        "Governs identification, disclosure, recusal, and arm's-length approval of actual, potential, or perceived personal, financial, and familial conflicts of interest.",
        [
            "Duty of Loyalty: Personnel shall never place personal, financial, political, or family interests ahead of organizational duties.",
            "Mandatory Disclosure: Any ownership stake (>5%), outside directorship, secondary employment, or family relationship with a vendor, client, or competitor must be disclosed in writing.",
            "Procurement & Hiring Recusal: Conflicted staff shall immediately recuse themselves from vendor selection, bid evaluation, contract negotiation, or recruitment panels.",
            "Related-Party Arm's-Length Rule: Any transaction with a Director, Shareholder, or related party requires independent market valuation and disinterested Board approval.",
            "Annual & Event-Driven Updates: Declarations are mandatory upon onboarding, annually each January, and within seven (7) days of any new conflict arising.",
        ],
        [
            "Maintain a secure Register of Interests administered by the Company Secretary and Compliance Officer.",
            "Cross-check vendor onboarding KYC beneficial ownership records against the internal Employee & Director Interest Register.",
            "Issue written Conflict Management Plans defining recusal boundaries where a disclosed conflict can be safely managed.",
        ],
        [
            "100% annual COI declaration completion across Board, Management, and Procurement.",
            "100% of related-party transactions approved at arm's length and disclosed in audited financial notes.",
        ],
    ),
    (
        "pol_hr_recruitment_eeo",
        "Human Resources, Recruitment, Probation & Equal Opportunity Policy",
        CAT_CORPORATE_POLICIES,
        "POL-HR-006",
        "All Hiring Managers, HR Personnel, Applicants, Probationary Staff, and Permanent Employees",
        "Employment Act, Equal Opportunities Commission Standards, ILO Discrimination (Employment & Occupation) Convention",
        "Sets transparent, merit-based standards for workforce planning, fair recruitment, background verification, structured onboarding, probation evaluation, and career progression.",
        [
            "Merit & Equal Opportunity: Recruitment, promotion, training, and remuneration decisions shall be strictly merit-based without unlawful discrimination.",
            "Structured Selection: All vacancies require approved job descriptions, standardized competency scoring rubrics, and panel interviews.",
            "Pre-Employment Verification: Offers are conditional upon identity verification, academic/professional credential checks, and two independent references.",
            "Probation Management: New hires undergo a documented probation period (typically 3–6 months) with mandatory 30-, 60-, and pre-confirmation performance reviews.",
            "Written Contracts: Every employee shall receive a signed written Contract of Employment prior to commencement.",
        ],
        [
            "Publish approved role requisitions with clear salary bands and reporting structures.",
            "Complete 30-day HR, IT, Security, and Departmental onboarding checklists for every new starter.",
            "Conduct formal confirmation or structured extension/remediation reviews at least fourteen (14) days before probation expiry.",
            "Maintain confidential, audit-ready personnel files with statutory tax and social security registrations.",
        ],
        [
            "100% of hires onboarded with signed employment contracts and completed background checks.",
            "100% on-time probation confirmation reviews.",
            "90-day new-hire retention rate >= 92%.",
        ],
    ),
    (
        "pol_compensation_payroll_benefits",
        "Compensation, Payroll, Benefits & Statutory Deductions Policy",
        CAT_CORPORATE_POLICIES,
        "POL-HR-007",
        "All Permanent, Fixed-Term, and Executive Employees, HR, and Finance Payroll Teams",
        "Employment Act, Income Tax Act (PAYE), National Social Security Fund (NSSF) Act, Workers' Compensation Act",
        "Governs equitable salary grading, payroll processing controls, overtime, performance bonuses, statutory tax/pension remittances, and employee benefits administration.",
        [
            "Internal Equity & Market Competitiveness: Pay grades shall be structured transparently using objective job evaluation and periodic market benchmarking.",
            "Timely Payroll Disbursement: Salaries shall be paid accurately on or before the designated monthly payday via verifiable bank transfer accompanied by itemized payslips.",
            "Statutory Compliance: PAYE income tax, social security/pension contributions, local service taxes, and statutory levies shall be deducted accurately and remitted before statutory deadlines.",
            "Segregation of Payroll Duties: Payroll preparation, HR variance verification, and Finance bank release shall be performed by separate authorized officers.",
            "Salary Confidentiality: Individual compensation records are strictly confidential and protected against unauthorized disclosure.",
        ],
        [
            "Lock monthly payroll cut-off changes (new hires, exits, leave adjustments, overtime) at least five (5) working days before payday.",
            "Reconcile payroll variance reports month-over-month and obtain CFO/HR dual sign-off prior to bank upload.",
            "Archive statutory payment receipts (URA/NSSF/pension) monthly for audit and employee verification.",
        ],
        [
            "99.9% payroll accuracy rate with zero late salary disbursements.",
            "100% on-time statutory tax and social security filings (zero late penalties).",
        ],
    ),
    (
        "pol_leave_hybrid_work",
        "Leave, Attendance, Remote & Hybrid Work Guidelines",
        CAT_CORPORATE_POLICIES,
        "POL-HR-008",
        "All Full-Time, Part-Time, Probationary, Remote, and Hybrid Personnel",
        "Employment Act (Annual, Sick, Maternity & Paternity Leave Provisions), Occupational Safety Standards",
        "Defines statutory and enhanced leave entitlements, attendance standards, flexible/hybrid work eligibility, home-office cybersecurity, and business continuity coverage.",
        [
            "Statutory & Company Leave: Clear entitlements covering Annual Leave, Sick Leave, Maternity/Paternity Leave, Compassionate Leave, and Study/Exam Leave.",
            "Planned Handover: Employees taking scheduled leave exceeding three (3) days must submit a written handover brief designating a cover colleague.",
            "Hybrid & Remote Eligibility: Flexible work arrangements are granted based on role suitability, performance standing, and written manager approval.",
            "Remote Security & Ergonomics: Remote workers must use encrypted company devices, secure networks/VPN, and maintain a safe, distraction-free workspace.",
            "Core Collaboration Hours: Hybrid and remote teams shall observe defined core availability hours for synchronous meetings and client responsiveness.",
        ],
        [
            "Submit leave requests in advance through the HR/Leave system (minimum 14 days for annual leave > 5 days).",
            "Encourage employees to take at least 75% of annual leave within the leave year to prevent burnout and manage accrual liability.",
            "Review hybrid work agreements semi-annually against measurable output KPIs rather than physical presence alone.",
        ],
        [
            "100% leave balances reconciled monthly with HR and Payroll.",
            "Zero unapproved extended absences or security breaches on remote endpoints.",
        ],
    ),
    (
        "pol_hse_occupational_safety",
        "Workplace Health, Safety & Environment (HSE / OSH) Policy",
        CAT_CORPORATE_POLICIES,
        "POL-HSE-009",
        "All Employees, Contractors, Visitors, Field Personnel, and Facility Managers",
        "Occupational Safety and Health Act, ISO 45001 Occupational Health & Safety, National Environment Act",
        "Commits the organization to a zero-harm workplace through hazard identification, fire/emergency preparedness, PPE standards, incident investigation, and environmental stewardship.",
        [
            "Zero-Harm Commitment: Every worker has the right and duty to stop any unsafe activity without fear of reprisal.",
            "Risk Assessment & Controls: Routine workplace hazard inspections and task-specific Job Safety Analyses (JSA) shall precede high-risk operations.",
            "Emergency Preparedness: All premises shall maintain unobstructed fire exits, serviced fire extinguishers, first-aid kits, designated fire marshals, and semi-annual evacuation drills.",
            "Incident & Near-Miss Reporting: All workplace injuries, occupational illnesses, and near-misses must be reported within twenty-four (24) hours and investigated via Root Cause Analysis (RCA).",
            "PPE & Ergonomics: Appropriate Personal Protective Equipment and ergonomic workstations shall be provided free of charge where required by role.",
        ],
        [
            "Appoint a trained Safety Officer and cross-departmental HSE Committee meeting quarterly.",
            "Maintain a statutory Workplace Incident Register and notify labour/OSH authorities of reportable accidents within statutory windows.",
            "Require all site contractors to complete HSE induction and hold valid Workers' Compensation coverage.",
        ],
        [
            "Zero fatalities and Lost-Time Injury Frequency Rate (LTIFR) < 1.0.",
            "100% completion of semi-annual fire & emergency drills across all offices/sites.",
            "100% of reported hazards remediated within target SLA.",
        ],
    ),
    (
        "pol_disciplinary_grievance",
        "Disciplinary, Grievance & Workplace Investigation Guidelines",
        CAT_CORPORATE_POLICIES,
        "POL-HR-010",
        "All Employees, Line Managers, HR Officers, and Disciplinary / Appeal Panel Members",
        "Employment Act (Fair Termination & Disciplinary Hearing Procedures), Principles of Natural Justice",
        "Establishes fair, transparent, and legally defensible procedures for addressing workplace misconduct, poor performance, and employee grievances.",
        [
            "Natural Justice Guarantee: No formal disciplinary sanction or termination shall occur without written allegations, reasonable preparation time, a fair hearing, right to a representative, and right of appeal.",
            "Progressive Discipline: Minor infractions follow progressive coaching, verbal warning, first written warning, and final written warning before dismissal.",
            "Gross Misconduct: Serious offenses (fraud, theft, violence, severe harassment, willful data breach, bribery) may result in immediate suspension pending investigation and summary dismissal.",
            "Employee Grievance Channel: Employees may raise workplace grievances informally or formally without fear of victimization, with guaranteed written resolution timelines.",
            "Impartial Panels: Disciplinary and appeal panels shall exclude any manager directly conflicted in the underlying dispute.",
        ],
        [
            "Issue formal Hearing Notice at least forty-eight (48) hours prior to any disciplinary hearing, attaching relevant evidence.",
            "Record signed minutes of every disciplinary and grievance hearing and issue reasoned written outcomes within five (5) business days.",
            "Allow employees seven (7) business days to lodge a formal written appeal to a senior independent officer.",
        ],
        [
            "100% procedural compliance with statutory fair-hearing checklists.",
            "Zero wrongful-termination rulings resulting from procedural defects.",
        ],
    ),
    (
        "pol_infosec_cybersecurity",
        "Information Security, Cybersecurity & Acceptable Use Policy (ISO 27001)",
        CAT_CORPORATE_POLICIES,
        "POL-SEC-011",
        "All Employees, Contractors, Administrators, Cloud Services, Endpoints, and Third-Party Integrators",
        "ISO/IEC 27001:2022, NIST Cybersecurity Framework, Computer Misuse Act, Electronic Signatures Act",
        "Protects confidentiality, integrity, and availability of organizational systems and client data through Zero-Trust access, encryption, vulnerability management, and incident response.",
        [
            "Least Privilege & MFA: Multi-Factor Authentication (MFA) and Role-Based Access Control (RBAC) are mandatory for all corporate email, ERP, cloud, and TrustSeal accounts.",
            "Data Classification & Encryption: All Confidential and Restricted data must be encrypted in transit (TLS 1.3) and at rest (AES-256), with strict prohibitions on unencrypted USB transfers.",
            "Acceptable Use: Corporate IT assets must not be used for unauthorized software installation, shadow IT storage, phishing, or unlawful content.",
            "Patch & Vulnerability Management: Critical security patches shall be deployed within seventy-two (72) hours; penetration testing conducted at least annually.",
            "Incident Response & Containment: Suspected malware, phishing, credential compromise, or unauthorized access must be reported to IT Security within two (2) hours.",
        ],
        [
            "Provision and revoke user access promptly via formal Joiner-Mover-Leaver (JML) workflows (same-day revocation on exit).",
            "Run automated daily encrypted off-site backups with quarterly disaster-recovery restore verification.",
            "Conduct quarterly phishing simulations and mandatory annual cybersecurity awareness training.",
        ],
        [
            "100% MFA adoption across all corporate and privileged accounts.",
            "100% critical vulnerabilities patched within 72 hours.",
            "Zero unencrypted laptops or unmanaged production admin accounts.",
        ],
    ),
    (
        "pol_data_protection_privacy",
        "Data Protection, Privacy & Records Retention Policy",
        CAT_CORPORATE_POLICIES,
        "POL-DPO-012",
        "All Departments Processing Personal Data of Employees, Customers, Vendors, and Beneficiaries",
        "Data Protection and Privacy Act (Uganda 2019), EU GDPR, ISO/IEC 27701 Privacy Information Management",
        "Governs lawful collection, consent, purpose limitation, cross-border transfers, data subject rights, breach notification, and secure disposal of personal data.",
        [
            "Lawful Basis & Consent: Personal data shall only be collected on a documented lawful basis (consent, contract, statutory obligation, or legitimate interest) with clear privacy notices.",
            "Data Minimization & Accuracy: Collect only data strictly necessary for stated purposes and maintain mechanisms to keep records accurate and current.",
            "Data Subject Rights: Honor requests for access, correction, portability, objection, or erasure within statutory response windows (typically 30 days).",
            "Cross-Border Transfers: Personal data may only be transferred outside the jurisdiction where adequate protection or Standard Contractual Clauses are verified.",
            "72-Hour Breach Notification: Any personal data breach likely to risk individual rights shall be reported to the Data Protection Officer immediately and to the Supervisory Authority within 72 hours.",
        ],
        [
            "Maintain a live Record of Processing Activities (RoPA) and perform Data Protection Impact Assessments (DPIAs) for high-risk systems.",
            "Execute Data Processing Agreements (DPAs) with all cloud vendors and third-party processors.",
            "Enforce a documented Retention & Secure Destruction Schedule (shredding physical files, cryptographic erasure of digital archives).",
        ],
        [
            "100% of data subject requests resolved within statutory timelines.",
            "100% of third-party data processors covered by signed DPAs.",
            "Zero unreported personal data breaches.",
        ],
    ),
    (
        "pol_ai_digital_governance",
        "Artificial Intelligence (AI), Automation & Digital Governance Policy",
        CAT_CORPORATE_POLICIES,
        "POL-AI-013",
        "All Employees, Developers, Analysts, Vendors, and Leadership Using or Deploying AI Tools",
        "ISO/IEC 42001 AI Management System, EU AI Act Risk Principles, OECD AI Principles, Data Protection Laws",
        "Establishes safe, ethical, transparent, and compliant adoption of Generative AI, machine learning, and automated decision systems across the enterprise.",
        [
            "Approved AI Tools Only: Personnel shall only use enterprise-approved AI platforms with zero-data-retention / non-training contractual guarantees.",
            "No Confidential Data Leakage: Client PII, trade secrets, legal privilege, credentials, or unpublished financial data must never be pasted into public consumer AI tools.",
            "Human-in-the-Loop Accountability: AI-generated contracts, financial analyses, HR screening outputs, or client communications must always be reviewed and verified by a qualified human owner.",
            "Bias, Fairness & Transparency: Automated decision systems affecting employment, credit, or customer eligibility must be tested for algorithmic bias and documented for explainability.",
            "IP & Copyright Hygiene: AI-assisted code or creative deliverables must be vetted for open-source license compliance and third-party intellectual property infringement.",
        ],
        [
            "Maintain an Enterprise AI Asset & Use-Case Register classified by risk tier (Low / Medium / High).",
            "Require Legal, InfoSec, and DPO sign-off before deploying any high-risk AI model into production.",
            "Label AI-assisted external publications where required by regulation or client contract.",
        ],
        [
            "100% of production AI tools logged and risk-assessed in the AI Register.",
            "Zero incidents of confidential client data exposure via unauthorized public AI tools.",
        ],
    ),
    (
        "pol_financial_treasury_controls",
        "Financial Management, Treasury & Internal Controls Policy",
        CAT_CORPORATE_POLICIES,
        "POL-FIN-014",
        "Finance Department, Treasury, Budget Holders, Executive Signatories, and Internal Audit",
        "International Financial Reporting Standards (IFRS), Companies Act Accounting Provisions, COSO Internal Control Framework",
        "Defines budgeting, dual-authorization treasury controls, bank reconciliations, working capital management, tax compliance, and external audit readiness.",
        [
            "Segregation of Duties: Incompatible financial functions (requisitioning, vendor setup, invoice verification, payment approval, bank reconciliation) must be strictly separated.",
            "Dual-Signatory Treasury Mandate: All bank transfers, cheques, and mobile-money bulk disbursements above petty-cash limits require dual authorized electronic/physical sign-off.",
            "IFRS Compliance & Monthly Close: Management accounts shall be prepared on an accrual basis under IFRS and closed within ten (10) business days of month-end.",
            "Cash & Petty Cash Safeguards: Cash handling shall be minimized; petty cash operates strictly on an imprest voucher system with monthly surprise counts.",
            "Tax Governance: All VAT, WHT, Corporate Income Tax, and transfer pricing filings shall be accurate, reconciled, and submitted on or before statutory due dates.",
        ],
        [
            "Prepare annual zero-based or driver-based operating and CapEx budgets approved by the Board prior to the new financial year.",
            "Perform independent monthly reconciliations of all bank accounts, sub-ledgers (AR/AP), and tax control accounts.",
            "Verify supplier bank account changes via independent out-of-band callback before updating ERP payment master data.",
        ],
        [
            "Monthly financial close completed by Business Day 10.",
            "Zero unqualified statutory audit findings or material internal control weaknesses.",
            "100% bank accounts reconciled within 5 business days of month-end.",
        ],
    ),
    (
        "pol_procurement_vendor_tendering",
        "Procurement, Vendor Due Diligence & Tendering Guidelines",
        CAT_CORPORATE_POLICIES,
        "POL-PRC-015",
        "Procurement Team, Budget Holders, Tender Evaluation Committees, and Approved Suppliers",
        "CIPS Global Procurement Standards, Anti-Bribery Laws, Competition & Fair Trading Principles",
        "Ensures value for money, competitive transparency, ethical sourcing, supplier KYC vetting, and disciplined purchase-order governance.",
        [
            "Competitive Sourcing Thresholds: Direct purchase for micro-spend; minimum three (3) written quotes for medium spend; formal sealed RFP/Tender evaluated by a Tender Committee for high-value contracts.",
            "No PO, No Pay: All non-exempt external spend requires an approved Purchase Order or executed contract prior to delivery of goods or services.",
            "Supplier KYC & Sanctions Screening: Every new vendor must submit incorporation documents, tax registration, beneficial ownership details, and verified bank letters.",
            "Objective Evaluation: Bids shall be scored against pre-published technical, quality, ESG, and commercial weighting criteria.",
            "Three-Way Matching: Finance shall match Purchase Order, Goods Received Note (GRN) / Completion Certificate, and Supplier Invoice prior to payment.",
        ],
        [
            "Maintain a pre-qualified Approved Vendor List (AVL) reviewed annually for performance and compliance.",
            "Prohibit bid splitting designed to circumvent competitive tendering or executive approval thresholds.",
            "Conduct annual supplier performance scorecards for strategic vendors covering quality, on-time delivery, and SLA compliance.",
        ],
        [
            ">= 95% of addressable spend under approved POs or master agreements.",
            "100% of new suppliers completing KYC & conflict screening before onboarding.",
            "Average procurement cycle time within departmental SLA.",
        ],
    ),
    (
        "pol_travel_expense_reimbursement",
        "Corporate Travel, Per-Diem & Expense Reimbursement Policy",
        CAT_CORPORATE_POLICIES,
        "POL-FIN-016",
        "All Employees, Executives, Directors, and Consultants Incurring Business Travel or Expenses",
        "Corporate Tax Deductibility Standards, Internal Financial Control Guidelines",
        "Establishes fair, transparent rules for pre-approved business travel, accommodation caps, per-diem allowances, receipt documentation, and timely reimbursement.",
        [
            "Pre-Approval Requirement: Domestic and international business travel must be approved in writing by the Line Manager / Budget Holder prior to booking.",
            "Cost-Conscious Booking: Economy class airfare (standard), approved corporate hotels, and advance booking (>= 14 days where practicable) are mandatory.",
            "Original Receipt Verification: All claims require itemized tax receipts or fiscal invoices; unreceipted or personal expenses (alcohol, minibar, personal entertainment, fines) are non-reimbursable.",
            "Timely Submission & Accountability: Expense claims and travel advance retirements must be submitted within ten (10) business days of trip completion.",
            "Zero Fraud Tolerance: Falsified receipts or duplicate expense claims constitute gross misconduct.",
        ],
        [
            "Publish annually updated domestic and international per-diem and lodging rate tables.",
            "Audit 100% of high-value claims and random-sample 20% of routine claims before reimbursement.",
            "Process verified reimbursements within ten (10) business days of Finance approval.",
        ],
        [
            "100% of travel advances retired within 10 business days of return.",
            "95% of compliant expense claims reimbursed within 10 business days.",
        ],
    ),
    (
        "pol_enterprise_risk_audit",
        "Enterprise Risk Management (ERM) & Internal Audit Policy",
        CAT_CORPORATE_POLICIES,
        "POL-RSK-017",
        "Board Audit & Risk Committee, Executive Risk Owners, Internal Audit, and All Business Units",
        "ISO 31000 Risk Management, COSO ERM Framework, IIA Global Internal Audit Standards",
        "Creates a structured methodology to identify, score, mitigate, monitor, and assure strategic, operational, financial, legal, cyber, and reputational risks.",
        [
            "Board Risk Appetite: The Board defines explicit risk appetite and tolerance thresholds across strategic, financial, compliance, and cyber domains.",
            "Three Lines Model: Management owns risk controls (1st Line); Risk & Compliance oversee frameworks (2nd Line); Internal Audit provides independent assurance (3rd Line).",
            "Dynamic Risk Register: Every department shall maintain a scored Risk Register (Likelihood × Impact) with named risk owners and dated mitigation plans.",
            "Internal Audit Independence: Internal Audit reports functionally to the Audit & Risk Committee with unrestricted access to all records, systems, and personnel.",
            "Risk-Based Audit Plan: Annual internal audit plans prioritize high-inherent-risk processes, regulatory mandates, and prior control weaknesses.",
        ],
        [
            "Review and refresh the Enterprise Risk Register quarterly at Executive Management and Board Audit Committee meetings.",
            "Track all High and Critical audit findings to verified closure within 30–60 days.",
            "Conduct pre-launch risk assessments for new products, markets, M&A transactions, or major IT migrations.",
        ],
        [
            "100% of Critical/High audit findings remediated on schedule.",
            "Quarterly Enterprise Risk Heatmap presented to Board Audit & Risk Committee.",
        ],
    ),
    (
        "pol_business_continuity_bcp",
        "Business Continuity, Crisis Management & Disaster Recovery Policy",
        CAT_CORPORATE_POLICIES,
        "POL-BCP-018",
        "Crisis Management Team (CMT), IT Infrastructure, Operations, HR, and All Business Units",
        "ISO 22301 Business Continuity Management Systems, NIST SP 800-34 Contingency Planning",
        "Ensures rapid response, personnel safety, critical service continuity, and structured IT recovery during cyberattacks, natural disasters, utility outages, or supply disruptions.",
        [
            "Business Impact Analysis (BIA): Critical processes shall have documented Maximum Tolerable Period of Disruption (MTPD), Recovery Time Objectives (RTO), and Recovery Point Objectives (RPO).",
            "Crisis Command Structure: A designated Crisis Management Team led by the CEO/COO activates immediately upon Major Incident declaration.",
            "Life Safety First: Protection of employee, client, and visitor safety supersedes all property or commercial recovery priorities.",
            "IT Disaster Recovery: Mission-critical systems and databases shall maintain geographically redundant encrypted backups with tested failover procedures.",
            "Stakeholder Communications: Only designated spokespersons may issue official external crisis updates to customers, regulators, or media.",
        ],
        [
            "Maintain offline and cloud-accessible copies of the Crisis Contact Tree and Recovery Playbooks.",
            "Conduct at least one (1) tabletop crisis simulation and one (1) live IT disaster-recovery failover test annually.",
            "Perform a formal Post-Incident Review within fourteen (14) days of any real activation or drill to update playbooks.",
        ],
        [
            "100% of Tier-1 systems meeting target RTO/RPO in annual DR tests.",
            "Annual tabletop crisis exercise completed with documented lessons learned.",
        ],
    ),
    (
        "pol_esg_sustainability",
        "Environmental, Social & Governance (ESG) & Sustainability Policy",
        CAT_CORPORATE_POLICIES,
        "POL-ESG-019",
        "Board, Executive Leadership, Operations, Procurement, HR, and Supply Chain Partners",
        "GRI Standards, IFRS S1 & S2 Sustainability Disclosures, UN Sustainable Development Goals (SDGs), National Environment Act",
        "Integrates environmental stewardship, social equity, community impact, and transparent governance into corporate strategy and supply chain operations.",
        [
            "Environmental Stewardship: Actively measure and reduce energy consumption, carbon emissions, single-use plastics, water waste, and electronic waste.",
            "Social Responsibility & Decent Work: Uphold fair wages, diversity & inclusion, zero child/forced labour, and positive local community engagement.",
            "Responsible Supply Chain: Prioritize suppliers demonstrating environmental compliance, ethical labour standards, and local content development.",
            "Transparent ESG Reporting: Publish accurate, verifiable annual ESG metrics without greenwashing or unsubstantiated sustainability claims.",
            "Board Oversight: ESG targets and climate-related risks are reviewed annually by Executive Management and the Board.",
        ],
        [
            "Baseline annual Scope 1 & 2 resource usage (electricity, fuel, paper, waste) and set realistic reduction targets.",
            "Adopt digital-first, paperless workflows (using TrustSeal e-signatures and digital archives) to minimize print waste.",
            "Embed sustainability criteria into vendor evaluation and capital investment business cases.",
        ],
        [
            "Annual YoY reduction in paper/energy intensity per employee.",
            "100% of strategic suppliers acknowledging Supplier Sustainability Code.",
        ],
    ),
    (
        "pol_ip_confidentiality_secrets",
        "Intellectual Property, Confidentiality & Trade Secrets Policy",
        CAT_CORPORATE_POLICIES,
        "POL-IP-020",
        "All Employees, Founders, Contractors, R&D Teams, Consultants, and External Partners",
        "Industrial Property Act, Copyright & Neighbouring Rights Act, Trademarks Act, Trade Secrets Protection Standards",
        "Safeguards proprietary software, inventions, trademarks, client lists, pricing models, and confidential know-how throughout creation, licensing, and staff transitions.",
        [
            "Work-Made-for-Hire Ownership: All inventions, code, designs, methodologies, and content created within the scope of employment or commissioned engagement vest exclusively in the organization.",
            "Mandatory NDAs: Mutual or unilateral Non-Disclosure Agreements must be executed prior to sharing proprietary information with prospects, vendors, or investors.",
            "Trade Secret Safeguards: Sensitive algorithms, pricing models, and client databases must be labeled Confidential, access-restricted, and never stored on personal cloud drives.",
            "Respect for Third-Party IP: Personnel shall not copy, reverse-engineer, or deploy unlicensed third-party software, proprietary documents, or former-employer trade secrets.",
            "Exit IP Clearance: Departing personnel must return all company files, devices, and records and re-affirm post-employment confidentiality obligations.",
        ],
        [
            "Register core corporate trademarks, domains, and copyrightable flagship works promptly with URSB / WIPO / relevant IP registries.",
            "Maintain an Open-Source Software (OSS) license compliance review for all proprietary software releases.",
            "Embed IP Assignment and Confidentiality schedules in all employment and contractor agreements.",
        ],
        [
            "100% of employees and contractors with signed IP Assignment & NDA clauses.",
            "Zero unlicensed software installations or third-party IP infringement claims.",
        ],
    ),
    (
        "pol_brand_media_social",
        "Brand Identity, Media Relations & Social Media Guidelines",
        CAT_CORPORATE_POLICIES,
        "POL-MKT-021",
        "Marketing, Communications, Executive Spokespersons, and All Employees on Social Media",
        "Consumer Protection Standards, Defamation & Copyright Laws, Advertising Standards Codes",
        "Protects corporate reputation, brand consistency, official media engagement protocols, and responsible employee participation on public social platforms.",
        [
            "Authorized Media Spokespersons: Only the CEO, Board Chair, and designated Communications Lead may speak on the record to journalists or issue press releases.",
            "Brand Visual Consistency: Official logos, letterheads, typography, color palettes, and TrustSeal stamps must adhere strictly to approved Brand Identity Guidelines.",
            "Official Social Accounts: Corporate social channels require Marketing approval, MFA security, content calendars, and clear moderation rules.",
            "Personal Social Media Conduct: Employees sharing personal opinions must include disclaimers that views are their own and must never disclose confidential client/company data or disparage colleagues.",
            "Client Consent: Customer logos, testimonials, and project case studies require prior written Client Release authorization.",
        ],
        [
            "Route all media inquiries immediately to Corporate Communications for coordinated response.",
            "Conduct quarterly audits of brand templates, email signatures, and official social channel access.",
            "Activate the Crisis Communications Playbook immediately for viral reputation incidents.",
        ],
        [
            "100% of external press statements and client case studies formally pre-approved.",
            "Zero unauthorized leaks of non-public corporate information on social media.",
        ],
    ),
    (
        "pol_customer_service_complaints",
        "Customer Service Excellence, Complaints Handling & SLA Policy",
        CAT_CORPORATE_POLICIES,
        "POL-CX-022",
        "Client Success, Support, Sales, Operations, and All Customer-Facing Teams",
        "ISO 10002 Quality Management — Customer Satisfaction & Complaints Handling, Consumer Protection Laws",
        "Establishes responsive service-level benchmarks, transparent complaint resolution workflows, escalation tiers, and continuous client feedback loops.",
        [
            "Customer-First Standards: Every client interaction shall be courteous, transparent, accurate, and solution-oriented.",
            "Tiered SLA Commitments: Acknowledge all inquiries within defined SLA windows (Critical: <= 2 hours; High: <= 4 hours; Standard: <= 1 business day).",
            "Accessible Complaint Channels: Clients may lodge complaints via email, phone, portal, or in writing without barriers or punitive fees.",
            "Fair Redress & Escalation: Unresolved complaints escalate automatically from Frontline Support (Tier 1) to Department Manager (Tier 2) and Executive Sponsor (Tier 3).",
            "Root-Cause Closure: Recurring client complaints trigger mandatory operational Corrective and Preventive Action (CAPA).",
        ],
        [
            "Log 100% of customer complaints in the CRM/Ticketing register with unique tracking references.",
            "Measure Net Promoter Score (NPS) and Customer Satisfaction (CSAT) quarterly across active accounts.",
            "Review SLA attainment and top complaint drivers monthly at Operations Committee.",
        ],
        [
            ">= 95% compliance with contracted response and resolution SLAs.",
            "Customer Satisfaction (CSAT) >= 4.5 / 5.0.",
            "100% of formal complaints closed with documented client confirmation.",
        ],
    ),
    (
        "pol_document_control_seal",
        "Document Control, Archival & Digital Seal / Signature Policy",
        CAT_CORPORATE_POLICIES,
        "POL-DOC-023",
        "All Departments, Company Secretary, Legal, Records Managers, and Authorized Signatories",
        "Electronic Signatures Act, ISO 9001 Clause 7.5 Documented Information, Companies Act Statutory Recordkeeping",
        "Governs standardized drafting, versioning, cryptographic sealing, authorized physical/digital stamping, e-signature verification, and 7-year statutory archival.",
        [
            "Master Controlled Templates: Official corporate communications, contracts, and statutory filings shall use approved TrustSeal templates and official letterheads.",
            "Version & Approval Integrity: Every controlled document carries a unique reference, version number, owner, effective date, and next review date.",
            "Authorized Signing & Stamping: Electronic signatures, initials, and company seals/stamps may only be applied by officers authorized under the Delegated Authority Matrix with OTP/cryptographic verification.",
            "Tamper-Evident Preservation: Finalized institutional documents shall be sealed with SHA-256 integrity hashes and stored in the central TrustSeal Document Vault.",
            "Statutory Retention: Corporate, tax, HR, and contractual records shall be retained for at least seven (7) years (or permanently for constitutional/statutory registers).",
        ],
        [
            "Conduct annual document control reviews to retire superseded policies and prevent use of obsolete forms.",
            "Audit digital stamp and e-signature usage logs quarterly for unauthorized or anomalous activity.",
            "Enforce secure disposal certificates when non-permanent records exceed statutory retention limits.",
        ],
        [
            "100% of active policies reviewed within their 12-month review cycle.",
            "100% of executed contracts and statutory resolutions archived in the verified vault.",
        ],
    ),
    (
        "pol_third_party_outsourcing_risk",
        "Third-Party Risk Management (TPRM) & Outsourcing Policy",
        CAT_CORPORATE_POLICIES,
        "POL-TPR-024",
        "Procurement, IT Security, Legal, Compliance, and Business Owners Managing External Vendors",
        "ISO 27001 Supplier Relationships, EBA / Central Bank Outsourcing Guidelines, SOC 2 Supply Chain Standards",
        "Controls inherent risks from cloud providers, subcontractors, managed service providers, and critical suppliers across onboarding, monitoring, and exit.",
        [
            "Risk Tiering: Classify all third parties as Critical, High, Medium, or Low based on data sensitivity, operational dependency, and regulatory impact.",
            "Pre-Contract Assurance: Critical and High-risk vendors must pass security, financial viability, business continuity, and legal due diligence before onboarding.",
            "Mandatory Contractual Safeguards: Contracts must include SLAs, right-to-audit, breach notification (<= 24–48 hrs), sub-processor restrictions, and data return/deletion on exit.",
            "Ongoing Monitoring: Conduct annual security/compliance reviews and SLA audits of all Critical vendors.",
            "Exit & Concentration Strategy: Maintain documented exit plans to prevent vendor lock-in or sudden operational disruption.",
        ],
        [
            "Maintain a centralized Third-Party Vendor Register mapped to internal business owners and data flows.",
            "Collect current SOC 2 / ISO 27001 certificates and insurance renewals annually from Critical vendors.",
            "Test contingency switchover procedures for single-point-of-failure suppliers.",
        ],
        [
            "100% of Critical vendors risk-assessed prior to contract signature and reviewed annually.",
            "Zero Critical vendors operating without signed DPAs and SLAs.",
        ],
    ),
    (
        "pol_asset_fleet_facilities",
        "Corporate Asset Management, Fleet & Facilities Security Policy",
        CAT_CORPORATE_POLICIES,
        "POL-OPS-025",
        "Operations, Administration, IT Asset Managers, Fleet Drivers, and All Staff Issued Company Property",
        "IFRS IAS 16 Property, Plant & Equipment, Road Traffic & Safety Regulations, Premises Security Standards",
        "Governs lifecycle tracking, custody, preventive maintenance, physical access security, vehicle fleet safety, insurance coverage, and authorized disposal of organizational assets.",
        [
            "Fixed Asset Register: Every tangible asset above the capitalization threshold shall be uniquely tagged, logged in the Fixed Asset Register, and assigned to a named custodian.",
            "Physical Access Control: Offices, server rooms, and document vaults shall enforce visitor sign-in logs, badge/biometric access, and CCTV monitoring.",
            "Fleet Safety & Usage: Company vehicles may only be operated by licensed, authorized drivers for official business, with mandatory trip logs, seatbelts, and zero-drunk-driving rules.",
            "Insurance & Maintenance: All high-value equipment, buildings, and fleet vehicles shall maintain comprehensive insurance and scheduled preventive maintenance.",
            "Authorized Disposal: Obsolete or damaged assets require Finance/Operations write-off approval, data wiping (for IT devices), and transparent auction/recycling disposal.",
        ],
        [
            "Perform annual physical fixed-asset verification reconciling physical tags against accounting records.",
            "Require signed Asset Handover & Return forms during employee onboarding and offboarding.",
            "Inspect fleet safety kits, licenses, and service schedules monthly.",
        ],
        [
            "100% annual fixed-asset verification accuracy.",
            "Zero unreturned IT assets from departed staff.",
            "100% fleet vehicles current on statutory inspection and insurance.",
        ],
    ),
]


ORGTYPE_POLICY_SPECS: list[PolicySpec] = [
    (
        "pol_org_plc_listed_corp",
        "Public Limited & Listed Company (PLC) Governance & Disclosure Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-101",
        "Public Limited Companies (PLCs), Listed Issuers, Board Directors, Executive Officers & Insiders",
        "Companies Act (Cap. 106), Capital Markets Authority (CMA) Listing Rules, Insider Trading & Continuous Disclosure Regulations",
        "Governs price-sensitive disclosure, insider trading blackout windows, independent audit committees, shareholder equality, and investor relations for public companies.",
        [
            "Continuous Material Disclosure: Price-sensitive information shall be disclosed accurately and simultaneously to the exchange and public without selective leaks.",
            "Insider Trading Blackouts: Directors, executives, and insiders are strictly prohibited from trading company securities during closed periods ahead of earnings or while holding MNPI.",
            "Independent Board Oversight: Majority Non-Executive Board with an independent Audit Committee Chair and formal Nomination/Remuneration Committees.",
            "Minority Shareholder Protection: Equal voting rights per share class, transparent AGM proxy access, and independent fairness opinions on major related-party transactions.",
            "Audited Financial Integrity: Half-year unaudited and full-year IFRS audited financial statements published strictly within regulatory deadlines.",
        ],
        [
            "Maintain a real-time Insider List and require written Company Secretary pre-clearance for all Director/Officer share dealings.",
            "Publish an annual Corporate Governance Statement alongside the Annual Report.",
            "Operate a structured Investor Relations calendar ensuring fair access for institutional and retail shareholders.",
        ],
        [
            "100% timely exchange filings and earnings releases (zero regulatory fines).",
            "Zero insider trading or blackout-window violations.",
        ],
    ),
    (
        "pol_org_smc_sme_family",
        "Single Member Company (SMC), SME & Family Business Governance Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-102",
        "Single Member Companies (SMCs), SMEs, Founders, Nominee Directors & Family-Owned Enterprises",
        "Companies Act (Cap. 106), Companies (Single Member) Regulations 2016, Tax & Employment Statutory Rules",
        "Provides practical, lean governance separating personal and business finances, appointing statutory nominee directors, formalizing family roles, and ensuring succession continuity.",
        [
            "Strict Entity Separation: Company bank accounts, assets, and liabilities shall be strictly separated from the founder's or family's personal finances; all drawings documented as salary or lawful dividends.",
            "Nominee Director Continuity (SMC): Maintain a validly appointed and consented Nominee Director and Alternate Nominee Director registered with URSB to guarantee business continuity.",
            "Merit-Based Family Employment: Family members employed by the enterprise must hold defined job descriptions, market-aligned compensation, and objective performance reviews.",
            "Lean Financial Controls: Maintain monthly bookkeeping, cloud invoicing, tax compliance calendars, and dual review for large supplier payments.",
            "Succession & Estate Alignment: Align shareholder agreements, buy-sell provisions, and founder wills/trusts to prevent operational paralysis upon transition.",
        ],
        [
            "Hold quarterly advisory or family council reviews examining cash flow, tax obligations, and growth targets.",
            "File Annual Returns, Beneficial Ownership updates, and URA tax returns on schedule to keep the entity in good standing.",
            "Document key operational SOPs so institutional knowledge does not reside solely with the founder.",
        ],
        [
            "100% separation of corporate and personal bank transactions.",
            "100% up-to-date statutory filings and active Nominee Director registration.",
        ],
    ),
    (
        "pol_org_ngo_charity_npo",
        "NGO, Charity & Non-Profit (NPO) Governance, Safeguarding & Donor Compliance Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-103",
        "NGOs, Charities, Civil Society Organizations, Trustees, Program Staff, Volunteers & Implementing Partners",
        "Non-Governmental Organisations Act, NGO Bureau Regulations, Core Humanitarian Standard (CHS), IASC PSEA Six Core Principles",
        "Ensures transparent stewardship of donor grants, zero tolerance for Sexual Exploitation and Abuse (PSEA), beneficiary safeguarding, anti-fraud controls, and statutory NGO Bureau compliance.",
        [
            "Beneficiary Safeguarding & PSEA: Absolute zero tolerance for sexual exploitation, abuse, harassment, or harm toward children, vulnerable adults, or program beneficiaries.",
            "Restricted Fund Accounting: Donor grants shall be tracked via dedicated fund/project codes, spent strictly in line with approved grant budgets, and never commingled improperly.",
            "Non-Distribution Constraint: All surpluses and charitable assets must be reinvested exclusively toward the organization's registered public-benefit mission.",
            "Anti-Fraud & Aid Diversion Prevention: Rigorous beneficiary verification, field distribution audits, and sanctions/counter-terrorism screening of sub-grantees.",
            "Board / Trustee Independence: Governing Board members serve voluntarily in a fiduciary capacity with strict conflict-of-interest recusal.",
        ],
        [
            "Conduct mandatory safeguarding background checks and signed PSEA Code acknowledgments for all staff, volunteers, and field partners.",
            "Submit timely quarterly/annual narrative and audited financial reports to donors, NGO Bureau, and district authorities.",
            "Operate accessible, community-level feedback and safeguarding complaint mechanisms in local languages.",
        ],
        [
            "100% of grant expenditures compliant with donor guidelines (zero disallowed costs).",
            "100% staff and volunteer safeguarding/PSEA training completion.",
            "100% timely NGO permit renewals and annual statutory returns.",
        ],
    ),
    (
        "pol_org_sacco_cooperative",
        "SACCO, Cooperative Society & Credit Union Governance & Lending Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-104",
        "SACCOs, Savings & Credit Cooperatives, Executive Committees, Supervisory Committees, Credit Officers & Members",
        "Cooperative Societies Act, Tier 4 Microfinance Institutions & Money Lenders Act (UMRA), ICA Cooperative Principles",
        "Governs democratic member control, prudent credit underwriting, liquidity and capital adequacy ratios, savings mobilization, and Supervisory Committee oversight.",
        [
            "Democratic Member Governance: One-member-one-vote at the Annual General Meeting, transparent committee elections, and clear separation between Board, Management, and Supervisory Committee.",
            "Prudent Lending & Credit Appraisal: All member loans require verified savings history, repayment capacity assessment, guarantor/collateral security, and tiered Credit Committee approval.",
            "Liquidity & Reserve Adequacy: Maintain statutory liquidity reserves, institutional capital ratios, and Portfolio-at-Risk (PAR > 30 days) provisioning under UMRA/regulatory guidelines.",
            "Insider Lending Restrictions: Loans to Board members, Supervisory Committee, or staff must never exceed statutory caps or receive preferential non-market interest rates.",
            "Member Savings Protection: Daily cash reconciliation, dual vault custody, and transparent quarterly member statements.",
        ],
        [
            "Publish monthly financial performance, PAR aging, and liquidity ratios to the Board and Supervisory Committee.",
            "Conduct quarterly independent inspections by the Supervisory Committee reporting directly to the AGM.",
            "Deliver annual financial literacy and cooperative governance education to members.",
        ],
        [
            "Portfolio-at-Risk (PAR > 30 days) maintained <= 5%.",
            "Liquidity ratio and core capital maintained strictly above regulatory minimums.",
            "100% timely AGM convening and annual audited accounts filing.",
        ],
    ),
    (
        "pol_org_fbo_religious",
        "Faith-Based Organization (FBO) & Religious Institution Stewardship & Governance Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-105",
        "Churches, Mosques, Religious Institutions, Clergy, Elders/Deacons, Trustees, Volunteers & Ministry Staff",
        "Trustees Incorporation Act, Charitable Stewardship Standards, Child & Vulnerable Adult Safeguarding Laws",
        "Establishes transparent financial stewardship of tithes and offerings, child/youth ministry safeguarding, property trusteeship, and accountable leadership governance.",
        [
            "Transparent Stewardship of Funds: All offerings, tithes, donations, and project funds shall be counted by at least two unrelated authorized stewards, logged immediately, and banked intact.",
            "Child & Vulnerable Person Safeguarding: Mandatory vetting, two-adult supervision rules, and strict safeguarding protocols for all children's, youth, and pastoral care ministries.",
            "Property & Land Trusteeship: Institutional land titles, buildings, and vehicles shall be registered strictly in the name of the Incorporated Trustees, never individual leaders.",
            "Benevolence & Social Outreach Integrity: Welfare and community relief disbursements require documented assessment criteria and transparent committee sign-off.",
            "Accountable Leadership & Conflict Care: Clear separation between spiritual leadership and financial treasury sign-off, with independent annual financial review.",
        ],
        [
            "Present transparent quarterly and annual financial statements to the Governing Council and congregation/assembly.",
            "Require dual signatories on all institutional bank accounts and capital project contracts.",
            "Maintain clear HR contracts, payroll compliance, and pastoral care ethics boundaries for employed staff.",
        ],
        [
            "100% dual-counted offering logs reconciled to bank deposits within 48 hours.",
            "100% safeguarding clearance for youth and children's ministry volunteers.",
        ],
    ),
    (
        "pol_org_public_parastatal",
        "Public Sector, Government Agency & Parastatal Governance & Citizen Charter",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-106",
        "Government Ministries, Statutory Authorities, Local Governments, Parastatals & Public Officers",
        "Public Finance Management Act (PFMA), Public Procurement & Disposal of Public Assets (PPDA) Act, Leadership Code Act",
        "Aligns public institutions with statutory public finance controls, transparent PPDA procurement, citizen service-delivery standards, access to information, and zero corruption.",
        [
            "Public Accountability & Value for Money: Public funds shall be expended strictly within Parliament/Board-approved appropriations and workplans.",
            "PPDA Procurement Compliance: All public tenders, evaluations, contract awards, and asset disposals shall follow statutory PPDA thresholds and open competition rules.",
            "Citizen Service Charter: Publish clear, measurable turnaround times, transparent fee schedules, and accessible grievance redress for all public services.",
            "Asset & Income Declaration: Accounting Officers and designated public officials shall file mandatory wealth and conflict-of-interest declarations.",
            "Audit & Parliamentary Oversight: Cooperate fully with the Auditor General and implement Public Accounts Committee (PAC) recommendations promptly.",
        ],
        [
            "Publish approved annual procurement plans, contract awards, and service standards on official public portals.",
            "Conduct quarterly internal audit reviews of vote-book controls, payroll integrity, and project execution.",
            "Ensure timely responses to citizen Access-to-Information requests within statutory timelines.",
        ],
        [
            "Unqualified Auditor General opinion on annual financial statements.",
            ">= 90% compliance with published Citizen Service Charter turnaround times.",
            "100% PPDA procurement audit compliance.",
        ],
    ),
    (
        "pol_org_trust_foundation",
        "Trust, Private Foundation & Endowment Governance & Investment Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-107",
        "Charitable & Family Trusts, Private Foundations, Endowments, Trustees & Investment Committees",
        "Trustees Act, Trustees Incorporation Act, Prudent Investor Rule, Anti-Money Laundering & Tax Exemption Rules",
        "Governs fiduciary administration of trust corpus, prudent investment allocation, transparent grantmaking/distributions, beneficiary protection, and perpetual stewardship.",
        [
            "Fiduciary Fidelity to Trust Deed: Trustees shall administer all trust assets strictly in accordance with the Settlor's Deed of Trust and applicable law.",
            "Prudent Investment Policy: Endowment assets shall be diversified across approved asset classes balancing capital preservation, liquidity, risk tolerance, and sustainable yield.",
            "Transparent Grantmaking & Distributions: Grants and beneficiary distributions follow documented eligibility criteria, due diligence, milestone reporting, and conflict-free review.",
            "Segregation of Trust Property: Trust funds and property titles must be strictly segregated from personal assets of Trustees or Founders.",
            "Annual Trust Accounting: Maintain comprehensive capital and income accounts audited annually and shared with beneficiaries/regulators as required.",
        ],
        [
            "Review investment portfolio performance and asset allocation benchmarks quarterly against the Investment Policy Statement (IPS).",
            "Conduct annual Trustee fiduciary training and conflict-of-interest affirmations.",
            "Archive all Trust Deeds, Deeds of Variation, and distribution resolutions in tamper-evident vault storage.",
        ],
        [
            "Portfolio risk and liquidity maintained within IPS target bands.",
            "100% of grants and distributions supported by documented Trustee resolutions.",
        ],
    ),
    (
        "pol_org_partnership_prof_firm",
        "Partnership, Law Firm & Professional Practice Governance & Client Care Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-108",
        "Law Firms, Audit/Accounting Firms, Architectural/Engineering Practices, Partners, Associates & Staff",
        "Partnership Act (Cap. 110), Advocates / Accountants Professional Conduct Regulations, ISQM 1 Quality Management",
        "Regulates partner governance, mandatory client conflict checks, strict client trust/escrow accounting, professional indemnity, and matter quality supervision.",
        [
            "Mandatory Conflict Checking: No new client or matter may be accepted until a firm-wide conflict-of-interest and AML/KYC check is cleared and logged.",
            "Client Trust & Escrow Segregation: Client funds shall be held exclusively in designated Client Trust Bank Accounts, strictly separated from Firm operating funds, with monthly three-way reconciliation.",
            "Engagement Letters & Fee Transparency: Every mandate requires a signed Letter of Engagement defining scope, fee structure, disbursements, and liability terms.",
            "Professional Secrecy & Privilege: Strict protection of attorney-client / professional privilege, ethical walls (Chinese walls), and secure matter file custody.",
            "Partner Supervision & Peer Review: Every formal legal opinion, audit report, or technical certification requires independent second-partner quality sign-off.",
        ],
        [
            "Maintain active Practicing Certificates and adequate Professional Indemnity Insurance for all partners and practitioners.",
            "Track billable time, WIP, disbursements, and statutory court/filing deadlines in a centralized practice management calendar.",
            "Conduct annual Continuing Professional Development (CPD) compliance tracking.",
        ],
        [
            "100% of new matters cleared through Conflict & KYC checks prior to work.",
            "Zero client trust account reconciliation discrepancies.",
            "100% of practitioners maintaining valid annual practicing certificates and CPD hours.",
        ],
    ),
    (
        "pol_org_trade_assoc_chamber",
        "Trade Association, Chamber of Commerce & Member Body Governance Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-109",
        "Industry Associations, Chambers of Commerce, Professional Institutes, Secretariat & Member Representatives",
        "Companies Limited by Guarantee / Societies Law, Competition & Antitrust Compliance Standards",
        "Governs fair member admission, strict antitrust/competition guardrails during industry meetings, transparent policy advocacy, and secretariat accountability.",
        [
            "Strict Antitrust & Competition Compliance: Association meetings, committees, and forums shall never be used to discuss or coordinate member pricing, market allocation, output limits, or boycotts.",
            "Fair & Transparent Membership: Clear, non-discriminatory admission criteria, tiered dues schedules, member rights, and fair suspension/expulsion appeal processes.",
            "Ethical Policy Advocacy: Public policy submissions and regulatory engagements must be evidence-based, transparent, and free from improper lobbying.",
            "Democratic Elections & Term Limits: Transparent, independently verified Council/Board elections with clearly enforced officer term limits.",
            "Secretariat Neutrality: Employed secretariat staff serve all members impartially without favoring individual corporate sponsors.",
        ],
        [
            "Read a formal Antitrust Compliance Reminder at the start of every industry committee or working-group meeting.",
            "Publish annual member impact reports and audited financial statements ahead of the AGM.",
            "Protect member directory data strictly in line with data protection and anti-spam consent rules.",
        ],
        [
            "Zero competition/antitrust compliance incidents.",
            ">= 85% annual member renewal and satisfaction rate.",
        ],
    ),
    (
        "pol_org_cbo_social_enterprise",
        "Community-Based Organization (CBO) & Social Enterprise Impact & Governance Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-110",
        "CBOs, Grassroots Associations, Social Enterprises, Founders, Community Leaders & Impact Investors",
        "Local Government CBO Registration Guidelines, Social Enterprise Impact Standards, Environmental & Fair Trade Principles",
        "Balances sustainable earned-revenue operations with measurable social/community mission lock, participatory local governance, and transparent impact reporting.",
        [
            "Mission Lock & Social Impact: Commercial activities shall measurably advance the defined social, economic, or environmental community purpose.",
            "Participatory Community Voice: Community representatives and beneficiaries shall be meaningfully consulted in program design, pricing fairness, and impact evaluation.",
            "Simple, Transparent Financial Hygiene: Maintain clear cashbooks, mobile-money/bank reconciliations, dual payment approvals, and community-accessible financial summaries.",
            "Fair Local Value & Inclusion: Prioritize local hiring, fair supplier/farmer pricing, gender inclusion, and youth empowerment.",
            "Zero Exploitation & Safeguarding: Uphold safe, respectful community engagement with clear local complaint channels.",
        ],
        [
            "Define 3–5 clear Social Impact KPIs (e.g., households reached, jobs created, income uplift) tracked quarterly.",
            "Renew district/local government CBO registrations and business permits on schedule.",
            "Publish an annual Community Impact & Financial Transparency Summary.",
        ],
        [
            "100% achievement of annual community consultation and impact reporting milestones.",
            "Positive operating sustainability while meeting >= 80% of target social impact metrics.",
        ],
    ),
    (
        "pol_org_startup_venture",
        "Startup, High-Growth Tech & Venture Studio Governance & Scaling Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-111",
        "Startups, Venture Studios, Incubators, Founders, Early Employees, Advisors & Seed/Series Investors",
        "Companies Act, Venture Capital Governance Norms, IP Assignment & Data Privacy Regulations",
        "Establishes clean cap-table hygiene, founder vesting, IP ownership, lean security-by-design, investor reporting, and ethical rapid scaling.",
        [
            "Cap-Table & Equity Integrity: All founder shares, ESOP grants, SAFEs, and convertible notes shall be formally documented, board-approved, and tracked in a single authoritative cap table.",
            "Founder & Contributor IP Assignment: Every founder, engineer, designer, and advisor must sign a clean PIIA (Proprietary Information & Inventions Assignment) before contributing code or IP.",
            "Investor Reporting & Cash Runway Discipline: Issue transparent monthly/quarterly investor updates tracking MRR/ARR, burn rate, cash runway, and key risks.",
            "Security & Privacy by Design: Embed MFA, encrypted secrets management, least-privilege cloud IAM, and privacy compliance from MVP stage onward.",
            "Ethical Culture During Hypergrowth: Maintain zero tolerance for harassment, burnout culture, or misleading customer/investor metrics.",
        ],
        [
            "Maintain a continuously updated Virtual Data Room (VDR) containing incorporation records, IP assignments, customer contracts, and financials.",
            "Review cash runway monthly and trigger fundraising or cost-optimization plans at >= 9 months runway.",
            "Use standardized vesting schedules (e.g., 4-year vesting with 1-year cliff) for all equity awards.",
        ],
        [
            "100% clean IP chain-of-title and reconciled cap table (due-diligence ready).",
            "100% on-time monthly/quarterly investor reporting.",
        ],
    ),
    (
        "pol_org_multinational_group",
        "Multinational Group & Holding Company Subsidiary Oversight Policy",
        CAT_ORGTYPE_POLICIES,
        "POL-ORG-112",
        "Holding Companies, Regional Headquarters, Group Executives, Subsidiary Boards & Country Managers",
        "OECD Transfer Pricing Guidelines, IFRS 10 Consolidated Financial Statements, Cross-Border Sanctions & Export Controls",
        "Governs group-wide reserved matters, arm's-length intercompany transfer pricing, subsidiary board accountability, consolidated risk, and cross-border regulatory compliance.",
        [
            "Group Reserved Matters: Major capital expenditures, M&A, debt facilities, brand changes, and C-suite appointments at subsidiaries require prior Holding Company Board approval.",
            "Arm's-Length Transfer Pricing: All intercompany management fees, IP royalties, loans, and goods transfers shall be backed by written Intercompany Agreements and OECD-compliant benchmarking.",
            "Local Legal Autonomy with Group Floor: Subsidiaries must comply with all host-country laws while meeting or exceeding Group minimum standards on ethics, ABAC, HSE, and cybersecurity.",
            "Sanctions & Export Controls: Strict screening against UN, OFAC, EU, and UK sanctions lists for all cross-border counterparties, banks, and shipments.",
            "Consolidated Reporting: Standardized Group chart of accounts and monthly IFRS consolidation packages submitted by every subsidiary.",
        ],
        [
            "Appoint a Group-nominated Non-Executive Director or Regional Liaison on each subsidiary Board.",
            "Maintain contemporaneous Master File and Local File transfer pricing documentation annually.",
            "Conduct rotational Group Internal Audits across all operating subsidiaries every 18–24 months.",
        ],
        [
            "100% of subsidiaries submitting monthly IFRS consolidation packs on schedule.",
            "Zero transfer-pricing penalties or sanctions-compliance breaches.",
        ],
    ),
]


SECTOR_POLICY_SPECS: list[PolicySpec] = [
    (
        "pol_sec_banking_fintech_aml",
        "Banking, Microfinance & FinTech AML / CFT / KYC & Consumer Protection Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-201",
        "Commercial Banks, Microfinance Institutions, Payment Service Providers (PSPs), Mobile Money & FinTechs",
        "Anti-Money Laundering Act (FIA), Financial Institutions Act, National Payment Systems Act, FATF 40 Recommendations",
        "Establishes risk-based Customer Due Diligence (CDD/EDD), PEP/sanctions screening, automated transaction monitoring, Suspicious Transaction Reporting (STR), and fair digital lending.",
        [
            "Risk-Based KYC & Beneficial Ownership: Verify customer identity, source of funds, and ultimate beneficial owners (UBOs) before activating accounts or wallets; apply Enhanced Due Diligence (EDD) to PEPs and high-risk sectors.",
            "Real-Time Sanctions & Transaction Monitoring: Screen customers and cross-border transfers against UN/OFAC/EU/local sanctions and flag structuring, velocity spikes, or unusual patterns.",
            "Mandatory STR & CTR Filing: The Money Laundering Control Officer (MLCO) shall file Suspicious Transaction Reports (STRs) with the Financial Intelligence Authority promptly, observing strict anti-tipping-off rules.",
            "Consumer Protection & Transparent Pricing: Disclose all interest rates (APR), fees, penalties, and dispute channels clearly prior to loan or payment product onboarding.",
            "Payment Security & Safeguarding: Enforce PCI-DSS, strong customer authentication (2FA), and 100% ring-fenced trust-account safeguarding of customer e-money float.",
        ],
        [
            "Appoint an independent Board-approved Money Laundering Control Officer (MLCO) with direct Board Risk Committee reporting.",
            "Conduct annual independent AML/CFT compliance audits and mandatory annual AML training for all frontline and operations staff.",
            "Retain KYC dossiers and transaction audit trails for at least seven (7) years post-account closure.",
        ],
        [
            "100% of active customers KYC-verified and risk-rated.",
            "100% of suspicious alerts triaged within 48 hours and STRs filed within statutory deadlines.",
            "Zero regulatory sanctions or customer-float reconciliation gaps.",
        ],
    ),
    (
        "pol_sec_insurance_pensions",
        "Insurance & Pension Fund Underwriting, Claims & Fiduciary Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-202",
        "Insurance Companies, Brokers, Reinsurers, Retirement Benefit Schemes & Fund Administrators",
        "Insurance Act (IRA), Retirement Benefits Regulatory Authority (URBRA) Act, IAIS Core Principles, IFRS 17",
        "Governs ethical underwriting, fair and timely claims settlement, actuarial solvency, policyholder privacy, and prudent pension fund custody.",
        [
            "Fair Underwriting & Disclosure: Policy wordings, exclusions, waiting periods, and premium schedules must be written in plain, non-misleading language.",
            "Timely & Equitable Claims Settlement: Valid claims shall be assessed objectively and settled promptly within statutory turnaround times; declined claims require reasoned written notice and appeal rights.",
            "Solvency & Reinsurance Prudence: Maintain statutory capital adequacy margins, technical reserves verified by qualified actuaries, and rated reinsurance treaties.",
            "Pension Fund Custody Separation: Retirement scheme assets must be held by an independent licensed Custodian and managed by a licensed Fund Manager separated from sponsor operations.",
            "Anti-Insurance Fraud Controls: Deploy systematic claims verification, medical/loss-adjuster vetting, and fraud analytics.",
        ],
        [
            "Submit quarterly solvency, claims-aging, and actuarial valuation returns to the regulator.",
            "Audit broker/agent commissions and sales practices to prevent mis-selling.",
            "Issue annual transparent benefit statements to all pension scheme members.",
        ],
        [
            "Solvency margin strictly above statutory regulatory threshold.",
            ">= 95% of complete claims settled within target SLA.",
        ],
    ),
    (
        "pol_sec_healthcare_clinical",
        "Healthcare, Hospital & Clinic Clinical Governance, Patient Safety & Privacy Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-203",
        "Hospitals, Clinics, Diagnostic Laboratories, Telemedicine Platforms, Clinicians & Support Staff",
        "Medical & Dental Practitioners Act, Public Health Act, WHO Patient Safety Framework, HIPAA / Data Protection Standards",
        "Protects patient safety, informed consent, medical confidentiality, infection prevention and control (IPC), clinical incident reporting, and biohazard waste disposal.",
        [
            "Patient Safety & Informed Consent: Every diagnostic or surgical procedure requires documented informed consent (except life-saving emergencies) and WHO surgical/medication safety checklists.",
            "Strict Medical Confidentiality: Electronic Health Records (EHRs) and physical charts are strictly confidential; access is restricted to treating personnel with full audit logging.",
            "Infection Prevention & Control (IPC): Enforce hand hygiene, instrument sterilization, isolation protocols, PPE compliance, and antimicrobial stewardship.",
            "Clinical Credentialing: Verify active medical/nursing/pharmacy practicing licenses for all clinical staff prior to duty and annually.",
            "Biohazard & Medical Waste Management: Segregate sharps, infectious, pharmaceutical, and general waste at point of generation for licensed treatment/incineration.",
        ],
        [
            "Hold monthly Morbidity & Mortality (M&M) and Clinical Quality Assurance reviews in a non-punitive learning culture.",
            "Report notifiable infectious diseases and severe adverse clinical events immediately to health authorities.",
            "Calibrate critical diagnostic and life-support biomedical equipment on documented preventive schedules.",
        ],
        [
            "100% active practicing-license verification across all clinicians.",
            "Zero preventable sentinel patient-safety events or unauthorized EHR breaches.",
        ],
    ),
    (
        "pol_sec_pharma_medsupplies",
        "Pharmaceuticals & Medical Supplies GDP, Cold-Chain & Pharmacovigilance Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-204",
        "Pharmaceutical Manufacturers, Importers, Wholesalers, Pharmacies & Medical Device Distributors",
        "National Drug Policy & Authority (NDA) Act, WHO Good Distribution Practices (GDP) & Good Manufacturing Practices (GMP)",
        "Ensures medicine authenticity, temperature-controlled cold-chain integrity, batch traceability, counterfeit prevention, rapid recalls, and adverse-event reporting.",
        [
            "Licensed Sourcing & Anti-Counterfeit Verification: Procure medicines and devices strictly from NDA/regulator-licensed manufacturers and verified supply chains with batch Certificates of Analysis (CoA).",
            "Storage & Cold-Chain Integrity: Maintain continuous calibrated temperature/humidity monitoring (2–8°C cold-chain; 15–25°C ambient) with automated excursion alarms and backup power.",
            "FEFO & Batch Traceability: Enforce First-Expired-First-Out (FEFO) inventory dispatch and end-to-end batch lot tracking from import to dispensing.",
            "Rapid Product Recall Protocol: Maintain tested capability to quarantine and recall affected batches within twenty-four (24) hours of a safety alert.",
            "Pharmacovigilance: Log and report suspected Adverse Drug Reactions (ADRs) and product quality defects to the Drug Authority within statutory timelines.",
        ],
        [
            "Quarantine expired, damaged, or returned stock in physically locked zones pending licensed destruction.",
            "Conduct semi-annual mock recall drills and warehouse GDP self-inspections.",
            "Ensure all dispensing and technical oversight is supervised by a registered Pharmacist.",
        ],
        [
            "Zero uninvestigated cold-chain temperature excursions.",
            "100% batch traceability and mock recall completion <= 24 hours.",
        ],
    ),
    (
        "pol_sec_education_schools",
        "Education, Schools & Universities Child Protection, Academic Integrity & Campus Safety Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-205",
        "Primary & Secondary Schools, Universities, TVET Institutes, Faculty, Administrators & Boarding Staff",
        "Education Act, Children Act, Ministry of Education & Sports Guidelines, Academic Quality Assurance Standards",
        "Establishes student safeguarding and anti-bullying, academic honesty, transparent grading, campus security, inclusive learning, and student record privacy.",
        [
            "Child & Student Safeguarding: Zero tolerance for corporal punishment, bullying, sexual misconduct, or abuse; mandatory background vetting for all teachers, coaches, and support staff.",
            "Academic Integrity & Examination Security: Strict controls against plagiarism, exam leakage, grade tampering, and unethical AI misuse, with fair academic disciplinary panels.",
            "Campus & Boarding Safety: Controlled gate access, fire/dormitory safety compliance, safe transport, school nurse/first-aid readiness, and emergency parent notification.",
            "Inclusive & Non-Discriminatory Education: Reasonable accommodations for learners with disabilities and equitable scholarship/bursary administration.",
            "Student Data & Media Consent: Protect student academic, health, and behavioral records; obtain written parental consent before publishing photos of minors.",
        ],
        [
            "Appoint a trained Designated Safeguarding Lead (DSL) accessible confidentially to all students and parents.",
            "Conduct termly fire/safety drills and independent boarding/kitchen hygiene inspections.",
            "Verify faculty teaching credentials and conduct annual pedagogical quality evaluations.",
        ],
        [
            "100% staff safeguarding vetting and annual Child Protection training.",
            "Zero examination integrity breaches or unaddressed bullying reports.",
        ],
    ),
    (
        "pol_sec_it_saas_telecom",
        "IT, SaaS & Telecommunications Secure SDLC, Cloud Security & Uptime Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-206",
        "Software Companies, SaaS Platforms, Cloud Providers, Telecoms, Engineering, DevOps & SRE Teams",
        "ISO/IEC 27001 & 27017 Cloud Security, SOC 2 Trust Services Criteria, OWASP ASVS, Communications Regulator Standards",
        "Governs secure software engineering, CI/CD change control, multi-tenant data isolation, 99.9%+ availability SLAs, vulnerability disclosure, and incident post-mortems.",
        [
            "Secure SDLC & Peer Code Review: All production code changes require version control, automated security/SAST/dependency scanning, and independent peer code review before merge.",
            "Environment & Tenant Isolation: Strict separation of Development, Staging, and Production environments (no raw customer PII in non-prod) and cryptographic/logical multi-tenant isolation.",
            "Secrets & Infrastructure as Code: Zero hardcoded credentials in repositories; manage keys via KMS/HSM/Secrets Managers with automated rotation.",
            "Availability & Change Control: Maintain documented deployment rollback procedures, blue/green or canary releases, and real-time 24/7 observability alerting.",
            "Coordinated Vulnerability Disclosure: Publish a security.txt / responsible disclosure channel and triage external vulnerability reports within 48 hours.",
        ],
        [
            "Conduct annual independent third-party penetration tests and remediate High/Critical findings within 14–30 days.",
            "Publish transparent real-time service status updates and blameless Root Cause Analysis (RCA) reports within 5 business days of any P1 outage.",
            "Review IAM roles, API keys, and cloud firewall rules quarterly.",
        ],
        [
            "Production service availability >= 99.9%.",
            "100% of production merges peer-reviewed and CI security-scanned.",
            "Mean Time to Recover (MTTR) for P1 incidents <= 60 minutes.",
        ],
    ),
    (
        "pol_sec_manufacturing_industrial",
        "Manufacturing & Industrial Quality Assurance (ISO 9001), Plant Safety & Environmental Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-207",
        "Factories, Industrial Plants, Production Lines, QA/QC Engineers, Maintenance & Warehouse Personnel",
        "ISO 9001 Quality Management, ISO 14001 Environmental Management, Occupational Safety & Health (Factories) Regulations",
        "Controls raw-material quality, statistical process control, machine guarding and Lockout-Tagout (LOTO), hazardous chemical handling, and industrial effluent management.",
        [
            "Machine Safety & Lockout-Tagout (LOTO): Mandatory physical machine guards, emergency stop switches, and strict LOTO energy isolation before any maintenance or cleaning.",
            "Incoming, In-Process & Final QC: Batch inspection checkpoints against technical specifications with formal quarantine of non-conforming goods.",
            "Hazardous Materials & SDS: Maintain up-to-date Safety Data Sheets (SDS), secondary spill containment, ventilation, and certified chemical handling PPE.",
            "Preventive Maintenance & Calibration: Scheduled servicing of production machinery, boilers, pressure vessels, and calibrated measuring instruments.",
            "Emissions & Effluent Compliance: Monitor air emissions, noise levels, and wastewater discharge strictly within National Environment Management standards.",
        ],
        [
            "Conduct daily pre-shift safety toolbox talks and equipment walkaround checks.",
            "Investigate every product defect or customer return via formal 8D / CAPA methodology.",
            "Perform annual statutory inspections of lifting gear, boilers, and electrical installations.",
        ],
        [
            "First-Pass Production Yield >= 98% and defect rate below target PPM.",
            "Zero LOTO violations or reportable environmental discharge breaches.",
        ],
    ),
    (
        "pol_sec_construction_engineering",
        "Construction, Engineering & Infrastructure Site HSE, QA/QC & Subcontractor Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-208",
        "Civil Contractors, Engineering Firms, Project Managers, Site Engineers, Subcontractors & Site Workers",
        "Building Control Act, Occupational Safety & Health Act, FIDIC Contract Standards, Environmental & Social Impact Assessment (ESIA)",
        "Enforces zero-accident site safety, working-at-height and excavation permits, structural material testing, environmental mitigation, and subcontractor compliance.",
        [
            "Permit-to-Work (PTW) System: Mandatory written permits for working at height (>1.8m), hot works, deep excavations, confined spaces, and heavy crane lifts.",
            "Mandatory Site PPE & Induction: Zero entry to active construction zones without site safety induction, hard hat, high-vis vest, safety boots, and task-specific PPE.",
            "Structural QA/QC & Material Testing: Independent laboratory testing of concrete cubes, steel reinforcement, asphalt, and soils prior to covering works, signed off by the Resident Engineer.",
            "Subcontractor Safety Accountability: All subcontractors are contractually bound to identical HSE, insurance, and fair-wage standards.",
            "Environmental & Community Protection: Control site dust, noise, stormwater runoff, traffic signage, and public pedestrian barriers.",
        ],
        [
            "Hold daily pre-work Toolbox Talks and weekly joint Client-Contractor HSE inspections.",
            "Maintain an active Site Diary, Inspection & Test Plan (ITP), and As-Built drawing register.",
            "Ensure valid Contractors' All Risks (CAR) and Workers' Compensation insurance before site mobilization.",
        ],
        [
            "Zero fatal accidents and 100% Permit-to-Work compliance on high-risk tasks.",
            "100% passing material quality test certificates prior to milestone sign-off.",
        ],
    ),
    (
        "pol_sec_agriculture_food",
        "Agriculture, Agribusiness & Food Processing HACCP Safety, Traceability & Sustainability Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-209",
        "Farms, Outgrower Schemes, Agro-Processors, Cold Storage Facilities, Packhouses & Food Exporters",
        "ISO 22000 / HACCP Food Safety, GlobalG.A.P., National Bureau of Standards (UNBS), Fair Labour & Agrochemical Laws",
        "Ensures farm-to-fork food safety, hygiene, responsible agrochemical stewardship, fair smallholder outgrower practices, and export traceability.",
        [
            "HACCP & Food Hygiene Controls: Identify and continuously monitor Critical Control Points (CCPs) for biological, chemical, and physical food contamination.",
            "Agrochemical & MRL Compliance: Use only regulator-approved inputs applied by trained personnel wearing PPE, strictly observing pre-harvest intervals and Maximum Residue Limits (MRLs).",
            "Lot & Farm Traceability: Maintain batch records linking finished food products back to harvest date, farm/cooperative plot, and processing shift.",
            "Fair Smallholder & Labour Standards: Transparent weighing, timely farmer payments, zero child or forced labour, and safe seasonal worker welfare.",
            "Soil, Water & Biodiversity Care: Promote water conservation, integrated pest management, and zero illegal deforestation.",
        ],
        [
            "Conduct regular microbiological, aflatoxin, and water-potability laboratory testing.",
            "Enforce strict packhouse hygiene (handwashing stations, hairnets, pest control logs, allergen segregation).",
            "Audit outgrower cooperatives annually for quality, fair pricing, and safe agrochemical storage.",
        ],
        [
            "100% compliance with UNBS / export destination food safety and MRL standards.",
            "Zero food-safety product recalls or border shipment rejections.",
        ],
    ),
    (
        "pol_sec_energy_mining_utilities",
        "Energy, Oil & Gas, Mining & Utilities Process Safety, ESIA & Community Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-210",
        "Power Generators, Renewable Energy Developers, Oil & Gas Operators, Mining Companies & Utility Providers",
        "Petroleum / Mining / Electricity Acts, IFC Performance Standards, Voluntary Principles on Security & Human Rights, ISO 45001/14001",
        "Governs high-hazard process safety, environmental and social impact management (ESMP), local content, land acquisition ethics, and host-community grievance redress.",
        [
            "Process Safety & Asset Integrity: Strict engineering controls, HAZOP studies, blowout/spill prevention, and high-voltage isolation standards to prevent catastrophic incidents.",
            "Environmental Restoration & ESMP: Full compliance with approved ESIA conditions, biodiversity offsets, tailings/waste management, and funded decommissioning/rehabilitation plans.",
            "Ethical Land Access & Resettlement: Fair, transparent, prior-informed compensation aligned with national law and IFC Performance Standard 5.",
            "Local Content & Community Relations: Prioritize national workforce training, local supplier participation, and transparent community grievance mechanisms.",
            "Security & Human Rights: Site security personnel must be vetted and trained in proportionate force and human-rights compliance.",
        ],
        [
            "Maintain 24/7 emergency spill/fire response equipment and conduct joint drills with local emergency authorities.",
            "Publish regular environmental monitoring reports (air, groundwater, noise) to regulators and community liaison committees.",
            "Verify regulatory licenses, royalties, and local-content filings quarterly.",
        ],
        [
            "Zero Tier-1 process safety events or uncontained environmental spills.",
            "100% of host-community grievances logged and addressed within 30 days.",
        ],
    ),
    (
        "pol_sec_realestate_hospitality",
        "Real Estate, Property Management & Hospitality Guest Safety, Tenancy & Maintenance Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-211",
        "Property Developers, Landlords, Facility Managers, Hotels, Resorts & Serviced Apartments",
        "Landlord & Tenant Act, Tourism & Hospitality Licensing Regulations, Fire Safety & Public Health Codes",
        "Establishes fair tenancy administration, fire/life safety compliance, hospitality hygiene, guest data privacy, preventive building maintenance, and deposit accounting.",
        [
            "Fair Tenancy & Deposit Protection: Written lease agreements, transparent service-charge accounting, lawful notice periods, and ring-fenced security deposit refunds upon exit inspection.",
            "Fire, Life Safety & Security: Valid annual fire certificates, functioning smoke detectors/sprinklers, emergency lighting, 24/7 access control, and trained floor wardens.",
            "Hospitality & Food Hygiene: Strict housekeeping sanitation, safe drinking water testing, kitchen HACCP hygiene, and pool/recreation safety supervision.",
            "Guest & Tenant Privacy: Protect guest registration data, CCTV footage, and keycard access logs against unauthorized disclosure or misuse.",
            "Preventive Maintenance & Accessibility: Scheduled servicing of elevators, HVAC, generators, and plumbing with clear SLA turnaround for tenant repair tickets.",
        ],
        [
            "Conduct documented Move-In and Move-Out condition inspections with timestamped photographic evidence.",
            "Maintain valid statutory hospitality, liquor, food-handler medical, and lift-safety certificates.",
            "Audit service-charge collections and sinking-fund reserves annually with transparent tenant statements.",
        ],
        [
            "100% current fire, lift, and public-health safety certifications.",
            ">= 95% urgent maintenance requests resolved within 24 hours.",
        ],
    ),
    (
        "pol_sec_logistics_transport",
        "Logistics, Transport, Courier & Fleet Safety, Chain-of-Custody & Customs Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-212",
        "Freight Forwarders, Haulage Companies, Couriers, Warehousing Operators & Corporate Fleet Units",
        "Traffic & Road Safety Act, East African Community Customs Management Act, ADR Dangerous Goods Standards, ISO 39001 Road Safety",
        "Controls driver fatigue and road safety, cargo chain-of-custody, hazardous goods transport, customs declaration integrity, and GPS fleet telematics.",
        [
            "Driver Safety & Fatigue Limits: Enforce valid commercial driving permits, maximum daily driving hours with mandatory rest breaks, zero mobile-phone use while driving, and zero alcohol/drug tolerance.",
            "Vehicle Roadworthiness: Mandatory pre-trip daily safety checklists (brakes, tyres, lights, load lashing) and scheduled preventive maintenance.",
            "Cargo Chain-of-Custody: Tamper-evident container/parcel seals, digital Proof of Delivery (POD), and immediate reporting of shortages, damage, or hijacking.",
            "Dangerous Goods & Customs Integrity: Strict UN classification, placarding, and licensing for hazardous cargo; 100% truthful customs HS-code and valuation declarations.",
            "Insurance & Liability: Maintain active Goods-in-Transit (GIT), Third-Party, and Comprehensive motor insurance across all active routes.",
        ],
        [
            "Monitor speed, harsh braking, and route deviations via GPS telematics with monthly driver safety scorecards.",
            "Conduct annual defensive-driving refresher training and medical/vision checks for all commercial drivers.",
            "Audit customs clearing agents and bonded warehouse reconciliations quarterly.",
        ],
        [
            "Preventable road accident rate reduced YoY toward zero.",
            ">= 98% On-Time-In-Full (OTIF) delivery with verified digital POD.",
        ],
    ),
    (
        "pol_sec_retail_ecommerce",
        "Retail, E-Commerce & FMCG Consumer Protection, Returns & Payment Security Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-213",
        "Retail Chains, Supermarkets, Online Marketplaces, Direct-to-Consumer Brands & Store Operations",
        "Sale of Goods & Supply of Services Act, Electronic Transactions Act, PCI-DSS Payment Security, Consumer Protection Laws",
        "Governs transparent pricing, authentic product sourcing, fair returns and warranties, secure online/POS checkout, inventory shrinkage controls, and omni-channel customer trust.",
        [
            "Transparent Pricing & Authentic Goods: Display clear tax-inclusive prices, honor advertised promotions, and enforce zero tolerance for counterfeit, expired, or mislabeled merchandise.",
            "Fair Returns, Refunds & Warranties: Publish clear return/exchange windows, honor statutory defective-goods remedies, and process verified refunds promptly.",
            "POS & E-Commerce Payment Security: Never store raw card CVV/PAN data; use PCI-DSS compliant payment gateways, HTTPS checkout, and fraud-screening controls.",
            "Inventory & Cash Loss Prevention: Daily POS till reconciliations, cycle inventory counts, receiving verification, and CCTV monitoring at checkout/stockrooms.",
            "Ethical Marketing & Consent: Obtain explicit opt-in consent for SMS/email marketing with instant 1-click unsubscribe.",
        ],
        [
            "Perform daily shelf-life checks on perishable FMCG goods and remove near-expiry stock per markdown/disposal rules.",
            "Audit e-commerce product descriptions and delivery lead-time estimates monthly for accuracy.",
            "Train store and support staff on consumer rights and de-escalation procedures.",
        ],
        [
            "Inventory shrinkage maintained <= 0.8% of retail revenue.",
            "100% of verified refunds processed within 5–7 business days.",
        ],
    ),
    (
        "pol_sec_professional_consulting",
        "Legal, Audit, Tax & Management Consulting Quality Control (ISQM 1) & Independence Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-214",
        "Advisory, Audit, Tax, Legal, Valuation & Management Consulting Firms and Engagement Teams",
        "ISQM 1 Quality Management, IESBA Code of Ethics for Professional Accountants, Professional Regulatory Codes",
        "Upholds engagement quality review, auditor/advisor independence, rigorous client acceptance, anti-money laundering screening, and deliverable sign-off controls.",
        [
            "Independence & Objectivity: Maintain strict independence in mind and appearance on all assurance, audit, and valuation engagements; prohibit contingent fees where restricted.",
            "Client & Engagement Acceptance: Assess prospective client integrity, AML/sanctions risk, team competence, and scope feasibility before accepting any mandate.",
            "Engagement Quality Review (EQR): High-risk, public-interest, and complex advisory deliverables require documented independent partner review prior to issuance.",
            "Working Paper & Evidence Integrity: Assemble complete, locked engagement working-paper files within sixty (60) days of report date, retained for at least seven (7) years.",
            "Client Confidentiality & Data Rooms: Segregate client files strictly per engagement team using encrypted collaboration vaults.",
        ],
        [
            "Collect annual Independence & Confidentiality confirmations from every partner and professional staff member.",
            "Perform annual cold-file quality inspections across a representative sample of completed engagements.",
            "Use standardized proposal, engagement letter, and deliverable QA checklists.",
        ],
        [
            "100% of high-risk engagements completing independent EQR before sign-off.",
            "Zero regulatory independence or professional-ethics sanctions.",
        ],
    ),
    (
        "pol_sec_media_publishing",
        "Media, Broadcasting, Publishing & Creative Editorial Ethics & Copyright Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-215",
        "Print & Digital Publishers, Broadcasters, Production Studios, Journalists, Editors & Content Creators",
        "Press & Journalist Ethics Codes, Copyright & Neighbouring Rights Act, Communications Broadcasting Standards, Defamation Laws",
        "Protects editorial independence, rigorous fact-checking, right of reply, copyright/licensing clearance, protection of minors, and transparent sponsored-content labeling.",
        [
            "Accuracy, Fact-Checking & Right of Reply: Verify factual claims through at least two independent reliable sources and offer fair right of reply prior to publishing critical reporting.",
            "Editorial Independence & Sponsored Labeling: Maintain a clear firewall between newsroom editorial judgment and commercial advertising; label all paid/sponsored content unmistakably.",
            "Copyright & Rights Clearance: Obtain documented licenses or talent/model releases for all third-party images, music, video clips, and archival footage before publication.",
            "Defamation & Privacy Safeguards: Route investigative or legally sensitive stories through pre-publication legal review and respect privacy of minors and crime victims.",
            "Corrections & Retractions: Publish prompt, prominent, transparent corrections whenever material factual errors are identified.",
        ],
        [
            "Maintain a Rights & Licensing Clearance Log for all published/broadcast productions.",
            "Enforce watershed/content-rating standards and hate-speech moderation across digital comment sections.",
            "Train editorial staff annually on media law, digital verification, and AI-deepfake detection.",
        ],
        [
            "Zero successful defamation or copyright-infringement claims.",
            "100% of sponsored pieces clearly disclosed and rights-cleared.",
        ],
    ),
    (
        "pol_sec_tourism_conservation",
        "Tourism, Travel & Conservation Guest Safety, Sustainable Travel & Crisis Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-216",
        "Tour Operators, Safari Lodges, Travel Agencies, Guides & Eco-Tourism Enterprises",
        "Tourism Act, Wildlife Conservation Laws, GSTC Global Sustainable Tourism Criteria, Aviation & Transport Safety Rules",
        "Establishes guest safety and medical evacuation readiness, ethical wildlife and heritage protection, transparent booking/cancellation terms, and local community benefit-sharing.",
        [
            "Guest Safety & Emergency Evacuation: Maintain vetted 4x4 safari/tour vehicles, satellite/radio communications, trained wilderness first-aid guides, and active medical evacuation partnerships.",
            "Wildlife & Environmental Ethics: Enforce strict non-harassment wildlife viewing distances, leave-no-trace waste policies, and zero support for illegal wildlife trade.",
            "Transparent Booking & Refund Terms: Clearly disclose itinerary inclusions, park permit rules, cancellation schedules, and mandatory travel insurance recommendations prior to deposit.",
            "Guide Licensing & Conduct: Employ licensed, culturally knowledgeable guides adhering to strict guest-respect, anti-harassment, and road-safety rules.",
            "Community & Heritage Respect: Promote fair local employment, authentic community enterprises, and respectful cultural photography consent.",
        ],
        [
            "Verify guest emergency contacts, allergies, and travel insurance details prior to tour departure.",
            "Inspect tour vehicles, first-aid kits, and fire equipment before every itinerary.",
            "Collect post-trip guest safety and sustainability feedback to drive continuous improvement.",
        ],
        [
            "Zero preventable guest safety or wildlife-compliance incidents.",
            "Guest satisfaction rating >= 4.7 / 5.0.",
        ],
    ),
    (
        "pol_sec_wash_environment",
        "Water, Sanitation & Environmental Services (WASH) Quality & Public Health Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-217",
        "Water Utilities, Bottling/Treatment Plants, Waste Management Firms, Recycling & Sanitation Operators",
        "Water Act, National Environment (Waste Management) Regulations, WHO Drinking-Water Quality Guidelines, ISO 14001",
        "Governs drinking-water potability testing, safe faecal/solid waste collection, hazardous waste manifest tracking, worker immunization/PPE, and pollution prevention.",
        [
            "Water Quality & Potability Assurance: Routine laboratory microbiological, chemical, and turbidity testing against WHO and national drinking-water standards with immediate boil/shutoff triggers.",
            "Safe Waste Collection & Manifesting: Licensed transport, GPS-tracked disposal at authorized treatment/landfill facilities, and signed Waste Transfer Manifests.",
            "Worker Health & Immunization: Provide full protective gear, hepatitis/tetanus vaccinations, decontamination showers, and confined-space gas detection for sanitation crews.",
            "Effluent & Leachate Control: Prevent groundwater or surface-water contamination through lined containment, treatment verification, and spill response kits.",
            "Community Hygiene & Continuity: Maintain rapid response for pipe bursts, sewer overflows, or service interruptions.",
        ],
        [
            "Publish monthly water quality and environmental compliance test logs for regulators and customers.",
            "Audit third-party recycling and disposal sites annually to prevent illegal dumping.",
            "Maintain calibrated chlorination, pH, and flow-monitoring instrumentation.",
        ],
        [
            ">= 99.5% compliance with potable water quality standards.",
            "100% of waste loads accompanied by verified disposal manifests.",
        ],
    ),
    (
        "pol_sec_humanitarian_development",
        "Humanitarian Relief & International Development Field Security, Do-No-Harm & Integrity Policy",
        CAT_SECTOR_POLICIES,
        "POL-SEC-218",
        "International NGOs, Relief Agencies, Development Contractors, Field Missions & Local Implementing Partners",
        "Core Humanitarian Standard (CHS), Sphere Minimum Standards, Humanitarian Principles (Humanity, Neutrality, Impartiality, Independence)",
        "Governs impartial humanitarian aid delivery, hostile-environment field security, Do-No-Harm conflict sensitivity, anti-diversion supply chain controls, and beneficiary accountability.",
        [
            "Humanitarian Principles & Do-No-Harm: Deliver assistance strictly based on need without political, ethnic, or religious bias, continuously assessing programs to avoid escalating local tensions.",
            "Field Duty of Care & Security: Maintain location-specific Security Risk Assessments (SRAs), movement tracking, hibernation/evacuation plans, and psychosocial staff support.",
            "Aid Diversion & Supply Chain Integrity: Dual-verified beneficiary registration, warehouse tally controls, post-distribution monitoring (PDM), and zero tolerance for kickbacks or ghost beneficiaries.",
            "Protection & PSEA Mainstreaming: Embed gender-based violence (GBV) risk mitigation, child protection, and zero-tolerance PSEA across every camp, clinic, and distribution site.",
            "Accountability to Affected Populations (AAP): Guarantee safe, accessible, multi-channel community feedback and complaint desks with documented closure loops.",
        ],
        [
            "Require mandatory security briefings and HEAT/field safety training prior to deployment in high-risk zones.",
            "Conduct independent Post-Distribution Monitoring (PDM) within 14–30 days of major cash or relief distributions.",
            "Verify implementing-partner financial capacity and safeguarding policies prior to sub-grant disbursement.",
        ],
        [
            "100% of high-risk field offices maintaining current Security Plans and quarterly drills.",
            "100% of aid distributions verified through Post-Distribution Monitoring.",
            "Zero uninvestigated PSEA or aid-diversion allegations.",
        ],
    ),
]


ALL_POLICY_SPECS: list[PolicySpec] = (
    CORPORATE_POLICY_SPECS + ORGTYPE_POLICY_SPECS + SECTOR_POLICY_SPECS
)


def build_policies_guidelines_entries(start_index: int = 1200) -> list[dict[str, Any]]:
    """Return catalog entries compatible with business_docs_catalog.py."""
    items: list[dict[str, Any]] = []
    idx = start_index
    for (
        slug_base,
        title,
        category,
        policy_code,
        applicability,
        regulatory_alignment,
        summary,
        directives,
        guidelines,
        kpis,
    ) in ALL_POLICY_SPECS:
        idx += 1
        items.append({
            "index": idx,
            "slug": f"bib-{slug_base.replace('_', '-')}",
            "name": title,
            "title": title,
            "category": category,
            "edition": f"{policy_code} · Master Policy & Guidelines",
            "description": summary,
            "summary": summary,
            "focus": f"{title} ({policy_code})",
            "edition_note": f"Aligned to {regulatory_alignment}.",
            "tags": f"policy, guidelines, compliance, governance, {policy_code.lower()}, {category.lower()}",
            "sections": 12,
            "is_business_box": True,
            "is_policy_guideline": True,
            "policy_code": policy_code,
            "applicability": applicability,
            "regulatory_alignment": regulatory_alignment,
            "directives": directives,
            "guidelines": guidelines,
            "kpis": kpis,
        })
    return items


def render_policy_guideline_html(entry: dict[str, Any]) -> str:
    """Render a comprehensive, multi-page (4–6 A4 pages) institutional Policy & Guidelines HTML."""
    title_u = _html.escape(entry["name"].upper())
    category = _html.escape(entry["category"])
    policy_code = _html.escape(entry.get("policy_code") or "POL-001")
    applicability = _html.escape(entry.get("applicability") or "All Personnel, Officers & Stakeholders")
    regulatory = _html.escape(entry.get("regulatory_alignment") or "Applicable Statutory & International Governance Standards")
    summary = _html.escape(entry.get("summary") or entry.get("description") or "")
    directives = entry.get("directives") or []
    guidelines = entry.get("guidelines") or []
    kpis = entry.get("kpis") or []

    directives_html = "".join(
        f"  <li><strong>Directive 5.{i}:</strong> {_html.escape(d)}</li>\n"
        for i, d in enumerate(directives, start=1)
    )
    guidelines_html = "".join(
        f"  <li><strong>Guideline 6.{i}:</strong> {_html.escape(g)}</li>\n"
        for i, g in enumerate(guidelines, start=1)
    )
    kpis_html = "".join(
        f"  <li><strong>KPI 9.{i}:</strong> {_html.escape(k)}</li>\n"
        for i, k in enumerate(kpis, start=1)
    )

    return f"""<h1>{title_u}</h1>
<blockquote>
  <p><strong>Policy Code:</strong> {policy_code} &nbsp;·&nbsp; <strong>Document Ref:</strong> {_f('document_ref')} &nbsp;·&nbsp; <strong>Version:</strong> 1.0 (Board-Approved Master)</p>
  <p><strong>Organization:</strong> {_f('organization_name')} &nbsp;·&nbsp; <strong>Category:</strong> {category} &nbsp;·&nbsp; <strong>Effective Date:</strong> {_f('effective_date')}</p>
  <p><strong>Policy Owner:</strong> {_f('owner_name')} &nbsp;·&nbsp; <strong>Approval Authority:</strong> {_f('approver_name')} &nbsp;·&nbsp; <strong>Review Cycle:</strong> Annual (Next Review: {_f('review_date')})</p>
  <p><strong>Regulatory &amp; Standard Alignment:</strong> {regulatory}</p>
</blockquote>

<h2>1. Policy Statement, Mandate &amp; Strategic Objectives</h2>
<p>1.1 <strong>Authoritative Policy Mandate.</strong> {_f('organization_name')} is committed to maintaining the highest institutional standards of governance, legal compliance, operational integrity, and stakeholder trust. {summary}</p>
<p>1.2 <strong>Binding Force.</strong> This Policy and its accompanying Operational Guidelines constitute a mandatory institutional directive adopted by the Governing Board / Executive Management of {_f('organization_name')}. Compliance is a condition of ongoing employment, directorship, membership, partnership, or vendor engagement.</p>
<p>1.3 <strong>Core Objectives.</strong> The objectives of this Policy are to: (a) establish unambiguous rules of conduct and operational control; (b) protect personnel, clients, beneficiaries, and organizational assets from preventable risk; (c) ensure verifiable alignment with statutory law and international best practice; and (d) provide an auditable governance baseline sealed within TrustSeal.</p>

<h2>2. Scope, Applicability &amp; Covered Persons</h2>
<p>2.1 <strong>Covered Entities &amp; Personnel.</strong> This Policy applies comprehensively to: <strong>{applicability}</strong> across all headquarters, regional branches, field offices, remote work locations, digital platforms, and operating subsidiaries of {_f('organization_name')}.</p>
<p>2.2 <strong>Third-Party &amp; Partner Extension.</strong> Contractors, consultants, joint-venture partners, implementing partners, and suppliers acting on behalf of or accessing systems of {_f('organization_name')} shall uphold equivalent standards as incorporated by reference into their binding agreements.</p>
<p>2.3 <strong>Precedence of Stricter Law.</strong> Where any host-country statute, regulatory directive, or sector license imposes a stricter requirement than this Policy, the stricter statutory requirement shall prevail without diminishing the remaining safeguards herein.</p>

<h2>3. Statutory, Regulatory &amp; International Standards Alignment</h2>
<p>3.1 <strong>Primary Legal &amp; Governance Benchmarks.</strong> This Policy has been drafted to align directly with <strong>{regulatory}</strong>, together with the constitutional documents (Memorandum &amp; Articles of Association, Charter, Trust Deed, or Bylaws) of {_f('organization_name')}.</p>
<p>3.2 <strong>Regulatory Updates.</strong> The Policy Owner ({_f('owner_name')}) and Legal / Compliance Officer ({_f('compliance_officer')}) shall monitor legislative amendments, regulatory circulars, and industry standard revisions continuously and propose timely Policy updates whenever material changes take effect.</p>

<h2>4. Key Definitions &amp; Interpretation</h2>
<ul>
  <li><strong>&ldquo;Organization&rdquo;</strong> means {_f('organization_name')}, including all its controlled operating units, projects, branches, and authorized committees.</li>
  <li><strong>&ldquo;Governing Authority&rdquo;</strong> means the Board of Directors, Board of Trustees, Executive Committee, or Sole Member empowered to adopt binding institutional policy.</li>
  <li><strong>&ldquo;Policy Owner&rdquo;</strong> means {_f('owner_name')}, designated to maintain, interpret, communicate, and monitor enterprise-wide adherence to this Policy.</li>
  <li><strong>&ldquo;Covered Person&rdquo;</strong> means every officer, employee, contractor, volunteer, agent, or representative falling within Section 2.</li>
  <li><strong>&ldquo;Material Breach&rdquo;</strong> means any intentional, reckless, or repeated violation of a Mandatory Directive in Section 5 that exposes the Organization or its stakeholders to legal, financial, safety, or reputational harm.</li>
  <li><strong>&ldquo;Controlled Evidence&rdquo;</strong> means signed registers, audit logs, inspection certificates, risk assessments, or TrustSeal cryptographically sealed records verifying compliance.</li>
</ul>

<h2>5. Core Policy Principles &amp; Mandatory Directives</h2>
<p>5.1 <strong>Mandatory Institutional Rules.</strong> All Covered Persons shall strictly observe the following core policy directives without exception unless a formal written waiver is granted under Section 10:</p>
<ul>
{directives_html}</ul>
<p>5.2 <strong>Zero-Circumvention Clause.</strong> No Covered Person may indirectly achieve through an agent, subcontractor, related party, or informal arrangement any outcome prohibited by these directives.</p>

<h2>6. Operational Guidelines, Standard Procedures &amp; Implementation Controls</h2>
<p>6.1 <strong>Day-to-Day Execution Guidelines.</strong> To operationalize the directives in Section 5 consistently across all teams, the following standard procedures and controls are mandatory:</p>
<ol>
{guidelines_html}</ol>
<p>6.2 <strong>Documentation &amp; Auditability.</strong> Every approval, exception review, inspection, training completion, and incident closure executed under these guidelines shall be contemporaneously recorded with date, responsible officer, and verifiable supporting evidence in the Organization&rsquo;s central repository ({_f('project_code')}).</p>
<p>6.3 <strong>Segregation &amp; Dual Review.</strong> High-impact operational, financial, legal, or safety decisions under this Policy shall incorporate independent second-person verification to eliminate single-point-of-failure error or abuse.</p>

<h2>7. Governance, Roles &amp; Responsibilities (RACI Accountability)</h2>
<ul>
  <li><strong>Governing Board / Oversight Committee (Accountable):</strong> Approves this Policy and major revisions, sets organizational risk appetite, reviews quarterly compliance reports, and oversees independent escalation of executive breaches.</li>
  <li><strong>Chief Executive / Managing Director ({_f('approver_name')} — Executive Sponsor):</strong> Ensures adequate budget, staffing, and leadership tone-from-the-top to embed this Policy across every department.</li>
  <li><strong>Policy Owner ({_f('owner_name')} — Responsible):</strong> Maintains operational procedures, delivers staff guidance, tracks KPIs, coordinates annual reviews, and maintains controlled evidence records.</li>
  <li><strong>Department Heads &amp; Line Managers ({_f('department_lead')} — Responsible):</strong> Implement daily controls within their teams, ensure 100% staff onboarding/training, and escalate exceptions promptly.</li>
  <li><strong>Legal, Compliance &amp; Internal Audit ({_f('compliance_officer')} — Assurance):</strong> Provides independent regulatory interpretation, conducts periodic compliance testing, investigates reported breaches, and reports audit findings to the Audit &amp; Risk Committee.</li>
  <li><strong>All Covered Persons (Responsible):</strong> Read, understand, and comply with this Policy in daily work, complete mandatory training, and promptly report suspected violations or hazards.</li>
</ul>

<h2>8. Reporting, Escalation, Whistleblowing &amp; Incident Management</h2>
<p>8.1 <strong>Duty to Report.</strong> Any Covered Person who observes, suspects, or becomes aware of an actual or potential breach of this Policy, a regulatory violation, or a safety/security incident shall report it immediately to their Line Manager, the Policy Owner ({_f('owner_name')}), or the Compliance Officer ({_f('compliance_officer')}).</p>
<p>8.2 <strong>Confidential &amp; Anonymous Speak-Up Channel.</strong> Where a reporter is uncomfortable escalating through normal management lines, or where senior leadership may be implicated, reports may be lodged confidentially via the Organization&rsquo;s Ethics / Whistleblower Channel ({_f('ethics_channel')}) or directly to the Chair of the Audit &amp; Risk Committee.</p>
<p>8.3 <strong>Non-Retaliation Guarantee.</strong> {_f('organization_name')} strictly prohibits retaliation, intimidation, or adverse employment action against any person who raises a concern or assists an investigation in good faith.</p>
<p>8.4 <strong>Incident Containment &amp; CAPA.</strong> Confirmed incidents shall undergo immediate containment, objective Root Cause Analysis (RCA), formal Corrective and Preventive Action (CAPA) assignment, and statutory regulatory notification where legally required.</p>

<h2>9. Compliance Monitoring, Audits &amp; Key Performance Indicators (KPIs)</h2>
<p>9.1 <strong>Continuous Assurance &amp; Periodic Audits.</strong> Compliance with this Policy shall be monitored through monthly operational self-checks, quarterly Management reviews, and scheduled independent Internal Audit testing.</p>
<p>9.2 <strong>Policy Effectiveness KPIs.</strong> The Policy Owner shall report performance quarterly against the following mandatory metrics:</p>
<ul>
{kpis_html}  <li><strong>Training &amp; Attestation Rate:</strong> 100% of active Covered Persons completing onboarding and annual refresher acknowledgments.</li>
  <li><strong>Audit Finding Closure:</strong> 100% of High/Critical compliance audit findings remediated within agreed target dates.</li>
</ul>

<h2>10. Exceptions, Waivers &amp; Non-Compliance Consequences</h2>
<p>10.1 <strong>Strict Waiver Control.</strong> Temporary exceptions to non-statutory provisions of this Policy may only be granted where compelling operational justification exists, compensating risk controls are documented, Compliance ({_f('compliance_officer')}) concurs in writing, and {_f('approver_name')} approves a time-bound waiver (maximum ninety (90) days). No waiver may ever authorize a breach of statutory law.</p>
<p>10.2 <strong>Disciplinary &amp; Contractual Consequences.</strong> Non-compliance with this Policy shall be addressed proportionately under the Disciplinary Guidelines, ranging from formal coaching and written warnings to suspension or summary dismissal for gross misconduct, termination of vendor/partner contracts, civil recovery of losses, and referral to law enforcement or regulatory authorities where warranted.</p>

<h2>11. Training, Awareness, Annual Review &amp; Document Control</h2>
<p>11.1 <strong>Mandatory Communication &amp; Training.</strong> This Policy shall be published on the Organization&rsquo;s internal portal and TrustSeal Document Library, briefed during new-hire induction, and reinforced through annual mandatory compliance refresher training.</p>
<p>11.2 <strong>Scheduled Review &amp; Version Control.</strong> The Policy Owner ({_f('owner_name')}) shall review this Policy at least once every twelve (12) months (next scheduled review: {_f('review_date')}), or sooner following regulatory changes, audit findings, or major organizational restructuring.</p>
<p>11.3 <strong>Cryptographic Archival &amp; Revision Log.</strong> All approved versions and historical superseded editions shall be preserved with SHA-256 TrustSeal integrity verification for a minimum of seven (7) statutory years.</p>
<ul>
  <li><strong>Version 1.0 ({_f('effective_date')}):</strong> Initial Master Institutional Policy &amp; Guidelines adopted and published — Owner: {_f('owner_name')}.</li>
</ul>

<h2>12. Formal Institutional Adoption, Corporate Seal &amp; Personnel Acknowledgment</h2>
<p><strong>ADOPTED AND APPROVED</strong> as an official binding Policy &amp; Operational Guideline of <strong>{_f('organization_name')}</strong>, effective as of {_f('effective_date')}:</p>
<ul>
  <li><strong>Policy Owner / Prepared By:</strong> {_f('owner_name')} &nbsp;·&nbsp; Title: {_f('owner_title')} &nbsp;·&nbsp; Signature: ________________________ &nbsp;·&nbsp; Date: {_f('effective_date')}</li>
  <li><strong>Legal &amp; Compliance Concurrence:</strong> {_f('compliance_officer')} &nbsp;·&nbsp; Signature: ________________________ &nbsp;·&nbsp; Date: {_f('effective_date')}</li>
  <li><strong>Executive / Board Approval:</strong> {_f('approver_name')} &nbsp;·&nbsp; Title: {_f('approver_title')} &nbsp;·&nbsp; Signature: ________________________ &nbsp;·&nbsp; Date: {_f('effective_date')}</li>
</ul>
<p><strong>COVERED PERSON ACKNOWLEDGMENT:</strong> I confirm that I have received, read, and understood <strong>{title_u} ({policy_code})</strong> and agree to comply fully with its directives, operational guidelines, and reporting obligations.</p>
<p><strong>Name:</strong> {_f('employee_name')} &nbsp;·&nbsp; <strong>Department / Role:</strong> {_f('employee_role')} &nbsp;·&nbsp; <strong>Signature:</strong> ________________________ &nbsp;·&nbsp; <strong>Date:</strong> {_f('sign_date')}</p>
<p><em>[Affix Official Corporate Seal / TrustSeal Cryptographic Approval Stamp below]</em></p>
"""
