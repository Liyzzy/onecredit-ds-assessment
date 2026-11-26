import json
import re
from pathlib import Path

from extract import assess_risk, get_financial_facts, get_litigation_facts

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "companies.jsonl"
SUMMARIES_DIR = ROOT / "summaries"

# Load all companies into dictionary
def load_companies_by_id() -> dict[str, dict]:
    lookup = {}
    with DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                c = json.loads(line) # convert text into python dictionary
                lookup[c["registrationNumber"]] = c
    return lookup

def load_summaries(version_name: str) -> dict[str, str]:
    """Load summaries/<version_name>.jsonl into {reg_no: summary_text}."""
    path = SUMMARIES_DIR / f"{version_name}.jsonl"
    results = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                results[row["registrationNumber"]] = row["summary"]
    return results

def has_currency_bug(text: str) -> bool:
    if "$" in text:
        return True
    if re.search(r"\bMYR\b", text):
        return True
    return False

def check_critical_facts(company: dict, summary: str) -> tuple[int, int]:
    low = summary.lower()
    fin = get_financial_facts(company)
    lit = get_litigation_facts(company)

    checks = []

    if company["profile"]["status"] != "Active":
        checks.append("winding up" in low or "winding-up" in low)

    if len(lit["winding_up_active"]) > 0:
        checks.append("winding-up petition" in low or "winding up petition" in low)

    if not fin["has_financials"]:
        checks.append(
            "no financial" in low
            or "not available" in low
            or "not provided" in low
            or "unavailable" in low
        )
    else:
        if fin["latest_equity"] < 0:
            checks.append("negative equity" in low or "-18,522" in low)
        if len(fin["bad_audits"]) > 0:
            checks.append(
                "disclaimer" in low
                or "going concern" in low
                or "continue operating" in low
                or "survival" in low
            )

    caught = sum(1 for passed in checks if passed)
    return caught, len(checks)

# check if the there is a high risk warning in the first 30 words of summary generated
def warns_early(summary: str) -> bool:
    first_30 = " ".join(summary.split()[:30]).lower()
    warning_words = [
        "high risk",
        "winding up",
        "winding-up",
        "negative equity",
        "disclaimer",
        "audit warning",
        "not recommended",
        "caution",
    ]
    for word in warning_words:
        if word in first_30:
            return True
    return False

def evaluate_version(version_name: str, companies: dict[str, dict]) -> dict:
    summaries = load_summaries(version_name)
    word_counts = []
    concise_count = 0
    currency_bug_count = 0
    total_facts_caught = 0
    total_facts_expected = 0
    high_risk_total = 0
    high_risk_warned_early = 0
    structured_count = 0
    for reg, text in summaries.items():
        company = companies[reg]
        fin = get_financial_facts(company)
        lit = get_litigation_facts(company)
        risk = assess_risk(company, fin, lit)
        
        # 1. Word count
        words = len(text.split())
        word_counts.append(words)
        if 60 <= words <= 150:
            concise_count += 1

        # 2. Currency bugs ($ or MYR)
        if has_currency_bug(text):
            currency_bug_count += 1

        # 3. Critical risk recall
        caught, expected = check_critical_facts(company, text)
        total_facts_caught += caught
        total_facts_expected += expected

        # 4. Early warning for HIGH RISK companies
        if risk["triage"].startswith("HIGH RISK"):
            high_risk_total += 1
            if warns_early(text):
                high_risk_warned_early += 1

        # 5. Consistent Triage Card sections
        if "**Triage:**" in text and "**Red Flags:**" in text and "**Check next:**" in text:
            structured_count += 1

    n = len(summaries)
    return {
        "version": version_name,
        "count": n,
        "avg_words": round(sum(word_counts) / n, 1),
        "concise_pct": round((concise_count / n) * 100, 1),
        "currency_bugs": currency_bug_count,
        "fact_recall_pct": round((total_facts_caught / total_facts_expected) * 100, 1),
        "early_warn_str": f"{high_risk_warned_early}/{high_risk_total}",
        "structured_pct": round((structured_count / n) * 100, 1),
    }

def main() -> None:
    companies = load_companies_by_id()
    v1 = evaluate_version("v1_baseline", companies)
    v2 = evaluate_version("v2_hybrid", companies)
    print("\n=== V1 BASELINE vs V2 HYBRID EVALUATION ===\n")
    print(f"{'Metric':<30} | {'v1_baseline':<15} | {'v2_hybrid':<15}")
    print("-" * 66)
    print(f"{'Companies Evaluated':<30} | {v1['count']:<15} | {v2['count']:<15}")
    print(f"{'Average Word Count':<30} | {v1['avg_words']:<15} | {v2['avg_words']:<15}")
    print(f"{'Concise (60-150 words)':<30} | {str(v1['concise_pct']) + '%':<15} | {str(v2['concise_pct']) + '%':<15}")
    print(f"{'Currency Bugs ($ or MYR)':<30} | {v1['currency_bugs']:<15} | {v2['currency_bugs']:<15}")
    print(f"{'Critical Risk Recall':<30} | {str(v1['fact_recall_pct']) + '%':<15} | {str(v2['fact_recall_pct']) + '%':<15}")
    print(f"{'High-Risk Warned in 1st 30w':<30} | {v1['early_warn_str']:<15} | {v2['early_warn_str']:<15}")
    print(f"{'Consistent Card Structure':<30} | {str(v1['structured_pct']) + '%':<15} | {str(v2['structured_pct']) + '%':<15}")

if __name__ == "__main__":
    main()