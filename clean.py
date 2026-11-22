import json
import pandas as pd

# ---------- EXTRACT: load raw data ----------
with open("data/raw.json", encoding="utf-8") as f:
    df = pd.DataFrame(json.load(f))

print("Raw shape:", df.shape)

# ---------- TRANSFORM ----------
# 1. Price: "£51.77" -> 51.77
df["price"] = (
    df["price"]
    .str.replace("£", "", regex=False)
    .str.replace("Â", "", regex=False)   # safety net for encoding garbage
    .astype(float)
)

# 2. Rating: "Three" -> 3
rating_map = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
df["rating"] = df["rating"].map(rating_map)

# 3. Stock: "In stock (22 available)" -> 22
df["stock"] = df["stock"].str.extract(r"(\d+)")[0].astype("Int64")

# 4. Text cleanup
df["title"] = df["title"].str.strip()
df["category"] = df["category"].str.strip()

# 5. Missing descriptions: flag them instead of silently dropping
df["has_description"] = df["description"].notna()
df["description"] = df["description"].fillna("").str.strip()

# 6. Remove duplicates (same book URL = same book)
before = len(df)
df = df.drop_duplicates(subset="url").reset_index(drop=True)
print(f"Removed {before - len(df)} duplicate rows")

# ---------- VALIDATE ----------
assert df["title"].notna().all(), "Found null titles"
assert df["url"].is_unique, "Duplicate URLs remain"
assert (df["price"] > 0).all(), "Found non-positive prices"
assert df["rating"].between(1, 5).all(), "Rating outside 1-5 (check rating_map)"
assert df["stock"].notna().all(), "Could not parse some stock values"
assert df["category"].notna().all(), "Found null categories"

print("All validation checks passed")

# ---------- LOAD to CSV ----------
df.to_csv("data/clean.csv", index=False, encoding="utf-8")

# ---------- Quick summary ----------
print("\nClean shape:", df.shape)
print(df.dtypes)
print("\nBooks per category (top 5):")
print(df["category"].value_counts().head())
print("\nBooks without description:", (~df["has_description"]).sum())