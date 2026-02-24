import aiohttp
import asyncio
import pandas as pd
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

# ---------------- Configuration ----------------
TEHRAN_TZ = ZoneInfo("Asia/Tehran")
API_URL = "https://mftplus.com/ajax/default/calendar?need=search"
PAGE_SIZE = 9
MAX_CONCURRENCY = 5
MAX_EMPTY_PAGES = 2

CSV_FILE = "mftplus_courses_filter.csv"
JSON_FILE = "mftplus_courses_filter.json"
LOG_FILE = "COURSE_LOG.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://mftplus.com/calendar"
}

# ---------------- Load JSON samples ----------------
with open("data/places.json", encoding="utf-8") as f:
    places_data = json.load(f)
with open("data/departments.json", encoding="utf-8") as f:
    departments_data = json.load(f)
with open("data/groups.json", encoding="utf-8") as f:
    groups_data = json.load(f)
with open("data/courses.json", encoding="utf-8") as f:
    courses_data = json.load(f)
with open("data/months.json", encoding="utf-8") as f:
    months_data = json.load(f)

# ---------------- Helpers ----------------
def multi_select(options, key_name="title"):
    if not options:
        return []
    print("\nSelect options (comma-separated numbers, or empty for none):")
    for i, opt in enumerate(options):
        print(f"{i+1}. {opt.get(key_name, 'N/A')}")
    raw = input("Your choice: ").strip()
    if not raw:
        return []
    idxs = []
    for s in raw.split(","):
        s = s.strip()
        if s.isdigit():
            i = int(s) - 1
            if 0 <= i < len(options):
                idxs.append(i)
    return [options[i] for i in idxs]

def get_ids(items):
    return [
        item["id"]["$oid"] if isinstance(item.get("id"), dict) else item.get("id")
        for item in items
    ]

def make_course_link(course):
    return (
        f"https://mftplus.com/lesson/"
        f"{course.get('lessonId','')}/"
        f"{course.get('lessonUrl','')}?refp={quote(course.get('center',''))}"
    )

def normalize(course, is_active, changed_at):
    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": course["id"]["$oid"],
        "title": course.get("title", ""),
        "department": course.get("dep", ""),
        "center": course.get("center", ""),
        "teacher": course.get("author", ""),
        "start_date": course.get("start", ""),
        "end_date": course.get("end", ""),
        "capacity": course.get("capacity", ""),
        "duration_hours": course.get("time", ""),
        "days": " | ".join(course.get("days", [])),
        "min_price": course.get("minCost", ""),
        "max_price": course.get("maxCost", ""),
        "course_url": make_course_link(course),
        "cover": course.get("cover", ""),
        "is_active": is_active,
        "changed_at": changed_at,
        "updated_at": now
    }

# ---------------- SAFE load_existing ----------------
def load_existing():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame()

    if os.path.getsize(CSV_FILE) == 0:
        return pd.DataFrame()

    try:
        df = pd.read_csv(CSV_FILE)
        return df if not df.empty else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

# ---------------- Save ----------------
def save_all(df, new_courses, expired_courses, revived_courses):
    if df.empty:
        df = pd.DataFrame(columns=[
            "id","title","department","center","teacher",
            "start_date","end_date","capacity","duration_hours",
            "days","min_price","max_price","course_url",
            "cover","is_active","changed_at","updated_at"
        ])

    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    df.to_json(JSON_FILE, force_ascii=False, indent=2)

    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"\n<details>\n"
            f"<summary>📊 Sync {now} "
            f"📈({len(new_courses)})|📉({len(expired_courses)})|♻️({len(revived_courses)})</summary>\n\n"
        )
        for title, items, emoji in [
            ("New courses", new_courses, "📈"),
            ("Expired courses", expired_courses, "📉"),
            ("Revived courses", revived_courses, "♻️")
        ]:
            if items:
                f.write(f"<details>\n<summary>{emoji} {title} ({len(items)})</summary>\n\n")
                for c in items:
                    f.write(f"- [{c['title']}]({c['course_url']}) | {c['center']}\n")
                f.write("</details>\n")
        f.write("</details>\n")

# ---------------- Fetch ----------------
async def fetch_page(session, payload):
    try:
        async with session.post(API_URL, data=payload) as resp:
            return json.loads(await resp.text())
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return []

async def fetch_all_courses(payload):
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY)
    courses, skip, empty = [], 0, 0

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        while True:
            payload["skip"] = skip
            data = await fetch_page(session, payload)
            if not data:
                empty += 1
                if empty >= MAX_EMPTY_PAGES:
                    break
            else:
                empty = 0
                courses.extend(data)
                print(f"✅ skip={skip} → {len(data)} courses")
            skip += PAGE_SIZE
            await asyncio.sleep(0.2)

    return courses

# ---------------- Main ----------------
async def main():
    print("Step 1 → Select Places:")
    place_ids = get_ids(multi_select(places_data))

    print("\nStep 2 → Select Departments:")
    dep_ids = get_ids(multi_select(departments_data))

    group_ids = []
    if dep_ids:
        print("\nStep 3 → Select Groups:")
        group_ids = get_ids(multi_select([g for g in groups_data if g.get("department_id") in dep_ids]))

    course_ids = []
    if group_ids:
        print("\nStep 4 → Select Courses:")
        course_ids = get_ids(multi_select([c for c in courses_data if c.get("group_id") in group_ids]))

    print("\nStep 5 → Select Months:")
    month_ids = get_ids(multi_select(months_data))

    payload = {
        "place[]": place_ids,
        "department[]": dep_ids,
        "group[]": group_ids,
        "course[]": course_ids,
        "month[]": month_ids,
        "sort": "",
        "skip": 0,
        "pSkip": 0,
        "type": "all"
    }

    existing_df = load_existing()
    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    existing_map = {
        str(row["id"]): row.to_dict()
        for _, row in existing_df.iterrows()
    }

    old_active_ids = {k for k, v in existing_map.items() if v.get("is_active") == 1}
    old_inactive_ids = {k for k, v in existing_map.items() if v.get("is_active") == 0}

    raw_courses = await fetch_all_courses(payload)
    print(f"🎯 Total fetched: {len(raw_courses)}")

    api_courses, api_ids = [], set()
    for c in raw_courses:
        cid = c["id"]["$oid"]
        api_ids.add(cid)
        prev = existing_map.get(cid)
        changed = not prev or prev["is_active"] == 0
        api_courses.append(
            normalize(c, 1, now if changed else prev.get("changed_at"))
        )

    new_courses = [c for c in api_courses if c["id"] not in existing_map]
    revived_courses = [c for c in api_courses if c["id"] in old_inactive_ids]

    expired_courses = []
    for cid in old_active_ids - api_ids:
        row = existing_map[cid]
        row["is_active"] = 0
        row["changed_at"] = now
        row["updated_at"] = now
        expired_courses.append(row)

    # -------- FINAL MERGE (DICT → NO DUPLICATES) --------
    final_map = {}
    for cid, row in existing_map.items():
        final_map[cid] = row
    for c in api_courses:
        final_map[c["id"]] = c
    for c in expired_courses:
        final_map[c["id"]] = c

    final_df = pd.DataFrame(final_map.values())

    save_all(final_df, new_courses, expired_courses, revived_courses)

    print(f"✨ New: {len(new_courses)}")
    print(f"⏸️ Expired: {len(expired_courses)}")
    print(f"♻️ Revived: {len(revived_courses)}")

if __name__ == "__main__":
    asyncio.run(main())
