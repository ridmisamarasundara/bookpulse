import os, sys, json, time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import create_engine, text

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
BATCH_SIZE = 10
SLEEP_SECONDS = 8
AUDIENCES = {"children", "teens", "adults", "general"}

client = genai.Client()
engine = create_engine("postgresql+psycopg2://bp:bp@localhost:5432/bookpulse")
CONFIG = types.GenerateContentConfig(response_mime_type="application/json", temperature=0)

class DailyQuota(Exception):
    pass

def call_model(prompt):
    for attempt in range(3):
        try:
            return client.models.generate_content(
                model=MODEL, contents=prompt, config=CONFIG).text
        except Exception as e:
            msg = str(e)
            if "PerDay" in msg or "per day" in msg.lower():
                raise DailyQuota(msg)
            if any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
                wait = 20 * (attempt + 1)
                print(f"  temporary API error, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("API retries exhausted")

def build_prompt(batch):
    items = "\n".join(f"[{bid}] {desc[:600]}" for bid, desc in batch)
    return (
        "For each book below, return ONLY a JSON array with exactly one object "
        'per book. Each object must have the keys "id" (the number in brackets, '
        'as an integer), "summary" (one sentence, maximum 25 words) and '
        '"audience" (one of: children, teens, adults, general).\n\n' + items
    )

def validate_item(o):
    summary = str(o["summary"]).strip()
    audience = str(o["audience"]).strip().lower()
    assert audience in AUDIENCES, f"bad audience: {audience}"
    assert 0 < len(summary.split()) <= 30, "summary length out of range"
    return int(o["id"]), summary, audience

def enrich_batch(batch):
    """Returns {book_id: (summary, audience)} for items that pass validation."""
    wanted = {bid for bid, _ in batch}
    raw = call_model(build_prompt(batch))
    data = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
    good = {}
    for o in data:
        try:
            bid, s, a = validate_item(o)
            if bid in wanted:
                good[bid] = (s, a)
        except Exception as e:
            print("  item failed validation:", e)
    return good

def save(good):
    with engine.begin() as conn:
        for bid, (s, a) in good.items():
            conn.execute(text(
                "INSERT INTO book_insights (book_id, summary, audience, model) "
                "VALUES (:id, :s, :a, :m) ON CONFLICT (book_id) DO NOTHING"),
                {"id": bid, "s": s, "a": a, "m": MODEL})

def report(stats):
    total = sum(stats.values())
    if not total:
        return
    passed = stats["first_try"] + stats["after_retry"]
    print("\n--- Quality report (this run) ---")
    print(f"Model: {MODEL}")
    print(f"Passed first try: {stats['first_try']}/{total}")
    print(f"Passed after retry: {stats['after_retry']}/{total}")
    print(f"Failed: {stats['failed']}/{total}")
    print(f"Pass rate: {passed / total:.0%}")

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT book_id, description FROM books
            WHERE description <> ''
              AND book_id NOT IN (SELECT book_id FROM book_insights)
            ORDER BY book_id
        """)).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} books to enrich")

    stats = {"first_try": 0, "after_retry": 0, "failed": 0}
    for start in range(0, len(rows), BATCH_SIZE):
        todo = [(r[0], r[1]) for r in rows[start:start + BATCH_SIZE]]
        print(f"Batch {start // BATCH_SIZE + 1}: {len(todo)} books")
        for attempt in (1, 2):
            try:
                good = enrich_batch(todo)
            except DailyQuota:
                print("\nDaily free quota reached. Progress is saved; rerun later.")
                report(stats)
                sys.exit(0)
            except Exception as e:
                print("  batch error:", e)
                good = {}
            save(good)
            stats["first_try" if attempt == 1 else "after_retry"] += len(good)
            todo = [t for t in todo if t[0] not in good]
            if not todo:
                break
            time.sleep(SLEEP_SECONDS)
        stats["failed"] += len(todo)
        time.sleep(SLEEP_SECONDS)

    report(stats)