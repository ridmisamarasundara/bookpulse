import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")                 # save files without opening windows
import matplotlib.pyplot as plt
import plotly.express as px
from sqlalchemy import create_engine

engine = create_engine("postgresql+psycopg2://bp:bp@localhost:5432/bookpulse")
os.makedirs("charts", exist_ok=True)

# ---------- Load data with SQL joins ----------
books = pd.read_sql("""
    SELECT b.book_id, b.title, b.price, b.rating, b.stock,
           c.name AS category, i.audience
    FROM books b
    JOIN categories c USING (category_id)
    LEFT JOIN book_insights i USING (book_id)
""", engine)
print("Loaded", len(books), "books;", books["audience"].notna().sum(), "enriched")

# ---------- Chart 1: average price per category (top 10 categories) ----------
top = books["category"].value_counts().head(10).index
avg_price = (books[books["category"].isin(top)]
             .groupby("category")["price"].mean().sort_values())
fig, ax = plt.subplots(figsize=(9, 5))
avg_price.plot(kind="barh", ax=ax, color="#4C78A8")
ax.set_title("Average book price by category (10 largest categories)")
ax.set_xlabel("Average price (£)")
ax.set_ylabel("")
plt.tight_layout()
fig.savefig("charts/avg_price_by_category.png", dpi=150)
plt.close(fig)

# ---------- Chart 2: rating distribution ----------
ratings = books["rating"].value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
fig, ax = plt.subplots(figsize=(7, 4.5))
ax.bar(ratings.index.astype(str), ratings.values, color="#F58518")
ax.set_title("Rating distribution")
ax.set_xlabel("Star rating")
ax.set_ylabel("Number of books")
for x, y in zip(ratings.index.astype(str), ratings.values):
    ax.text(x, y, str(y), ha="center", va="bottom")
plt.tight_layout()
fig.savefig("charts/rating_distribution.png", dpi=150)
plt.close(fig)

# ---------- Chart 3: LLM audience labels ----------
aud = books["audience"].value_counts()
if len(aud):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(aud.index, aud.values, color="#54A24B")
    ax.set_title(f"Audience labels from the LLM ({aud.sum()} books)")
    ax.set_ylabel("Number of books")
    plt.tight_layout()
    fig.savefig("charts/audience_labels.png", dpi=150)
    plt.close(fig)
else:
    print("No audience data yet; run enrich.py first.")

# ---------- Chart 4 (interactive): price vs rating, saved as HTML ----------
fig = px.scatter(
    books, x="rating", y="price", color="category", hover_name="title",
    title="Price vs rating (hover for the book title)",
    labels={"rating": "Star rating", "price": "Price (£)"},
)
fig.write_html("charts/price_vs_rating.html")

print("Charts saved in the charts/ folder")