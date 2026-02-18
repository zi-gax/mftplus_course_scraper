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

CSV_FILE = "mftplus_courses_async.csv"
JSON_FILE = "mftplus_courses_async.json"
LOG_FILE = "COURSE_LOG.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://mftplus.com/calendar"
}

# ---------------- Stage 1: Fetch ----------------
async def fetch_page(session, skip):
    payload = {"term": "", "sort": "", "skip": skip, "pSkip": 0, "type": "all"}
    try:
        async with session.post(API_URL, data=payload) as resp:
            return json.loads(await resp.text())
    except Exception as e:
        print(f"⚠️ skip={skip} error: {e}")
        return []

async def fetch_all_courses():
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY)
    courses, skip, empty = [], 0, 0

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        while True:
            data = await fetch_page(session, skip)
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

# ---------------- Stage 2: Normalize ----------------
def make_course_link(course):
    return (
        f"https://mftplus.com/lesson/"
        f"{course.get('lessonId','')}/"
        f"{course.get('lessonUrl','')}?refp={quote(course.get('center',''))}"
    )

def normalize(course, is_active=1, changed_at=None):
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
        "changed_at": changed_at or now,
        "updated_at": now
    }

# ---------------- Stage 3: Load ----------------
def load_existing():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame()

# ---------------- Stage 4: Save ----------------
def save_all(df, new_courses, expired_courses=[], revived_courses=[]):
    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    df.to_json(JSON_FILE, force_ascii=False, indent=2)
    print("💾 CSV & JSON updated")

    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n<details>\n<summary>📊 Sync {now} 📈({len(new_courses)})|📉({len(expired_courses)})|♻️({len(revived_courses)})</summary>\n\n")
        
        if new_courses:
            f.write(f"\n<details>\n<summary> 📈 New courses ({len(new_courses)})</summary>\n\n")
            for c in new_courses:
                f.write(f"- [{c['title']}]({c['course_url']}) | {c['center']}\n")
            f.write("</details>\n")

        if expired_courses:
            f.write(f"\n<details>\n<summary> 📉 Expired courses ({len(expired_courses)})</summary>\n\n")
            for c in expired_courses:
                f.write(f"- [{c['title']}]({c['course_url']}) | {c['center']}\n")
            f.write("</details>\n")

        if revived_courses:
            f.write(f"\n<details>\n<summary> ♻️ Revived courses ({len(revived_courses)})</summary>\n\n")
            for c in revived_courses:
                f.write(f"- [{c['title']}]({c['course_url']}) | {c['center']}\n")
            f.write("</details>\n")

        f.write("</details>\n")

# ---------------- Main ----------------
async def main():
    existing_df = load_existing()
    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # existing IDs
    old_ids = set(existing_df["id"].astype(str)) if not existing_df.empty else set()
    old_active_ids = set(existing_df.loc[existing_df["is_active"] == 1, "id"].astype(str)) if not existing_df.empty else set()
    old_inactive_ids = set(existing_df.loc[existing_df["is_active"] == 0, "id"].astype(str)) if not existing_df.empty else set()

    # fetch API
    raw_courses = await fetch_all_courses()
    print(f"🎯 Total fetched: {len(raw_courses)}")

    # normalize API courses as active
    api_courses = []
    api_ids = set()
    for c in raw_courses:
        course_id = c["id"]["$oid"]
        changed_at = now if course_id not in old_ids or course_id in old_inactive_ids else None
        normalized = normalize(c, is_active=1, changed_at=changed_at)
        api_courses.append(normalized)
        api_ids.add(course_id)

    api_df = pd.DataFrame(api_courses)

    # detect new courses
    new_courses = [c for c in api_courses if c["id"] not in old_ids]

    # detect expired (was active, now missing)
    expired_courses = []
    if not existing_df.empty:
        expired_ids = old_active_ids - api_ids
        if expired_ids:
            expired_df = existing_df[existing_df["id"].astype(str).isin(expired_ids)].copy()
            expired_df["is_active"] = 0
            expired_df["changed_at"] = now
            expired_df["updated_at"] = now
            expired_courses = expired_df.to_dict("records")

    # detect revived (was inactive, now back)
    revived_courses = [c for c in api_courses if c["id"] in old_inactive_ids]

    # merge final dataset
    final_df = existing_df.copy() if not existing_df.empty else pd.DataFrame()
    # remove old active courses that are in API (we will append updated API courses)
    final_df = final_df[~final_df["id"].astype(str).isin(api_ids)]
    final_df = pd.concat([final_df, api_df], ignore_index=True)
    # append expired courses
    if expired_courses:
        final_df = pd.concat([final_df, pd.DataFrame(expired_courses)], ignore_index=True)

    save_all(final_df, new_courses, expired_courses, revived_courses)

    print(f"✨ New: {len(new_courses)}")
    print(f"⏸️ Expired: {len(expired_courses)}")
    print(f"♻️ Revived: {len(revived_courses)}")

if __name__ == "__main__":
    asyncio.run(main())
