from bs4 import BeautifulSoup
import requests
import pandas as pd
import json
import os
import re
from time import sleep

# ---------------- CONFIG ----------------
CSV_FILE = "../mftplus_courses.csv"
OUTPUT_JSON = "courses_full_data.json"
OUTPUT_FOLDER = "course_fields"
LINK_COLUMN = "course_url"
LESSON_ID_REGEX = r"/lesson/(\d+)/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

FIELDS = [
    "description",
    "prerequisites",
    "curriculum",
    "skills_acquired",
    "career_opportunities"
]

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

# ---------------- CLEANING ----------------
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
    text = INVISIBLE_CHARS.sub("", text)
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
    cleaned = [normalize_string(item) for item in lst if normalize_string(item)]
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

# ---------------- SAVE EACH FIELD SEPARATELY ----------------
def save_fields_separately(data, output_folder=OUTPUT_FOLDER):
    os.makedirs(output_folder, exist_ok=True)

    # create subfolders for each field
    for field in FIELDS:
        os.makedirs(os.path.join(output_folder, field), exist_ok=True)

    for course in data:
        lesson_id = course.get("lesson_id")
        if not lesson_id:
            continue
        for field in FIELDS:
            content = course.get(field)
            if content is None:
                continue
            path = os.path.join(output_folder, field, f"{lesson_id}.txt")
            # join list items if needed
            if isinstance(content, list):
                content = "\n".join(content)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    print(f"✅ Saved each field into folders under '{output_folder}'")

# ---------------- MAIN ----------------
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

    # clean data
    cleaned = [clean_object(item) for item in results]

    # save full cleaned JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(cleaned)} courses to {OUTPUT_JSON}")

    # save each field into separate folder
    save_fields_separately(cleaned)

# ---------------- RUN ----------------
if __name__ == "__main__":
    main()