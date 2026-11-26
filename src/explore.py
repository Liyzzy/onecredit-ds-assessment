import json
from pathlib import Path

# 1. Find data/companies.jsonl starting from this file
ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "companies.jsonl"


def load_companies() -> list[dict]:
    companies = []
    with DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip(): # skip the empty lines
                companies.append(json.loads(line))
    return companies

def main() -> None:
    companies = load_companies()
    print(f"Loaded {len(companies)} companies.\n")

    not_active = []
    no_financials = []
    bad_audit = []
    negative_equity = []
    loss_making = []
    defendant_cases = []
    winding_up_petitions = []

    for c in companies:
        reg = c["registrationNumber"]
        name = c["profile"]["companyName"]
        label = f"{reg} ({name})"

        # Check company status
        status = c["profile"]["status"]
        if status != "Active":
            not_active.append(f"{label} -> {status}")

        # Check Financials (sort by year so [-1] is always the latest year)
        years = sorted(c["financials"]["years"], key=lambda y: y["financialYear"])
        if not years:
            no_financials.append(label)
        else:
            # Check audit opinions across all years
            for y in years:
                opinion = y["audit"]["opinion"]
                if opinion != "Unqualified":
                    bad_audit.append(f"{label} (FY{y['financialYear']}) -> {opinion}")
                    
            # Check latest year's equity and profit
            latest = years[-1]["statements"]
            if latest["totalEquity"] < 0:
                negative_equity.append(f"{label} -> Equity: RM {latest['totalEquity']:,}")
            if latest["profitAfterTax"] < 0:
                loss_making.append(f"{label} -> PAT: RM {latest['profitAfterTax']:,}")

        # Check Court cases
        cases = c["litigation"]["cases"]
        def_cases = [case for case in cases if case["role"] == "defendant"]
        if def_cases:
            defendant_cases.append(f"{label} -> {len(def_cases)} defendant case(s)")

        for case in def_cases:
            if case["caseType"] == "Winding-up petition":
                winding_up_petitions.append(f"{label} -> {case['caseNumber']} ({case['status']})")

    # Print results cleanly
    sections = [
        ("NOT ACTIVE", not_active),
        ("NO FINANCIALS (0 YEARS)", no_financials),
        ("NON-UNQUALIFIED AUDIT", bad_audit),
        ("NEGATIVE EQUITY (LATEST YEAR)", negative_equity),
        ("LOSS-MAKING (LATEST YEAR)", loss_making),
        ("DEFENDANT IN COURT CASES", defendant_cases),
        ("DEFENDANT IN WINDING-UP PETITION", winding_up_petitions),
    ]

    for title, items in sections:
        print(f"=== {title} ({len(items)}) ===")
        for item in items:
            print("  -", item)
        print()

if __name__ == "__main__":
    main()