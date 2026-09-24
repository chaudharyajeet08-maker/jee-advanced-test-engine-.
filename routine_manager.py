import os
import json
import re
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

ROUTINE_DB_PATH = "database/daily_routine.json"

TIME_PATTERNS = [
    re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)?\b"),
    re.compile(r"\b(\d{1,2})\s*(am|pm|AM|PM)\b"),
]


class ExtractedTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    time: str = Field(description="24-hour HH:MM time for the task, best guess if not explicit.")
    title: str = Field(description="Short, clear title of the task or meeting.")
    priority: str = Field(default="Medium", description="High, Medium, or Low.")


class ExtractedTaskList(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tasks: List[ExtractedTask] = Field(default_factory=list)


def _normalize_time(hour: int, minute: int, meridian: Optional[str]) -> str:
    if meridian:
        meridian = meridian.lower()
        if meridian == "pm" and hour != 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
    return f"{hour:02d}:{minute:02d}"


def parse_tasks_with_regex(raw_text: str) -> List[dict]:
    tasks = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        found_time = None
        m = TIME_PATTERNS[0].search(line)
        if m:
            hour, minute, meridian = int(m.group(1)), int(m.group(2)), m.group(3)
            found_time = _normalize_time(hour, minute, meridian)
        else:
            m = TIME_PATTERNS[1].search(line)
            if m:
                hour, meridian = int(m.group(1)), m.group(2)
                found_time = _normalize_time(hour, 0, meridian)

        title = TIME_PATTERNS[0].sub("", line)
        title = TIME_PATTERNS[1].sub("", title)
        title = re.sub(r"^[\-\*•\.\:\,\s]+|[\-\*•\.\:\,\s]+$", "", title).strip()
        if not title:
            title = line

        tasks.append({
            "time": found_time or "09:00",
            "title": title,
            "priority": "Medium",
        })
    return tasks


def parse_tasks_with_ai(raw_text: str, client, model_name: str) -> List[dict]:
    if not client:
        return parse_tasks_with_regex(raw_text)

    prompt = f"""
    You are a personal time-management assistant. Read the pasted content below (it may be an
    email, a college/exam timetable, a meeting note, or a rough to-do list) and extract a clean
    list of individual tasks/events with the time they should happen.

    RULES:
    1. If a task has no explicit time, make a sensible estimate based on context (e.g. morning
       routine items early, study blocks in study hours, meetings at their stated time).
    2. Keep titles short and actionable (max ~8 words).
    3. Times must be 24-hour HH:MM format.
    4. Assign priority as High, Medium, or Low based on urgency/importance implied in the text.

    CONTENT:
    {raw_text}
    """
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": ExtractedTaskList,
            },
        )
        data = json.loads(response.text)
        tasks = data.get("tasks", [])
        cleaned = []
        for t in tasks:
            time_val = t.get("time", "09:00")
            if not re.match(r"^\d{1,2}:\d{2}$", str(time_val)):
                time_val = "09:00"
            cleaned.append({
                "time": time_val,
                "title": t.get("title", "Untitled Task").strip(),
                "priority": t.get("priority", "Medium"),
            })
        return cleaned if cleaned else parse_tasks_with_regex(raw_text)
    except Exception:
        return parse_tasks_with_regex(raw_text)


def load_routine() -> List[dict]:
    if os.path.exists(ROUTINE_DB_PATH):
        try:
            with open(ROUTINE_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_routine(tasks: List[dict]) -> None:
    os.makedirs(os.path.dirname(ROUTINE_DB_PATH), exist_ok=True)
    with open(ROUTINE_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)


def add_tasks(date_str: str, parsed_tasks: List[dict]) -> List[dict]:
    existing = load_routine()
    for t in parsed_tasks:
        existing.append({
            "id": str(uuid.uuid4()),
            "date": date_str,
            "time": t["time"],
            "title": t["title"],
            "priority": t.get("priority", "Medium"),
            "done": False,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
    existing.sort(key=lambda x: (x["date"], x["time"]))
    save_routine(existing)
    return existing


def toggle_done(task_id: str) -> List[dict]:
    tasks = load_routine()
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = not t["done"]
    save_routine(tasks)
    return tasks


def delete_task(task_id: str) -> List[dict]:
    tasks = load_routine()
    tasks = [t for t in tasks if t["id"] != task_id]
    save_routine(tasks)
    return tasks


def tasks_for_date(date_str: str) -> List[dict]:
    return sorted(
        [t for t in load_routine() if t["date"] == date_str],
        key=lambda x: x["time"],
    )
