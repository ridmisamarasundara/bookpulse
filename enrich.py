import os, sys, json, time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import create_engine, text

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")  # change in .env if needed
SLEEP_SECONDS = 6            # keeps you under typical free-tier requests/minute
AUDIENCES = {"children", "teens", "adults", "general"}

client = genai.Client()      # reads GEMINI_API_KEY from the environment
engine = create_engine("postgresql+psycopg2://bp:bp@localhost:5432/bookpulse")

CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0,
)

def build_prompt(desc):
    return (
        "From this book description, return ONLY a JSON object with exactly "
        'these keys: "summary" (a single sentence, maximum 25 words) and '
        '"audience" (one of: children, teens, adults, general).\n\n'
        "Description: " + desc[:2000]
    )

def call_model(desc):
    """One API call, with backoff if we hit the free-tier rate limit."""
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=build_prompt(desc), config=CONFIG
            )
            return resp.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 30 * (attempt + 1)
                print(f"  rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("rate limit retries exhausted")

def validate(raw):
    """Quality checks. Returns a clean dict or raises."""
    out = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
    assert isinstance(out, dict), "not a JSON object"
    summary = str(out["summary"]).strip()
    audience = str(out["audience"]).strip().lower()
    assert audience in AUDIENCES, f"bad audience: {audience}"
    assert 0 < len(summary.split()) <= 30, "summary length out of range"
    return {"summary": summary, "audience": audience}

def enrich(desc):
    """Returns (result_or_None, status). One retry if validation fails."""
    for attempt in (1, 2):
        try:
            result = validate(call_model(desc))
            return result, ("first_try" if attempt == 1 else "after_retry")
        except Exception as e:
            print(f"  attempt {attempt} failed: {e}")
            time.sleep(SLEEP_SECONDS)
    return None, "failed"

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT book_id, title, description FROM books
            WHERE description <> ''
              AND book_id NOT IN (SELECT book_id FROM book_insights)
            ORDER BY book_id
        """)).fetchall()
    if limit:
        rows = rows[:limit]

    stats = {"first_try": 0, "after_retry": 0, "failed": 0}
    for i, (book_id, title, desc) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {title[:50]}")
        result, status = enrich(desc)
        stats[status] += 1
        if result:
            with engine.begin() as conn:     # saves each row immediately
                conn.execute(text(
                    "INSERT INTO book_insights (book_id, summary, audience, model) "
                    "VALUES (:id, :s, :a, :m)"),
                    {"id": book_id, "s": result["summary"],
                     "a": result["audience"], "m": MODEL})
        time.sleep(SLEEP_SECONDS)

    total = sum(stats.values())
    if total:
        passed = stats["first_try"] + stats["after_retry"]
        print("\n--- Quality report ---")
        print(f"Model: {MODEL}")
        print(f"Passed first try: {stats['first_try']}/{total}")
        print(f"Passed after retry: {stats['after_retry']}/{total}")
        print(f"Failed: {stats['failed']}/{total}")
        print(f"Overall pass rate: {passed / total:.0%}")