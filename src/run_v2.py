import json
import time 
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from extract import build_fact_sheet

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "companies.jsonl"
OUT_FILE = ROOT / "summaries" / "v2_hybrid.jsonl"

MODEL_NAME = "gemini-3.5-flash-lite"

# 15 companies covering all flag case in the dataset
SAMPLE_IDS = [
    "SYN-000545",  # Winding up + Going concern audit + 8 defendant cases
    "SYN-001212",  # Winding up + 7 defendant cases
    "SYN-000286",  # Active, BUT pending winding-up petition
    "SYN-001389",  # Active, BUT pending winding-up petition (8 cases)
    "SYN-000302",  # 0 years of financials
    "SYN-000333",  # 0 years of financials + former name
    "SYN-001203",  # 0 years of financials + corporate shareholder
    "SYN-000217",  # Disclaimer of opinion (FY2023)
    "SYN-001569",  # Disclaimer of opinion (FY2022)
    "SYN-000451",  # Negative equity + loss-making + former name
    "SYN-000067",  # Loss-making active company
    "SYN-000148",  # Loss-making active company
    "SYN-000267",  # Plaintiff-only lawsuits (NOT defendant!) + former name
    "SYN-000381",  # Healthy clean + corporate shareholder
    "SYN-000029",  # Healthy clean baseline
]

# Prompt to generate triage summary to Gemini
PROMPT = """You write short, plain-English triage summaries for a team vetting Malaysian suppliers and business partners.

STRICT RULES:
1. Keep the whole summary between 80 and 130 words. Easy to skim in 10 seconds!
2. Use ONLY the facts provided below. Do NOT invent any numbers or claims.
3. Always use RM for currency (never $ or MYR).
4. Do NOT repeat the company name, registration number, industry, or state as a title or table (the UI already displays them).
5. Use simple, everyday English — avoid heavy accounting jargon.
6. Follow this EXACT Markdown layout:

**Triage:** <exact Triage Verdict from the Fact Sheet>

**Red Flags:** <one short clear line listing all Red Flags, or "None detected.">

- **Business & People:** <1 short sentence on age, status, activity, and any watch items>
- **Money:** <1 short sentence on revenue trend, profit, equity, and audit status — or state clearly if 0 financials>
- **Court Cases:** <1 short sentence clearly separating defendant vs plaintiff cases, or "None.">

**Check next:** <1 short practical next step for the vetting team>

VERIFIED FACT SHEET:
"""

def load_companies() -> list[dict]:
    companies = []
    with DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                companies.append(json.loads(line))
    return companies

# 
def load_already_done() -> set[str]:
    """Check which companies are already saved so we don't waste API calls."""
    done = set() # why set ? because it excepts no duplicates and faster to check 
    if not OUT_FILE.exists():
        return done
    with OUT_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                done.add(row["registrationNumber"])
    return done

def main() -> None:
    load_dotenv()
    client = genai.Client()  # Initialize the Gemini client

    all_companies = load_companies()
    already_done = load_already_done()
    print(f"Already saved: {len(already_done)} companies.")

    # pick 15 samples 
    selected = []
    for c in all_companies:
        if c["registrationNumber"] in SAMPLE_IDS:
            selected.append(c)

    # Loop through and ask gemini for each missing company
    for index, company in enumerate(selected, start=1):
        reg = company["registrationNumber"]
        name = company["profile"]["companyName"]

        if reg in already_done:
            print(f"[{index}/{len(selected)}] Skipping {reg} ({name}) - already saved.")
            continue

        print(f"[{index}/{len(selected)}] Summarizing {reg} ({name})...")
        fact_sheet = build_fact_sheet(company)
        full_prompt = PROMPT + fact_sheet

        try: 
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=full_prompt,
            )
            summary_text = (response.text or "").strip()

            record = {
                "registrationNumber": reg,
                "summary": summary_text,
            }
            with OUT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(f"   Saved! ({len(summary_text.split())} words)")
            time.sleep(6)

        except Exception as err:
            print(f" FAILED for {reg}: {err}")

    print("\nDone! Refresh http://localhost:8000 to view v2_hybrid!")

if __name__ == "__main__":
    main()