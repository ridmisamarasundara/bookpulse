import os
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://bp:bp@localhost:5432/bookpulse"
)
engine = create_engine(DATABASE_URL)

app = FastAPI(
    title="BookPulse API",
    description="Scraped books, cleaned with pandas, enriched with an LLM.",
    version="1.0",
)

# LEFT JOIN so books without an LLM insight still appear
BOOK_SELECT = """
SELECT b.book_id, b.title, b.price, b.rating, b.stock,
       c.name AS category, i.summary, i.audience, b.url
FROM books b
JOIN categories c USING (category_id)
LEFT JOIN book_insights i USING (book_id)
"""


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/books")
def list_books(
    category: str | None = None,
    audience: str | None = None,
    min_rating: int = Query(1, ge=1, le=5),
    limit: int = Query(20, ge=1, le=100),
):
    sql = BOOK_SELECT + " WHERE b.rating >= :min_rating"
    params = {"min_rating": min_rating, "limit": limit}
    if category:
        sql += " AND LOWER(c.name) = LOWER(:category)"
        params["category"] = category
    if audience:
        sql += " AND i.audience = :audience"
        params["audience"] = audience.lower()
    sql += " ORDER BY b.book_id LIMIT :limit"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@app.get("/books/{book_id}")
def get_book(book_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text(BOOK_SELECT + " WHERE b.book_id = :id"), {"id": book_id}
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return dict(row)


@app.get("/stats/categories")
def category_stats():
    sql = """
    SELECT c.name AS category,
           COUNT(*) AS book_count,
           ROUND(AVG(b.price), 2) AS avg_price,
           ROUND(AVG(b.rating), 2) AS avg_rating
    FROM books b JOIN categories c USING (category_id)
    GROUP BY c.name
    ORDER BY book_count DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


@app.get("/stats/audiences")
def audience_stats():
    sql = """
    SELECT audience, COUNT(*) AS book_count
    FROM book_insights GROUP BY audience ORDER BY book_count DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]