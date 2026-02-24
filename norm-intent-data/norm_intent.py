import pandas as pd
import re

# ---------------- CONFIG ----------------
INPUT_CSV = "../mftplus_courses.csv"
OUTPUT_CSV = "courses_norm_intent.csv"

# ---------------- HELPERS ----------------
FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def fa_to_en(val):
    if pd.isna(val):
        return None
    return str(val).translate(FA_TO_EN)

def normalize_price(val):
    if not val or pd.isna(val):
        return None
    val = fa_to_en(val).replace(",", "")
    return int(val) if val.isdigit() else None

def normalize_bool(val):
    try:
        return bool(int(val))
    except:
        return False

def normalize_updated_at(val):
    if not val or pd.isna(val):
        return None
    return str(val).split(" ")[0]  

# ---------------- MAIN ----------------
df = pd.read_csv(INPUT_CSV)

COLUMNS_TO_KEEP = [
    "id","lesson_id","title", "teacher", "start_date", "end_date",
    "capacity", "duration_hours", "days",
    "min_price", "max_price","class_id","is_active",
    "updated_at" 
]

rows = []

for _, row in df.iterrows():
    new_row = {}

    for col in COLUMNS_TO_KEEP:
        if col not in row:
            new_row[col] = None
            continue

        val = row[col]

        # normalization
        if col == "teacher":
            new_row[col] = None if val in ["مشخص نشده", "", None] else val
        elif col in ["start_date", "end_date"]:
            new_row[col] = val 
        elif col == "capacity" and not pd.isna(val):
            new_row[col] = int(fa_to_en(val))
        elif col == "duration_hours" and not pd.isna(val):
            new_row[col] = int(fa_to_en(val))
        elif col == "days":
            new_row[col] = fa_to_en(val)
        elif col in ["min_price", "max_price"]:
            new_row[col] = normalize_price(val)
        elif col == "is_active":
            new_row[col] = normalize_bool(val)
        elif col == "updated_at":
            new_row[col] = normalize_updated_at(val)
        else:
            new_row[col] = val

    rows.append(new_row)

normalized_df = pd.DataFrame(rows)

# ---------------- SAVE ----------------
normalized_df.to_csv(
    OUTPUT_CSV,
    index=False,
    encoding="utf-8-sig"
)

print(f"✅ Normalized CSV saved to: {OUTPUT_CSV}")