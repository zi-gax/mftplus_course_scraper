from bs4 import BeautifulSoup
import requests
import pandas as pd
import json
import os
import re
from time import sleep

# ---------------- CONFIG ----------------
CSV_FILE = "mftplus_courses_async.csv"
OUTPUT_JSON = "courses_full_data.json"
LINK_COLUMN = "course_url"
LESSON_ID_REGEX = r"/lesson/(\d+)/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# ---------------- EXTRACT LESSON ID ----------------
def extract_lesson_id(url):
    match = re.search(LESSON_ID_REGEX, url)
    return match.group(1) if match else None

# ---------------- GET UNIQUE URLS ----------------
def extract_unique_urls_by_lessonid(csv_file):
    if not os.path.exists(csv_file):
        print(f"❌ File not found: {csv_file}")
        return []

    df = pd.read_csv(csv_file)

    if LINK_COLUMN not in df.columns:
        print(f"❌ Column '{LINK_COLUMN}' not found in CSV")
        return []

    unique_ids = set()
    urls = []

    for link in df[LINK_COLUMN].dropna():
        link = link.strip()
        lesson_id = extract_lesson_id(link)
        if not lesson_id:
            continue
        if lesson_id in unique_ids:
            continue

        unique_ids.add(lesson_id)
        urls.append(link)

    return urls

# ---------------- SCRAPE COURSE PAGE ----------------
def scrape_course(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")

    lesson_id = extract_lesson_id(url)

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    desc_tag = soup.select_one("div.forced-ellipsis p")
    description = desc_tag.get_text(" ", strip=True) if desc_tag else ""

    prerequisites = []
    curriculum = []
    skills_acquired = []
    career_opportunities = []

    for h2 in soup.find_all("h2"):
        text = h2.get_text(strip=True)
        ul = h2.find_next("ul", class_="custom-ul")
        if not ul:
            continue

        items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]

        if "پیش نیاز" in text:
            prerequisites = items
        elif "سرفصل" in text:
            curriculum = items
        elif "کسب توانایی" in text:
            skills_acquired = items
        elif "بازار کار" in text:
            career_opportunities = items

    return {
        "lesson_id": lesson_id,
        "title": title,
        "description": description,
        "prerequisites": prerequisites,
        "curriculum": curriculum,
        "skills_acquired": skills_acquired,
        "career_opportunities": career_opportunities,
        "url": url
    }

# ---------------- MAIN (SCRAPER) ----------------
def main():
    urls = extract_unique_urls_by_lessonid(CSV_FILE)
    print(f"🔗 {len(urls)} unique URLs found")

    results = []

    for i, url in enumerate(urls, 1):
        print(f"📘 [{i}/{len(urls)}] Scraping: {url}")
        try:
            data = scrape_course(url)
            results.append(data)
            sleep(1)
        except Exception as e:
            print(f"❌ Error scraping {url}:", e)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(results)} courses to {OUTPUT_JSON}")

# ---------------- RUN SCRAPER ----------------
if __name__ == "__main__":
    main()
    
CLEAN_OUTPUT_JSON = "courses_full_data.json"

# پاک کردن کاراکترهای نامرئی و همه یونیکدهای غیر استاندارد
INVISIBLE_CHARS = re.compile(r"[\u200e\u200f]")
UNICODE_CLEAN = re.compile(r"[^\w\s\.,;:!?()؟،\-–—'\"/]+")
MULTI_DASH = re.compile(r"-{3,}")
NOISE_REGEX = re.compile(
    r"""
    ^\s*$ |
    ادامه.* |
    ^[-–—]+$ |
    •
    """,
    re.VERBOSE
)

def normalize_string(text):
    if text is None:
        return None

    # حذف کاراکترهای نامرئی اولیه
    text = INVISIBLE_CHARS.sub("", text)
    # حذف تمام یونیکدهای غیرمعمول
    text = UNICODE_CLEAN.sub("", text)
    text = text.replace("\t", " ")
    text = MULTI_DASH.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text or NOISE_REGEX.search(text):
        return None

    return text


def clean_list(lst):
    if not lst or not isinstance(lst, list):
        return None

    cleaned = []
    for item in lst:
        item = normalize_string(item)
        if item:
            cleaned.append(item)

    return cleaned or None


def clean_object(obj):
    cleaned = {}
    for k, v in obj.items():
        if isinstance(v, list):
            v = clean_list(v)
        elif isinstance(v, str):
            v = normalize_string(v)
        cleaned[k] = v
    return cleaned


def run_cleaner():
    if not os.path.exists(OUTPUT_JSON):
        return

    with open(OUTPUT_JSON, encoding="utf-8") as f:
        data = json.load(f)

    cleaned = [clean_object(item) for item in data]

    with open(CLEAN_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print("🧹 Clean finished")

run_cleaner()