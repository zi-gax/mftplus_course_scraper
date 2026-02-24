import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ================== Config ==================
BASE_URL = "https://mftplus.com/ajax/default/calendar"
HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0"
}
TIMEZONE = ZoneInfo("Asia/Tehran")

PATH_PLACES = "places.json"
PATH_DEPARTMENTS = "departments.json"
PATH_COURSES = "data/courses.json"
PATH_GROUPS = "data/groups.json"
PATH_MONTHS = "data/months.json"
    
# ================== Helpers ==================
def fetch_json(need: str):
    """Fetch JSON data from mftplus calendar API"""
    url = f"{BASE_URL}?need={need}"
    r = requests.post(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def normalize_list(data):
    """Ensure response is always a list"""
    if isinstance(data, dict):
        return data.get("result", [])
    if isinstance(data, list):
        return data
    raise ValueError("Unexpected response format")


def extract_id_title(item):
    """Extract MongoDB ObjectId + title safely"""
    if not isinstance(item, dict):
        raise ValueError(f"Invalid item: {item}")

    title = item.get("title")
    raw_id = item.get("id")

    if not title:
        raise ValueError(f"Missing title: {item}")

    if isinstance(raw_id, dict) and "$oid" in raw_id:
        oid = raw_id["$oid"]
    elif isinstance(raw_id, str):
        oid = raw_id
    else:
        raise ValueError(f"Unknown id format: {item}")

    return oid, title


def now_tehran():
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== Places ==================
places_raw = fetch_json("place")
save_json(PATH_PLACES, places_raw)
print(f"✔ Saved {len(places_raw)} places to {PATH_PLACES}")

# ================== Departments ==================
departments_raw = fetch_json("department")
items = normalize_list(departments_raw)
now = now_tehran()

departments = []
for item in items:
    dept_id, title = extract_id_title(item)
    departments.append({
        "id": dept_id,
        "title": title,
        "active": 1,
        "first_seen": now,
        "last_seen": now,
        "last_state_change": now
    })

save_json(PATH_DEPARTMENTS, departments)
print(f"✔ Saved {len(departments)} departments to {PATH_DEPARTMENTS}")

# ================== Months ==================

months_raw = fetch_json("month")
months = normalize_list(months_raw)

now = now_tehran()

dataset_months = []
for m in months:
    dataset_months.append({
        "id": m["id"], 
        "title": m["title"], 
        "active": 1,
        "first_seen": now,
        "last_seen": now,
        "last_state_change": now
    })

save_json(PATH_MONTHS, dataset_months)
print(f"✔ Saved {len(dataset_months)} months to {PATH_MONTHS}")

# ================== Groups ==================

def fetch_groups_by_department(department_id: str):
    url = f"{BASE_URL}?need=group"
    payload = {
        "ids[]": department_id
    }
    r = requests.post(url, headers={
        **HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_oid(item):
    raw_id = item.get("id")
    if isinstance(raw_id, dict) and "$oid" in raw_id:
        return raw_id["$oid"]
    if isinstance(raw_id, str):
        return raw_id
    raise ValueError(f"Unknown id format: {item}")

active_departments = [d for d in departments if d.get("active") == 1]

now = now_tehran()
groups = []

for dept in active_departments:
    dept_id = dept["id"]
    dept_title = dept["title"]

    print(f"▶ Fetching groups for department: {dept_title}")

    groups_raw = fetch_groups_by_department(dept_id)
    group_items = normalize_list(groups_raw)

    for g in group_items:
        group_id = extract_oid(g)

        groups.append({
            "id": group_id,
            "title": g.get("title"),
            "department_id": dept_id,
            "department_title": dept_title,
            "active": 1,
            "first_seen": now,
            "last_seen": now,
            "last_state_change": now
        })

save_json(PATH_GROUPS, groups)
print(f"✔ Saved {len(groups)} groups to {PATH_GROUPS}")

# ================== Courses ==================

def fetch_courses_by_group(group_id: str):
    url = f"{BASE_URL}?need=course"
    payload = {
        "ids[]": group_id
    }
    r = requests.post(url, headers={
        **HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()


active_groups = [g for g in groups if g.get("active") == 1]

now = now_tehran()
courses = []

for grp in active_groups:
    group_id = grp["id"]
    group_title = grp["title"]
    dept_id = grp["department_id"]
    dept_title = grp["department_title"]

    print(f"▶ Fetching courses for group: {group_title} (Department: {dept_title})")

    courses_raw = fetch_courses_by_group(group_id)
    course_items = normalize_list(courses_raw)

    for c in course_items:
        course_id = extract_oid(c)

        courses.append({
            "id": course_id,
            "title": c.get("title"),
            "group_id": group_id,
            "group_title": group_title,
            "department_id": dept_id,
            "department_title": dept_title,
            "active": 1,
            "first_seen": now,
            "last_seen": now,
            "last_state_change": now
        })

save_json(PATH_COURSES, courses)
print(f"✔ Saved {len(courses)} courses to {PATH_COURSES}")
