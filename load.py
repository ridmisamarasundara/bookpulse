import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://bp:bp@localhost:5432/bookpulse")

DDL = """
DROP TABLE IF EXISTS book_insights;
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
  category_id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE books (
  book_id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  price NUMERIC(6,2),
  rating INT CHECK (rating BETWEEN 1 AND 5),
  stock INT,
  description TEXT,
  url TEXT UNIQUE,
  category_id INT REFERENCES categories(category_id)
);

CREATE TABLE book_insights (
  book_id INT PRIMARY KEY REFERENCES books(book_id),
  summary TEXT,
  audience TEXT,
  model TEXT,
  created_at TIMESTAMP DEFAULT now()
);
"""

# 1. Create schema
with engine.begin() as conn:
    conn.execute(text(DDL))

# 2. Read cleaned data
df = pd.read_csv("data/clean.csv")

# 3. Load categories first (the "parent" table)
cats = pd.DataFrame({"name": sorted(df["category"].unique())})
cats.to_sql("categories", engine, if_exists="append", index=False)

# 4. Map category names to IDs with a pandas merge
cat_ids = pd.read_sql("SELECT category_id, name FROM categories", engine)
books = df.merge(cat_ids, left_on="category", right_on="name", how="left")
assert books["category_id"].notna().all(), "Some books have no category_id"

# 5. Load books (the "child" table)
books = books[["title", "price", "rating", "stock", "description", "url", "category_id"]]
books.to_sql("books", engine, if_exists="append", index=False)

# 6. Verify with a JOIN
check = pd.read_sql("""
    SELECT c.name AS category, COUNT(*) AS books
    FROM books b JOIN categories c USING (category_id)
    GROUP BY c.name ORDER BY books DESC LIMIT 5
""", engine)
print(check)
print("Total books in DB:", pd.read_sql("SELECT COUNT(*) AS n FROM books", engine)["n"][0])