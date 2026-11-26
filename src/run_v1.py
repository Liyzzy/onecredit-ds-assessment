import json
import time 
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "companies.jsonl"
OUT_FILE = ROOT / "summaries" / "v1_baseline.jsonl"

MODEL_NAME = "gemini-3.5-flash-lite"

# 15 companies covering EVERY tricky case in the dataset
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

PROMPT = """Write a short Markdown summary of this company for a team vetting potential suppliers or project partners.

Company record (JSON):
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
        full_prompt = PROMPT + json.dumps(company)

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

    print("\nDone! Refresh http://localhost:8000 to view v1_baseline!")

if __name__ == "__main__":
    main()