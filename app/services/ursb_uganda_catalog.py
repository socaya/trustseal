"""URSB & Uganda Companies Act (OBRS) Statutory Company Document Templates.

Comprehensive suite of 30 full-length, filing-ready statutory documents & forms
aligned to:
- The Companies Act, Cap. 106 (formerly Act No. 1 of 2012, as amended 2022)
- The Companies (General) Regulations, 2016 (S.I. 2016 No. 7)
- The Companies (Single Member) Regulations, 2016 (S.I. 2016 No. 72)
- The Companies (Beneficial Owner) Regulations, 2023 (S.I. 2023 No. 5)
- The Business Names Registration Act, Cap. 105 & Partnership Act, Cap. 110
- The Insolvency Act, Cap. 108
- Uganda Registration Services Bureau (URSB) Online Business Registration System (OBRS)
"""
from __future__ import annotations

import html as _html
from typing import Any

URSB_CATEGORY = "URSB & Uganda Companies Act (OBRS)"


def _f(name: str) -> str:
    return "{{" + name + "}}"


# (slug_base, title, form_code, statutory_ref, summary, key_provisions, checklist_items, attestation_role)
URSB_OBRS_SPECS: list[tuple[str, str, str, str, str, list[str], list[str], str]] = [
    (
        "ursb_name_reservation_app",
        "URSB Application for Reservation of Company / Business Name (OBRS)",
        "OBRS Name Reservation",
        "Section 36, The Companies Act, Cap. 106 & Reg. 6, Companies (General) Regulations, 2016",
        "Official application to the Registrar of Companies (URSB) to search and reserve up to three proposed company or business names via OBRS for 30 days.",
        [
            "Proposed Primary Name (1st Choice): " + _f("proposed_name_1") + " (Suffix: Limited / SMC Limited / PLC).",
            "Proposed Alternative Name (2nd Choice): " + _f("proposed_name_2") + ".",
            "Proposed Alternative Name (3rd Choice): " + _f("proposed_name_3") + ".",
            "Entity Classification: " + _f("entity_type") + " · Primary Business Sector / ISIC Activity: " + _f("business_activity") + ".",
            "Applicant / Promoter Particulars: " + _f("applicant_name") + " · NIN / Passport No.: " + _f("applicant_nin") + " · Phone & Email: " + _f("contact_details") + ".",
        ],
        [
            "Confirm proposed name is not identical or confusingly similar to an existing entity on the URSB OBRS Register.",
            "Confirm name contains no restricted words (e.g. Royal, National, Bank, Chamber) without Ministerial consent.",
            "Attach URSB PRN payment receipt for Name Reservation fee (UGX 24,000) via URA e-Payment portal.",
        ],
        "Applicant / Promoter / Advocate",
    ),
    (
        "ursb_form_s18_reg_company",
        "Company Form S.18 — Application for Registration of a Company (OBRS)",
        "Company Form S.18",
        "Section 18, The Companies Act, Cap. 106 (Uganda)",
        "Core statutory OBRS incorporation application capturing reserved company name, type of company, nominal share capital in UGX, registered office, first directors, and subscribers.",
        [
            "Reserved Company Name: " + _f("organization_name") + " · Name Reservation Reference: " + _f("name_reservation_ref") + ".",
            "Company Type: " + _f("company_type") + " (Private Limited by Shares / Public Limited / Limited by Guarantee / Single Member Company).",
            "Nominal Share Capital: UGX " + _f("nominal_capital_ugx") + " divided into " + _f("total_shares") + " ordinary shares of UGX " + _f("par_value_ugx") + " each.",
            "Registered Office Address: Plot " + _f("plot_no") + ", " + _f("street_road") + ", " + _f("district_city") + ", Uganda · Postal Address: " + _f("postal_address") + ".",
            "Initial Directors & Subscribers Schedule: " + _f("directors_subscribers_schedule") + " (with National ID / Passport Numbers, TINs, and Share Allocations).",
        ],
        [
            "Upload signed Company Form S.18, Memorandum & Articles of Association, Form 18, Form 20, and BO Form 1 on OBRS.",
            "Ensure all Ugandan directors provide NIRA NINs and foreign directors attach notarized passport bio-data pages.",
            "Pay URSB Registration Fee & Stamp Duty on Nominal Capital via URA Payment Registration Number (PRN).",
        ],
        "All Subscribers / First Directors",
    ),
    (
        "ursb_memo_articles_private_shares",
        "Memorandum & Articles of Association — Private Company Limited by Shares (Table A)",
        "MEMARTS (Table A)",
        "Sections 7–15 & Table A, First Schedule, The Companies Act, Cap. 106",
        "Complete Memorandum & Articles of Association for a Ugandan Private Company Limited by Shares, incorporating share transfer restrictions, director powers, board quorum, and general meeting rules.",
        [
            "Clause 1 (Name): The name of the Company is " + _f("organization_name") + " (Private Company Limited by Shares).",
            "Clause 2 (Registered Office): The Registered Office of the Company shall be situated in the Republic of Uganda at " + _f("registered_office") + ".",
            "Clause 3 (Objects): To carry on the business of " + _f("principal_objects") + " and all lawful ancillary commercial, advisory, investment, and contractual activities.",
            "Clause 4 (Liability): The liability of the members is limited to the amount, if any, unpaid on the shares respectively held by them.",
            "Clause 5 (Share Capital): The authorized share capital is UGX " + _f("nominal_capital_ugx") + " divided into " + _f("total_shares") + " Ordinary Shares of UGX " + _f("par_value_ugx") + " each, with right to increase, subdivide, or consolidate.",
            "Articles of Association (Private Company Restrictions): Right to transfer shares is restricted by Board pre-emption rights; membership limited to 100 members; public invitation to subscribe for shares or debentures is prohibited.",
        ],
        [
            "Executed by all Subscribers with full names, residential addresses, occupations, shares taken, and signatures.",
            "Attested by an independent Witness (Advocate of the High Court of Uganda or Commissioner for Oaths).",
            "Assessed for Uganda Stamp Duty (0.5% of nominal capital + UGX 35,000 on MEMARTS) before OBRS upload.",
        ],
        "Subscribers & Attesting Witness / Advocate",
    ),
    (
        "ursb_memo_articles_single_member",
        "Memorandum & Articles of Association — Single Member Company (SMC Limited)",
        "SMC MEMARTS",
        "Section 4(1) Cap. 106 & The Companies (Single Member) Regulations, 2016 (S.I. 2016 No. 72)",
        "Tailored Memorandum & Articles of Association for a Uganda Single Member Company (SMC Limited) incorporating mandatory Nominee Director and Alternate Nominee Director succession clauses.",
        [
            "Clause 1 (Name): The name of the Company is " + _f("organization_name") + " (SMC) Limited.",
            "Clause 2 (Sole Member): The Company is formed by one sole subscriber and member, " + _f("sole_member_name") + " (NIN/Passport: " + _f("sole_member_nin") + "), holding 100% of issued share capital.",
            "Clause 3 (Share Capital): UGX " + _f("nominal_capital_ugx") + " divided into " + _f("total_shares") + " ordinary shares of UGX " + _f("par_value_ugx") + " each.",
            "Clause 4 (Nominee & Alternate Nominee Director): In compliance with Reg. 6 of S.I. 2016 No. 72, " + _f("nominee_director_name") + " is designated Nominee Director and " + _f("alternate_nominee_name") + " as Alternate Nominee Director to manage affairs upon death or incapacity of the Sole Member.",
            "Clause 5 (Written Sole-Member Resolutions): All resolutions of the Sole Member recorded in writing and signed shall have full force as resolutions of a General Meeting.",
        ],
        [
            "Attach signed Consent of Nominee Director & Alternate Nominee Director (Form 3 under SMC Regulations).",
            "Upload alongside Form S.18, Form 18, Form 20, and BO Form 1 on the URSB OBRS portal.",
        ],
        "Sole Member & Attesting Witness",
    ),
    (
        "ursb_memo_articles_guarantee",
        "Memorandum & Articles of Association — Company Limited by Guarantee (NGO / Non-Profit)",
        "MEMARTS (Table C)",
        "Section 9 & Table C, First Schedule, The Companies Act, Cap. 106",
        "Complete Memorandum & Articles of Association for a Company Limited by Guarantee without Share Capital (NGO, Foundation, Association, or Industry Chamber) compliant with URSB & NGO Bureau.",
        [
            "Clause 1 (Name): The name of the Company is " + _f("organization_name") + " Limited (by Guarantee).",
            "Clause 2 (Non-Profit Objects): To promote " + _f("charitable_objects") + " for public benefit across Uganda without distribution of dividends or profits to members.",
            "Clause 3 (Income & Property Application): All income and property of the Company shall be applied solely towards the promotion of its objects; no portion shall be paid or transferred directly or indirectly by way of dividend or bonus to members.",
            "Clause 4 (Member Guarantee): Every member undertakes to contribute an amount not exceeding UGX " + _f("guarantee_amount_ugx") + " to the assets of the Company in the event of winding up.",
            "Clause 5 (Dissolution Clause): Upon winding up, any surplus assets remaining after satisfaction of liabilities shall be transferred to a similar non-profit institution having like objects.",
        ],
        [
            "Verify objects align with Uganda NGO Act if intending to apply for an NGO Permit after URSB incorporation.",
            "Executed by founding Guarantors/Members and witnessed by an Advocate.",
        ],
        "Founding Members / Subscribers & Witness",
    ),
    (
        "ursb_memo_articles_public",
        "Memorandum & Articles of Association — Public Limited Company (PLC)",
        "PLC MEMARTS",
        "Sections 5–15 & Table A, The Companies Act, Cap. 106",
        "Comprehensive Memorandum & Articles of Association for a Ugandan Public Limited Company (PLC) eligible for public share offerings, CMA oversight, and Uganda Securities Exchange listing.",
        [
            "Clause 1 (Name): The name of the Company is " + _f("organization_name") + " Public Limited Company (PLC).",
            "Clause 2 (Share Capital & Free Transferability): Authorized share capital of UGX " + _f("nominal_capital_ugx") + " with freely transferable shares and authority to issue ordinary, preference, and convertible instruments.",
            "Clause 3 (Board Governance & Audit Committee): Minimum of two (2) directors (recommended five with independent non-executive directors), mandatory qualified Company Secretary, and Board Audit & Risk Committee.",
            "Clause 4 (Annual General Meetings & Statutory Audits): Mandatory Annual General Meeting within statutory timelines, audited IFRS financial statements laid before members, and proxy voting rights.",
        ],
        [
            "Ensure at least two (2) founding directors and minimum statutory subscribed capital.",
            "Follow up incorporation with Certificate of Commencement of Business (Section 113, Cap. 106).",
        ],
        "Subscribers & Company Secretary",
    ),
    (
        "ursb_form_a1_nominal_capital",
        "Statement of Nominal Share Capital (Form A1 / URA Stamp Duty Assessment)",
        "Form A1",
        "The Stamps Act, Cap. 339 & Section 18, Companies Act, Cap. 106",
        "Official statement declaring the authorized nominal share capital in Uganda Shillings (UGX) for URA Stamp Duty assessment (0.5% on nominal capital) during incorporation or capital increase.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration / Reservation No.: " + _f("document_ref") + ".",
            "Authorized Nominal Share Capital: UGX " + _f("nominal_capital_ugx") + ".",
            "Share Structure: " + _f("total_shares") + " Ordinary Shares at par value of UGX " + _f("par_value_ugx") + " per share.",
            "Stamp Duty Payable (0.5% of Nominal Capital): UGX " + _f("stamp_duty_ugx") + " · URA PRN Reference: " + _f("ura_prn") + ".",
        ],
        [
            "Generate URA PRN for 0.5% Stamp Duty on nominal capital (exempt if nominal capital is UGX 5,000,000 or below per statutory threshold).",
            "Upload signed Form A1 and URA Stamp Duty receipt on OBRS.",
        ],
        "Director / Company Secretary / Advocate",
    ),
    (
        "ursb_form_1_declaration_compliance",
        "Statutory Declaration of Compliance with Requirements of Registration (Form 1)",
        "Company Form 1",
        "Section 19(2), The Companies Act, Cap. 106",
        "Sworn statutory declaration by an Advocate of the High Court of Uganda or a named Director/Secretary confirming full compliance with all registration prerequisites under Cap. 106.",
        [
            "Deponent Particulars: I, " + _f("deponent_name") + ", of " + _f("deponent_address") + " (Advocate of the High Court of Uganda / Named Director / Company Secretary), do solemnly and sincerely declare as follows:",
            "Compliance Attestation: That all requirements of the Companies Act, Cap. 106 in respect of the registration of " + _f("organization_name") + " and all matters precedent and incidental thereto have been duly complied with.",
            "Truthfulness Declaration: I make this solemn declaration conscientiously believing the same to be true and by virtue of the Statutory Declarations Act, Cap. 24.",
        ],
        [
            "Must be sworn before a Commissioner for Oaths or Magistrate in Uganda.",
            "Attach Commissioner for Oaths stamp, signature, date, and place of swearing.",
        ],
        "Deponent & Commissioner for Oaths",
    ),
    (
        "ursb_foreign_company_reg",
        "Foreign Company Registration Return & Statement of Particulars (Section 252, OBRS)",
        "Form 24 / Sec. 252",
        "Sections 251–254, The Companies Act, Cap. 106",
        "Complete OBRS registration dossier for a company incorporated outside Uganda establishing a place of business in Uganda, listing certified charter, directors, and local authorized representative.",
        [
            "Foreign Company Name: " + _f("organization_name") + " · Country of Incorporation: " + _f("home_jurisdiction") + " · Home Reg. No.: " + _f("home_reg_no") + ".",
            "Principal Place of Business in Uganda: Plot " + _f("plot_no") + ", " + _f("street_road") + ", " + _f("district_city") + ", Uganda.",
            "Authorized Local Representative in Uganda (Service of Process): " + _f("local_rep_name") + " · NIN/Passport: " + _f("local_rep_nin") + " · Address: " + _f("local_rep_address") + ".",
            "Schedule of Directors & Company Secretary (with nationalities, residential addresses, and passport details): " + _f("directors_list") + ".",
        ],
        [
            "Attach notarized/apostilled certified copy of foreign Certificate of Incorporation and Charter/MEMARTS.",
            "File within 30 days of establishing a place of business in Uganda via URSB OBRS.",
        ],
        "Authorized Representative / Director",
    ),
    (
        "ursb_business_name_reg",
        "Statement of Particulars for Registration of a Business Name (Sole Proprietorship / Firm)",
        "BN Form 1 (OBRS)",
        "Sections 3–5, The Business Names Registration Act, Cap. 105",
        "Official OBRS registration statement for registering a Sole Proprietorship or trading Business Name in Uganda with proprietor details, business address, and nature of trade.",
        [
            "Proposed / Reserved Business Name: " + _f("organization_name") + " · Name Reservation Ref: " + _f("name_reservation_ref") + ".",
            "General Nature of Business: " + _f("business_activity") + " · Date of Commencement: " + _f("effective_date") + ".",
            "Principal Place of Business: Plot " + _f("plot_no") + ", " + _f("street_road") + ", " + _f("district_city") + ", Uganda.",
            "Proprietor / Partners Particulars: Full Name " + _f("owner_name") + " · Nationality: " + _f("nationality") + " · NIN/Passport: " + _f("owner_nin") + " · Residential Address: " + _f("owner_address") + ".",
        ],
        [
            "Attach National ID (for Ugandan citizens) or valid Passport & Work Permit (for non-citizens).",
            "Pay Business Name Registration fee via URA PRN and submit through OBRS.",
        ],
        "Proprietor / All Partners",
    ),
    (
        "ursb_partnership_deed_reg",
        "Partnership Deed & Statement of Particulars for URSB OBRS Registration",
        "Partnership Deed",
        "The Partnership Act, Cap. 110 & Business Names Registration Act, Cap. 105",
        "Full legal Partnership Deed and OBRS registration particulars defining partner capital contributions, profit/loss sharing ratios, management authority, retirement, and dissolution.",
        [
            "Firm Name & Registered Address: " + _f("organization_name") + ", carrying on business at " + _f("registered_office") + ", Uganda.",
            "Partners & Capital Contributions: " + _f("partners_schedule") + " · Total Partnership Capital: UGX " + _f("nominal_capital_ugx") + ".",
            "Profit & Loss Sharing Ratio: Net profits and losses shall be shared among Partners in the agreed proportions (" + _f("profit_ratio") + ") after partnership expenses.",
            "Banking, Drawings & Decision-Making: Partnership bank account signatories, annual audited accounts, restrictions on unilateral guarantees, and dispute resolution by arbitration in Kampala.",
        ],
        [
            "Assess Partnership Deed for Stamp Duty with URA before uploading to OBRS.",
            "File alongside BN Form 1 and copies of all Partners' National IDs / Passports.",
        ],
        "All Partners & Attesting Witness",
    ),
    (
        "ursb_form_18_registered_office",
        "Company Form 18 — Notice of Situation / Change of Registered Office & Postal Address",
        "Company Form 18",
        "Sections 115–116, The Companies Act, Cap. 106 (Uganda)",
        "Mandatory URSB statutory notice notifying the Registrar of Companies of the initial situation or any subsequent change in the Company's registered physical office and postal address in Uganda.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No. (BRN): " + _f("document_ref") + ".",
            "Notice Type: Initial Situation of Registered Office / Change of Registered Office effective " + _f("effective_date") + ".",
            "New Registered Physical Address: Plot " + _f("plot_no") + ", Building/Floor " + _f("building_name") + ", " + _f("street_road") + ", " + _f("village_parish") + ", " + _f("subcounty_division") + ", " + _f("district_city") + ", Uganda.",
            "Registered Postal Address & Official Email: P.O. Box " + _f("postal_address") + " · Official OBRS Email: " + _f("official_email") + " · Telephone: " + _f("official_phone") + ".",
        ],
        [
            "File on URSB OBRS within 14 days of incorporation or within 14 days of any change of registered office.",
            "Ensure Board Resolution approving change of registered office is attached if filing a change.",
        ],
        "Director or Company Secretary",
    ),
    (
        "ursb_form_20_directors_secretary",
        "Company Form 20 — Notice of Particulars / Change of Directors & Company Secretary",
        "Company Form 20",
        "Section 228, The Companies Act, Cap. 106 (Uganda)",
        "Mandatory URSB OBRS filing recording the particulars of initial Directors & Company Secretary or notifying appointments, resignations, removals, or changes in personal particulars.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No. (BRN): " + _f("document_ref") + ".",
            "Effective Date of Appointment / Change: " + _f("effective_date") + ".",
            "Particulars of Directors (Full Name, Former Name, Nationality, NIN/Passport, Date of Birth, Residential Address, Occupation, Other Directorships): " + _f("directors_particulars") + ".",
            "Particulars of Company Secretary (Full Name / Corporate Secretary Name, Reg. No., Residential/Registered Address, Email & Phone): " + _f("secretary_particulars") + ".",
        ],
        [
            "Must be filed on URSB OBRS within 14 days of appointment or change of any Director or Company Secretary.",
            "Attach supporting Board/Shareholder Resolution, Consent to Act, and National ID / Passport copies.",
        ],
        "Director or Company Secretary",
    ),
    (
        "ursb_consent_act_director_sec",
        "Consent to Act as Director / Company Secretary & Statutory Qualification Declaration",
        "Consent Form (OBRS)",
        "Sections 185–192 & 228, The Companies Act, Cap. 106",
        "Formal written consent and statutory eligibility declaration signed by an incoming Director or Company Secretary confirming they are not disqualified under Cap. 106.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Appointee Particulars: Full Name " + _f("appointee_name") + " · Role: " + _f("appointee_role") + " · Nationality: " + _f("nationality") + " · NIN/Passport: " + _f("appointee_nin") + ".",
            "Statutory Qualification Declaration: I hereby consent to act in the said office and declare that I am over 18 years of age, of sound mind, not an undischarged bankrupt, and not disqualified from acting as a director or officer under the Companies Act, Cap. 106.",
        ],
        [
            "Attach copy of National ID (Ugandans) or Passport bio-page (non-citizens).",
            "Upload alongside Company Form 20 on URSB OBRS.",
        ],
        "Incoming Director / Company Secretary",
    ),
    (
        "ursb_smc_nominee_director",
        "Single Member Company (SMC) Notice & Consent of Nominee & Alternate Nominee Director",
        "SMC Form 3 / Reg. 6",
        "Regulation 6, The Companies (Single Member) Regulations, 2016 (S.I. 2016 No. 72)",
        "Mandatory OBRS filing for Ugandan Single Member Companies designating the Nominee Director and Alternate Nominee Director with their signed statutory consents.",
        [
            "Single Member Company Name: " + _f("organization_name") + " (SMC) Limited · URSB Reg. No.: " + _f("document_ref") + ".",
            "Sole Member: " + _f("sole_member_name") + " (NIN/Passport: " + _f("sole_member_nin") + ").",
            "Designated Nominee Director: " + _f("nominee_director_name") + " · NIN/Passport: " + _f("nominee_nin") + " · Residential Address: " + _f("nominee_address") + " · Relationship: " + _f("nominee_relationship") + ".",
            "Designated Alternate Nominee Director: " + _f("alternate_nominee_name") + " · NIN/Passport: " + _f("alt_nominee_nin") + " · Residential Address: " + _f("alt_nominee_address") + ".",
            "Statutory Undertaking: Both Nominee and Alternate Nominee hereby consent to act and manage the Company's affairs and transfer shares to legal heirs upon death or incapacity of the Sole Member.",
        ],
        [
            "Attach National ID / Passport copies of Sole Member, Nominee Director, and Alternate Nominee Director.",
            "File with URSB OBRS at incorporation or within 14 days of any change of Nominee.",
        ],
        "Sole Member, Nominee Director & Alternate Nominee",
    ),
    (
        "ursb_resignation_director_notice",
        "Formal Notice of Resignation of Director / Company Secretary (OBRS Filing Pack)",
        "Resignation Notice",
        "Section 228, The Companies Act, Cap. 106",
        "Formal written resignation letter and accompanying Board Acknowledgement Resolution required by URSB OBRS to remove an outgoing Director or Company Secretary on Form 20.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Resigning Officer: " + _f("resigning_officer_name") + " · Office Held: " + _f("office_held") + " · Effective Date of Resignation: " + _f("effective_date") + ".",
            "Notice & Confirmation: I hereby tender my formal resignation from the Board / office of Company Secretary and confirm that I have no outstanding claims against the Company for compensation or loss of office save as agreed in writing.",
            "Board Resolution Accepting Resignation: Resolved that the resignation be accepted and the Company Secretary be directed to file Company Form 20 on URSB OBRS within 14 days.",
        ],
        [
            "Ensure remaining number of directors satisfies the statutory minimum (1 for SMC, 2 for Public/standard Private).",
            "Upload Resignation Letter, Board Resolution, and updated Form 20 on OBRS.",
        ],
        "Resigning Officer & Board Chairperson",
    ),
    (
        "ursb_bo_form_1_beneficial_owner",
        "Beneficial Ownership Register & Notice of Particulars of Beneficial Owners (BO Form 1)",
        "BO Form 1 (S.I. 5/2023)",
        "Section 119A Cap. 106 & The Companies (Beneficial Owner) Regulations, 2023 (S.I. 2023 No. 5)",
        "Mandatory URSB OBRS Beneficial Ownership disclosure form declaring every natural person who ultimately owns or controls >=10% shares/voting rights or exercises effective control.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Reg. No. (BRN): " + _f("document_ref") + " · Date of Filing: " + _f("effective_date") + ".",
            "Beneficial Owner 1 Particulars: Full Legal Name " + _f("bo1_name") + " · NIN/Passport: " + _f("bo1_nin") + " · Nationality: " + _f("bo1_nationality") + " · Date of Birth: " + _f("bo1_dob") + " · Residential Address: " + _f("bo1_address") + " · Ownership/Voting %: " + _f("bo1_pct") + "% · Date Became BO: " + _f("bo1_date") + ".",
            "Beneficial Owner 2 / Additional Natural Persons: " + _f("bo_additional_schedule") + ".",
            "Nature of Ownership or Control: Direct/indirect holding of shares, voting rights, right to appoint/remove majority of Board, or exercise of significant influence/control.",
            "Statutory Certification: Certified true and accurate in compliance with the Companies (Beneficial Owner) Regulations, 2023 and Uganda AML/CFT framework.",
        ],
        [
            "Mandatory for ALL Ugandan companies on OBRS — failure attracts daily statutory penalties and blocks post-registration filings.",
            "File within 14 days of maintaining or updating the Company's internal Register of Beneficial Owners.",
        ],
        "Director and/or Company Secretary",
    ),
    (
        "ursb_form_10_return_allotment",
        "Company Form 10 — Return of Allotment of Shares (OBRS)",
        "Company Form 10",
        "Section 61, The Companies Act, Cap. 106 (Uganda)",
        "Official URSB OBRS Return of Allotment detailing newly allotted shares for cash or non-cash consideration, allottee particulars, nominal values, and paid-up amounts.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Date(s) of Allotment: " + _f("effective_date") + " · Class of Shares Allotted: " + _f("share_class") + " (Ordinary / Preference).",
            "Shares Allotted for Cash: " + _f("cash_shares_count") + " shares · Nominal Amount per Share: UGX " + _f("par_value_ugx") + " · Amount Paid / Due per Share: UGX " + _f("paid_per_share_ugx") + ".",
            "Shares Allotted Otherwise than in Cash (if any): " + _f("non_cash_details") + ".",
            "Schedule of Allottees (Full Name, Address, NIN/Passport, Number of Shares Allotted): " + _f("allottees_schedule") + ".",
        ],
        [
            "File Company Form 10 on URSB OBRS within 60 days after allotment of shares.",
            "Attach Board Resolution authorizing allotment and update BO Form 1 if ownership thresholds change.",
        ],
        "Director or Company Secretary",
    ),
    (
        "ursb_share_transfer_form",
        "Instrument of Transfer of Shares & Board Approval Resolution (OBRS)",
        "Share Transfer Form",
        "Sections 83–87, The Companies Act, Cap. 106",
        "Statutory Instrument of Transfer of Shares (Transferor to Transferee) with consideration in UGX, stamp duty declaration, and Board Resolution approving registration of transfer on OBRS.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Transferor (Seller): " + _f("transferor_name") + " (NIN/Passport: " + _f("transferor_nin") + ", Address: " + _f("transferor_address") + ").",
            "Transferee (Buyer): " + _f("transferee_name") + " (NIN/Passport: " + _f("transferee_nin") + ", Address: " + _f("transferee_address") + ").",
            "Shares Transferred & Consideration: " + _f("shares_transferred") + " Ordinary Shares (Certificate No. " + _f("old_cert_no") + ") in consideration of UGX " + _f("consideration_ugx") + ".",
            "Board Resolution Approving Transfer: Resolved that the transfer be approved, the Register of Members updated, a new Share Certificate issued, and filing lodged on URSB OBRS.",
        ],
        [
            "Pay Uganda Stamp Duty on Share Transfer via URA e-Payment before lodging on OBRS.",
            "Attach Share Transfer Form, Board Resolution, copy of Transferee ID/Passport, and updated BO Form 1.",
        ],
        "Transferor, Transferee, Witnesses & Director",
    ),
    (
        "ursb_increase_share_capital",
        "Notice & Special Resolution for Increase of Nominal Share Capital (OBRS)",
        "Form 12 / Sec. 71",
        "Sections 69–71, The Companies Act, Cap. 106",
        "Combined Special Resolution of Members and Statutory Notice to URSB increasing the Company's authorized nominal share capital in UGX, ready for URA Stamp Duty and OBRS filing.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Existing Nominal Share Capital: UGX " + _f("old_capital_ugx") + " divided into " + _f("old_shares") + " shares.",
            "Increase Amount: By UGX " + _f("increase_amount_ugx") + " through creation of " + _f("new_shares") + " new Ordinary Shares of UGX " + _f("par_value_ugx") + " each, ranking pari passu.",
            "New Total Authorized Share Capital: UGX " + _f("new_capital_ugx") + ".",
            "Special Resolution Passed on " + _f("effective_date") + ": Resolved by >=75% majority that the share capital be increased and Clause 5 of the Memorandum of Association amended accordingly.",
        ],
        [
            "File within 30 days of passing the resolution on URSB OBRS.",
            "Pay 0.5% Stamp Duty on the incremental share capital amount via URA PRN.",
        ],
        "Chairperson / Director & Company Secretary",
    ),
    (
        "ursb_share_certificate_ug",
        "Official Share Certificate under The Companies Act, Cap. 106 (Uganda)",
        "Share Certificate",
        "Section 91, The Companies Act, Cap. 106",
        "Formal statutory Share Certificate evidencing legal title to fully/partly paid shares in a Ugandan company, ready for corporate seal/stamp and dual director/secretary execution.",
        [
            "Certificate Number: " + _f("certificate_no") + " · Number of Shares: " + _f("shares_held") + " · Class: " + _f("share_class") + ".",
            "Company Name: " + _f("organization_name") + " · Incorporated under the Companies Act, Cap. 106 (URSB Reg. No.: " + _f("document_ref") + ").",
            "Registered Shareholder: THIS IS TO CERTIFY THAT " + _f("shareholder_name") + " of " + _f("shareholder_address") + " is the Registered Holder of " + _f("shares_held") + " Ordinary Shares of UGX " + _f("par_value_ugx") + " each, numbered " + _f("distinctive_numbers") + " inclusive, subject to the Memorandum and Articles of Association.",
            "Execution: Given under the Common Seal / Authorized Signatures of the Company on " + _f("effective_date") + ".",
        ],
        [
            "Issue within 60 days after allotment or registration of transfer per Section 90, Cap. 106.",
            "Affix official Company Seal / TrustSeal Cryptographic Stamp and signatures of two Directors (or Director & Secretary).",
        ],
        "Two Directors (or Director & Company Secretary)",
    ),
    (
        "ursb_register_of_members",
        "Statutory Register of Members, Shareholdings & Transfers (Section 119, Cap. 106)",
        "Register of Members",
        "Sections 119–125, The Companies Act, Cap. 106",
        "Mandatory internal statutory Register of Members kept at the Registered Office in Uganda recording member names, addresses, shares held, amounts paid, entry dates, and cessations.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + " · Registered Office: " + _f("registered_office") + ".",
            "Summary of Issued Share Capital: " + _f("total_issued_shares") + " shares of UGX " + _f("par_value_ugx") + " each (Total Paid-Up: UGX " + _f("paid_up_capital_ugx") + ").",
            "Register Entries (Folio, Member Name, NIN/Passport, Postal/Physical Address, Date Entered, Shares Acquired, Certificate No., Transfer/Cessation Date, Balance): " + _f("members_ledger_entries") + ".",
        ],
        [
            "Must be maintained continuously at the Company's Registered Office in Uganda and open to inspection per Section 122.",
            "Reconcile annually before submitting the URSB OBRS Annual Return.",
        ],
        "Company Secretary / Authorized Director",
    ),
    (
        "ursb_annual_return_shares",
        "Annual Return of a Company Having a Share Capital (OBRS Annual Filing)",
        "Annual Return (Sec. 132)",
        "Section 132 & Third Schedule, The Companies Act, Cap. 106",
        "Complete annual statutory return for a Ugandan company with share capital, reporting registered office, share capital summary, indebtedness/charges, current directors, secretary, and shareholders.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Reg. No. (BRN): " + _f("document_ref") + " · Return Made Up To Date: " + _f("return_date") + ".",
            "Registered Office & Register Location: " + _f("registered_office") + " · Official Email: " + _f("official_email") + ".",
            "Summary of Share Capital & Debentures: Authorized UGX " + _f("nominal_capital_ugx") + " · Issued " + _f("total_issued_shares") + " shares · Paid-Up UGX " + _f("paid_up_capital_ugx") + " · Total Mortgages/Charges Registered: UGX " + _f("total_charges_ugx") + ".",
            "List of Past & Present Members (Shareholders) & Share Transfers Since Last Return: " + _f("shareholders_schedule") + ".",
            "Particulars of Directors & Company Secretary at Date of Return: " + _f("directors_secretary_list") + ".",
            "Private Company Certificate (Sec. 135): Certified that the Company has not issued any invitation to the public to subscribe for shares or debentures since the last return.",
        ],
        [
            "File annually on URSB OBRS within 42 days after the Annual General Meeting (or anniversary date).",
            "Pay URSB Annual Return fee via URA PRN; late filing incurs statutory late-filing surcharges.",
        ],
        "Director AND Company Secretary",
    ),
    (
        "ursb_annual_return_no_shares",
        "Annual Return of a Company Not Having a Share Capital (Guarantee / NGO — OBRS)",
        "Annual Return (Sec. 133)",
        "Section 133, The Companies Act, Cap. 106",
        "Official URSB OBRS Annual Return for Companies Limited by Guarantee (NGOs, Associations, Foundations) reporting registered office, member count, total charges, and current Directors/Secretary.",
        [
            "Company Name: " + _f("organization_name") + " Limited (by Guarantee) · URSB Reg. No.: " + _f("document_ref") + " · Return Date: " + _f("return_date") + ".",
            "Registered Office Address: " + _f("registered_office") + ".",
            "Total Indebtedness / Registered Charges: UGX " + _f("total_charges_ugx") + " · Total Active Members: " + _f("member_count") + ".",
            "Particulars of Current Board of Directors / Trustees & Company Secretary: " + _f("directors_secretary_list") + ".",
        ],
        [
            "File annually on URSB OBRS along with Audited Financial Statements where required.",
            "Keep Beneficial Ownership / Controlling Persons register updated alongside the Annual Return.",
        ],
        "Director AND Company Secretary",
    ),
    (
        "ursb_special_resolution_filing",
        "Filing Copy of Special / Ordinary Resolution for Registration with URSB (OBRS)",
        "Resolution Filing (Sec. 150)",
        "Section 150, The Companies Act, Cap. 106 (Uganda)",
        "Certified statutory copy of a Special or Ordinary Resolution passed at a General Meeting (or written resolution) formatted for registration with URSB OBRS within 30 days.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Meeting Particulars: Passed at an Extraordinary / Annual General Meeting duly convened and held at " + _f("meeting_venue") + " on " + _f("effective_date") + " (Quorum Present: " + _f("quorum_pct") + "%).",
            "Text of Special / Ordinary Resolution: IT WAS RESOLVED THAT " + _f("resolution_text") + ".",
            "Authorization to File: IT WAS FURTHER RESOLVED THAT the Company Secretary / Authorized Director be and is hereby authorized to lodge this resolution and all requisite forms with the Registrar of Companies via URSB OBRS.",
        ],
        [
            "Must be registered with URSB within 30 days of passing per Section 150, Cap. 106.",
            "Pay URSB Resolution registration fee via URA PRN and upload signed copy on OBRS.",
        ],
        "Chairperson & Company Secretary",
    ),
    (
        "ursb_change_of_name_pack",
        "Special Resolution & Application for Change of Company Name (Section 40, OBRS)",
        "Change of Name (Sec. 40)",
        "Section 40, The Companies Act, Cap. 106",
        "Complete OBRS filing pack for changing a Ugandan company's registered name, including new name reservation reference, Special Resolution, and Registrar approval application.",
        [
            "Current Registered Company Name: " + _f("current_company_name") + " · URSB Reg. No.: " + _f("document_ref") + ".",
            "Proposed New Company Name (Reserved on OBRS): " + _f("new_company_name") + " · Name Reservation Ref: " + _f("name_reservation_ref") + ".",
            "Special Resolution: Pursuant to Section 40 of the Companies Act, Cap. 106 and subject to the approval of the Registrar of Companies, the name of the Company be and is hereby changed from " + _f("current_company_name") + " to " + _f("new_company_name") + ".",
            "Continuity of Rights & Obligations: Confirmed that the change of name shall not affect any rights, obligations, or legal proceedings of the Company.",
        ],
        [
            "Reserve the new name on URSB OBRS first before passing and filing the Special Resolution.",
            "Upon issuance of Certificate of Change of Name, update URA TIN, bank mandates, and official letterheads.",
        ],
        "Director & Company Secretary",
    ),
    (
        "ursb_conversion_company_type",
        "Special Resolution & Application for Conversion of Company Type (Private / Public / SMC)",
        "Conversion Pack (Sec. 30–34)",
        "Sections 30–34, The Companies Act, Cap. 106",
        "Formal Special Resolution and OBRS application converting a company between Private Limited, Single Member Company (SMC), and Public Limited Company (PLC) with amended Articles.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Conversion Direction: Converting from " + _f("current_company_type") + " to " + _f("target_company_type") + " effective upon issuance of Certificate of Conversion by URSB.",
            "Special Resolution: Resolved that the Company be converted pursuant to Sections 30–34 of Cap. 106, that the Company Name suffix be updated accordingly, and that the altered Memorandum & Articles of Association be adopted.",
        ],
        [
            "Attach altered Memorandum & Articles of Association, updated Form 20, and Statement in Lieu of Prospectus (if converting to Public).",
            "Lodge on URSB OBRS with conversion filing fee PRN.",
        ],
        "Chairperson, Director & Company Secretary",
    ),
    (
        "ursb_particulars_of_charge",
        "Statement of Particulars of a Mortgage, Charge or Debenture (Section 105, OBRS)",
        "Charge Filing (Sec. 105)",
        "Sections 105–112, The Companies Act, Cap. 106",
        "Official URSB OBRS filing statement for registering a corporate mortgage, debenture, or floating/fixed charge (or Memorandum of Satisfaction) within the mandatory 42-day statutory window.",
        [
            "Chargor (Company) Name: " + _f("organization_name") + " · URSB Reg. No.: " + _f("document_ref") + ".",
            "Chargee / Lender Particulars: " + _f("lender_name") + " · Address: " + _f("lender_address") + ".",
            "Date & Description of Instrument Creating Charge: " + _f("charge_instrument_desc") + " dated " + _f("effective_date") + ".",
            "Principal Amount Secured: " + _f("currency") + " " + _f("secured_amount") + " · Short Particulars of Charged Property / Assets: " + _f("charged_property_desc") + ".",
            "Board Resolution Authorizing Borrowing & Creation of Charge: Confirmed duly passed in compliance with the Company's borrowing powers under its Articles.",
        ],
        [
            "CRITICAL STATUTORY DEADLINE: Must be registered with URSB within 42 days of creation (Section 105), failing which the charge is void against a liquidator/creditor.",
            "Attach stamped Mortgage/Debenture Deed and Board Resolution on OBRS.",
        ],
        "Director / Company Secretary / Chargee Advocate",
    ),
    (
        "ursb_declaration_of_solvency",
        "Statutory Declaration of Solvency & Members' Voluntary Winding Up Resolution",
        "Solvency Declaration",
        "Section 271 Cap. 106 & Section 60, The Insolvency Act, Cap. 108",
        "Sworn Directors' Declaration of Solvency (confirming ability to pay all debts within 12 months) paired with Special Resolution for Members' Voluntary Winding Up and Liquidator appointment.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + ".",
            "Directors' Sworn Declaration: We, being a majority of the Directors of the Company, have made a full inquiry into the affairs of the Company and formed the opinion that the Company will be able to pay its debts in full within twelve (12) months from commencement of winding up.",
            "Statement of Assets & Liabilities as at " + _f("statement_date") + ": Total Realizable Assets UGX " + _f("total_assets_ugx") + " · Total Liabilities UGX " + _f("total_liabilities_ugx") + " · Estimated Surplus UGX " + _f("net_surplus_ugx") + ".",
            "Special Resolution & Liquidator Appointment: Resolved that the Company be wound up voluntarily and " + _f("liquidator_name") + " (Licensed Insolvency Practitioner) be appointed Liquidator.",
        ],
        [
            "Declaration of Solvency must be sworn before a Commissioner for Oaths within 30 days preceding the Special Resolution.",
            "File with URSB OBRS and Official Receiver, and publish statutory notice in the Uganda Gazette.",
        ],
        "Majority of Directors & Commissioner for Oaths",
    ),
    (
        "ursb_voluntary_deregistration",
        "Application for Voluntary Deregistration / Striking Off of a Dormant Company (OBRS)",
        "Deregistration (Sec. 265)",
        "Section 265, The Companies Act, Cap. 106 (Uganda)",
        "Complete OBRS application and Directors' Statutory Declaration requesting the Registrar of Companies to strike off a solvent, dormant company with no assets, liabilities, or pending litigation.",
        [
            "Company Name: " + _f("organization_name") + " · URSB Registration No.: " + _f("document_ref") + " · URA TIN: " + _f("ura_tin") + ".",
            "Special Resolution for Deregistration: Passed on " + _f("effective_date") + " resolving that the Company has ceased operations and applying to the Registrar of Companies for voluntary striking off under Section 265.",
            "Directors' Statutory Declaration of Dormancy & Nil Liabilities: Declaring that the Company has not traded for the preceding period, has no outstanding tax liabilities with URA, no unpaid creditors, no undistributed assets, and no pending legal proceedings.",
        ],
        [
            "Ensure all prior Annual Returns are up to date (or cleared) and obtain URA Tax Clearance / Deregistration confirmation.",
            "File Special Resolution, Directors' Statutory Declaration, and application on URSB OBRS.",
        ],
        "All Directors & Commissioner for Oaths",
    ),
]


def render_ursb_obrs_html(entry: dict[str, Any]) -> str:
    """Render an authentic, multi-page (3–4 page) Republic of Uganda / URSB OBRS statutory instrument."""
    title_u = _html.escape(entry["name"].upper())
    form_code = _html.escape(entry.get("ursb_form_code") or "URSB OBRS")
    stat_ref = _html.escape(entry.get("ursb_statutory_ref") or "The Companies Act, Cap. 106")
    summary = _html.escape(entry.get("summary") or "")
    provisions = entry.get("ursb_provisions") or []
    checklist = entry.get("ursb_checklist") or []
    att_role = _html.escape(entry.get("ursb_attestation_role") or "Director / Company Secretary")

    prov_html = "\n".join(f"  <li>{p}</li>" for p in provisions)
    chk_html = "\n".join(f"  <li>{_html.escape(c)}</li>" for c in checklist)

    return f"""<p style="text-align:center;font-weight:700;letter-spacing:0.08em;margin-bottom:2pt;">THE REPUBLIC OF UGANDA</p>
<p style="text-align:center;font-size:10pt;color:#334155;margin-top:0;margin-bottom:8pt;">IN THE MATTER OF {stat_ref.upper()}</p>
<h1>{title_u}</h1>
<blockquote>
  <p><strong>Statutory Registry:</strong> Uganda Registration Services Bureau (URSB) — Online Business Registration System (OBRS) &nbsp;·&nbsp; <strong>Official Instrument:</strong> {form_code}</p>
  <p><strong>Company / Entity Name:</strong> {_f('organization_name')} &nbsp;·&nbsp; <strong>URSB Reg. No. (BRN):</strong> {_f('document_ref')}</p>
  <p><strong>URA Tax Identification No. (TIN):</strong> {_f('ura_tin')} &nbsp;·&nbsp; <strong>Filing / Effective Date:</strong> {_f('effective_date')}</p>
  <p><strong>Registered Office District:</strong> {_f('district_city')}, Republic of Uganda &nbsp;·&nbsp; <strong>URA PRN Receipt No.:</strong> {_f('ura_prn')}</p>
</blockquote>

<h2>1. Statutory Authority, Purpose &amp; Legal Effect</h2>
<p>1.1 <strong>Mandate.</strong> {summary}</p>
<p>1.2 <strong>OBRS Electronic Submission.</strong> This statutory instrument is prepared for electronic lodgment with the Registrar of Companies via the <strong>URSB Online Business Registration System (OBRS)</strong> pursuant to <strong>{stat_ref}</strong>, the Electronic Transactions Act (Cap. 99), and the Electronic Signatures Act (Cap. 98) of the Laws of Uganda.</p>
<p>1.3 <strong>Legal Force.</strong> Upon acceptance and registration by the Registrar of Companies, the particulars, resolutions, and declarations contained herein shall form part of the official public corporate record of {_f('organization_name')} and bind the Company, its officers, and its members in accordance with Ugandan law.</p>

<h2>2. Statutory Particulars &amp; Operative Provisions</h2>
<ol>
{prov_html}
</ol>

<h2>3. Corporate Identity, Registered Office &amp; Presenter Particulars</h2>
<ul>
  <li><strong>Full Registered / Proposed Entity Name:</strong> {_f('organization_name')}</li>
  <li><strong>Registered Physical Office (Uganda):</strong> Plot {_f('plot_no')}, Building/Floor {_f('building_name')}, {_f('street_road')}, {_f('village_parish')}, {_f('subcounty_division')}, {_f('district_city')}, Republic of Uganda</li>
  <li><strong>Registered Postal Address &amp; Official Contacts:</strong> P.O. Box {_f('postal_address')} · Official OBRS Email: {_f('official_email')} · Telephone: {_f('official_phone')}</li>
  <li><strong>Authorized Share Capital &amp; Currency:</strong> UGX {_f('nominal_capital_ugx')} divided into {_f('total_shares')} shares of UGX {_f('par_value_ugx')} each</li>
  <li><strong>Presenter / Company Secretary / Filing Advocate:</strong> {_f('owner_name')} · Law Firm / Practice No.: {_f('presenter_firm')} · Contact: {_f('presenter_contact')}</li>
</ul>

<h2>4. Schedule of Directors, Shareholders &amp; Beneficial Owners (Cap. 106 &amp; S.I. 5/2023)</h2>
<p>4.1 <strong>Officers &amp; Members Record.</strong> The current duly appointed Directors, Company Secretary, Shareholders, and Ultimate Beneficial Owners (holding &gt;=10% equity, voting rights, or effective control) are recorded below for URSB OBRS verification:</p>
<ul>
  <li><strong>Director / Subscriber 1:</strong> Full Name: {_f('director_1_name')} · Nationality: {_f('director_1_nationality')} · NIN / Passport No.: {_f('director_1_nin')} · Residential Address: {_f('director_1_address')} · Shares / Role: {_f('director_1_shares')}</li>
  <li><strong>Director / Subscriber 2:</strong> Full Name: {_f('director_2_name')} · Nationality: {_f('director_2_nationality')} · NIN / Passport No.: {_f('director_2_nin')} · Residential Address: {_f('director_2_address')} · Shares / Role: {_f('director_2_shares')}</li>
  <li><strong>Company Secretary / Nominee Director:</strong> Full Name: {_f('secretary_name')} · Qualification / Reg. No.: {_f('secretary_reg')} · Address &amp; Contact: {_f('secretary_contact')}</li>
  <li><strong>Beneficial Ownership Compliance Attestation:</strong> The Company confirms that its internal Register of Beneficial Owners is maintained at the Registered Office in Uganda and updated on OBRS within fourteen (14) days of any change per the Companies (Beneficial Owner) Regulations, 2023 (S.I. No. 5 of 2023).</li>
</ul>

<h2>5. Accompanying Board / Members&rsquo; Resolution Authorizing Filing</h2>
<p>5.1 <strong>Duly Convened Meeting.</strong> At a duly convened meeting of the Board of Directors / General Meeting of Members of <strong>{_f('organization_name')}</strong> held at {_f('district_city')}, Uganda on {_f('effective_date')}, a quorum being present, IT WAS RESOLVED AS FOLLOWS:</p>
<ol>
  <li><strong>Approval of Instrument:</strong> THAT the contents, particulars, and statutory disclosures set out in this {form_code} be and are hereby approved and adopted in full.</li>
  <li><strong>Authorization to Execute &amp; Lodge on OBRS:</strong> THAT any Director and/or the Company Secretary ({_f('owner_name')}) be and is hereby authorized to sign, seal, pay requisite URA PRN statutory fees and stamp duty, and lodge this instrument electronically on the URSB OBRS portal.</li>
  <li><strong>Statutory Registers Update:</strong> THAT upon issuance of URSB confirmation/certificate, the Company Secretary shall immediately update the Company&rsquo;s Statutory Registers (Members, Directors, Charges, and Beneficial Owners) and archive certified copies in TrustSeal.</li>
</ol>

<h2>6. OBRS Filing, URA Payment &amp; Statutory Deadline Checklist</h2>
<ul>
{chk_html}
  <li>Verify all names and National Identification Numbers (NINs) match NIRA records (for Ugandan citizens) or valid notarized passports (for foreign nationals).</li>
  <li>Retain the URA Payment Registration Number (PRN) receipt, OBRS acknowledgment slip, and stamped URSB certified copy in the TrustSeal Evidence Vault for seven (7) years.</li>
</ul>

<h2>7. Statutory Declaration &amp; Warning Against False Statements</h2>
<p>7.1 <strong>Compliance Declaration (Statutory Declarations Act, Cap. 24).</strong> We / I hereby solemnly and sincerely declare that all information, particulars, shareholdings, identities, and supporting attachments lodged in connection with this {form_code} are true, complete, and accurate to the best of our / my knowledge and belief.</p>
<p>7.2 <strong>Statutory Notice of Offence (Section 288, Cap. 106).</strong> The signatories acknowledge that willfully making a statement false in any material particular in any return, report, certificate, or statutory form required by the Companies Act constitutes a criminal offence punishable by fine and/or imprisonment under the Laws of Uganda.</p>

<h2>8. Formal Execution, Seal &amp; Commissioner for Oaths Attestation</h2>
<p><strong>DATED</strong> at {_f('district_city')}, Republic of Uganda this {_f('effective_date')}.</p>
<p><strong>Executed by ({att_role}):</strong> {_f('signatory_name')} &nbsp;·&nbsp; NIN/Passport: {_f('signatory_nin')} &nbsp;—&nbsp; Signature: ___________________________</p>
<p><strong>Countersigned (Director / Company Secretary):</strong> {_f('second_signatory_name')} &nbsp;·&nbsp; NIN/Passport: {_f('second_signatory_nin')} &nbsp;—&nbsp; Signature: ___________________________</p>
<p><strong>SWORN / WITNESSED BEFORE ME</strong> at {_f('district_city')}, Uganda on {_f('effective_date')}:<br/>
<strong>Advocate of the High Court of Uganda / Commissioner for Oaths:</strong> {_f('witness_name')} &nbsp;—&nbsp; Signature, Practicing Seal &amp; Stamp: ___________________________</p>
""".strip()


def build_ursb_obrs_entries(start_index: int = 1081) -> list[dict[str, Any]]:
    """Build all 30 URSB & Uganda Companies Act (OBRS) catalog entries."""
    items: list[dict[str, Any]] = []
    idx = start_index - 1
    for slug_base, title, form_code, stat_ref, summary, provisions, checklist, att_role in URSB_OBRS_SPECS:
        idx += 1
        items.append({
            "slug": f"bib-{slug_base}__ug_obrs",
            "index": idx,
            "name": title,
            "title": title,
            "category": URSB_CATEGORY,
            "edition": f"Uganda OBRS · {form_code}",
            "description": f"{summary} ({stat_ref}).",
            "summary": summary,
            "focus": title,
            "edition_note": f"Aligned to {stat_ref} for URSB OBRS filing.",
            "tags": f"ursb, obrs, uganda, companies-act, cap-106, statutory, {form_code.lower()}",
            "sections": 5,
            "is_business_box": True,
            "is_ursb_obrs": True,
            "ursb_form_code": form_code,
            "ursb_statutory_ref": stat_ref,
            "ursb_provisions": provisions,
            "ursb_checklist": checklist,
            "ursb_attestation_role": att_role,
        })
    return items
