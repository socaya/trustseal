"""1,000-Style Institutional Stamp & Seal Templates Catalog.

Provides 100 distinct institutional stamp archetypes across 12 professional categories
rendered across 10 distinct physical stamp geometries, border treatments, ink palettes,
and layouts (= 1,000 unique stamp templates) with fast lazy SVG generation, full-text
search, and multi-facet filtering (category, kind/shape, style, color).
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from typing import Any


def _esc(val: str) -> str:
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _uid(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts).encode("utf-8", "ignore")
    return hashlib.md5(raw).hexdigest()[:8]


def _fit(text: str, max_px: float, base_px: float, spacing: float = 1.4, ratio: float = 0.64) -> int:
    n = max(1, len(text))
    if n * (base_px * ratio + spacing) <= max_px:
        return max(7, round(base_px))
    return max(7, min(round(base_px), round((max_px / n - spacing) / ratio)))


# 10 Distinct Visual Styles × 100 Stamp Archetypes = 1,000 Unique Stamp Templates
# (style_slug, style_label, kind, shape, width_mm, height_mm, default_color, style_desc)
STAMP_STYLES: list[tuple[str, str, str, str, int, int, str, str]] = [
    ("classic-double-seal", "Classic Double-Ring Seal", "seal", "circle", 42, 42, "#002769", "42×42 mm double-ring circular institutional seal"),
    ("notary-starburst-seal", "Starburst Wax / Notary Seal", "seal", "starburst", 45, 45, "#9b1c1c", "45×45 mm serrated starburst notary & corporate seal"),
    ("dated-corporate-ring", "Circular Dated Registry Seal", "company_dated", "circle_dated", 45, 45, "#1d4ed8", "45×45 mm circular seal with dynamic date line"),
    ("oval-executive-seal", "Oval Executive Seal", "seal", "oval", 55, 36, "#047857", "55×36 mm elliptical corporate executive seal"),
    ("rect-office-dated", "Rectangular Office & Signatory", "company_rect", "rect_dated", 70, 35, "#0f294a", "70×35 mm office stamp with date, ref & signatory line"),
    ("rubber-bold-frame", "Bold Framed Rubber Stamp", "rubber", "rect_bold", 60, 24, "#b91c1c", "60×24 mm bold double-bordered status rubber stamp"),
    ("rounded-badge-modern", "Modern Rounded Badge", "rubber", "rounded", 58, 26, "#0f766e", "58×26 mm sleek rounded-corner operational badge"),
    ("shield-crest-seal", "Heraldic Shield Crest", "rubber", "shield", 45, 45, "#312e81", "45×45 mm heraldic shield compliance & verification stamp"),
    ("square-registry-box", "Square Registry Box Stamp", "rubber", "square", 42, 42, "#1e293b", "42×42 mm structured square archive & registry box"),
    ("vintage-diagonal-stamp", "Vintage Diagonal / Accent", "rubber", "diagonal", 65, 28, "#7f1d1d", "65×28 mm angled executive rubber impression stamp"),
]

# 100 Distinct Institutional Stamp Archetypes across 12 Professional Categories
# (slug_base, name, category, top_arc, bottom_arc, center_1, center_2, verb)
STAMP_ARCHETYPES: list[tuple[str, str, str, str, str, str, str, str]] = [
    # 1. Corporate & Company Seals (10)
    ("corp_common_seal", "Official Company Common Seal", "Corporate & Company Seals", "YOUR ORGANIZATION LIMITED", "COMMON SEAL · INCORPORATED", "OFFICIAL", "SEAL", "SEALED"),
    ("corp_board_secretariat", "Board Secretariat Seal", "Corporate & Company Seals", "OFFICE OF THE COMPANY SECRETARY", "BOARD GOVERNANCE REGISTRY", "BOARD", "APPROVED", "CERTIFIED"),
    ("corp_managing_director", "Office of the Managing Director", "Corporate & Company Seals", "OFFICE OF THE MANAGING DIRECTOR", "EXECUTIVE AUTHORITY", "M.D.", "APPROVED", "AUTHORIZED"),
    ("corp_ceo_authorization", "CEO Executive Sign-Off", "Corporate & Company Seals", "CHIEF EXECUTIVE OFFICER", "CORPORATE HEADQUARTERS", "EXECUTIVE", "SIGNED", "APPROVED"),
    ("corp_registered_office", "Registered Head Office", "Corporate & Company Seals", "REGISTERED HEAD OFFICE", "OFFICIAL CORRESPONDENCE", "HEAD", "OFFICE", "RECEIVED"),
    ("corp_branch_office", "Regional Branch Office", "Corporate & Company Seals", "REGIONAL BRANCH OFFICE", "AUTHORIZED BRANCH SEAL", "BRANCH", "OFFICIAL", "ISSUED"),
    ("corp_share_registry", "Share Registry & Transfer Seal", "Corporate & Company Seals", "CORPORATE SHARE REGISTRY", "CAPITAL & EQUITY CONTROL", "SHARES", "REGISTERED", "ALLOTTED"),
    ("corp_procurement_unit", "Procurement & Disposal Unit", "Corporate & Company Seals", "PROCUREMENT & DISPOSAL UNIT", "VENDOR & TENDER CONTROL", "PDU", "VERIFIED", "CLEARED"),
    ("corp_internal_audit", "Internal Audit & Assurance", "Corporate & Company Seals", "INTERNAL AUDIT DEPARTMENT", "INDEPENDENT ASSURANCE", "AUDITED", "CHECKED", "AUDITED"),
    ("corp_records_archive", "Central Records & Archives", "Corporate & Company Seals", "CENTRAL RECORDS & ARCHIVES", "CONTROLLED DOCUMENT VAULT", "ARCHIVED", "CONTROLLED", "FILED"),

    # 2. Approval & Workflow Stamps (10)
    ("wf_approved", "Approved", "Approval & Workflow Stamps", "DOCUMENT WORKFLOW CONTROL", "AUTHORIZED APPROVAL", "APPROVED", "VERIFIED", "APPROVED"),
    ("wf_approved_payment", "Approved for Payment", "Approval & Workflow Stamps", "TREASURY & FINANCE CONTROL", "PAYMENT AUTHORIZATION", "APPROVED", "FOR PAYMENT", "AUTHORIZED"),
    ("wf_reviewed_cleared", "Reviewed & Cleared", "Approval & Workflow Stamps", "MANAGEMENT REVIEW DESK", "QUALITY VERIFIED", "REVIEWED", "& CLEARED", "REVIEWED"),
    ("wf_received_dated", "Received & Logged", "Approval & Workflow Stamps", "CENTRAL INTAKE REGISTRY", "INCOMING CORRESPONDENCE", "RECEIVED", "LOGGED", "RECEIVED"),
    ("wf_verified_authentic", "Verified Authentic", "Approval & Workflow Stamps", "AUTHENTICITY VERIFICATION", "TRUSTSEAL INTEGRITY", "VERIFIED", "AUTHENTIC", "VERIFIED"),
    ("wf_urgent_priority", "Urgent / Priority Action", "Approval & Workflow Stamps", "PRIORITY DISPATCH DESK", "IMMEDIATE ATTENTION", "URGENT", "PRIORITY", "EXPEDITE"),
    ("wf_draft_review", "Draft — For Review Only", "Approval & Workflow Stamps", "DOCUMENT CONTROL SYSTEM", "NOT FOR FINAL EXECUTION", "DRAFT", "FOR REVIEW", "DRAFT"),
    ("wf_superseded", "Superseded / Obsolete", "Approval & Workflow Stamps", "DOCUMENT ARCHIVE CONTROL", "REPLACED BY NEW VERSION", "SUPERSEDED", "OBSOLETE", "VOIDED"),
    ("wf_cancelled_void", "Cancelled / Void", "Approval & Workflow Stamps", "TRANSACTION CONTROL", "NULL AND VOID", "CANCELLED", "VOID", "VOID"),
    ("wf_final_executed", "Final Executed Copy", "Approval & Workflow Stamps", "EXECUTION REGISTRY", "BINDING ORIGINAL RECORD", "FINAL", "EXECUTED", "EXECUTED"),

    # 3. Finance, Accounting & Audit (10)
    ("fin_paid_full", "Paid in Full", "Finance, Accounting & Audit", "ACCOUNTS RECEIVABLE", "SETTLEMENT CONFIRMED", "PAID", "IN FULL", "PAID"),
    ("fin_posted_ledger", "Posted to General Ledger", "Finance, Accounting & Audit", "FINANCE & ACCOUNTING", "GENERAL LEDGER ENTRY", "POSTED", "TO LEDGER", "POSTED"),
    ("fin_audited_ifrs", "Audited — IFRS Compliant", "Finance, Accounting & Audit", "EXTERNAL AUDIT ASSURANCE", "IFRS FINANCIAL REVIEW", "AUDITED", "IFRS", "AUDITED"),
    ("fin_tax_cleared", "Tax & VAT Verified", "Finance, Accounting & Audit", "TAX COMPLIANCE UNIT", "VAT & WHT VERIFIED", "TAX", "VERIFIED", "CLEARED"),
    ("fin_credit_approved", "Credit Limit Approved", "Finance, Accounting & Audit", "CREDIT CONTROL COMMITTEE", "TRADE CREDIT APPROVED", "CREDIT", "APPROVED", "APPROVED"),
    ("fin_reconciled", "Bank Reconciled", "Finance, Accounting & Audit", "TREASURY RECONCILIATION", "STATEMENT MATCHED", "BANK", "RECONCILED", "MATCHED"),
    ("fin_original_invoice", "Original Tax Invoice", "Finance, Accounting & Audit", "COMMERCIAL BILLING DESK", "FISCAL TAX DOCUMENT", "ORIGINAL", "INVOICE", "ISSUED"),
    ("fin_duplicate_copy", "Duplicate Accounting Copy", "Finance, Accounting & Audit", "FINANCE ARCHIVE COPY", "NOT FOR RE-PAYMENT", "DUPLICATE", "FILE COPY", "COPIED"),
    ("fin_petty_cash", "Petty Cash Disbursed", "Finance, Accounting & Audit", "PETTY CASH IMPREST", "VOUCHER SETTLED", "PETTY CASH", "DISBURSED", "PAID"),
    ("fin_budget_checked", "Budget Availability Checked", "Finance, Accounting & Audit", "BUDGET & PLANNING UNIT", "FUNDS COMMITTED", "BUDGET", "CHECKED", "COMMITTED"),

    # 4. Legal, Notary & Commissioner for Oaths (9)
    ("leg_commissioner_oaths", "Commissioner for Oaths", "Legal, Notary & Commissioner for Oaths", "COMMISSIONER FOR OATHS", "SWORN & ATTESTED BEFORE ME", "COMMISSIONER", "FOR OATHS", "SWORN"),
    ("leg_notary_public", "Notary Public Seal", "Legal, Notary & Commissioner for Oaths", "NOTARY PUBLIC", "NOTARIAL AUTHENTICATION", "NOTARY", "PUBLIC", "NOTARIZED"),
    ("leg_certified_true_copy", "Certified True Copy of Original", "Legal, Notary & Commissioner for Oaths", "CERTIFIED TRUE COPY", "ORIGINAL SIGHTED & VERIFIED", "CERTIFIED", "TRUE COPY", "CERTIFIED"),
    ("leg_advocate_chambers", "Advocates & Legal Counsel", "Legal, Notary & Commissioner for Oaths", "ADVOCATES & SOLICITORS", "LEGAL CHAMBERS SEAL", "LEGAL", "COUNSEL", "ATTESTED"),
    ("leg_privileged_conf", "Legally Privileged & Confidential", "Legal, Notary & Commissioner for Oaths", "ATTORNEY-CLIENT PRIVILEGE", "DO NOT DISCLOSE", "PRIVILEGED", "CONFIDENTIAL", "RESTRICTED"),
    ("leg_executed_deed", "Signed, Sealed & Delivered", "Legal, Notary & Commissioner for Oaths", "DEED EXECUTION REGISTRY", "SIGNED SEALED DELIVERED", "SEALED", "AS A DEED", "DELIVERED"),
    ("leg_affidavit_jurat", "Affidavit / Statutory Declaration", "Legal, Notary & Commissioner for Oaths", "STATUTORY DECLARATION", "COMMISSIONED & DATED", "DECLARED", "& SWORN", "SWORN"),
    ("leg_witnessed_by", "Witnessed & Attested", "Legal, Notary & Commissioner for Oaths", "EXECUTION ATTESTATION", "IN THE PRESENCE OF", "WITNESSED", "ATTESTED", "WITNESSED"),
    ("leg_without_prejudice", "Without Prejudice", "Legal, Notary & Commissioner for Oaths", "LEGAL SETTLEMENT NOTICE", "PROTECTED COMMUNICATION", "WITHOUT", "PREJUDICE", "PROTECTED"),

    # 5. URSB, Registry & Government Filings (8)
    ("reg_ursb_obrs_filed", "URSB OBRS Filing Copy", "URSB, Registry & Government Filings", "URSB OBRS SUBMISSION", "COMPANIES ACT CAP. 106", "OBRS", "FILED COPY", "LODGED"),
    ("reg_statutory_return", "Annual Statutory Return", "URSB, Registry & Government Filings", "STATUTORY COMPLIANCE", "REGISTRAR OF COMPANIES", "ANNUAL", "RETURN", "FILED"),
    ("reg_beneficial_owner", "Beneficial Ownership Verified", "URSB, Registry & Government Filings", "BENEFICIAL OWNERSHIP", "S.I. 2023 NO. 5 COMPLIANT", "BO FORM", "VERIFIED", "FILED"),
    ("reg_ura_tax_filed", "URA Tax Filing Receipt", "URSB, Registry & Government Filings", "TAX REVENUE FILING", "PRN PAYMENT VERIFIED", "TAX", "LODGED", "RECEIPTED"),
    ("reg_land_registry", "Land Title / Conveyancing", "URSB, Registry & Government Filings", "LAND & CONVEYANCING DESK", "TITLE SEARCH VERIFIED", "TITLE", "VERIFIED", "REGISTERED"),
    ("reg_public_procurement", "PPDA Tender Submission", "URSB, Registry & Government Filings", "PUBLIC TENDER REGISTRY", "SEALED BID SUBMISSION", "TENDER", "RECEIVED", "LOGGED"),
    ("reg_court_registry", "Court / Tribunal Filing", "URSB, Registry & Government Filings", "JUDICIAL FILING DESK", "PLEADINGS RECEIVED", "COURT", "FILED", "FILED"),
    ("reg_customs_cleared", "Customs & Border Cleared", "URSB, Registry & Government Filings", "CUSTOMS CLEARANCE UNIT", "RELEASE ORDER GRANTED", "CUSTOMS", "CLEARED", "RELEASED"),

    # 6. SACCO, Banking & Microfinance (9)
    ("sac_sacco_seal", "SACCO Official Society Seal", "SACCO, Banking & Microfinance", "SAVINGS & CREDIT COOPERATIVE", "REGISTERED SACCO SOCIETY", "SACCO", "OFFICIAL", "SEALED"),
    ("sac_credit_committee", "SACCO Credit Committee Approved", "SACCO, Banking & Microfinance", "SACCO CREDIT COMMITTEE", "LOAN APPRAISAL APPROVED", "LOAN", "APPROVED", "APPROVED"),
    ("sac_teller_received", "Cash Teller — Received", "SACCO, Banking & Microfinance", "BANKING HALL TELLER", "MEMBER DEPOSIT VERIFIED", "CASH", "RECEIVED", "POSTED"),
    ("sac_teller_paid", "Cash Teller — Paid", "SACCO, Banking & Microfinance", "BANKING HALL TELLER", "WITHDRAWAL DISBURSED", "CASH", "PAID", "DISBURSED"),
    ("sac_guarantor_verified", "Guarantor & KYC Verified", "SACCO, Banking & Microfinance", "MEMBER CREDIT SECURITY", "GUARANTOR & NIN CHECKED", "GUARANTOR", "VERIFIED", "VERIFIED"),
    ("sac_supervisory_audit", "Supervisory Committee Audited", "SACCO, Banking & Microfinance", "SACCO SUPERVISORY COMMITTEE", "INDEPENDENT MEMBER AUDIT", "SUPERVISORY", "AUDITED", "AUDITED"),
    ("sac_collateral_custody", "Collateral Vault Custody", "SACCO, Banking & Microfinance", "SECURITY VAULT CUSTODY", "ORIGINAL TITLE HELD", "COLLATERAL", "HELD", "SECURED"),
    ("sac_share_certificate", "SACCO Share Capital Seal", "SACCO, Banking & Microfinance", "MEMBER SHARE CAPITAL", "PERMANENT EQUITY REGISTER", "SHARES", "CERTIFIED", "ISSUED"),
    ("sac_aml_kyc_cleared", "AML / CFT & KYC Cleared", "SACCO, Banking & Microfinance", "COMPLIANCE & MLCO DESK", "CDD / SANCTIONS CLEARED", "AML / KYC", "CLEARED", "CLEARED"),

    # 7. HR, Confidentiality & Security (8)
    ("hr_confidential", "Strictly Confidential", "HR, Confidentiality & Security", "INFORMATION CLASSIFICATION", "AUTHORIZED EYES ONLY", "STRICTLY", "CONFIDENTIAL", "RESTRICTED"),
    ("hr_private_personnel", "Private & Confidential — HR", "HR, Confidentiality & Security", "HUMAN RESOURCES VAULT", "EMPLOYEE PERSONNEL FILE", "HR", "CONFIDENTIAL", "PROTECTED"),
    ("hr_probation_confirmed", "Probation Confirmed", "HR, Confidentiality & Security", "PEOPLE & TALENT OFFICE", "PERMANENT APPOINTMENT", "PROBATION", "CONFIRMED", "CONFIRMED"),
    ("hr_background_vetted", "Background Check Cleared", "HR, Confidentiality & Security", "PRE-EMPLOYMENT VETTING", "CREDENTIALS VERIFIED", "VETTED", "CLEARED", "VERIFIED"),
    ("hr_security_restricted", "Restricted — Do Not Copy", "HR, Confidentiality & Security", "SECURITY CLASSIFICATION", "UNAUTHORIZED COPY PROHIBITED", "RESTRICTED", "NO COPY", "CLASSIFIED"),
    ("hr_payroll_approved", "Payroll Verified & Approved", "HR, Confidentiality & Security", "PAYROLL & BENEFITS UNIT", "STATUTORY REMITTANCES OK", "PAYROLL", "APPROVED", "APPROVED"),
    ("hr_exit_cleared", "Staff Exit Clearance Complete", "HR, Confidentiality & Security", "OFFBOARDING & ASSET RETURN", "ALL DEPARTMENTS CLEARED", "EXIT", "CLEARED", "CLEARED"),
    ("hr_dpa_protected", "Personal Data Protected", "HR, Confidentiality & Security", "DATA PROTECTION OFFICER", "DPPA / GDPR CONTROLLED", "DATA", "PROTECTED", "SECURED"),

    # 8. Operations, QA & ISO Compliance (8)
    ("ops_iso9001_qa", "ISO 9001 Quality Approved", "Operations, QA & ISO Compliance", "QUALITY MANAGEMENT SYSTEM", "ISO 9001 COMPLIANT", "QA", "PASSED", "PASSED"),
    ("ops_inspected_ok", "Inspected & Passed", "Operations, QA & ISO Compliance", "QUALITY CONTROL LAB", "MEETS SPECIFICATIONS", "INSPECTED", "PASSED", "PASSED"),
    ("ops_quarantine_hold", "Quarantine / On Hold", "Operations, QA & ISO Compliance", "NON-CONFORMANCE CONTROL", "DO NOT RELEASE", "ON HOLD", "QUARANTINE", "HELD"),
    ("ops_controlled_copy", "Controlled Master Copy", "Operations, QA & ISO Compliance", "ISO DOCUMENT CONTROL", "OFFICIAL CONTROLLED COPY", "CONTROLLED", "COPY", "CONTROLLED"),
    ("ops_uncontrolled_copy", "Uncontrolled Copy — Reference", "Operations, QA & ISO Compliance", "DOCUMENT DISTRIBUTION", "CHECK MASTER VERSION", "UNCONTROLLED", "REFERENCE", "REFERENCE"),
    ("ops_calibrated_ok", "Equipment Calibrated", "Operations, QA & ISO Compliance", "METROLOGY & CALIBRATION", "INSTRUMENT VERIFIED", "CALIBRATED", "CERTIFIED", "VERIFIED"),
    ("ops_hse_cleared", "HSE Safety Cleared", "Operations, QA & ISO Compliance", "HEALTH SAFETY ENVIRONMENT", "PERMIT TO WORK ISSUED", "HSE", "CLEARED", "APPROVED"),
    ("ops_capa_closed", "CAPA Verified & Closed", "Operations, QA & ISO Compliance", "CORRECTIVE ACTION BOARD", "ROOT CAUSE RESOLVED", "CAPA", "CLOSED", "CLOSED"),

    # 9. Shipping, Logistics & Warehouse (7)
    ("log_goods_received", "Goods Received in Good Order", "Shipping, Logistics & Warehouse", "WAREHOUSE RECEIVING BAY", "QUANTITY & QUALITY CHECKED", "GOODS", "RECEIVED", "RECEIVED"),
    ("log_dispatched", "Dispatched / Shipped", "Shipping, Logistics & Warehouse", "LOGISTICS DISPATCH DESK", "WAYBILL & SEAL VERIFIED", "SHIPPED", "DISPATCHED", "SHIPPED"),
    ("log_pod_signed", "Proof of Delivery (POD)", "Shipping, Logistics & Warehouse", "DELIVERY CONFIRMATION", "CONSIGNEE ACCEPTED", "DELIVERED", "POD", "DELIVERED"),
    ("log_fragile_handle", "Fragile — Handle With Care", "Shipping, Logistics & Warehouse", "CARGO HANDLING NOTICE", "DO NOT STACK OR DROP", "FRAGILE", "CARE", "FRAGILE"),
    ("log_cold_chain", "Cold Chain Verified (2–8°C)", "Shipping, Logistics & Warehouse", "TEMPERATURE CONTROLLED", "THERMAL LOG INTACT", "COLD CHAIN", "VERIFIED", "VERIFIED"),
    ("log_export_cleared", "Export Documentation Cleared", "Shipping, Logistics & Warehouse", "EXPORT FREIGHT CONTROL", "CERTIFICATE OF ORIGIN OK", "EXPORT", "CLEARED", "CLEARED"),
    ("log_stock_audited", "Inventory Count Verified", "Shipping, Logistics & Warehouse", "STOCK CONTROL & STORES", "CYCLE COUNT MATCHED", "STOCK", "VERIFIED", "COUNTED"),

    # 10. Healthcare, Pharma & Clinical (7)
    ("med_clinical_approved", "Medical Director Approved", "Healthcare, Pharma & Clinical", "OFFICE OF MEDICAL DIRECTOR", "CLINICAL GOVERNANCE", "CLINICAL", "APPROVED", "APPROVED"),
    ("med_lab_verified", "Laboratory Result Verified", "Healthcare, Pharma & Clinical", "CLINICAL DIAGNOSTIC LAB", "PATHOLOGIST VERIFIED", "LAB RESULT", "VERIFIED", "VERIFIED"),
    ("med_pharmacy_dispensed", "Pharmacy Dispensed", "Healthcare, Pharma & Clinical", "REGISTERED PHARMACY", "PRESCRIPTION CHECKED", "DISPENSED", "PHARMACY", "DISPENSED"),
    ("med_medical_records", "Confidential Medical Record", "Healthcare, Pharma & Clinical", "HEALTH INFORMATION UNIT", "PATIENT PRIVACY PROTECTED", "MEDICAL", "RECORD", "CONFIDENTIAL"),
    ("med_fit_for_duty", "Medically Cleared / Fit", "Healthcare, Pharma & Clinical", "OCCUPATIONAL HEALTH CLINIC", "EXAMINATION COMPLETE", "MEDICALLY", "CLEARED", "CLEARED"),
    ("med_gdp_batch_ok", "Pharma Batch Released (GDP)", "Healthcare, Pharma & Clinical", "QUALITY ASSURANCE PHARMA", "COA & COLD CHAIN OK", "BATCH", "RELEASED", "RELEASED"),
    ("med_consent_verified", "Informed Consent Verified", "Healthcare, Pharma & Clinical", "PATIENT SAFETY UNIT", "CONSENT EXECUTED", "CONSENT", "VERIFIED", "SIGNED"),

    # 11. Education, Academic & Certification (7)
    ("edu_registrar_seal", "Academic Registrar Seal", "Education, Academic & Certification", "OFFICE OF ACADEMIC REGISTRAR", "OFFICIAL TRANSCRIPT SEAL", "ACADEMIC", "REGISTRAR", "CERTIFIED"),
    ("edu_certified_transcript", "Official Certified Transcript", "Education, Academic & Certification", "ACADEMIC RECORDS OFFICE", "VALID ONLY WITH SEAL", "OFFICIAL", "TRANSCRIPT", "VERIFIED"),
    ("edu_admissions_cleared", "Admissions Office Cleared", "Education, Academic & Certification", "ADMISSIONS & ENROLLMENT", "CREDENTIALS VERIFIED", "ADMITTED", "CLEARED", "ADMITTED"),
    ("edu_bursar_cleared", "Bursar / Fees Cleared", "Education, Academic & Certification", "OFFICE OF THE BURSAR", "TUITION ACCOUNT CLEARED", "FEES", "CLEARED", "CLEARED"),
    ("edu_exam_verified", "Examination Board Verified", "Education, Academic & Certification", "EXAMINATIONS & SENATE", "RESULTS AUTHENTICATED", "EXAM", "VERIFIED", "APPROVED"),
    ("edu_library_cleared", "Library Clearance Stamp", "Education, Academic & Certification", "CENTRAL ACADEMIC LIBRARY", "NO OVERDUE MATERIALS", "LIBRARY", "CLEARED", "CLEARED"),
    ("edu_award_certificate", "Certificate of Achievement", "Education, Academic & Certification", "INSTITUTIONAL TRAINING", "COMPETENCY CERTIFIED", "CERTIFIED", "AWARD", "ISSUED"),

    # 12. Real Estate, Construction & Engineering (7)
    ("eng_issued_construction", "Issued for Construction (IFC)", "Real Estate, Construction & Engineering", "ENGINEERING DESIGN CONTROL", "APPROVED DRAWING ISSUE", "ISSUED FOR", "CONSTRUCTION", "IFC"),
    ("eng_as_built", "As-Built Record Drawing", "Real Estate, Construction & Engineering", "PROJECT COMPLETION ARCHIVE", "FINAL FIELD VERIFIED", "AS-BUILT", "RECORD", "VERIFIED"),
    ("eng_resident_engineer", "Resident Engineer Approved", "Real Estate, Construction & Engineering", "RESIDENT ENGINEER OFFICE", "SITE INSPECTION PASSED", "ENGINEER", "APPROVED", "APPROVED"),
    ("eng_quantity_surveyor", "Quantity Surveyor Certified", "Real Estate, Construction & Engineering", "VALUATION & BOQ CONTROL", "IPC CERTIFICATE VERIFIED", "QS", "CERTIFIED", "CERTIFIED"),
    ("eng_structural_checked", "Structural Design Checked", "Real Estate, Construction & Engineering", "STRUCTURAL ENGINEERING", "LOAD & CODE COMPLIANT", "STRUCTURAL", "CHECKED", "CHECKED"),
    ("eng_property_mgmt", "Property Management Official", "Real Estate, Construction & Engineering", "ESTATE & TENANCY OFFICE", "LEASE & INSPECTION SEAL", "PROPERTY", "OFFICIAL", "VERIFIED"),
    ("eng_handover_accepted", "Practical Completion Accepted", "Real Estate, Construction & Engineering", "PROJECT HANDOVER BOARD", "SNAG LIST CLEARED", "HANDOVER", "ACCEPTED", "ACCEPTED"),
]


def _render_style_svg(
    *,
    shape: str,
    color: str,
    top_arc: str,
    bottom_arc: str,
    c1: str,
    c2: str,
    verb: str,
    slug: str,
) -> str:
    """Fast deterministic vector SVG generator for all 10 physical stamp geometries."""
    uid = _uid(slug, shape, color)
    top_u = top_arc.upper()
    bot_u = bottom_arc.upper()
    c1_u = c1.upper()
    c2_u = c2.upper()
    verb_u = verb.upper()

    if shape == "circle":
        fs_top = _fit(top_u, 275, 16, 1.6, 0.66)
        fs_bot = _fit(bot_u, 275, 14, 1.5, 0.66)
        fs_c1 = _fit(c1_u, 142, 20, 1.0, 0.64)
        fs_c2 = _fit(c2_u, 138, 17, 1.0, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" width="160" height="160" data-stamp-root="1">'
            f'<defs><path id="t-{uid}" d="M -112 0 A 112 112 0 0 1 112 0" fill="none"/>'
            f'<path id="b-{uid}" d="M -122 0 A 122 122 0 0 0 122 0" fill="none"/></defs>'
            f'<circle r="144" fill="none" stroke="{color}" stroke-width="3.6"/>'
            f'<circle r="134" fill="none" stroke="{color}" stroke-width="1.2"/>'
            f'<circle r="86" fill="none" stroke="{color}" stroke-width="1.3"/>'
            f'<text font-family="Georgia, serif" font-size="{fs_top}" font-weight="700" letter-spacing="1.5" fill="{color}">'
            f'<textPath href="#t-{uid}" startOffset="50%" text-anchor="middle">{_esc(top_u)}</textPath></text>'
            f'<text font-family="Georgia, serif" font-size="{fs_bot}" font-weight="700" letter-spacing="1.4" fill="{color}">'
            f'<textPath href="#b-{uid}" startOffset="50%" text-anchor="middle">{_esc(bot_u)}</textPath></text>'
            f'<text x="-112" y="5" text-anchor="middle" font-size="13" fill="{color}">★</text>'
            f'<text x="112" y="5" text-anchor="middle" font-size="13" fill="{color}">★</text>'
            f'<text y="-4" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c1}" font-weight="700" fill="{color}">{_esc(c1_u)}</text>'
            f'<text y="20" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c2}" font-weight="700" fill="{color}">{_esc(c2_u)}</text>'
            f'</svg>'
        )

    if shape == "starburst":
        pts = []
        spikes = 36
        for i in range(spikes * 2):
            ang = math.pi * i / spikes
            r = 148 if i % 2 == 0 else 137
            pts.append(f"{r * math.cos(ang):.1f},{r * math.sin(ang):.1f}")
        poly = " ".join(pts)
        fs_top = _fit(top_u, 258, 15, 1.4, 0.66)
        fs_bot = _fit(bot_u, 258, 13, 1.3, 0.66)
        fs_c1 = _fit(c1_u, 136, 19, 1.0, 0.64)
        fs_c2 = _fit(c2_u, 132, 16, 1.0, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" width="160" height="160" data-stamp-root="1">'
            f'<defs><path id="t-{uid}" d="M -108 0 A 108 108 0 0 1 108 0" fill="none"/>'
            f'<path id="b-{uid}" d="M -118 0 A 118 118 0 0 0 118 0" fill="none"/></defs>'
            f'<polygon points="{poly}" fill="none" stroke="{color}" stroke-width="2.4"/>'
            f'<circle r="130" fill="none" stroke="{color}" stroke-width="1.4"/>'
            f'<circle r="84" fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="4,3"/>'
            f'<text font-family="Georgia, serif" font-size="{fs_top}" font-weight="700" letter-spacing="1.4" fill="{color}">'
            f'<textPath href="#t-{uid}" startOffset="50%" text-anchor="middle">{_esc(top_u)}</textPath></text>'
            f'<text font-family="Georgia, serif" font-size="{fs_bot}" font-weight="700" letter-spacing="1.3" fill="{color}">'
            f'<textPath href="#b-{uid}" startOffset="50%" text-anchor="middle">{_esc(bot_u)}</textPath></text>'
            f'<text y="-5" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c1}" font-weight="700" fill="{color}">{_esc(c1_u)}</text>'
            f'<text y="19" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c2}" font-weight="700" fill="{color}">{_esc(c2_u)}</text>'
            f'</svg>'
        )

    if shape == "circle_dated":
        fs_top = _fit(top_u, 272, 15, 1.5, 0.66)
        fs_bot = _fit(bot_u, 272, 13, 1.4, 0.66)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" width="160" height="160" data-stamp-root="1">'
            f'<defs><path id="t-{uid}" d="M -112 0 A 112 112 0 0 1 112 0" fill="none"/>'
            f'<path id="b-{uid}" d="M -122 0 A 122 122 0 0 0 122 0" fill="none"/></defs>'
            f'<circle r="144" fill="none" stroke="{color}" stroke-width="3.2"/>'
            f'<circle r="134" fill="none" stroke="{color}" stroke-width="1.1"/>'
            f'<circle r="88" fill="none" stroke="{color}" stroke-width="1.2"/>'
            f'<line x1="-82" y1="-22" x2="82" y2="-22" stroke="{color}" stroke-width="1.1"/>'
            f'<line x1="-82" y1="26" x2="82" y2="26" stroke="{color}" stroke-width="1.1"/>'
            f'<text font-family="Georgia, serif" font-size="{fs_top}" font-weight="700" letter-spacing="1.4" fill="{color}">'
            f'<textPath href="#t-{uid}" startOffset="50%" text-anchor="middle">{_esc(top_u)}</textPath></text>'
            f'<text font-family="Georgia, serif" font-size="{fs_bot}" font-weight="700" letter-spacing="1.3" fill="{color}">'
            f'<textPath href="#b-{uid}" startOffset="50%" text-anchor="middle">{_esc(bot_u)}</textPath></text>'
            f'<text y="-32" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="700" letter-spacing="2" fill="{color}">{_esc(verb_u)}</text>'
            f'<text y="8" text-anchor="middle" font-family="Courier New, monospace" font-size="16" font-weight="700" fill="{color}" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            f'<text y="48" text-anchor="middle" font-family="Arial, sans-serif" font-size="9.5" font-weight="700" letter-spacing="1.4" fill="{color}">{_esc(c1_u)}</text>'
            f'</svg>'
        )

    if shape == "oval":
        fs_top = _fit(top_u, 270, 14, 1.2, 0.64)
        fs_c1 = _fit(c1_u + " " + c2_u, 250, 20, 1.2, 0.64)
        fs_bot = _fit(bot_u, 250, 11, 1.2, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-175 -115 350 230" width="180" height="118" data-stamp-root="1">'
            f'<ellipse rx="164" ry="102" fill="none" stroke="{color}" stroke-width="3.4"/>'
            f'<ellipse rx="154" ry="92" fill="none" stroke="{color}" stroke-width="1.2"/>'
            f'<ellipse rx="124" ry="56" fill="none" stroke="{color}" stroke-width="1"/>'
            f'<text y="-66" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_top}" font-weight="700" letter-spacing="1.2" fill="{color}">{_esc(top_u[:28])}</text>'
            f'<text y="6" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c1}" font-weight="700" letter-spacing="1.2" fill="{color}">{_esc(c1_u + " " + c2_u)}</text>'
            f'<text y="76" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_bot}" font-weight="700" letter-spacing="1.4" fill="{color}">{_esc(bot_u[:30])}</text>'
            f'</svg>'
        )

    if shape == "rect_dated":
        fs_co = _fit(top_u, 336, 15, 1.2, 0.64)
        fs_sub = _fit(bot_u, 330, 11, 1.1, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 190" width="190" height="95" data-stamp-root="1">'
            f'<rect x="6" y="6" width="368" height="178" rx="6" fill="none" stroke="{color}" stroke-width="3.2"/>'
            f'<rect x="13" y="13" width="354" height="164" rx="3" fill="none" stroke="{color}" stroke-width="1.1"/>'
            f'<line x1="13" y1="62" x2="367" y2="62" stroke="{color}" stroke-width="1.1"/>'
            f'<line x1="13" y1="126" x2="367" y2="126" stroke="{color}" stroke-width="1.1"/>'
            f'<text x="190" y="34" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_co}" font-weight="700" letter-spacing="1.1" fill="{color}">{_esc(top_u)}</text>'
            f'<text x="190" y="52" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_sub}" font-weight="700" letter-spacing="1.1" fill="{color}">{_esc(bot_u)}</text>'
            f'<text x="190" y="84" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="700" letter-spacing="2.4" fill="{color}">{_esc(verb_u)}</text>'
            f'<text x="190" y="112" text-anchor="middle" font-family="Courier New, monospace" font-size="20" font-weight="700" fill="{color}" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            f'<text x="26" y="156" font-family="Arial, sans-serif" font-size="10.5" font-weight="700" fill="{color}">SIGN: ______________________</text>'
            f'<text x="242" y="156" font-family="Arial, sans-serif" font-size="10.5" font-weight="700" fill="{color}">REF: ________</text>'
            f'</svg>'
        )

    if shape == "rect_bold":
        line = f"{c1_u} {c2_u}".strip()
        fs_m = _fit(line, 310, 30, 2.2, 0.66)
        fs_s = _fit(top_u, 316, 11, 1.4, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 144" width="180" height="72" data-stamp-root="1">'
            f'<rect x="6" y="6" width="348" height="132" fill="none" stroke="{color}" stroke-width="4.5"/>'
            f'<rect x="15" y="15" width="330" height="114" fill="none" stroke="{color}" stroke-width="1.3"/>'
            f'<text x="180" y="76" text-anchor="middle" font-family="Arial Black, Impact, sans-serif" font-size="{fs_m}" font-weight="900" letter-spacing="2.2" fill="{color}">{_esc(line)}</text>'
            f'<line x1="34" y1="94" x2="326" y2="94" stroke="{color}" stroke-width="1.1"/>'
            f'<text x="180" y="114" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_s}" font-weight="700" letter-spacing="1.4" fill="{color}">{_esc(top_u)}</text>'
            f'</svg>'
        )

    if shape == "rounded":
        line = f"{c1_u} {c2_u}".strip()
        fs_m = _fit(line, 290, 26, 2.0, 0.66)
        fs_s = _fit(bot_u, 290, 11, 1.3, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 156" width="180" height="78" data-stamp-root="1">'
            f'<rect x="8" y="8" width="344" height="140" rx="28" fill="none" stroke="{color}" stroke-width="3.6"/>'
            f'<rect x="16" y="16" width="328" height="124" rx="22" fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="6,4"/>'
            f'<text x="180" y="78" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_m}" font-weight="800" letter-spacing="2.0" fill="{color}">{_esc(line)}</text>'
            f'<text x="180" y="110" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_s}" font-weight="700" letter-spacing="1.3" fill="{color}">{_esc(bot_u)}</text>'
            f'</svg>'
        )

    if shape == "shield":
        fs_c1 = _fit(c1_u, 152, 22, 1.2, 0.64)
        fs_c2 = _fit(c2_u, 144, 18, 1.2, 0.64)
        fs_top = _fit(verb_u, 140, 11, 1.6, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-150 -160 300 320" width="150" height="160" data-stamp-root="1">'
            f'<path d="M -118 -134 L 118 -134 L 118 -10 C 118 76 52 126 0 148 C -52 126 -118 76 -118 -10 Z" fill="none" stroke="{color}" stroke-width="3.8"/>'
            f'<path d="M -107 -123 L 107 -123 L 107 -12 C 107 66 46 112 0 133 C -46 112 -107 66 -107 -12 Z" fill="none" stroke="{color}" stroke-width="1.2"/>'
            f'<line x1="-94" y1="-68" x2="94" y2="-68" stroke="{color}" stroke-width="1.2"/>'
            f'<text y="-88" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_top}" font-weight="700" letter-spacing="1.8" fill="{color}">{_esc(verb_u)}</text>'
            f'<text y="-14" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c1}" font-weight="700" fill="{color}">{_esc(c1_u)}</text>'
            f'<text y="18" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c2}" font-weight="700" fill="{color}">{_esc(c2_u)}</text>'
            f'<text y="66" text-anchor="middle" font-family="Courier New, monospace" font-size="12" font-weight="700" fill="{color}" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            f'<text y="102" text-anchor="middle" font-size="14" fill="{color}">★ ★ ★</text>'
            f'</svg>'
        )

    if shape == "square":
        fs_top = _fit(top_u, 224, 13, 1.0, 0.64)
        fs_c1 = _fit(c1_u, 210, 24, 1.4, 0.64)
        fs_c2 = _fit(c2_u, 210, 19, 1.2, 0.64)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 260" width="150" height="150" data-stamp-root="1">'
            f'<rect x="8" y="8" width="244" height="244" fill="none" stroke="{color}" stroke-width="3.6"/>'
            f'<rect x="17" y="17" width="226" height="226" fill="none" stroke="{color}" stroke-width="1.2"/>'
            f'<line x1="17" y1="68" x2="243" y2="68" stroke="{color}" stroke-width="1.2"/>'
            f'<line x1="17" y1="194" x2="243" y2="194" stroke="{color}" stroke-width="1.2"/>'
            f'<text x="130" y="48" text-anchor="middle" font-family="Arial, sans-serif" font-size="{fs_top}" font-weight="700" letter-spacing="1.1" fill="{color}">{_esc(top_u[:26])}</text>'
            f'<text x="130" y="122" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c1}" font-weight="700" fill="{color}">{_esc(c1_u)}</text>'
            f'<text x="130" y="156" text-anchor="middle" font-family="Georgia, serif" font-size="{fs_c2}" font-weight="700" fill="{color}">{_esc(c2_u)}</text>'
            f'<text x="130" y="224" text-anchor="middle" font-family="Courier New, monospace" font-size="14" font-weight="700" fill="{color}" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            f'</svg>'
        )

    # diagonal / vintage
    line = f"{c1_u} {c2_u}".strip()
    fs_m = _fit(line, 286, 26, 2.2, 0.66)
    fs_b = _fit(bot_u, 290, 10.5, 1.3, 0.64)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 180" width="190" height="90" data-stamp-root="1">'
        f'<g transform="rotate(-7 190 90)">'
        f'<rect x="18" y="28" width="344" height="124" rx="4" fill="none" stroke="{color}" stroke-width="4"/>'
        f'<rect x="26" y="36" width="328" height="108" rx="2" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<text x="190" y="92" text-anchor="middle" font-family="Arial Black, Impact, sans-serif" font-size="{fs_m}" font-weight="900" letter-spacing="2.2" fill="{color}">{_esc(line)}</text>'
        f'<text x="190" y="124" text-anchor="middle" font-family="Courier New, monospace" font-size="{fs_b}" font-weight="700" letter-spacing="1.2" fill="{color}">{_esc(bot_u)}</text>'
        f'</g></svg>'
    )


@lru_cache(maxsize=1)
def get_1000_stamp_catalog() -> list[dict[str, Any]]:
    """Build lightweight metadata for all 1,000 institutional stamp templates (SVG rendered lazily)."""
    out: list[dict[str, Any]] = []
    for slug_base, name, category, top_arc, bottom_arc, c1, c2, verb in STAMP_ARCHETYPES:
        for style_slug, style_label, kind, shape, w_mm, h_mm, color, style_desc in STAMP_STYLES:
            slug = f"st1k-{slug_base.replace('_', '-')}-{style_slug}"
            out.append({
                "slug": slug,
                "name": f"{name} — {style_label}",
                "short_name": name,
                "category": category,
                "kind": kind,
                "style": style_slug,
                "style_label": style_label,
                "shape": shape,
                "color": color,
                "width_mm": w_mm,
                "height_mm": h_mm,
                "description": f"{style_desc} for {name.lower()} ({category}).",
                "top_arc": top_arc,
                "bottom_arc": bottom_arc,
                "c1": c1,
                "c2": c2,
                "verb": verb,
            })
    return out


@lru_cache(maxsize=1)
def get_1000_stamp_by_slug() -> dict[str, dict[str, Any]]:
    return {it["slug"]: it for it in get_1000_stamp_catalog()}


def render_stamp_item(item: dict[str, Any]) -> dict[str, Any]:
    """Hydrate a metadata item with its vector SVG and Stamp Studio layout dict."""
    svg = _render_style_svg(
        shape=item["shape"],
        color=item["color"],
        top_arc=item["top_arc"],
        bottom_arc=item["bottom_arc"],
        c1=item["c1"],
        c2=item["c2"],
        verb=item["verb"],
        slug=item["slug"],
    )
    layout = {
        "company": item["top_arc"],
        "top_text": item["top_arc"],
        "bottom_text": item["bottom_arc"],
        "subtitle": item["bottom_arc"],
        "text": f"{item['c1']}\n{item['c2']}",
        "center_lines": [item["c1"], item["c2"]],
        "verb": item["verb"],
        "color": item["color"],
        "shape": item["shape"],
        "style": item["style"],
        "date_format": "DD MMM YYYY",
        "width_mm": item["width_mm"],
        "height_mm": item["height_mm"],
        "size_value": f"{item['width_mm']}x{item['height_mm']}",
    }
    return {
        "slug": item["slug"],
        "name": item["name"],
        "category": item["category"],
        "kind": item["kind"],
        "style": item["style"],
        "style_label": item["style_label"],
        "shape": item["shape"],
        "color": item["color"],
        "size_mm": f"{item['width_mm']}×{item['height_mm']} mm",
        "description": item["description"],
        "layout": layout,
        "svg": svg,
    }


def get_stamp_catalog_facets(builtin_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cats: dict[str, int] = {}
    styles: dict[str, dict[str, Any]] = {}
    kinds: dict[str, int] = {}
    for b in (builtin_items or []):
        cats[b["category"]] = cats.get(b["category"], 0) + 1
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
    for it in get_1000_stamp_catalog():
        cats[it["category"]] = cats.get(it["category"], 0) + 1
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        if it["style"] not in styles:
            styles[it["style"]] = {"style": it["style"], "label": it["style_label"], "count": 0}
        styles[it["style"]]["count"] += 1
    return {
        "categories": [{"category": k, "count": v} for k, v in cats.items()],
        "styles": list(styles.values()),
        "kinds": [{"kind": k, "count": v} for k, v in kinds.items()],
    }


def search_stamp_catalog(
    *,
    builtin_items: list[dict[str, Any]] | None = None,
    q: str = "",
    category: str = "",
    style: str = "",
    kind: str = "",
    page: int = 1,
    per_page: int = 24,
) -> dict[str, Any]:
    """Fast paginated & multi-facet search across built-in + 1,000 stamp templates."""
    ql = (q or "").strip().lower()
    tokens = [t for t in ql.split() if t]
    cat_f = (category or "").strip()
    style_f = (style or "").strip()
    kind_f = (kind or "").strip()

    builtins = builtin_items or []
    gen = get_1000_stamp_catalog()
    total_catalog = len(builtins) + len(gen)

    matched: list[tuple[bool, dict[str, Any]]] = []
    for b in builtins:
        if cat_f and cat_f.upper() != "ALL" and b["category"] != cat_f:
            continue
        if style_f and style_f.upper() != "ALL":
            continue
        if kind_f and kind_f.upper() != "ALL" and b["kind"] != kind_f:
            continue
        if tokens:
            hay = f"{b['name']} {b['category']} {b['kind']} {b['description']}".lower()
            if not all(tok in hay for tok in tokens):
                continue
        matched.append((True, b))

    for it in gen:
        if cat_f and cat_f.upper() != "ALL" and it["category"] != cat_f:
            continue
        if style_f and style_f.upper() != "ALL" and it["style"] != style_f:
            continue
        if kind_f and kind_f.upper() != "ALL" and it["kind"] != kind_f:
            continue
        if tokens:
            hay = f"{it['name']} {it['category']} {it['kind']} {it['style_label']} {it['description']} {it['top_arc']} {it['c1']} {it['c2']}".lower()
            if not all(tok in hay for tok in tokens):
                continue
        matched.append((False, it))

    total = len(matched)
    per_page = max(6, min(96, int(per_page or 24)))
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(total_pages, int(page or 1)))
    start = (page - 1) * per_page

    page_items = [
        (item if is_builtin else render_stamp_item(item))
        for is_builtin, item in matched[start : start + per_page]
    ]
    facets = get_stamp_catalog_facets(builtins)
    return {
        "total": total,
        "catalog_total": total_catalog,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": facets["categories"],
        "styles": facets["styles"],
        "kinds": facets["kinds"],
        "items": page_items,
    }
