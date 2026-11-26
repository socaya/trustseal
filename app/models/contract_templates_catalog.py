"""Enterprise Library of 1,050+ Full-Length, Ready-to-Execute Contract Templates.

Every template in this catalog generates a complete, multi-page legal agreement
(14 structured articles: Recitals, Definitions, Scope, Deliverables & Acceptance,
Fees & Taxation, Term / Probation / Renewal, Warranties, Intellectual Property,
Confidentiality & Data Protection, SLA & Governance, Indemnification & Liability,
Suspension & Force Majeure, Termination & Transition, Governing Law & Disputes,
General Provisions, and Full Execution Block) plus structured ``default_key_terms``
and ``default_deliverables`` blueprints requiring minimal customization.
"""
from __future__ import annotations

import html as _html
from functools import lru_cache
from typing import Any


# ---------------------------------------------------------------------------
# 1. Practice Areas & Core Contract Archetypes (15 Categories × 10 Archetypes = 150)
#    × 7 Enterprise / Industry / Jurisdiction Editions = 1,050 Full Templates!
# ---------------------------------------------------------------------------

PRACTICE_ARCHETYPES: list[tuple[str, str, str, list[tuple[str, str, str, str]]]] = [
    # (Category, default_contract_type, default_project_category, [(slug_base, title_base, summary, domain_clauses_focus), ...])
    (
        "Commercial & Services",
        "msa",
        "client_delivery",
        [
            ("master_services_agreement", "Master Services Agreement (MSA)", "Comprehensive umbrella services framework governing multiple Statements of Work, change orders, SLAs, and commercial risk allocation.", "professional and managed commercial services"),
            ("statement_of_work_delivery", "Project Statement of Work (SOW)", "Milestone-driven project execution agreement with weighted deliverables, acceptance gates, payment tranches, and defect warranty.", "milestone-bound project delivery and implementation"),
            ("management_consulting_agreement", "Management & Strategy Consulting Agreement", "Executive advisory engagement covering strategic diagnostics, board deliverables, retainer fees, and strict confidentiality.", "executive strategy and management advisory"),
            ("managed_services_agreement", "Managed Services & Support Agreement", "Ongoing operational support contract with tiered SLA response matrices, uptime service credits, and monthly recurring billing.", "24/7 managed operations and service desk support"),
            ("business_process_outsourcing", "Business Process Outsourcing (BPO) Agreement", "End-to-end outsourced operations contract with KPI scorecards, data security controls, step-in rights, and exit transition.", "outsourced business operations and back-office processing"),
            ("marketing_agency_retainer", "Marketing & Creative Agency Retainer", "Full-service brand, campaign, and media buying agreement with IP assignment, media spend approvals, and performance KPIs.", "brand strategy, creative production, and media campaigns"),
            ("sales_agency_commission", "Commercial Sales Agency & Commission Agreement", "Territory-based commercial representation agreement defining qualified leads, commission tiers, clawbacks, and exclusivity.", "commercial sales representation and territory distribution"),
            ("event_management_services", "Corporate Event & Conference Management Agreement", "Turnkey corporate event production contract covering venue coordination, vendor management, cancellation tiers, and insurance.", "corporate event production and logistics"),
            ("facilities_management_contract", "Integrated Facilities Management Agreement", "Comprehensive commercial building maintenance, security, janitorial, and HVAC service agreement with health & safety compliance.", "integrated commercial facilities and building maintenance"),
            ("training_capacity_building", "Corporate Training & Capacity Building Agreement", "Structured curriculum delivery, certification workshops, participant licensing, and training material ownership terms.", "executive training, workshops, and workforce certification"),
        ],
    ),
    (
        "Employment, HR & Probation",
        "employment_probation",
        "hr_onboarding",
        [
            ("employment_90day_probation", "Employment Contract (90-Day Probation)", "Full-length permanent employment agreement featuring a structured 90-day probation period, 30/60/90-day reviews, and confirmation.", "full-time employment with a 90-day probationary evaluation"),
            ("employment_6month_probation", "Senior Management Employment (6-Month Probation)", "Executive-track employment contract with 180-day probation, performance bonus targets, confidentiality, and restrictive covenants.", "senior management employment with 6-month probation"),
            ("executive_ceo_employment", "Chief Executive / C-Suite Employment Agreement", "Board-level executive service agreement covering base salary, STI/LTI equity incentives, severance, and fiduciary duties.", "C-suite executive leadership and board accountability"),
            ("fixed_term_project_employment", "Fixed-Term Project Employment Contract", "Time-bound employment contract aligned to a specific project lifecycle with statutory gratuity and renewal notice rules.", "fixed-term project-tied employment"),
            ("remote_hybrid_employment", "Remote & Hybrid Work Employment Agreement", "Modern distributed workforce contract covering home-office stipends, information security, working hours, and cross-border tax.", "remote and hybrid distributed employment"),
            ("independent_contractor_agreement", "Independent Contractor & Freelancer Agreement", "Clear independent status agreement with deliverable invoicing, tax self-responsibility, IP assignment, and non-solicitation.", "independent specialist contracting services"),
            ("sales_executive_commission_emp", "Sales Executive Employment & Commission Plan", "Employment agreement incorporating quarterly quota attainment, commission schedules, clawback rules, and territory protection.", "commercial sales employment with incentive compensation"),
            ("internship_graduate_trainee", "Graduate Trainee & Internship Agreement", "Structured learning and mentorship contract with stipend terms, supervision milestones, IP assignment, and conversion option.", "graduate trainee and structured internship program"),
            ("employee_secondment_agreement", "Inter-Company Employee Secondment Agreement", "Tripartite secondment agreement governing host-entity supervision, cost recharge, benefits continuity, and repatriation.", "temporary inter-company employee secondment"),
            ("mutual_separation_severance", "Mutual Separation & Severance Settlement Deed", "Comprehensive termination settlement agreement with ex-gratia severance, full and final release, and non-disparagement.", "mutual employment separation and release of claims"),
        ],
    ),
    (
        "VitalWorks Enterprise Suite",
        "sow",
        "client_delivery",
        [
            ("vitalworks_enterprise_msa", "VitalWorks Enterprise Master Services Agreement", "Flagship VitalWorks commercial framework governing multi-year enterprise transformation, infrastructure, and advisory projects.", "VitalWorks enterprise transformation and operational delivery"),
            ("vitalworks_project_sow", "VitalWorks Project Delivery Statement of Work", "Comprehensive VitalWorks SOW with phased project governance, milestone acceptance certificates, and weighted payment tranches.", "VitalWorks phased project implementation"),
            ("vitalworks_clinical_systems", "VitalWorks Clinical Systems Deployment Agreement", "Healthcare IT and clinical workflow deployment contract with patient data privacy, uptime guarantees, and clinical sign-off.", "VitalWorks clinical systems and digital health deployment"),
            ("vitalworks_infrastructure_epc", "VitalWorks Infrastructure & Engineering Contract", "Turnkey engineering, procurement, and commissioning contract with performance bonds, liquidated damages, and snagging.", "VitalWorks engineering and infrastructure commissioning"),
            ("vitalworks_workforce_probation", "VitalWorks Employment & 90-Day Probation Contract", "Standard VitalWorks Group employment contract with structured 30/60/90-day probation reviews and IP protection.", "VitalWorks workforce engagement and probation governance"),
            ("vitalworks_vendor_supply", "VitalWorks Approved Vendor & Supply Agreement", "Strategic VitalWorks supplier agreement covering quality assurance, delivery lead times, warranty, and anti-bribery compliance.", "VitalWorks strategic supply chain and vendor delivery"),
            ("vitalworks_sla_managed_ops", "VitalWorks Managed Operations & SLA Contract", "24/7 managed operations contract with severity-based response times, monthly governance reviews, and service credits.", "VitalWorks managed operations and SLA compliance"),
            ("vitalworks_channel_partner", "VitalWorks Authorized Channel Partner Agreement", "Regional reseller and systems integrator agreement with certification requirements, deal registration, and revenue share.", "VitalWorks authorized channel and systems integration"),
            ("vitalworks_data_processing", "VitalWorks Data Processing & Security Addendum", "Comprehensive DPA aligning with GDPR and regional Data Protection Acts, covering sub-processors and breach notification.", "VitalWorks personal data processing and cybersecurity"),
            ("vitalworks_joint_delivery_jv", "VitalWorks Consortium & Joint Delivery Agreement", "Multi-party consortium agreement for large-scale enterprise and public-sector tenders with clear scope and liability split.", "VitalWorks joint consortium project delivery"),
        ],
    ),
    (
        "VitalWills Estate & Fiduciary",
        "custom",
        "legal_governance",
        [
            ("vitalwills_last_will_testament", "VitalWills Comprehensive Last Will & Testament", "Full formal testamentary instrument covering revocation of prior wills, executor appointment, specific bequests, residue, and attestation.", "testamentary estate disposition and executor administration"),
            ("vitalwills_family_discretionary_trust", "VitalWills Family Discretionary Trust Deed", "Multi-generational family trust deed defining settlor, trustees, beneficiaries, investment powers, distributions, and perpetuity.", "discretionary family trust governance and asset protection"),
            ("vitalwills_revocable_living_trust", "VitalWills Revocable Living Trust Agreement", "Inter-vivos living trust designed for seamless incapacity planning, probate avoidance, and structured successor trustee handoff.", "inter-vivos revocable living trust administration"),
            ("vitalwills_enduring_poa", "VitalWills Enduring Power of Attorney", "Comprehensive financial and property power of attorney with donor capacity safeguards, attorney duties, and accounting obligations.", "enduring financial and property power of attorney"),
            ("vitalwills_healthcare_directive", "VitalWills Advance Healthcare Directive & Medical Proxy", "Formal living will and healthcare proxy appointing a medical decision-maker and specifying end-of-life care preferences.", "advance healthcare directive and medical proxy authority"),
            ("vitalwills_codicil_amendment", "VitalWills Formal Codicil to Last Will", "Legally structured codicil modifying specific clauses or bequests of an existing principal Last Will while republishing the remainder.", "formal testamentary codicil and will modification"),
            ("vitalwills_executor_engagement", "VitalWills Professional Executor & Probate Mandate", "Fiduciary engagement agreement appointing VitalWills as professional executor/administrator with fee schedule and reporting.", "professional estate administration and probate representation"),
            ("vitalwills_guardianship_deed", "VitalWills Deed of Testamentary Guardianship", "Dedicated legal instrument appointing primary and alternate guardians for minor children along with educational trust guidance.", "testamentary guardianship and minor welfare provisions"),
            ("vitalwills_charitable_endowment", "VitalWills Charitable Foundation & Endowment Deed", "Philanthropic trust and endowment instrument governing charitable objects, board of trustees, grant-making, and audit.", "charitable foundation and perpetual endowment governance"),
            ("vitalwills_safe_custody_vault", "VitalWills Will Custody & Digital Vault Agreement", "Fiduciary custody agreement for physical and cryptographic preservation of testamentary instruments with release protocols.", "fiduciary safe custody and digital vault preservation"),
        ],
    ),
    (
        "VitalReturns Tax & Fiscal",
        "msa",
        "client_delivery",
        [
            ("vitalreturns_tax_advisory_engagement", "VitalReturns Corporate Tax Advisory Engagement", "Comprehensive tax consultancy engagement covering corporate income tax opinions, structuring, compliance calendars, and liability.", "corporate tax advisory and fiscal structuring"),
            ("vitalreturns_statutory_audit_letter", "VitalReturns Statutory Audit & Assurance Agreement", "Formal external audit engagement aligned with ISA standards, management representations, materiality, and reporting deadlines.", "independent statutory financial audit and assurance"),
            ("vitalreturns_transfer_pricing_study", "VitalReturns Transfer Pricing Documentation Contract", "OECD-aligned Master File, Local File, and benchmarking study engagement for multinational related-party transactions.", "transfer pricing documentation and benchmarking"),
            ("vitalreturns_vat_indirect_tax", "VitalReturns VAT & Customs Compliance Retainer", "Ongoing indirect tax review, monthly VAT return reconciliation, refund audits, and customs tariff advisory contract.", "VAT reconciliation, refund claims, and customs compliance"),
            ("vitalreturns_payroll_paye_admin", "VitalReturns Managed Payroll & PAYE Agreement", "End-to-end monthly payroll processing, statutory PAYE/social security remittance, payslip distribution, and confidentiality.", "managed payroll processing and statutory remittances"),
            ("vitalreturns_tax_dispute_representation", "VitalReturns Tax Controversy & Tribunal Mandate", "Formal mandate for tax audit defense, notice of objection drafting, ADR negotiations, and Tax Appeals Tribunal representation.", "tax audit defense and revenue dispute resolution"),
            ("vitalreturns_due_diligence_ma", "VitalReturns Tax & Financial Due Diligence Contract", "Buy-side or sell-side M&A due diligence engagement covering historical tax exposures, contingent liabilities, and red-flag reports.", "transaction tax and financial due diligence"),
            ("vitalreturns_private_wealth_tax", "VitalReturns Private Client & Capital Gains Mandate", "Discreet tax residency, capital gains optimization, and personal wealth compliance engagement for HNW individuals.", "private client wealth and capital gains tax advisory"),
            ("vitalreturns_sme_accounting_retainer", "VitalReturns SME Bookkeeping & Annual Returns", "Monthly management accounts, bank reconciliations, statutory filings, and year-end corporate tax return preparation.", "SME accounting, bookkeeping, and statutory returns"),
            ("vitalreturns_health_check_review", "VitalReturns Statutory Tax Health-Check Agreement", "Diagnostic compliance review of historical corporate tax, VAT, withholding tax, and payroll filings with remediation roadmap.", "comprehensive statutory tax health-check diagnostics"),
        ],
    ),
    (
        "Technology, SaaS & IP",
        "msa",
        "client_delivery",
        [
            ("enterprise_saas_subscription", "Enterprise SaaS Subscription & SLA Agreement", "Cloud software subscription contract with user tiers, 99.9% uptime SLA, data ownership, security controls, and auto-renewal.", "cloud SaaS platform subscription and uptime governance"),
            ("custom_software_development", "Custom Software Development Agreement", "Agile/waterfall software engineering contract with sprint milestones, source code IP assignment, UAT acceptance, and bug warranty.", "bespoke software architecture, engineering, and delivery"),
            ("software_license_onprem", "Enterprise On-Premise Software License Agreement", "Perpetual or term software licensing contract covering deployment scope, maintenance updates, audit rights, and reverse-engineering bans.", "on-premise enterprise software licensing and support"),
            ("api_integration_license", "API Access & Platform Integration Agreement", "Developer and enterprise API usage contract specifying rate limits, authentication security, webhooks, and uptime commitments.", "commercial API access and system integration"),
            ("white_label_oem_software", "White-Label & OEM Software Reseller Agreement", "Co-branding and OEM embedding license covering brand guidelines, wholesale pricing, Tier-1/Tier-2 support, and territory rights.", "white-label software licensing and OEM distribution"),
            ("data_processing_agreement_dpa", "Data Processing Agreement (GDPR / Regional DPA)", "Comprehensive controller-processor DPA detailing processing instructions, TOMs, sub-processor lists, SCCs, and 72-hour breach notice.", "personal data processing and cross-border transfer compliance"),
            ("source_code_escrow_agreement", "Tripartite Software Source Code Escrow Agreement", "Three-party escrow arrangement securing source code deposits, verification testing, and release triggers upon vendor insolvency.", "software source code escrow and continuity protection"),
            ("ai_model_data_license", "AI Model & Commercial Dataset License Agreement", "Modern AI licensing contract governing training data provenance, output ownership, bias/safety guardrails, and usage restrictions.", "AI model deployment and commercial dataset licensing"),
            ("ip_assignment_deed", "Deed of Intellectual Property Assignment", "Absolute assignment of patents, copyrights, trademarks, source code, and moral rights waivers with further assurance covenants.", "absolute intellectual property transfer and assignment"),
            ("cybersecurity_pentest_agreement", "Cybersecurity & Penetration Testing Authorization", "Authorized security assessment contract defining rules of engagement, scope IP ranges, zero-day disclosure, and liability caps.", "authorized cybersecurity audit and penetration testing"),
        ],
    ),
    (
        "Procurement, Supply & Logistics",
        "vendor_supply",
        "vendor_procurement",
        [
            ("master_supply_agreement", "Master Goods Supply Agreement", "Long-term commercial supply contract covering purchase orders, forecasting, Incoterms, quality inspection, and price adjustment.", "recurring commercial goods supply and quality assurance"),
            ("contract_manufacturing_oem", "Contract Manufacturing & OEM Production Agreement", "Bespoke product manufacturing contract governing bill of materials, tooling ownership, QA testing, recalls, and exclusivity.", "contract manufacturing and OEM quality governance"),
            ("exclusive_distribution_agreement", "Exclusive Commercial Distribution Agreement", "Regional distribution contract setting minimum purchase quotas, marketing commitments, brand protection, and termination buyback.", "exclusive territorial distribution of commercial goods"),
            ("freight_forwarding_logistics", "Freight Forwarding & Multimodal Logistics Contract", "International shipping and customs brokerage agreement covering bills of lading, demurrage, cargo insurance, and transit SLAs.", "international freight forwarding and customs clearance"),
            ("warehousing_3pl_fulfillment", "3PL Warehousing & Fulfillment Services Agreement", "Third-party logistics contract covering inventory accuracy, shrinkage thresholds, pick-and-pack SLAs, and warehouseman's lien.", "third-party warehousing and order fulfillment"),
            ("equipment_supply_installation", "Capital Equipment Supply & Commissioning Contract", "Turnkey machinery procurement covering factory acceptance testing (FAT), site installation, operator training, and warranty.", "capital equipment supply, installation, and commissioning"),
            ("annual_maintenance_amc", "Annual Maintenance & Spare Parts Contract (AMC)", "Preventive and corrective equipment maintenance agreement with response SLAs, genuine spare parts supply, and uptime guarantees.", "preventive and corrective equipment maintenance"),
            ("fleet_leasing_transport", "Commercial Fleet Leasing & Haulage Agreement", "Dedicated transport and vehicle leasing contract covering driver compliance, fuel surcharges, GPS tracking, and cargo liability.", "commercial fleet leasing and dedicated haulage"),
            ("raw_materials_offtake", "Long-Term Raw Materials Offtake Agreement", "Commodity supply and offtake contract featuring index-linked pricing, quality assay testing, take-or-pay volumes, and force majeure.", "long-term raw materials supply and offtake"),
            ("vendor_code_of_conduct", "Supplier ESG, Anti-Bribery & Quality Compliance Deed", "Binding supplier compliance covenant covering anti-corruption, fair labor, environmental standards, and audit rights.", "supplier ESG, ethics, and anti-bribery compliance"),
        ],
    ),
    (
        "Real Estate & Construction",
        "commercial_lease",
        "client_delivery",
        [
            ("commercial_office_lease", "Commercial Office Lease Agreement", "Full institutional commercial lease covering rent escalations, service charge, fit-out period, quiet enjoyment, and forfeiture.", "commercial office premises leasing and service charges"),
            ("retail_mall_lease", "Retail & Shopping Centre Lease Agreement", "Retail tenancy contract featuring base rent plus turnover rent, trading hours, signage rules, and anchor-tenant covenants.", "retail premises leasing and turnover rent governance"),
            ("industrial_warehouse_lease", "Industrial & Logistics Warehouse Lease", "Heavy-use industrial lease covering floor load limits, environmental indemnities, structural repair, and expansion options.", "industrial warehouse and logistics facility leasing"),
            ("fidic_design_build_contract", "Design-Build Construction Contract (FIDIC-Aligned)", "Comprehensive turnkey construction contract covering employer's requirements, engineer's certificates, variations, retention, and DLP.", "design-build civil and building construction"),
            ("construction_subcontract", "Back-to-Back Construction Subcontract Agreement", "Subcontractor execution agreement flowing down main contract obligations, interim valuations, pay-when-paid, and site safety.", "back-to-back specialist construction subcontracting"),
            ("architectural_design_services", "Architectural & Engineering Consultancy Contract", "RIBA/FIDIC-style design consultancy covering concept to tender stages, BIM ownership, site supervision, and PI insurance.", "architectural and structural engineering consultancy"),
            ("property_management_agreement", "Commercial Property Management Agreement", "Managing agent contract covering rent collection, tenant vetting, preventive maintenance, trust accounting, and management fees.", "commercial real estate and tenant management"),
            ("real_estate_sale_agreement", "Agreement for Sale of Commercial Property", "Formal conveyancing sale contract covering deposit stakeholder holding, title due diligence, completion notice, and vacant possession.", "commercial real estate acquisition and conveyancing"),
            ("joint_real_estate_development", "Real Estate Joint Development Agreement (JDA)", "Landowner-developer joint venture governing land contribution, development finance, revenue/unit sharing, and project escrow.", "joint real estate development and revenue sharing"),
            ("coworking_serviced_office", "Serviced Office & Co-Working Membership Agreement", "Flexible workspace license covering dedicated suites, IT connectivity, meeting credits, deposit, and short-notice renewal.", "flexible serviced office and co-working licensing"),
        ],
    ),
    (
        "Banking, Finance & Investment",
        "msa",
        "legal_governance",
        [
            ("corporate_term_loan", "Senior Corporate Term Loan Facility Agreement", "Institutional loan agreement detailing drawdown conditions precedent, interest/SOFR margin, amortization, financial covenants, and defaults.", "senior corporate term loan financing"),
            ("revolving_credit_facility", "Revolving Working Capital Credit Facility", "Flexible multi-draw credit line covering commitment fees, borrowing base certificates, clean-down periods, and security.", "revolving working capital credit facility"),
            ("shareholders_agreement_sha", "Comprehensive Shareholders' Agreement (SHA)", "Corporate governance pact covering board composition, reserved matters, pre-emption, drag-along, tag-along, and deadlock resolution.", "shareholder governance, voting, and exit rights"),
            ("share_purchase_agreement_spa", "Share Purchase Agreement (M&A SPA)", "Full M&A acquisition contract with purchase price adjustment, locked-box/completion accounts, warranties, disclosure, and indemnities.", "private company share acquisition and M&A closing"),
            ("safe_investment_instrument", "Post-Money SAFE Investment Agreement", "Startup equity financing instrument defining valuation cap, discount rate, pro-rata rights, and liquidity event conversion.", "early-stage SAFE equity financing"),
            ("convertible_loan_note", "Convertible Loan Note Instrument", "Bridge financing note detailing interest accrual, qualified financing conversion discount, maturity redemption, and investor rights.", "convertible debt financing and equity conversion"),
            ("corporate_guarantee_indemnity", "Deed of Corporate Guarantee & Indemnity", "Unconditional continuing parent/third-party guarantee securing principal borrower obligations with independent indemnity covenants.", "continuing corporate guarantee and financial indemnity"),
            ("escrow_account_agreement", "Commercial M&A / Project Escrow Agreement", "Tripartite escrow deed governing deposit custody, milestone/closing release instructions, interest accrual, and dispute interpleader.", "commercial transaction escrow custody"),
            ("asset_purchase_agreement", "Business & Asset Purchase Agreement (APA)", "Selective acquisition of business assets, customer contracts, IP, and employee transfers while excluding legacy liabilities.", "selective business and asset acquisition"),
            ("receivables_factoring_agreement", "Invoice Factoring & Receivables Finance Agreement", "Working capital receivables purchase contract covering advance rates, discount fees, debtor notification, and recourse terms.", "commercial invoice factoring and receivables finance"),
        ],
    ),
    (
        "Healthcare & Life Sciences",
        "msa",
        "client_delivery",
        [
            ("clinical_trial_agreement", "Clinical Trial Site Agreement (CTA)", "Sponsor-institution clinical research contract covering IRB/ethics approvals, GCP compliance, subject injury indemnity, and publication.", "GCP-compliant clinical trial execution"),
            ("hospital_service_agreement", "Hospital & Clinical Specialist Services Agreement", "Institutional medical staffing and specialist department management contract covering credentialing, malpractice cover, and quality metrics.", "specialist hospital and clinical department services"),
            ("medical_device_supply", "Medical Equipment Supply & Calibration Contract", "Regulated medical device procurement covering regulatory approvals, installation, preventive calibration, and recall compliance.", "regulated medical device supply and servicing"),
            ("health_data_baa", "Healthcare Business Associate Agreement (BAA)", "Strict protected health information (PHI) safeguards, encryption standards, breach reporting, and sub-contractor flow-down.", "protected health information privacy and security"),
            ("telemedicine_platform_agreement", "Telemedicine & Digital Health Platform Agreement", "Virtual care delivery contract governing clinician licensing, e-prescribing compliance, platform uptime, and patient consent.", "telemedicine platform and virtual care governance"),
            ("pharmaceutical_distribution", "Pharmaceutical Cold-Chain Distribution Agreement", "GDP-compliant pharma distribution covering temperature-controlled logistics, batch traceability, pharmacovigilance, and returns.", "GDP pharmaceutical cold-chain distribution"),
            ("laboratory_reference_services", "Accredited Reference Laboratory Services Agreement", "Diagnostic specimen testing contract with turnaround time SLAs, ISO 15189 accreditation maintenance, and electronic reporting.", "accredited diagnostic laboratory testing services"),
            ("physician_employment_contract", "Consultant Physician Employment Agreement", "Hospital-physician contract covering clinical duties, call rotations, CME allowance, malpractice tail coverage, and probation.", "consultant physician clinical employment"),
            ("health_insurer_provider_panel", "Health Insurer Provider Network Agreement", "Payer-provider tariff and claims adjudication contract covering pre-authorization, electronic billing, and 30-day settlement.", "healthcare insurer provider panel and claims settlement"),
            ("biotech_research_collaboration", "Biotech & Academic Research Collaboration Deed", "Joint R&D agreement governing background/foreground IP, milestone royalties, patent prosecution, and commercialization rights.", "biotech joint research and IP commercialization"),
        ],
    ),
    (
        "Confidentiality & Strategic Deals",
        "nda",
        "legal_governance",
        [
            ("mutual_nda_comprehensive", "Comprehensive Mutual Non-Disclosure Agreement", "Balanced two-way confidentiality agreement with clear exclusions, residuals, 5-year survival, return/destruction, and injunctive relief.", "bilateral confidential information protection"),
            ("unilateral_nda_disclosing", "Unilateral Non-Disclosure Agreement (Disclosing Party)", "Protective one-way NDA designed for sharing proprietary financials, trade secrets, or technical IP with prospective vendors/buyers.", "unilateral trade secret and commercial disclosure"),
            ("ma_data_room_nda", "M&A Virtual Data Room Confidentiality Agreement", "Deal-specific NDA incorporating standstill covenants, non-solicitation of key staff, clean-team rules, and adviser responsibility.", "M&A due diligence and virtual data room confidentiality"),
            ("ncnda_international_trade", "Non-Circumvention & Non-Disclosure Agreement (NCNDA)", "ICC-aligned international trade protection contract securing broker introductions, commission entitlements, and 5-year non-circumvention.", "international trade non-circumvention and brokerage protection"),
            ("memorandum_of_understanding", "Strategic Memorandum of Understanding (MOU)", "Structured pre-contractual framework establishing collaboration scope, working committees, exclusivity window, and binding confidentiality.", "strategic institutional collaboration framework"),
            ("letter_of_intent_acquisition", "Letter of Intent (LOI) / Term Sheet — Acquisition", "Binding exclusivity and confidentiality paired with non-binding valuation, structure, due diligence timeline, and closing conditions.", "pre-acquisition deal terms and exclusivity"),
            ("joint_venture_agreement", "Corporate Joint Venture Agreement", "Comprehensive JV pact governing capital contributions, management committee, profit waterfall, IP licensing, and exit buyouts.", "strategic corporate joint venture operations"),
            ("general_partnership_deed", "Professional Partnership Deed", "Formal partnership constitution detailing capital accounts, profit-sharing ratios, partner admission/retirement, and dissolution.", "professional partnership governance and profit sharing"),
            ("contract_amendment_deed", "Deed of Contract Amendment & Variation", "Formal bilateral instrument modifying pricing, scope, timelines, or clauses of an existing principal agreement while preserving continuity.", "formal modification of an existing principal agreement"),
            ("novation_assignment_deed", "Tripartite Deed of Novation & Assignment", "Three-party deed transferring all rights, obligations, and liabilities under an existing contract from outgoing to incoming party.", "tripartite contract novation and liability transfer"),
        ],
    ),
    (
        "Energy, Mining & Natural Resources",
        "msa",
        "client_delivery",
        [
            ("solar_power_purchase_ppa", "Commercial Solar Power Purchase Agreement (PPA)", "Long-term clean energy offtake contract covering kWh tariff, escalation, net metering, performance ratio, and system buyout.", "commercial solar energy generation and offtake"),
            ("epc_renewable_plant", "Renewable Energy EPC Turnkey Contract", "Utility-scale solar/wind EPC contract covering grid interconnection, performance ratio testing, delay LDs, and 2-year DLP.", "renewable energy plant engineering and construction"),
            ("om_energy_facility", "Energy Plant Operations & Maintenance (O&M) Contract", "Long-term power plant O&M agreement with availability guarantees, preventive schedules, spare parts, and bonus/malus regime.", "power generation facility operations and maintenance"),
            ("mining_services_contract", "Contract Mining & Earthmoving Services Agreement", "Heavy mining operations contract covering BCM rates, blast safety, equipment availability, fuel supply, and environmental rehab.", "contract mining and heavy earthmoving operations"),
            ("fuel_supply_agreement", "Bulk Petroleum & Diesel Supply Agreement", "Commercial fuel supply contract covering Platts-indexed pricing, tank telemetry, quality specs, delivery SLAs, and credit terms.", "bulk commercial petroleum and fuel supply"),
            ("carbon_credit_offtake", "Verified Carbon Credit Offtake Agreement (ERPA)", "Emission reduction purchase agreement governing Verra/Gold Standard verification, delivery vintage, registry transfer, and pricing.", "verified carbon credit generation and offtake"),
            ("energy_audit_esco", "Energy Performance & ESCO Savings Contract", "Guaranteed energy-savings retrofit agreement sharing verified utility savings with measurement & verification (IPMVP) protocols.", "energy efficiency retrofit and shared savings"),
            ("mineral_exploration_jv", "Mineral Exploration Farm-In & Joint Venture", "Earn-in exploration agreement detailing minimum work expenditure, tenement maintenance, operator duties, and dilution formulas.", "mineral exploration earn-in and joint venture"),
            ("water_utility_concession", "Water Treatment & Supply Concession Contract", "Industrial water purification and supply agreement covering quality testing, minimum off-take, tariff indexation, and handover.", "industrial water treatment and utility supply"),
            ("environmental_remediation", "Environmental Impact & Remediation Services Contract", "Regulated environmental audit, EIA licensing, and site remediation contract with statutory compliance warranties.", "environmental impact assessment and site remediation"),
        ],
    ),
    (
        "Media, Creative & Licensing",
        "msa",
        "client_delivery",
        [
            ("brand_trademark_license", "Brand & Trademark Commercial Licensing Agreement", "Territory-scoped trademark licensing contract covering quality control approvals, minimum royalties, audit rights, and brand misuse.", "commercial brand and trademark licensing"),
            ("film_video_production", "Commercial Film & Video Production Agreement", "End-to-end production contract covering script approval, shoot schedule, talent releases, music clearances, and master delivery.", "commercial film and digital video production"),
            ("influencer_ambassador_deal", "Brand Ambassador & Influencer Endorsement Contract", "Creator partnership contract specifying content deliverables, usage rights, FTC/disclosure compliance, morality clause, and exclusivity.", "brand endorsement and digital creator campaigns"),
            ("sponsorship_partnership", "Corporate Event & Sports Sponsorship Agreement", "Title/tier sponsorship contract detailing naming rights, hospitality allocations, broadcast visibility, and ambush-marketing protection.", "corporate event and commercial sponsorship"),
            ("publishing_book_contract", "Publishing & Literary Rights Agreement", "Author-publisher contract governing print/eBook/audio rights, advance against royalties, editorial control, and reversion of rights.", "literary publishing and multi-format royalty licensing"),
            ("music_sync_licensing", "Music Synchronization & Master Use License", "Commercial sync license clearing composition and master recording rights for broadcast, streaming, and advertising campaigns.", "music synchronization and master recording clearance"),
            ("photography_commission", "Commercial Photography Commission & Usage License", "Editorial/advertising shoot contract defining day rates, retouching deliverables, territorial usage rights, and model releases.", "commercial photography production and usage licensing"),
            ("podcast_production_network", "Podcast Production & Ad-Sales Network Agreement", "Audio production and monetization contract covering episode cadence, host-read ad inventory, revenue share, and feed ownership.", "podcast production and advertising monetization"),
            ("franchise_operations_agreement", "Commercial Franchise Operations Agreement", "Full-format franchise contract covering initial franchise fee, ongoing royalties, operations manual, site approval, and training.", "commercial franchise system and brand operations"),
            ("merchandising_character_license", "Merchandising & Product Licensing Agreement", "Consumer product licensing contract governing design approvals, sample sign-off, wholesale royalty accounting, and sell-off.", "consumer goods merchandising and character licensing"),
        ],
    ),
    (
        "Telecom, Aviation & Maritime",
        "msa",
        "client_delivery",
        [
            ("enterprise_fiber_sla", "Enterprise Dedicated Fiber & Bandwidth Agreement", "Carrier-grade connectivity contract with 99.95% uptime SLA, latency/jitter thresholds, diverse routing, and outage credits.", "dedicated enterprise fiber connectivity and SLA"),
            ("tower_colocation_lease", "Telecom Tower Co-Location & Site Sharing Agreement", "Passive infrastructure sharing contract covering antenna loading, generator power SLA, site access, and annual escalation.", "telecom tower co-location and passive infrastructure"),
            ("data_center_colocation", "Tier-III Data Center Co-Location Agreement", "Rack/cage hosting contract covering redundant power (kW), cooling SLAs, biometric security, cross-connects, and remote hands.", "Tier-III data center rack hosting and power SLA"),
            ("aircraft_charter_agreement", "Corporate Aircraft Charter Agreement", "Executive aviation charter contract covering flight itinerary, crew compliance, fuel/landing fees, cancellation tiers, and insurance.", "corporate executive aircraft charter operations"),
            ("aircraft_dry_lease", "Commercial Aircraft Dry Lease Agreement", "Aviation leasing contract covering delivery condition, airworthiness directives, maintenance reserves, hull insurance, and redelivery.", "commercial aircraft dry leasing and maintenance reserves"),
            ("vessel_time_charter", "Maritime Vessel Time Charterparty Agreement", "Commercial shipping charter covering vessel specifications, hire rate, bunkers, off-hire clauses, and maritime arbitration.", "maritime vessel time charter operations"),
            ("port_terminal_handling", "Port Terminal & Stevedoring Services Agreement", "Container/bulk cargo handling contract covering crane productivity SLAs, demurrage, customs clearance, and cargo liability.", "port terminal handling and stevedoring operations"),
            ("satellite_vsat_services", "Satellite VSAT & Managed Connectivity Agreement", "Remote-site satellite communications contract covering bandwidth allocation, hardware lease, field maintenance, and uptime SLA.", "enterprise satellite VSAT connectivity"),
            ("roaming_interconnect_pact", "Telecom Interconnect & Wholesale Traffic Agreement", "Carrier wholesale voice/SMS/data termination contract covering rate decks, dispute thresholds, fraud prevention, and settlement.", "carrier wholesale telecom interconnect and settlement"),
            ("drone_uav_commercial_ops", "Commercial Drone / UAV Survey Services Agreement", "Civil-aviation compliant aerial mapping and inspection contract covering flight permits, airspace safety, and GIS deliverables.", "commercial UAV aerial survey and GIS delivery"),
        ],
    ),
    (
        "Education, NGO & Public Sector",
        "msa",
        "client_delivery",
        [
            ("grant_funding_agreement", "Institutional Grant & Donor Funding Agreement", "Philanthropic/donor grant contract detailing programmatic milestones, restricted funds accounting, audit rights, and clawback.", "institutional grant funding and impact compliance"),
            ("sub_grant_implementing_partner", "NGO Implementing Partner Sub-Grant Agreement", "Flow-down sub-grant agreement covering safeguarding policies, quarterly financial reporting, procurement rules, and M&E metrics.", "NGO implementing partner sub-grant delivery"),
            ("university_research_contract", "Sponsored University Research Agreement", "Industry-academia research contract governing principal investigator duties, publication review, background IP, and licensing option.", "sponsored academic research and IP governance"),
            ("edtech_school_deployment", "EdTech Institutional Licensing & LMS Agreement", "School/university learning platform contract covering student data privacy, teacher onboarding, uptime, and annual seat licensing.", "educational technology platform deployment"),
            ("public_procurement_works", "Public Sector Procurement & Supply Contract", "Statutory public tender contract incorporating performance securities, anti-corruption declarations, inspection, and payment milestones.", "public sector tendered procurement and delivery"),
            ("ngo_fiscal_sponsorship", "Fiscal Sponsorship & Program Hosting Agreement", "Non-profit fiscal hosting contract covering grant administration fees, charitable compliance, branding, and asset spin-off.", "non-profit fiscal sponsorship and grant hosting"),
            ("scholarship_fellowship_deed", "Corporate Scholarship & Fellowship Bond Deed", "Educational sponsorship agreement covering tuition disbursement, academic standing requirements, mentorship, and service bond.", "corporate scholarship funding and fellowship terms"),
            ("curriculum_licensing_pact", "Academic Curriculum & Accreditation License", "Institutional program licensing covering syllabus updates, faculty certification, examination moderation, and per-student royalties.", "academic curriculum and accreditation licensing"),
            ("international_aid_logistics", "Humanitarian Relief Logistics & Distribution Contract", "Emergency relief supply and last-mile distribution contract with zero-tolerance safeguarding, customs exemption, and chain of custody.", "humanitarian logistics and last-mile distribution"),
            ("ppp_public_private_concession", "Public-Private Partnership (PPP) Concession Framework", "Long-term infrastructure PPP framework detailing concession period, tariff formula, sovereign risk allocation, and handback.", "public-private partnership infrastructure concession"),
        ],
    ),
]


# 7 Enterprise / Industry / Jurisdiction Editions per Archetype -> 150 × 7 = 1,050 Full Templates!
EDITIONS: list[tuple[str, str, str, str, str]] = [
    # (suffix, label_tag, jurisdiction_default, commercial_posture, extra_clause_note)
    (
        "standard",
        "Standard Enterprise",
        "Kenya / England & Wales",
        "balanced commercial risk allocation suitable for standard corporate transactions",
        "Standard bilateral commercial protections, 30-day invoicing, and 12-month aggregate liability cap.",
    ),
    (
        "enterprise_pro",
        "Enterprise Master (High-Value)",
        "England & Wales / International",
        "enhanced enterprise governance, steering committee oversight, step-in rights, and audit trails",
        "Includes quarterly Executive Steering Committee reviews, ISO 27001 security controls, and formal transition assistance.",
    ),
    (
        "east_africa",
        "East Africa / EAC Edition",
        "Republic of Kenya (EAC Commercial Law)",
        "regional East African Community statutory compliance, withholding tax clarity, and Nairobi arbitration",
        "Aligned with Kenya Law of Contract Act, Data Protection Act, and Nairobi Centre for International Arbitration (NCIA) rules.",
    ),
    (
        "uk_eu",
        "UK & EU GDPR Edition",
        "England & Wales (UK/EU GDPR)",
        "strict UK/EU GDPR data protection, Late Payment of Commercial Debts compliance, and London arbitration",
        "Incorporates UK/EU GDPR Article 28 processor safeguards, Bribery Act 2010 covenants, and LCIA dispute resolution.",
    ),
    (
        "us_delaware",
        "US Commercial (Delaware)",
        "State of Delaware, USA",
        "US commercial standards, UCC warranty disclaimers, jury trial waiver, and AAA arbitration",
        "Structured under Delaware commercial law with express UCC implied-warranty disclaimers and mutual jury trial waiver.",
    ),
    (
        "sme_fasttrack",
        "SME Fast-Track Edition",
        "Kenya / Common Law",
        "streamlined execution for agile SME engagements with clear deliverables and rapid 14-day settlement",
        "Optimized for fast-moving SME deals with concise schedules, 14-day payment terms, and expedited mediation.",
    ),
    (
        "regulated_compliance",
        "Regulated & Audit-Ready Edition",
        "International Regulated Standards",
        "heightened regulatory audit rights, anti-money laundering (AML), KYC, and cryptographic TrustSeal retention",
        "Includes mandatory regulatory inspection access, AML/KYC representations, business continuity (BCP), and 7-year evidence retention.",
    ),
]


def _default_key_terms_for(ctype: str, edition_slug: str, title: str) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    if ctype == "employment_probation":
        p_days = 180 if "6-Month" in title or "Senior" in title else 90
        terms.append({
            "category": "probation",
            "term_key": "probation_period",
            "label": f"{p_days}-Day Probation Period",
            "value_text": f"{p_days} calendar days with formal 30/60/{p_days}-day performance reviews",
            "numeric_value": p_days,
            "unit": "days",
            "offset_days": p_days,
            "alert_days_before": 14,
            "clause_ref": "Article 5 (Probation & Confirmation)",
        })
        terms.append({
            "category": "renewal_notice",
            "term_key": "notice_period",
            "label": "Post-Probation Termination Notice",
            "value_text": "30 calendar days written notice (7 days during probation)",
            "clause_ref": "Article 12 (Termination)",
        })
    else:
        pay_days = 14 if edition_slug == "sme_fasttrack" else 30
        terms.append({
            "category": "financial",
            "term_key": "payment_terms",
            "label": "Payment & Settlement Window",
            "value_text": f"Net {pay_days} calendar days from undisputed invoice",
            "numeric_value": pay_days,
            "unit": "days",
            "clause_ref": "Article 4 (Fees, Invoicing & Tax)",
        })
        terms.append({
            "category": "sla",
            "term_key": "acceptance_sla",
            "label": "Deliverable Acceptance Window",
            "value_text": "10 business days to accept or issue written defect notice",
            "numeric_value": 10,
            "unit": "business_days",
            "clause_ref": "Article 3 (Deliverables & Acceptance)",
        })
        terms.append({
            "category": "liability_ip",
            "term_key": "liability_cap",
            "label": "Aggregate Liability Cap",
            "value_text": "100% of fees paid or payable in the preceding 12 months",
            "clause_ref": "Article 10 (Limitation of Liability)",
        })
    terms.append({
        "category": "compliance",
        "term_key": "confidentiality_survival",
        "label": "Confidentiality Survival Period",
        "value_text": "5 years following expiration or termination",
        "numeric_value": 5,
        "unit": "years",
        "clause_ref": "Article 8 (Confidentiality & Data Protection)",
    })
    return terms


def _default_deliverables_for(ctype: str, title: str) -> list[dict[str, Any]]:
    if ctype == "employment_probation":
        return [
            {"title": "30-Day Onboarding & Role Alignment Review", "deliverable_type": "probation_review", "project_phase": "Month 1", "offset_days": 30, "weight_pct": 25},
            {"title": "60-Day Mid-Probation Performance Check", "deliverable_type": "probation_review", "project_phase": "Month 2", "offset_days": 60, "weight_pct": 35},
            {"title": "Final Probation Confirmation & Permanent Sign-Off", "deliverable_type": "acceptance_gate", "project_phase": "Confirmation", "offset_days": 90, "weight_pct": 40},
        ]
    if ctype == "nda":
        return [
            {"title": "Executed Confidentiality Undertaking & Authorized Recipients List", "deliverable_type": "compliance_cert", "project_phase": "Initiation", "offset_days": 7, "weight_pct": 50},
            {"title": "Certificate of Return or Destruction of Confidential Materials", "deliverable_type": "compliance_cert", "project_phase": "Closeout", "offset_days": 180, "weight_pct": 50},
        ]
    return [
        {"title": "Phase 1 — Initiation, Governance Charter & Kickoff Sign-Off", "deliverable_type": "milestone", "project_phase": "Phase 1", "offset_days": 15, "weight_pct": 25},
        {"title": "Phase 2 — Core Delivery, Implementation & Interim Review", "deliverable_type": "milestone", "project_phase": "Phase 2", "offset_days": 45, "weight_pct": 45},
        {"title": "Phase 3 — Final Acceptance, Handover & Completion Certificate", "deliverable_type": "acceptance_gate", "project_phase": "Phase 3", "offset_days": 90, "weight_pct": 30},
    ]


def render_catalog_template_html(entry: dict[str, Any]) -> str:
    """Generate a full-length, 14-article production-ready legal contract HTML document."""
    t_esc = _html.escape(entry["name"].upper())
    cat = _html.escape(entry["category"])
    focus = _html.escape(entry["domain_focus"])
    posture = _html.escape(entry["commercial_posture"])
    ed_note = _html.escape(entry["edition_note"])
    ctype = entry["contract_type"]

    probation_clause = ""
    if ctype == "employment_probation":
        probation_clause = (
            "<h2>5. Probationary Period, Performance Reviews &amp; Confirmation</h2>"
            "<p>5.1 <strong>Probation Term.</strong> The engagement under this Agreement is subject to a formal probationary period "
            "ending on <strong>{{probation_end_date}}</strong>, during which the Organization shall evaluate performance, conduct, "
            "role alignment, and compliance with internal policies.</p>"
            "<p>5.2 <strong>Structured Reviews.</strong> Formal written reviews shall be conducted at 30 days, 60 days, and prior to "
            "the probation end date. The Organization may confirm permanent appointment in writing, extend probation once by up to "
            "thirty (30) days with documented improvement objectives, or terminate during probation upon seven (7) days' written notice.</p>"
        )
    else:
        probation_clause = (
            "<h2>5. Term, Renewal &amp; Governance Reviews</h2>"
            "<p>5.1 <strong>Commencement &amp; Duration.</strong> This Agreement takes effect on <strong>{{effective_date}}</strong> "
            "and shall remain in full force until completion of all Deliverables or <strong>{{expiration_date}}</strong>, unless "
            "extended by mutual written renewal or terminated earlier in accordance with Article 12.</p>"
            "<p>5.2 <strong>Governance Cadence.</strong> Each Party shall designate a primary Project Sponsor and Account Lead who "
            "shall conduct regular governance reviews to track milestone progress, risk registers, and commercial compliance.</p>"
        )

    # Build dynamic Schedules A & B from each template's structured deliverables & key terms
    deliv_items = entry.get("default_deliverables") or []
    sched_a_lis = "\n".join(
        f"  <li><strong>{_html.escape(str(d.get('title') or 'Deliverable'))}</strong> — Phase: {_html.escape(str(d.get('project_phase') or 'Execution'))} · Weight: {int(d.get('weight_pct') or 0)}% · Target Due: Day +{int(d.get('offset_days') or 30)} from Effective Date · Acceptance Criterion: Written sign-off in TrustSeal Deliverables Register.</li>"
        for d in deliv_items
    ) or "  <li><strong>Phase 1 — Initiation &amp; Kickoff Charter</strong> (25%) · <strong>Phase 2 — Core Delivery &amp; QA</strong> (45%) · <strong>Phase 3 — Final Acceptance &amp; Handover</strong> (30%).</li>"

    kt_items = entry.get("default_key_terms") or []
    sched_b_lis = "\n".join(
        f"  <li><strong>{_html.escape(str(k.get('label') or 'Key Term'))}</strong> ({_html.escape(str(k.get('category') or 'commercial').upper())}): {_html.escape(str(k.get('value_text') or 'As agreed in writing'))}</li>"
        for k in kt_items
    ) or "  <li><strong>Settlement Terms:</strong> Net 30 calendar days from verified invoice · <strong>Service Availability:</strong> 99.5% operational SLA · <strong>Notice Period:</strong> 30 days prior written notice.</li>"

    return f"""<h1>{t_esc}</h1>
<p><strong>THIS AGREEMENT</strong> (this &ldquo;Agreement&rdquo;) is made and entered into as of <strong>{{{{effective_date}}}}</strong> (the &ldquo;Effective Date&rdquo;) under Project <strong>{{{{project_name}}}}</strong> (Ref: <strong>{{{{project_code}}}}</strong>),</p>
<p><strong>BY AND BETWEEN:</strong></p>
<p>(1) <strong>The Organization</strong>, a duly incorporated entity acting through its authorized representatives (hereinafter referred to as the &ldquo;First Party&rdquo; or &ldquo;Organization&rdquo;); and</p>
<p>(2) <strong>{{{{counterparty_name}}}}</strong>, a duly authorized legal person or individual (hereinafter referred to as the &ldquo;Counterparty&rdquo; or &ldquo;Second Party&rdquo;).</p>
<p>The Organization and the Counterparty are each individually referred to as a &ldquo;Party&rdquo; and collectively as the &ldquo;Parties&rdquo;.</p>

<h2>RECITALS</h2>
<p><strong>WHEREAS</strong>, the Organization is executing Project <strong>{{{{project_name}}}}</strong> ({{{{project_code}}}}) within the {cat} practice domain and requires formal contractual governance covering {focus};</p>
<p><strong>WHEREAS</strong>, the Counterparty represents that it possesses the requisite qualifications, legal capacity, licenses, personnel, and operational resources to perform its obligations hereunder; and</p>
<p><strong>WHEREAS</strong>, the Parties wish to record their mutual rights, obligations, commercial terms, and governance controls in this binding written Agreement reflecting {posture}.</p>
<p><strong>NOW, THEREFORE</strong>, in consideration of the mutual covenants, promises, and consideration set forth herein, the receipt and sufficiency of which are hereby acknowledged, the Parties agree as follows:</p>

<h2>1. Definitions &amp; Interpretation</h2>
<p>1.1 <strong>&ldquo;Applicable Law&rdquo;</strong> means all statutes, regulations, statutory instruments, regulatory directives, tax legislation, data protection laws, and binding judicial orders in force in <strong>{{{{governing_law}}}}</strong>.</p>
<p>1.2 <strong>&ldquo;Confidential Information&rdquo;</strong> means all non-public commercial, technical, financial, legal, operational, customer, or personal information disclosed by or on behalf of either Party in any form, whether marked confidential or reasonably understood to be confidential.</p>
<p>1.3 <strong>&ldquo;Deliverables&rdquo;</strong> means all milestones, reports, work product, systems, goods, filings, or services specified in the Project Deliverables Schedule attached to or tracked under this Agreement.</p>
<p>1.4 <strong>&ldquo;Intellectual Property Rights&rdquo;</strong> means all patents, copyrights, moral rights, trademarks, trade secrets, database rights, designs, source code, methodologies, and know-how worldwide, whether registered or unregistered.</p>
<p>1.5 <strong>Interpretation.</strong> Headings are for convenience only. Words importing the singular include the plural and vice versa. References to written notice include cryptographically verifiable electronic communications recorded in TrustSeal.</p>

<h2>2. Scope of Engagement &amp; Primary Obligations</h2>
<p>2.1 <strong>Core Mandate.</strong> The Parties hereby establish the binding legal and operational terms governing {focus} under Project <strong>{{{{project_name}}}}</strong> ({{{{project_code}}}}).</p>
<p>2.2 <strong>Standard of Care.</strong> Each Party shall perform its obligations with the degree of skill, diligence, prudence, and foresight reasonably expected from a seasoned institutional practitioner in the {cat} sector, in strict compliance with Applicable Law.</p>
<p>2.3 <strong>Edition Governance Profile.</strong> {ed_note}</p>
<p>2.4 <strong>Change Control.</strong> Any material change to scope, schedule, deliverables, or fees shall be documented in a formal written Amendment or Change Order executed by authorized representatives of both Parties.</p>

<h2>3. Deliverables, Milestones &amp; Acceptance Protocol</h2>
<p>3.1 <strong>Delivery Schedule.</strong> All Deliverables shall be submitted in accordance with the agreed project phases, due dates, and weighted milestones tracked in the TrustSeal Contract Deliverables Register.</p>
<p>3.2 <strong>Inspection &amp; Acceptance.</strong> Upon formal submission of each Deliverable, the receiving Party shall have ten (10) business days to inspect and either (a) issue written Acceptance, or (b) deliver a detailed written Rejection Notice identifying material non-conformities.</p>
<p>3.3 <strong>Remediation.</strong> Where a Rejection Notice is issued, the delivering Party shall remedy the identified defects at no additional cost within ten (10) business days and re-submit for verification.</p>

<h2>4. Commercial Consideration, Invoicing &amp; Taxation</h2>
<p>4.1 <strong>Contract Value.</strong> In full consideration for the faithful performance of this Agreement, the agreed commercial value is <strong>{{{{currency}}}} {{{{deal_value}}}}</strong>, payable in accordance with accepted milestone tranches or agreed billing cycles.</p>
<p>4.2 <strong>Invoicing &amp; Settlement.</strong> Valid, undisputed invoices citing Contract Reference and Project Code <strong>{{{{project_code}}}}</strong> shall be settled via electronic funds transfer within the agreed settlement window. Disputed line items shall be notified in writing within seven (7) business days without delaying payment of undisputed portions.</p>
<p>4.3 <strong>Taxes &amp; Withholding.</strong> All sums stated are exclusive of Value Added Tax (VAT) or applicable sales taxes unless expressly stated otherwise. Each Party shall comply with statutory withholding tax rules and issue official tax credit certificates promptly.</p>

{probation_clause}

<h2>6. Representations, Warranties &amp; Compliance</h2>
<p>6.1 <strong>Mutual Authority.</strong> Each Party represents and warrants that it is validly existing, has full corporate or personal power to execute this Agreement, and that this Agreement constitutes a legal, valid, and binding obligation enforceable in accordance with its terms.</p>
<p>6.2 <strong>Anti-Bribery, AML &amp; Ethics.</strong> Neither Party nor its officers, employees, or agents shall offer, give, solicit, or accept any improper inducement, facilitation payment, or kickback in connection with this Agreement, and both Parties shall comply with all anti-corruption, sanctions, and AML laws.</p>
<p>6.3 <strong>Defect Warranty.</strong> For a period of ninety (90) days following final acceptance of any Deliverable, the delivering Party warrants that such Deliverable shall conform materially to the agreed specifications and be free from material defects.</p>

<h2>7. Intellectual Property Rights &amp; Licensing</h2>
<p>7.1 <strong>Background IP.</strong> Each Party retains sole and exclusive ownership of all pre-existing Intellectual Property Rights, tools, templates, and general know-how owned or developed prior to or independently of this Agreement (&ldquo;Background IP&rdquo;).</p>
<p>7.2 <strong>Foreground IP.</strong> Upon receipt of full payment of applicable fees, all right, title, and interest in bespoke Deliverables created exclusively for the Organization under this Agreement shall vest in the Organization, together with a perpetual, non-exclusive license to use any embedded Background IP strictly as necessary to enjoy the Deliverables.</p>

<h2>8. Confidentiality &amp; Data Protection</h2>
<p>8.1 <strong>Strict Non-Disclosure.</strong> Each receiving Party shall hold the disclosing Party&rsquo;s Confidential Information in strict confidence, apply at least the same degree of care it uses for its own sensitive information (and never less than reasonable care), and restrict access strictly to personnel and professional advisers on a need-to-know basis.</p>
<p>8.2 <strong>Exclusions.</strong> Confidentiality obligations do not apply to information that is publicly available without breach, was lawfully known prior to disclosure, is independently developed without reference to Confidential Information, or must be disclosed by law or court order (with prompt prior notice where lawful).</p>
<p>8.3 <strong>Personal Data Protection.</strong> Where either Party processes personal data in connection with this Agreement, it shall implement appropriate technical and organizational security measures, process data solely on documented instructions, and notify the other Party without undue delay (and within 72 hours) upon becoming aware of any personal data breach.</p>
<p>8.4 <strong>Survival.</strong> This Article 8 shall survive expiration or termination of this Agreement for five (5) years.</p>

<h2>9. Service Levels, Records &amp; Audit Rights</h2>
<p>9.1 <strong>Performance Monitoring.</strong> Performance against agreed Service Level Agreements, KPIs, and statutory obligations shall be tracked transparently within the Project governance register.</p>
<p>9.2 <strong>Books, Records &amp; Audit.</strong> Each Party shall maintain accurate operational, financial, and compliance records relating to this Agreement for seven (7) years and permit reasonable audit inspection upon ten (10) business days&rsquo; prior written notice.</p>

<h2>10. Indemnification &amp; Limitation of Liability</h2>
<p>10.1 <strong>Mutual Indemnity.</strong> Each Party shall indemnify, defend, and hold harmless the other Party from third-party claims, damages, and reasonable legal costs arising directly from (a) third-party intellectual property infringement caused by its Deliverables, (b) breach of confidentiality or data protection laws, or (c) gross negligence, fraud, or willful misconduct.</p>
<p>10.2 <strong>Exclusion of Consequential Loss.</strong> Neither Party shall be liable to the other for any indirect, incidental, special, punitive, or consequential loss, including loss of profit, revenue, or goodwill.</p>
<p>10.3 <strong>Liability Cap.</strong> Save for fraud, willful misconduct, death or personal injury caused by negligence, or indemnity obligations under Clause 10.1, each Party&rsquo;s aggregate cumulative liability under this Agreement shall not exceed one hundred percent (100%) of the total fees paid or payable hereunder in the twelve (12) months immediately preceding the event giving rise to liability.</p>

<h2>11. Formal Suspension &amp; Force Majeure</h2>
<p>11.1 <strong>Contract Suspension.</strong> The Parties may formally place this Agreement in <strong>SUSPENDED</strong> status upon written notice for documented operational, regulatory, or force majeure reasons. During any approved suspension, active deliverable due dates and SLA timers shall pause automatically and adjust correspondingly upon written resumption.</p>
<p>11.2 <strong>Force Majeure.</strong> Neither Party shall be in breach for delay or failure caused by events beyond its reasonable control (including acts of God, war, civil unrest, pandemic, governmental embargo, or widespread utility failure), provided prompt written notice is given and reasonable mitigation efforts are maintained. If a Force Majeure event persists beyond sixty (60) days, either Party may terminate without penalty.</p>

<h2>12. Termination &amp; Transition Assistance</h2>
<p>12.1 <strong>Termination for Cause.</strong> Either Party may terminate this Agreement immediately upon written notice if the other Party commits a material breach that remains uncured thirty (30) days after written notice specifying the breach, or enters insolvency, liquidation, or receivership.</p>
<p>12.2 <strong>Termination for Convenience.</strong> Either Party may terminate for convenience upon thirty (30) days&rsquo; prior written notice, subject to settlement of all accepted Deliverables and committed non-cancellable work performed up to the effective termination date.</p>
<p>12.3 <strong>Orderly Handover.</strong> Upon expiration or termination, the Parties shall cooperate in good faith for up to thirty (30) days to execute orderly transition, return of Confidential Information, and preservation of executed records in the TrustSeal Evidence Vault.</p>

<h2>13. Governing Law &amp; Dispute Resolution</h2>
<p>13.1 <strong>Governing Law.</strong> This Agreement and any non-contractual obligations arising out of it shall be governed by and construed in accordance with the laws of <strong>{{{{governing_law}}}}</strong>.</p>
<p>13.2 <strong>Escalation &amp; Arbitration.</strong> Any dispute arising out of or in connection with this Agreement shall first be referred to senior executives of both Parties for good-faith negotiation for fifteen (15) business days. If unresolved, the dispute shall be finally settled by binding arbitration before a single mutually appointed arbitrator in accordance with applicable institutional arbitration rules, whose award shall be final and binding.</p>

<h2>14. General Provisions, Assignment &amp; Notices</h2>
<p>14.1 <strong>Entire Agreement.</strong> This Agreement, together with its attached Schedules A, B, and C, Key Terms, and Deliverables Register, constitutes the entire agreement between the Parties and supersedes all prior negotiations, representations, or proposals.</p>
<p>14.2 <strong>Assignment &amp; Subcontracting.</strong> Neither Party may assign, novate, or subcontract any material right or obligation under this Agreement without the prior written consent of the other Party (not to be unreasonably withheld). Any approved subcontractor remains the sole responsibility of the appointing Party.</p>
<p>14.3 <strong>Severability &amp; Waiver.</strong> If any provision is held invalid or unenforceable by a competent court or tribunal, the remaining provisions shall remain in full force and effect. No failure or delay in exercising any right operates as a waiver thereof.</p>
<p>14.4 <strong>Formal Notices.</strong> All legal notices under this Agreement shall be in writing and delivered by hand, registered courier, or cryptographically verified electronic mail to the designated addresses in Schedule C.</p>

<h2>15. Data Protection, Cybersecurity &amp; Anti-Corruption</h2>
<p>15.1 <strong>Statutory Data Protection Compliance.</strong> Both Parties shall comply strictly with applicable Personal Data Protection and Privacy legislation (including the Uganda Data Protection and Privacy Act Cap. 97, Kenya DPA, GDPR, or equivalent statutory regime in <strong>{{{{governing_law}}}}</strong>), implementing technical and organizational safeguards commensurate with ISO/IEC 27001.</p>
<p>15.2 <strong>Cybersecurity &amp; Incident Notification.</strong> Each Party shall maintain endpoint security, access controls, and encrypted storage for all shared project files and notify the other Party within twenty-four (24) hours of confirming any security incident impacting shared Confidential Information.</p>
<p>15.3 <strong>Anti-Bribery, Sanctions &amp; Modern Slavery.</strong> Each Party warrants ongoing compliance with applicable anti-corruption statutes, AML/CFT controls, international sanctions lists, and ethical labor standards. Any verified breach of this Article 15 constitutes a non-curable material breach entitling immediate termination for cause.</p>

<h2>16. Insurance, Non-Solicitation &amp; Cryptographic Execution</h2>
<p>16.1 <strong>Insurance Coverage.</strong> Throughout the Term and for twelve (12) months thereafter, the performing Party shall maintain adequate Professional Indemnity, Public Liability, and (where applicable) Cyber Liability insurance with a reputable insurer and provide certificates of currency upon request.</p>
<p>16.2 <strong>Non-Solicitation.</strong> During the Term and for twelve (12) months following expiration or termination, neither Party shall knowingly solicit for employment or direct engagement any key personnel of the other Party directly involved in performing this Agreement without prior written consent.</p>
<p>16.3 <strong>Counterparts &amp; TrustSeal Cryptographic Execution.</strong> This Agreement may be executed in any number of counterparts and via electronic signatures and TrustSeal cryptographic corporate seals, each of which shall carry identical legal force, evidentiary admissibility, and non-repudiation as wet-ink originals.</p>

<h2>SCHEDULE A — STATEMENT OF WORK &amp; MILESTONE DELIVERABLES</h2>
<p><strong>Project Reference:</strong> {{{{project_name}}}} ({{{{project_code}}}}) &nbsp;·&nbsp; <strong>Practice Domain:</strong> {cat}</p>
<p>The following weighted deliverables and acceptance gates govern performance under Article 3 of this Agreement:</p>
<ol>
{sched_a_lis}
</ol>
<p><strong>Additional Technical / Scope Specifications:</strong> {{{{scope_specifications}}}}</p>

<h2>SCHEDULE B — KEY COMMERCIAL TERMS, FEES &amp; GOVERNANCE CONTROLS</h2>
<p><strong>Total Contract Value:</strong> {{{{currency}}}} {{{{deal_value}}}} &nbsp;·&nbsp; <strong>Effective Date:</strong> {{{{effective_date}}}} &nbsp;·&nbsp; <strong>Governing Law:</strong> {{{{governing_law}}}}</p>
<ul>
{sched_b_lis}
</ul>
<p><strong>Payment Account / Invoicing Instructions:</strong> Invoices citing Contract Reference {{{{document_ref}}}} and Project Code {{{{project_code}}}} shall be submitted electronically to Finance Accounts Payable.</p>

<h2>SCHEDULE C — AUTHORIZED NOTICE ADDRESSES &amp; EXECUTION</h2>
<ul>
  <li><strong>First Party (Organization):</strong> {{{{organization_name}}}} · Attention: {{{{owner_name}}}} · Registered Office: {{{{registered_office}}}}</li>
  <li><strong>Second Party (Counterparty):</strong> {{{{counterparty_name}}}} · Attention: {{{{counterparty_contact}}}} · Registered Office: {{{{counterparty_address}}}}</li>
</ul>

<h3>IN WITNESS WHEREOF</h3>
<p>The Parties hereto have caused this Agreement (comprising Articles 1 to 16 and Schedules A, B, and C) to be duly executed by their respective authorized signatories as of the Effective Date written above.</p>
<p><strong>FOR AND ON BEHALF OF {{{{organization_name}}}}:</strong><br/>Authorized Signatory: ______________________________ &nbsp;&nbsp; Title: ______________________ &nbsp;&nbsp; Date: ______________</p>
<p><strong>FOR AND ON BEHALF OF {{{{counterparty_name}}}}:</strong><br/>Authorized Signatory: ______________________________ &nbsp;&nbsp; Title: ______________________ &nbsp;&nbsp; Date: ______________</p>
<p><strong>WITNESSED BY:</strong><br/>Name: ______________________________ &nbsp;&nbsp; Signature: ______________________ &nbsp;&nbsp; Date: ______________</p>
"""


@lru_cache(maxsize=1)
def get_contract_template_catalog() -> list[dict[str, Any]]:
    """Build and cache the 1,050+ full-length Contract Templates catalog in memory."""
    items: list[dict[str, Any]] = []
    idx = 0
    for cat_name, ctype, proj_cat, archetypes in PRACTICE_ARCHETYPES:
        for slug_base, title_base, summary, domain_focus in archetypes:
            for ed_slug, ed_label, jur_default, posture, ed_note in EDITIONS:
                idx += 1
                slug = f"{slug_base}__{ed_slug}"
                full_name = title_base if ed_slug == "standard" else f"{title_base} — {ed_label}"
                kts = _default_key_terms_for(ctype, ed_slug, full_name)
                dls = _default_deliverables_for(ctype, full_name)
                items.append({
                    "catalog_slug": slug,
                    "catalog_index": idx,
                    "name": full_name,
                    "category": cat_name,
                    "edition": ed_label,
                    "jurisdiction": jur_default,
                    "contract_type": ctype,
                    "default_project_category": proj_cat,
                    "description": f"{summary} ({ed_label} · {jur_default}).",
                    "domain_focus": domain_focus,
                    "commercial_posture": posture,
                    "edition_note": ed_note,
                    "article_count": 14,
                    "default_key_terms": kts,
                    "default_deliverables": dls,
                    "default_key_terms_count": len(kts),
                    "default_deliverables_count": len(dls),
                    "state": "published",
                    "is_catalog": True,
                })
    return items


@lru_cache(maxsize=1)
def get_catalog_index_by_slug() -> dict[str, dict[str, Any]]:
    return {item["catalog_slug"]: item for item in get_contract_template_catalog()}


def get_catalog_categories_summary() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in get_contract_template_catalog():
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return [{"category": k, "count": v} for k, v in counts.items()]


def search_catalog_templates(
    *,
    q: str = "",
    category: str = "",
    contract_type: str = "",
    page: int = 1,
    per_page: int = 24,
) -> dict[str, Any]:
    """Fast in-memory search & pagination over all 1,050+ full-length templates."""
    all_items = get_contract_template_catalog()
    ql = (q or "").strip().lower()
    cat_f = (category or "").strip()
    type_f = (contract_type or "").strip().lower()

    tokens = [t for t in ql.split() if t]
    filtered = []
    for item in all_items:
        if cat_f and cat_f.upper() != "ALL" and item["category"] != cat_f:
            continue
        if type_f and type_f != "all" and item["contract_type"] != type_f:
            continue
        if tokens:
            hay = f"{item['name']} {item['category']} {item['edition']} {item['jurisdiction']} {item['description']}".lower()
            if not all(tok in hay for tok in tokens):
                continue
        filtered.append(item)

    total = len(filtered)
    per_page = max(6, min(100, int(per_page or 24)))
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(total_pages, int(page or 1)))
    start = (page - 1) * per_page
    slice_items = filtered[start : start + per_page]

    return {
        "total": total,
        "catalog_total": len(all_items),
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": get_catalog_categories_summary(),
        "items": [
            {
                "catalog_slug": it["catalog_slug"],
                "name": it["name"],
                "category": it["category"],
                "edition": it["edition"],
                "jurisdiction": it["jurisdiction"],
                "contract_type": it["contract_type"],
                "description": it["description"],
                "article_count": it["article_count"],
                "default_key_terms_count": it["default_key_terms_count"],
                "default_deliverables_count": it["default_deliverables_count"],
                "is_catalog": True,
                "preview_html": render_catalog_template_html(it),
            }
            for it in slice_items
        ],
    }
