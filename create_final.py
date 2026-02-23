import pandas as pd
import json
import re

# ---------- 1. بارگذاری CSV اصلی ----------
csv_file = "mftplus_courses_async.csv"
csv_df = pd.read_csv(csv_file)

# ---------- 2. پیدا کردن ستون URL ----------
url_column = None
for col in csv_df.columns:
    if "url" in col.lower() or "link" in col.lower():
        url_column = col
        break

if url_column is None:
    raise ValueError("❌ ستون URL یا لینک در CSV پیدا نشد!")

# ---------- 3. استخراج lesson_id از URL ----------
def extract_lesson_id(url):
    match = re.search(r'/lesson/(\d+)/', str(url))
    if match:
        return match.group(1)
    return None

csv_df["lesson_id"] = csv_df[url_column].apply(extract_lesson_id)

# ---------- 4. بارگذاری JSON تکمیلی ----------
json_file = "courses_full_data.json"
with open(json_file, "r", encoding="utf-8") as f:
    json_data = json.load(f)

json_df = pd.DataFrame(json_data)

# ---------- 5. ادغام CSV و JSON ----------
columns_to_add = [col for col in json_df.columns if col != "lesson_id"]
merged_df = csv_df.merge(
    json_df[["lesson_id"] + columns_to_add],
    on="lesson_id",
    how="left"
)

# ---------- 6. حذف ستون‌های غیر ضروری ----------
columns_to_drop = []

# ستون‌های اضافی JSON
for col in merged_df.columns:
    if col.lower() == "title_y":
        columns_to_drop.append(col)
    if col.lower() == "url" and col != url_column:
        columns_to_drop.append(col)

# ستون‌های غیر ضروری CSV
for col in ["changed_at", "updated_at", "cover"]:
    if col in merged_df.columns:
        columns_to_drop.append(col)

merged_df = merged_df.drop(columns=columns_to_drop)

# ---------- 7. تغییر نام ستون title_x به title ----------
if "title_x" in merged_df.columns:
    merged_df = merged_df.rename(columns={"title_x": "title"})

# ---------- 8. ذخیره CSV خروجی ----------
output_file = "mftplus_courses_final.csv"
merged_df.to_csv(output_file, index=False, encoding="utf-8-sig")

print(f"✅ CSV نهایی ساخته شد: {output_file}")