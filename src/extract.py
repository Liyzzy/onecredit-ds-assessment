import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "companies.jsonl"

# make the money format more readable and interpratable for api model
def format_rm(amount: float) -> str:
    """Turn a number into clean RM text, like RM 5.35M or RM -18,522."""
    if abs(amount) >= 1_000_000:
        millions = amount / 1_000_000
        return f"RM {millions:.2f}M"
    return f"RM {amount:,.0f}"

# 
def get_financial_facts(company: dict) -> dict:
    """Pull exact money trends and audit warnings using Python."""
    years = company["financials"]["years"]
    if len(years) == 0:
        return {"has_financials": False}
    
    # Check audit opinions across ALL years (not just the latest year!)
    bad_audits = []
    for y in years:
        opinion = y["audit"]["opinion"]
        if opinion != "Unqualified":
            fy = y["financialYear"]
            bad_audits.append(f"FY{fy}: {opinion}")
    first_year = years[0]
    latest_year = years[-1]
    latest_stmt = latest_year["statements"]

    # Calculate revenue % change from oldest year to latest year
    first_rev = first_year["statements"]["revenue"]
    latest_rev = latest_stmt["revenue"]
    rev_change_pct = None
    if len(years) >= 2 and first_rev > 0:
        rev_change_pct = ((latest_rev - first_rev) / first_rev) * 100

    # Grab net profit margin (stored as decimal: 0.0181 -> 1.8%)
    profit_ratios = latest_year["ratiosAndMetrics"]["profitability"]
    raw_margin = profit_ratios["netProfitMargin"]
    net_margin_pct = None
    if raw_margin is not None:
        net_margin_pct = raw_margin * 100
    return {
        "has_financials": True,
        "num_years": len(years),
        "first_fy": first_year["financialYear"],
        "latest_fy": latest_year["financialYear"],
        "first_revenue": format_rm(first_rev),
        "latest_revenue": format_rm(latest_rev),
        "rev_change_pct": rev_change_pct,
        "latest_profit": latest_stmt["profitAfterTax"],
        "latest_profit_rm": format_rm(latest_stmt["profitAfterTax"]),
        "net_margin_pct": net_margin_pct,
        "latest_equity": latest_stmt["totalEquity"],
        "latest_equity_rm": format_rm(latest_stmt["totalEquity"]),
        "bad_audits": bad_audits,
    }

def get_litigation_facts(company: dict) -> dict:
    """Separate Defendant cases (being sued) from Plaintiff cases (suing others)."""
    cases = company["litigation"]["cases"]

    defendant_total = 0         # total times being sued
    defendant_active = []       # Pending or Judgment entered
    winding_up_active = []      # Severe! Pending or Judgment winding-up petitions
    plaintiff_total = 0         # total times suing others

    for case in cases:
        role = case["role"]
        status = case["status"]
        case_type = case["caseType"]
        claim = format_rm(case["claimAmount"])
        detail = f"{case_type} ({status}, {claim})"

        if role == "defendant":
            defendant_total += 1
            if status in ("Pending", "Judgment entered"):
                defendant_active.append(detail)
                if case_type == "Winding-up petition":
                    winding_up_active.append(detail)
        elif role == "plaintiff":
            plaintiff_total += 1

    return {
        "defendant_total": defendant_total,
        "defendant_active": defendant_active,
        "winding_up_active": winding_up_active,
        "plaintiff_total": plaintiff_total,
    }
    
def assess_risk(company: dict, fin: dict, lit: dict) -> dict:
    """Assign Triage level and list all red flags using clear Python rules."""
    critical_flags = []
    caution_flags = []
    watch_items = []

    profile = company["profile"]

    # --- CRITICAL FLAGS (Instant High Risk) ---
    if profile["status"] != "Active":
        critical_flags.append(f"Company status is '{profile['status']}'")

    if len(lit["winding_up_active"]) > 0:
        for wu in lit["winding_up_active"]:
            critical_flags.append(f"Defendant in {wu}")

    if fin["has_financials"]:
        if fin["latest_equity"] < 0:
            critical_flags.append(f"Negative equity ({fin['latest_equity_rm']})")
        for audit_note in fin["bad_audits"]:
            critical_flags.append(f"Audit warning ({audit_note})")

    # --- CAUTION FLAGS (Needs Closer Check) ---
    if not fin["has_financials"]:
        caution_flags.append("No financial records available (0 years)")
    elif fin["latest_profit"] < 0:
        caution_flags.append(f"Loss-making in FY{fin['latest_fy']} (PAT {fin['latest_profit_rm']})")

    for case_note in lit["defendant_active"]:
        if "Winding-up petition" not in case_note:
            caution_flags.append(f"Active/judgment defendant case: {case_note}")

    # --- MINOR WATCH ITEMS (Good to know, doesn't block healthy companies) ---
    if len(profile["formerNames"]) > 0:
        old_name = profile["formerNames"][-1]["name"]
        watch_items.append(f"Former name: {old_name}")

    recent_dirs = 0
    for d in company["relationships"]["directors"]:
        if d["appointedOn"].startswith("2025"):
            recent_dirs += 1
    if recent_dirs > 0:
        watch_items.append(f"{recent_dirs} director(s) appointed recently in 2025")

    for s in company["relationships"]["shareholders"]:
        if s["type"] == "company":
            watch_items.append(f"Corporate shareholder: {s['name']} ({s['percentage']}%)")

    # Decide overall Triage bucket
    if len(critical_flags) > 0:
        triage = "HIGH RISK — Likely Skip"
    elif len(caution_flags) > 0:
        triage = "CAUTION — Look Closer"
    else:
        triage = "LOW RISK — Worth a Closer Look"

    return {
        "triage": triage,
        "critical_flags": critical_flags,
        "caution_flags": caution_flags,
        "watch_items": watch_items,
    }

# Build a short plain text fact sheet for gemini to summarize
def build_fact_sheet(company: dict) -> str:
    """Build a short, verified plain-text Fact Sheet for Gemini to summarize."""
    p = company["profile"]
    fin = get_financial_facts(company)
    lit = get_litigation_facts(company)
    risk = assess_risk(company, fin, lit)

    lines = []
    lines.append(f"Company: {p['companyName']} ({company['registrationNumber']})")
    lines.append(f"Profile: {p['status']} | Incorporated {p['incorporationDate']} | {p['industry']} ({p['natureOfBusiness']}) | {p['state']}")
    lines.append(f"Triage Verdict: {risk['triage']}")

    # Flags
    all_flags = risk["critical_flags"] + risk["caution_flags"]
    if len(all_flags) > 0:
        lines.append("Red Flags: " + "; ".join(all_flags))
    else:
        lines.append("Red Flags: None")

    if len(risk["watch_items"]) > 0:
        lines.append("Watch Items: " + "; ".join(risk["watch_items"]))

    # Financials line
    if not fin["has_financials"]:
        lines.append("Financials: No financial statements available (0 years).")
    else:
        rev_text = f"{fin['latest_revenue']} in FY{fin['latest_fy']}"
        if fin["rev_change_pct"] is not None:
            rev_text = f"{fin['first_revenue']} (FY{fin['first_fy']}) -> {fin['latest_revenue']} (FY{fin['latest_fy']}, {fin['rev_change_pct']:+.1f}%)"

        margin_text = ""
        if fin["net_margin_pct"] is not None:
            margin_text = f" ({fin['net_margin_pct']:.1f}% margin)"

        audit_text = "All audits clean (Unqualified)"
        if len(fin["bad_audits"]) > 0:
            audit_text = "Audit issues: " + ", ".join(fin["bad_audits"])

        lines.append(
            f"Financials ({fin['num_years']} yr): Revenue {rev_text} | "
            f"Latest Profit {fin['latest_profit_rm']}{margin_text} | "
            f"Equity {fin['latest_equity_rm']} | {audit_text}"
        )

    # Litigation line
    if lit["defendant_total"] == 0 and lit["plaintiff_total"] == 0:
        lines.append("Litigation: None")
    else:
        lit_parts = [f"Defendant (being sued): {lit['defendant_total']} total"]
        if len(lit["defendant_active"]) > 0:
            lit_parts.append("Active/Judgment against company: " + ", ".join(lit["defendant_active"]))
        if lit["plaintiff_total"] > 0:
            lit_parts.append(f"Plaintiff (company suing others — NOT a red flag by itself): {lit['plaintiff_total']} case(s)")
        lines.append("Litigation: " + " | ".join(lit_parts))

    # People line
    num_dirs = len(company["relationships"]["directors"])
    num_sh = len(company["relationships"]["shareholders"])
    lines.append(f"People: {num_dirs} director(s), {num_sh} shareholder(s)")

    return "\n".join(lines)


if __name__ == "__main__":
    test_ids = ["SYN-000029", "SYN-000286", "SYN-000451"]
    with DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                c = json.loads(line)
                if c["registrationNumber"] in test_ids:
                    print("=" * 60)
                    print(build_fact_sheet(c))