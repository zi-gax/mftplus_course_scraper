import aiohttp
import asyncio
import pandas as pd
import json
import os
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
import jdatetime
import re
from pandas.errors import EmptyDataError

# ---------------- CONFIG ----------------
TEHRAN_TZ = ZoneInfo("Asia/Tehran")
API_URL = "https://mftplus.com/ajax/default/calendar?need=search"

PAGE_SIZE = 9
MAX_CONCURRENCY = 5
MAX_EMPTY_PAGES = 2

CSV_FILE = "mftplus_courses.csv"
JSON_FILE = "mftplus_courses.json"
LOG_FILE = "COURSE_LOG.md"

COLUMNS = [
    "id", "class_id", "lesson_id",
    "title", "department", "center", "teacher",
    "start_date", "end_date", "capacity", "duration_hours",
    "days", "min_price", "max_price",
    "course_url", "cover", "certificate",
    "is_active", "changed_at", "updated_at"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://mftplus.com/calendar"
}

FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
MONTHS_FA = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3,
    "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9,
    "دی": 10, "بهمن": 11, "اسفند": 12
}

# ---------------- HELPERS ----------------
def fa_to_en_func(val):
    if pd.isna(val):
        return None
    return str(val).translate(FA_TO_EN)

def normalize_price(val):
    if not val or pd.isna(val):
        return None
    val = fa_to_en_func(val).replace(",", "")
    return int(val) if val.isdigit() else None

def normalize_bool(val):
    try:
        return bool(int(val))
    except:
        return False

def normalize_jalali_date(text):
    if not text or pd.isna(text):
        return None
    text = fa_to_en_func(text)
    match = re.search(r"(\d{1,2}) (\w+) (\d{4})", text)
    if not match:
        return None
    day, month_fa, year = match.groups()
    month = MONTHS_FA.get(month_fa)
    if not month:
        return None
    jd = jdatetime.date(int(year), month, int(day))
    return jd.togregorian().isoformat() 

def normalize_updated_at(val):
    if not val or pd.isna(val):
        return None
    return str(val).split(" ")[0]  
def make_course_link(course):
    return f"https://mftplus.com/lesson/{course.get('lessonId','')}/{course.get('lessonUrl','')}?refp={quote(course.get('center',''))}"

def normalize_course(course, is_active, changed_at):
    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    return {
        "id": course["id"]["$oid"],
        "class_id": course.get("number",""),
        "lesson_id": course.get("lessonId",""),
        "title": course.get("title",""),
        "department": course.get("dep",""),
        "center": course.get("center",""),
        "teacher": None if course.get("author") in ["مشخص نشده","",None] else course.get("author"),
        "start_date": normalize_jalali_date(course.get("start")),
        "end_date": normalize_jalali_date(course.get("end")),
        "capacity": int(fa_to_en_func(course.get("capacity"))) if course.get("capacity") not in [None,""] else None,
        "duration_hours": int(fa_to_en_func(course.get("time"))) if course.get("time") not in [None,""] else None,
        "days": " | ".join(course.get("days",[])),
        "min_price": normalize_price(course.get("minCost")),
        "max_price": normalize_price(course.get("maxCost")),
        "course_url": make_course_link(course),
        "cover": course.get("cover",""),
        "certificate": course.get("cer",""),
        "is_active": normalize_bool(is_active), 
        "changed_at": changed_at,
        "updated_at": now
    }

# ---------------- LOAD EXISTING ----------------
def load_existing():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(CSV_FILE)
        return df if not df.empty else pd.DataFrame(columns=COLUMNS)
    except EmptyDataError:
        return pd.DataFrame(columns=COLUMNS)

# ---------------- SAVE ----------------
def save_all(df, new, expired, revived):

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df['is_active'] = df['is_active'].apply(lambda x: normalize_bool(x))

    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    df.to_json(JSON_FILE, force_ascii=False, indent=2)
    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    with open(LOG_FILE,"a",encoding="utf-8") as f:
        f.write(f"\n<details><summary>📊 Sync {now} 📈({len(new)}) 📉({len(expired)}) ♻️({len(revived)})</summary>\n\n")
        for title, items in [("📈 New", new),("📉 Expired", expired),("♻️ Revived", revived)]:
            if items:
                f.write(f"<details><summary>{title} ({len(items)})</summary>\n\n")
                for c in items: f.write(f"- [{c['title']}]({c['course_url']}) | {c['center']}\n")
                f.write("</details>\n")
        f.write("</details>\n")

# ---------------- FETCH ----------------
async def fetch_page(session, payload):
    async with session.post(API_URL, data=payload) as r:
        return json.loads(await r.text())

async def fetch_all(payload):
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY)
    skip, empty, data_all = 0, 0, []
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        while True:
            payload["skip"] = skip
            data = await fetch_page(session, payload)
            if not data:
                empty += 1
                if empty >= MAX_EMPTY_PAGES: break
            else:
                empty = 0
                data_all.extend(data)
                print(f"✅ skip={skip} → {len(data)}")
            skip += PAGE_SIZE
            await asyncio.sleep(0.2)
    return data_all

# ---------------- SYNC ----------------
async def sync(payload):
    existing_df = load_existing()
    now = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    existing_map = {str(r["id"]): r.to_dict() for _, r in existing_df.iterrows()}
    old_active = {k for k,v in existing_map.items() if normalize_bool(v["is_active"])}
    old_inactive = {k for k,v in existing_map.items() if not normalize_bool(v["is_active"])}

    raw = await fetch_all(payload)
    api_ids, api_courses = set(), []
    for c in raw:
        cid = c["id"]["$oid"]
        api_ids.add(cid)
        prev = existing_map.get(cid)
        changed = not prev or not normalize_bool(prev["is_active"])
        api_courses.append(normalize_course(c,1,now if changed else prev.get("changed_at", now)))

    new = [c for c in api_courses if c["id"] not in existing_map]
    revived = [c for c in api_courses if c["id"] in old_inactive]
    expired = []
    for cid in old_active - api_ids:
        row = existing_map[cid]
        row["is_active"] = False
        row["changed_at"] = now
        row["updated_at"] = now
        expired.append(row)

    final = {r["id"]:r for r in existing_map.values()}
    for c in api_courses + expired: final[c["id"]] = c
    save_all(pd.DataFrame(final.values(),columns=COLUMNS),new,expired,revived)
    print(f"✨ New: {len(new)}, ⏸️ Expired: {len(expired)}, ♻️ Revived: {len(revived)}")

# ---------------- FILTER DATA ----------------
def load_filter_data():
    with open("filterparam-data/places.json", encoding="utf-8") as f: places = json.load(f)
    with open("filterparam-data/departments.json", encoding="utf-8") as f: departments = json.load(f)
    with open("filterparam-data/groups.json", encoding="utf-8") as f: groups = json.load(f)
    with open("filterparam-data/courses.json", encoding="utf-8") as f: courses = json.load(f)
    with open("filterparam-data/months.json", encoding="utf-8") as f: months = json.load(f)
    return places, departments, groups, courses, months

def multi_select(options, label="title"):
    if not options: return []
    for i,o in enumerate(options): print(f"{i+1}. {o.get(label,'N/A')}")
    raw = input("Enter numbers (comma) or empty: ").strip()
    if not raw: return []
    idxs = [int(x.strip())-1 for x in raw.split(",") if x.strip().isdigit() and 0 <= int(x.strip())-1 < len(options)]
    return [options[i] for i in idxs]

def get_ids(items):
    return [i["id"]["$oid"] if isinstance(i.get("id"), dict) else i.get("id") for i in items]

# ---------------- MENU ----------------
async def interactive_menu():
    print("""
1️- Sync all courses (auto)
2️- Sync with filters (interactive)
0️- Exit
""")
    choice = input("Select: ").strip()
    if choice=="1":
        payload = {"term": "", "sort": "", "skip":0, "pSkip":0, "type":"all"}
        await sync(payload)
    elif choice=="2":
        places,deps,groups,courses,months = load_filter_data()
        print("\nSelect Places:"); place_ids=get_ids(multi_select(places))
        print("\nSelect Departments:"); dep_ids=get_ids(multi_select(deps))
        group_ids=[]; course_ids=[]
        if dep_ids:
            print("\nSelect Groups:"); group_ids=get_ids(multi_select([g for g in groups if g["department_id"] in dep_ids]))
        if group_ids:
            print("\nSelect Courses:"); course_ids=get_ids(multi_select([c for c in courses if c["group_id"] in group_ids]))
        print("\nSelect Months:"); month_ids=get_ids(multi_select(months))
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
        await sync(payload)
    else:
        print("👋 Bye")

# ---------------- MAIN ----------------
async def main():
    parser = argparse.ArgumentParser(description="MFTPlus course sync")
    parser.add_argument("--all", action="store_true", help="Sync all courses automatically")
    parser.add_argument("--filter", action="store_true", help="Sync with interactive filters")
    args = parser.parse_args()

    if args.all:
        payload = {"term": "", "sort": "", "skip":0, "pSkip":0, "type":"all"}
        await sync(payload)
    elif args.filter:
        await interactive_menu()
    else:
        await interactive_menu()

if __name__=="__main__":
    asyncio.run(main())