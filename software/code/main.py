import os
import sys
import subprocess
from arduino.app_utils import Bridge, App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_objectdetection import VideoObjectDetection
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import threading
import struct
import re
import random
import datetime
import wave
import math
import sqlite3

ui = WebUI()
ui_ready = False

audio_card = "plughw:2,0"
mic_device = "plughw:1,0"
record_process = None

# ==========================================
# API KEYS
# ==========================================
user_groq_api_key = ""
user_cartesia_api_key = ""
user_cartesia_voice_id = "2a12b36c-7f9b-4c3a-9f7a-72731b15323a"

user_weather_loc = "Hyderabad"
user_timezone = "Asia/Kolkata"
user_timezone_country = "India"
user_language = "English"
user_calendar_url = ""

google_client_id = ""
google_client_secret = ""
google_refresh_token = ""
google_access_token = None
google_token_expiry = 0

GROQ_MODEL_MAIN = "groq/compound"
GROQ_MODEL_FAST = "groq/compound-mini"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

VIDEO_STREAM_PORT = 4912

COUNTRY_CONFIG = {
    "India": {"timezone": "Asia/Kolkata", "weather": "Hyderabad"},
    "United Kingdom": {"timezone": "Europe/London", "weather": "London"},
    "United States": {"timezone": "America/New_York", "weather": "New York"},
    "Japan": {"timezone": "Asia/Tokyo", "weather": "Tokyo"},
    "United Arab Emirates": {"timezone": "Asia/Dubai", "weather": "Dubai"},
    "Australia": {"timezone": "Australia/Sydney", "weather": "Sydney"},
    "France": {"timezone": "Europe/Paris", "weather": "Paris"},
    "Singapore": {"timezone": "Asia/Singapore", "weather": "Singapore"}
}

# Kept for compatibility with older stored locations. New code uses IANA time zones.
TZ_OFFSETS = {"India": 5.5, "Hyderabad": 5.5, "London": 0, "New York": -5, "Tokyo": 9, "Sydney": 10, "Paris": 1, "Dubai": 4}

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

current_audio_process = None
cancel_speech = False
speech_lock = threading.Lock()
speaker_card_global = "2"
global_volume = "100"
global_humor = "5"

voice_mute = False
local_is_dancing = False
is_hibernating = False
enable_night_reminders = True

speaker_controls_global = []
mic_controls_global = []

is_active_listening = False
is_curie_asleep = False

# POMODORO GLOBALS
pomodoro_running = False
pomodoro_paused = False
is_break_phase = False
pomodoro_seconds_left = 0
pomodoro_total_seconds = 0
pomodoro_timer_thread = None
last_pomodoro_day = -1
pomodoro_manual_pause = False
pomodoro_continue_grace_until = 0.0
pomo_goal_score = None
last_pomo_score = None

# BREATHING EXERCISE GLOBALS
breathing_running = False
breathing_paused = False
breathing_seconds_left = 0
breathing_total_seconds = 0
breathing_timer_thread = None

# FEATURE 1: Task Breakdown State
active_task_steps = []
current_task_index = 0
start_task_pending = False

last_focus_tier_sent = -1
STREAK_MILESTONES = {3, 7, 14, 30, 60, 100, 200, 365}

# --- VISION GLOBALS ---
phone_pickup_count = 0
phone_currently_visible = False
afk_count = 0
phone_pickup_start = 0 
total_phone_time = 0 

last_person_seen_time = time.time()
last_phone_seen_time = 0
last_pickup_time = 0
raw_detected_labels = "None"

consecutive_missing = 0
consecutive_present = 0

MOVEMENT_REMINDER_SECONDS = 3600
ABSENCE_RESET_SECONDS = 120
seated_session_start = None

proactive_queue = []
proactive_queue_lock = threading.Lock()

current_mood_code = 0

# ==========================================
# SQLITE (hardened: WAL mode + timeouts)
# ==========================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")
db_lock = threading.Lock()

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with db_lock:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                        date TEXT PRIMARY KEY,
                        pomodoro_sessions INTEGER DEFAULT 0,
                        total_score INTEGER DEFAULT 0,
                        total_phone_pickups INTEGER DEFAULT 0,
                        total_afk INTEGER DEFAULT 0,
                        late_night_flag INTEGER DEFAULT 0
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS brain_dump (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, done INTEGER DEFAULT 0)''')
        c.execute("DELETE FROM chat_history")
        conn.commit()
        conn.close()

def add_memory(role, content):
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
            conn.commit()
            conn.close()
    except Exception: pass

def get_recent_memory(limit=4):
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (limit,))
            rows = c.fetchall()
            conn.close()
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
    except Exception:
        return []

def get_user_facts():
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT fact FROM user_facts")
            rows = c.fetchall()
            conn.close()
            if not rows: return ""
            facts = [row[0] for row in rows]
            return "Facts you know about the user: " + ", ".join(facts) + "."
    except Exception:
        return ""

def update_memory_ui():
    if not ui_ready: return
    facts = get_user_facts()
    if not facts:
        ui.send_message("update_memory", {"text": "No memories recorded yet."})
    else:
        clean_facts = facts.replace("Facts you know about the user: ", "")
        ui.send_message("update_memory", {"text": clean_facts})

def compress_user_facts():
    global user_groq_api_key
    if not user_groq_api_key: return
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT id, fact FROM user_facts")
            rows = c.fetchall()
            conn.close()

        if len(rows) > 5:
            facts_text = " ".join([r[1] for r in rows])
            prompt = f"Compress these explicit user facts into one short factual sentence. Output ONLY the facts, no reasoning, no preamble, no examples: {facts_text}"
            messages = [{"role": "user", "content": prompt}]
            res_data = call_groq(messages, user_groq_api_key, model=GROQ_MODEL_FAST, max_tokens=100, temperature=0.1)
            summary = _clean_memory_result(res_data["choices"][0]["message"].get("content", "").strip())

            if summary:
                with db_lock:
                    conn = get_db_conn()
                    c = conn.cursor()
                    c.execute("DELETE FROM user_facts")
                    c.execute("INSERT INTO user_facts (fact) VALUES (?)", (summary,))
                    conn.commit()
                    conn.close()
                if ui_ready: ui.send_message("system_log", {"text": "🧠 Long-Term Memory Summarized."})
                update_memory_ui()
    except Exception: pass

def _clean_memory_result(res):
    """Remove reasoning/meta leakage before anything reaches long-term memory."""
    if not res:
        return ""
    res = re.sub(r"<think>.*?</think>", "", res, flags=re.I | re.S)
    res = re.sub(r"```(?:json|text)?|```", "", res, flags=re.I).strip()
    # Reasoning models sometimes append a visible chain-of-thought after the answer.
    cut_markers = [
        "here's a thinking process", "here is a thinking process",
        "thinking process:", "analysis:", "let's analyze", "step 1:",
        "examples of facts", "task:", "task -", "output only"
    ]
    low = res.lower()
    cut = len(res)
    for marker in cut_markers:
        pos = low.find(marker)
        if pos > 0:
            cut = min(cut, pos)
    res = res[:cut].strip()
    res = re.sub(r"^[-*•\s]+", "", res).strip()
    # Keep memory concise; never store obvious prompt/meta text.
    bad = ["extract permanent facts", "the user's message", "the user message",
           "here's a", "here is a", "i should", "i need to"]
    low = res.lower()
    if any(x in low for x in bad):
        return ""
    if len(res) > 300:
        return ""
    return res

def extract_and_save_facts(user_text):
    global user_groq_api_key
    if not user_groq_api_key: return
    try:
        prompt = (
            "You are a strict long-term-memory extractor. Read the user's message below. "
            "Return ONLY permanent, user-specific facts that are explicitly stated in the message. "
            "Examples: name, birthday, long-term preference, hobby, occupation. "
            "Do NOT describe the task, your reasoning, examples, instructions, or the extraction process. "
            "Do NOT infer anything. If there are no permanent facts, output exactly NONE. "
            "Keep the answer to one short sentence.\n\nUSER MESSAGE:\n" + user_text
        )
        messages = [
            {"role": "system", "content": "Return only the memory fact(s), or NONE. Never reveal reasoning."},
            {"role": "user", "content": prompt}
        ]
        res_data = call_groq(messages, user_groq_api_key, model=GROQ_MODEL_FAST, max_tokens=80, temperature=0.0)
        res = _clean_memory_result(res_data["choices"][0]["message"].get("content", "").strip())

        if not res or res.upper() == "NONE" or "NONE" in res.upper():
            return

        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("INSERT INTO user_facts (fact) VALUES (?)", (res,))
            conn.commit()
            conn.close()
        log_event("memory_saved", {"fact": res})
        if ui_ready: ui.send_message("system_log", {"text": f"🧠 Memory Saved: {res}"})
        update_memory_ui()
        compress_user_facts()
    except Exception as e:
        log_event("memory_error", {"error": str(e)})

# ==========================================
# BRAIN DUMP FUNCTIONS
# ==========================================
def add_brain_dump(item):
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("INSERT INTO brain_dump (item) VALUES (?)", (item,))
            conn.commit()
            conn.close()
        send_braindump_sync()
    except Exception: pass

def get_brain_dumps():
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT id, item, done FROM brain_dump WHERE done = 0 ORDER BY id DESC")
            rows = c.fetchall()
            conn.close()
        return [{"id": r[0], "item": r[1], "done": bool(r[2])} for r in rows]
    except Exception: return []

def toggle_brain_dump(item_id, done):
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("UPDATE brain_dump SET done = ? WHERE id = ?", (1 if done else 0, item_id))
            conn.commit()
            conn.close()
        send_braindump_sync()
    except Exception: pass

def send_braindump_sync():
    if not ui_ready: return
    dumps = get_brain_dumps()
    ui.send_message("braindump_sync", {"items": dumps})

# ==========================================
# HABIT TRACKING
# ==========================================
def get_local_date_key(offset_days=0):
    if ZoneInfo:
        local_time = datetime.datetime.now(ZoneInfo(user_timezone)) - datetime.timedelta(days=offset_days)
    else:
        offset = TZ_OFFSETS.get(user_weather_loc, 0)
        local_time = datetime.datetime.utcnow() + datetime.timedelta(hours=offset) - datetime.timedelta(days=offset_days)
    return local_time.strftime("%Y-%m-%d")

def log_habit_pomodoro(score, pickups, afk):
    try:
        date_key = get_local_date_key()
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO daily_stats (date, pomodoro_sessions, total_score, total_phone_pickups, total_afk) "
                "VALUES (?, 1, ?, ?, ?) "
                "ON CONFLICT(date) DO UPDATE SET pomodoro_sessions=pomodoro_sessions+1, "
                "total_score=total_score+?, total_phone_pickups=total_phone_pickups+?, total_afk=total_afk+?",
                (date_key, score, pickups, afk, score, pickups, afk)
            )
            conn.commit()
            conn.close()
        update_habits_ui()
    except Exception: pass

def log_habit_late_night():
    try:
        date_key = get_local_date_key()
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO daily_stats (date, late_night_flag) VALUES (?, 1) "
                "ON CONFLICT(date) DO UPDATE SET late_night_flag=1",
                (date_key,)
            )
            conn.commit()
            conn.close()
        update_habits_ui()
    except Exception: pass

def get_recent_habits(days=7):
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute(
                "SELECT date, pomodoro_sessions, total_score, total_phone_pickups, total_afk, late_night_flag "
                "FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)
            )
            rows = c.fetchall()
            conn.close()
        return rows
    except Exception:
        return []

# ==========================================
# STREAK TRACKING
# ==========================================
def get_today_session_count():
    try:
        date_key = get_local_date_key()
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT pomodoro_sessions FROM daily_stats WHERE date = ?", (date_key,))
            row = c.fetchone()
            conn.close()
        return row[0] if row else 0
    except Exception:
        return 0

def get_all_session_dates():
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT date FROM daily_stats WHERE pomodoro_sessions > 0 ORDER BY date ASC")
            rows = c.fetchall()
            conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []

def compute_streak_info():
    dates = get_all_session_dates()
    if not dates:
        return {"current": 0, "best": 0, "at_risk": False, "today_done": False}

    date_set = set(dates)
    today_key = get_local_date_key(0)
    yesterday_key = get_local_date_key(1)
    day_before_yesterday_key = get_local_date_key(2)
    today_done = today_key in date_set

    date_objs = sorted([datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in dates])
    best = 1
    run = 1
    for i in range(1, len(date_objs)):
        days_diff = (date_objs[i] - date_objs[i - 1]).days
        if days_diff == 1 or days_diff == 2: 
            if days_diff == 1:
                run += 1
        else:
            run = 1
        best = max(best, run)

    current = 0
    cursor_date = datetime.datetime.strptime(today_key, "%Y-%m-%d").date()
    
    if today_done:
        start_date = cursor_date
    elif yesterday_key in date_set:
        start_date = cursor_date - datetime.timedelta(days=1)
    elif day_before_yesterday_key in date_set:
        start_date = cursor_date - datetime.timedelta(days=2)
    else:
        start_date = None
        
    if start_date:
        while start_date.strftime("%Y-%m-%d") in date_set or (start_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d") in date_set:
            if start_date.strftime("%Y-%m-%d") in date_set:
                current += 1
            start_date -= datetime.timedelta(days=1)

    at_risk = (not today_done) and current > 0
    return {"current": current, "best": max(best, current), "at_risk": at_risk, "today_done": today_done}

def push_streak_update():
    info = compute_streak_info()
    last7 = []
    for i in range(6, -1, -1):
        d = get_local_date_key(i)
        try:
            with db_lock:
                conn = get_db_conn()
                c = conn.cursor()
                c.execute("SELECT pomodoro_sessions FROM daily_stats WHERE date = ?", (d,))
                row = c.fetchone()
                conn.close()
            done = bool(row and row[0] > 0)
        except Exception:
            done = False
        last7.append({"date": d, "done": done, "is_today": (i == 0)})
    info["last7"] = last7

    Bridge.notify("update_streak", info["current"])
    if ui_ready:
        ui.send_message("streak_sync", info)
    return info

def maybe_celebrate_streak_milestone(streak_count):
    if streak_count not in STREAK_MILESTONES:
        return
    Bridge.notify("celebrate", 1)
    fallback = f"[HAPPY] {streak_count} days in a row now — that's a real streak. Nice and steady."
    if not user_groq_api_key:
        queue_proactive_message(fallback)
        return
    try:
        prompt = (
            f"The user just hit a {streak_count}-day focus streak. Write ONE short, warm, matter-of-fact sentence celebrating it — "
            "no hype, no exclamation overload. Start with [HAPPY]. Respond in {user_language} (keep the tag in English)."
        )
        res_data = call_groq([{"role": "user", "content": prompt}], user_groq_api_key,
                              model=GROQ_MODEL_FAST, max_tokens=60, temperature=0.7)
        msg = res_data["choices"][0]["message"].get("content", "").strip()
        queue_proactive_message(msg if msg else fallback)
    except Exception:
        queue_proactive_message(fallback)

def update_habits_ui():
    if not ui_ready: return
    rows = get_recent_habits(7)
    lines = []
    for date, sessions, total_score, pickups, afk, late in rows:
        avg = round(total_score / sessions) if sessions else 0
        line = f"{date} — {sessions} sessions, {avg}% avg, {pickups} pickups, {afk} AFKs"
        if late: line += " 🌙 late night"
        lines.append(line)
    ui.send_message("habits_sync", {"lines": lines})
    push_streak_update()

def build_weekly_summary_text():
    global user_language
    rows = get_recent_habits(7)
    if not rows:
        return "[DEFAULT] I don't have enough data yet this week to give you a useful recap. Let's log a few more focus sessions first."

    # rows are newest -> oldest. Give the LLM already-computed trends instead of a raw data dump.
    ordered = list(reversed(rows))
    total_sessions = sum(r[1] for r in ordered)
    total_score = sum(r[2] for r in ordered)
    total_pickups = sum(r[3] for r in ordered)
    total_afk = sum(r[4] for r in ordered)
    late_days = sum(1 for r in ordered if r[5])
    overall_avg = round(total_score / total_sessions) if total_sessions else 0

    midpoint = max(1, len(ordered) // 2)
    early = ordered[:midpoint]
    recent = ordered[midpoint:]
    early_sessions = sum(r[1] for r in early)
    recent_sessions = sum(r[1] for r in recent)
    early_avg = round(sum(r[2] for r in early) / early_sessions) if early_sessions else overall_avg
    recent_avg = round(sum(r[2] for r in recent) / recent_sessions) if recent_sessions else overall_avg
    early_pickups = sum(r[3] for r in early)
    recent_pickups = sum(r[3] for r in recent)

    score_delta = recent_avg - early_avg
    pickup_delta = recent_pickups - early_pickups
    if score_delta >= 5:
        trend = f"Focus scores improved from about {early_avg}% earlier in the week to about {recent_avg}% recently."
    elif score_delta <= -5:
        trend = f"Focus scores slipped from about {early_avg}% earlier in the week to about {recent_avg}% recently."
    elif pickup_delta <= -2:
        trend = "Phone pickups decreased toward the end of the week, which suggests distractions were getting easier to manage."
    elif pickup_delta >= 2:
        trend = "Phone pickups increased toward the end of the week, so reducing easy phone access could help."
    else:
        trend = f"Focus was fairly steady at about {overall_avg}% across {total_sessions} sessions."

    streak_info = compute_streak_info()
    goal = min(100, max(80, recent_avg + 5))
    raw_data = (
        f"Overall average focus score: {overall_avg}%. Total sessions: {total_sessions}. "
        f"Phone pickups: {total_pickups}. Times away: {total_afk}. Late nights: {late_days}. "
        f"Current streak: {streak_info['current']} days; best streak: {streak_info['best']} days. "
        f"Computed trend: {trend} Next-session goal: beat {goal}%."
    )

    if not user_groq_api_key:
        return f"[DEFAULT] {trend} You logged {total_sessions} focus sessions this week at an average of {overall_avg}%. "
        f"For the next session, aim to beat {goal}%."

    prompt = (
        f"{raw_data}\n\n"
        "Turn this into a useful spoken weekly recap in 3-4 natural sentences. "
        "Do NOT list dates or repeat every metric. Mention the main trend, one useful observation, "
        "and one concrete next-session goal. Say 'average', never 'avg' or 'AVG'. "
        "Do not spell out symbols, abbreviations, or punctuation. "
        "Start with exactly one mood tag: [HAPPY], [DEFAULT], or [SAD]. "
        f"Respond in {user_language}."
    )
    messages = [
        {"role": "system", "content":
         "You are Curie. Give concise, useful spoken coaching from already-computed weekly data. "
         "Never dump raw data back to the user and never reveal reasoning."},
        {"role": "user", "content": prompt}
    ]
    try:
        res_data = call_groq(messages, user_groq_api_key, model=GROQ_MODEL_MAIN, max_tokens=140, temperature=0.4)
        text = res_data["choices"][0]["message"].get("content", "").strip()
        text = _clean_memory_result(text) if "thinking process" in text.lower() else text
        return text if text else f"[DEFAULT] {trend} Your average was {overall_avg}%. For the next session, aim to beat {goal}%."
    except Exception as e:
        log_event("weekly_summary_error", {"error": str(e)})
        return f"[DEFAULT] {trend} Your average was {overall_avg}%. For the next session, aim to beat {goal}%."

def prepare_weekly_summary():
    queue_proactive_message(build_weekly_summary_text())

def trigger_weekly_summary():
    threading.Thread(target=prepare_weekly_summary, daemon=True).start()

def weekly_summary_loop():
    last_sent_week = -1
    while True:
        time.sleep(300)
        try:
            offset = TZ_OFFSETS.get(user_weather_loc, 0)
            local_time = datetime.datetime.utcnow() + datetime.timedelta(hours=offset)
            iso_week = local_time.isocalendar()[1]
            if local_time.weekday() == 6 and local_time.hour == 18 and iso_week != last_sent_week:
                last_sent_week = iso_week
                trigger_weekly_summary()
        except Exception:
            pass

# ==========================================
# GOOGLE CALENDAR (real OAuth API, with iCal fallback)
# ==========================================
def get_google_access_token():
    global google_access_token, google_token_expiry
    if google_access_token and time.time() < google_token_expiry - 60:
        return google_access_token
    if not (google_client_id and google_client_secret and google_refresh_token):
        return None
    try:
        data = urllib.parse.urlencode({
            "client_id": google_client_id,
            "client_secret": google_client_secret,
            "refresh_token": google_refresh_token,
            "grant_type": "refresh_token"
        }).encode('utf-8')
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode('utf-8'))
            google_access_token = res["access_token"]
            google_token_expiry = time.time() + res.get("expires_in", 3600)
            return google_access_token
    except Exception as e:
        if ui_ready: ui.send_message("system_log", {"text": f"❌ Google token refresh failed: {e}"})
        return None

def get_calendar_events():
    global user_calendar_url, google_client_id, google_client_secret, google_refresh_token
    if google_client_id and google_client_secret and google_refresh_token:
        token = get_google_access_token()
        if token:
            try:
                now_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                url = ("https://www.googleapis.com/calendar/v3/calendars/primary/events?"
                       f"timeMin={urllib.parse.quote(now_iso)}&maxResults=5&singleEvents=true&orderBy=startTime")
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    events = []
                    for item in data.get("items", []):
                        summary = item.get("summary", "Untitled event")
                        start = item.get("start", {})
                        start_str = start.get("dateTime", start.get("date", ""))
                        events.append(f"{summary} ({start_str})")
                    return ("Upcoming Calendar Events: " + ", ".join(events[:3])) if events else ""
            except Exception as e:
                if ui_ready: ui.send_message("system_log", {"text": f"⚠️ Google Calendar API failed ({e}), falling back to iCal if set."})

    if not user_calendar_url or "http" not in user_calendar_url:
        return ""
    try:
        req = urllib.request.Request(user_calendar_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            events = []
            now_int = int(datetime.datetime.utcnow().strftime("%Y%m%d"))
            blocks = data.split("BEGIN:VEVENT")
            for block in blocks[1:]:
                if "SUMMARY:" in block and "DTSTART" in block:
                    summary_match = re.search(r'SUMMARY:(.*?)\n', block)
                    dtstart_match = re.search(r'DTSTART.*?:(\d{8})(T\d{6})?', block)
                    if summary_match and dtstart_match:
                        summary = summary_match.group(1).strip()
                        date_str = dtstart_match.group(1)
                        time_str = dtstart_match.group(2)
                        event_date_int = int(date_str)
                        if event_date_int >= now_int:
                            yr, mo, da = date_str[0:4], date_str[4:6], date_str[6:8]
                            nice_time = ""
                            if time_str:
                                hr, mn = time_str[1:3], time_str[3:5]
                                nice_time = f" at {hr}:{mn}"
                            events.append((event_date_int, f"{summary} (On {yr}-{mo}-{da}{nice_time})"))
            events.sort(key=lambda x: x[0])
            upcoming = [e[1] for e in events[:3]]
            return ("Upcoming Calendar Events: " + ", ".join(upcoming)) if upcoming else ""
    except Exception:
        return ""

def get_today_events():
    global google_client_id, google_client_secret, google_refresh_token, user_calendar_url, user_weather_loc
    if ZoneInfo:
        now_local = datetime.datetime.now(ZoneInfo(user_timezone))
        offset = now_local.utcoffset().total_seconds() / 3600.0
    else:
        offset = TZ_OFFSETS.get(user_weather_loc, 0)
        now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=offset)
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_local = day_start_local + datetime.timedelta(days=1)
    day_start_utc = day_start_local - datetime.timedelta(hours=offset)
    day_end_utc = day_end_local - datetime.timedelta(hours=offset)

    if google_client_id and google_client_secret and google_refresh_token:
        token = get_google_access_token()
        if token:
            try:
                tmin = day_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                tmax = day_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                url = ("https://www.googleapis.com/calendar/v3/calendars/primary/events?"
                       f"timeMin={urllib.parse.quote(tmin)}&timeMax={urllib.parse.quote(tmax)}&singleEvents=true&orderBy=startTime")
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    events = []
                    for item in data.get("items", []):
                        raw_summary = item.get("summary", "Untitled event").strip()
                        done = raw_summary.startswith("✅")
                        display_summary = raw_summary[1:].strip() if done else raw_summary
                        start = item.get("start", {})
                        start_str = start.get("dateTime", start.get("date", ""))
                        time_disp = "All day"
                        if "T" in start_str:
                            try:
                                dt = datetime.datetime.strptime(start_str[:19], "%Y-%m-%dT%H:%M:%S")
                                time_disp = dt.strftime("%I:%M %p").lstrip("0")
                            except Exception:
                                pass
                        events.append({"summary": display_summary, "time": time_disp, "id": item.get("id", ""), "done": done})
                    return events
            except Exception as e:
                if ui_ready: ui.send_message("system_log", {"text": f"⚠️ Today's calendar fetch failed: {e}"})

    if not user_calendar_url or "http" not in user_calendar_url:
        return []
    try:
        req = urllib.request.Request(user_calendar_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            events = []
            today_int = int(day_start_local.strftime("%Y%m%d"))
            blocks = data.split("BEGIN:VEVENT")
            for block in blocks[1:]:
                if "SUMMARY:" in block and "DTSTART" in block:
                    summary_match = re.search(r'SUMMARY:(.*?)\n', block)
                    dtstart_match = re.search(r'DTSTART.*?:(\d{8})(T\d{6})?', block)
                    if summary_match and dtstart_match:
                        summary = summary_match.group(1).strip()
                        date_str = dtstart_match.group(1)
                        time_str = dtstart_match.group(2)
                        if int(date_str) == today_int:
                            time_disp = "All day"
                            if time_str:
                                hr, mn = time_str[1:3], time_str[3:5]
                                time_disp = f"{hr}:{mn}"
                            events.append({"summary": summary, "time": time_disp, "id": "", "done": False})
            return events
    except Exception:
        return []

def toggle_calendar_task(event_id, mark_done):
    global google_client_id, google_client_secret, google_refresh_token
    if not event_id or not (google_client_id and google_client_secret and google_refresh_token):
        return False
    token = get_google_access_token()
    if not token:
        return False
    try:
        url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{urllib.parse.quote(event_id)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=8) as response:
            event = json.loads(response.read().decode('utf-8'))
        summary = event.get("summary", "").strip()
        is_done = summary.startswith("✅")
        if mark_done and not is_done:
            new_summary = "✅ " + summary
        elif not mark_done and is_done:
            new_summary = summary[1:].strip()
        else:
            new_summary = summary
        patch_req = urllib.request.Request(
            url, data=json.dumps({"summary": new_summary}).encode('utf-8'),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="PATCH"
        )
        with urllib.request.urlopen(patch_req, timeout=8) as response2:
            json.loads(response2.read().decode('utf-8'))
        send_calendar_sync()
        return True
    except Exception as e:
        if ui_ready: ui.send_message("system_log", {"text": f"❌ Task toggle failed: {e}"})
        return False

def send_calendar_sync():
    if not ui_ready: return
    events = get_today_events()
    ui.send_message("calendar_sync", {"events": events})
    if events:
        ui.send_message("system_log", {"text": f"📅 Calendar synced: {len(events)} event(s) today."})
    else:
        ui.send_message("system_log", {"text": "📅 Calendar synced: no events found for today."})

def calendar_sync_loop():
    while True:
        time.sleep(300)
        send_calendar_sync()

def add_calendar_reminder(text):
    global google_client_id, google_client_secret, google_refresh_token
    if not (google_client_id and google_client_secret and google_refresh_token):
        if ui_ready: ui.send_message("system_log", {"text": "⚠️ Reminder not saved: Google Calendar not configured."})
        return False
    token = get_google_access_token()
    if not token:
        if ui_ready: ui.send_message("system_log", {"text": "⚠️ Reminder not saved: Google auth failed."})
        return False
    try:
        url = ("https://www.googleapis.com/calendar/v3/calendars/primary/events/quickAdd?"
               f"text={urllib.parse.quote(text)}")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as response:
            json.loads(response.read().decode('utf-8'))
        if ui_ready: ui.send_message("system_log", {"text": f"📅 Reminder added: {text}"})
        send_calendar_sync()
        return True
    except Exception as e:
        if ui_ready: ui.send_message("system_log", {"text": f"❌ Reminder creation failed: {e}"})
        return False

# ==========================================
# TIMEZONE HELPER
# ==========================================
def get_local_time(location=None):
    if ZoneInfo:
        local_time = datetime.datetime.now(ZoneInfo(user_timezone))
    else:
        offset = TZ_OFFSETS.get(location or user_weather_loc, 0)
        local_time = datetime.datetime.utcnow() + datetime.timedelta(hours=offset)
    return local_time.strftime("%I:%M %p"), local_time.strftime("%A, %B %d"), local_time.hour

# ==========================================
# 8-BIT CHIME GENERATOR
# ==========================================
def generate_and_play_chime(tier):
    try:
        sample_rate = 16000
        file_path = f"/tmp/chime_{tier}.wav"

        with wave.open(file_path, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            audio_data = bytearray()

            def add_tone(freq, duration_sec):
                frames = int(sample_rate * duration_sec)
                for i in range(frames):
                    t = float(i) / sample_rate
                    envelope = 1.0 - (i / frames)
                    val = int(32767.0 * 0.3 * envelope * math.sin(2.0 * math.pi * freq * t))
                    audio_data.extend(struct.pack("<h", val))

            if tier == "boot":
                # Soft rising three-note startup/wake chime.
                add_tone(392.00, 0.14)
                add_tone(523.25, 0.14)
                add_tone(659.25, 0.18)
                add_tone(783.99, 0.32)
            elif tier == "good":
                add_tone(523.25, 0.15); add_tone(659.25, 0.15); add_tone(783.99, 0.15)
                add_tone(1046.50, 0.4); add_tone(783.99, 0.15); add_tone(1046.50, 0.6)
            elif tier == "mid":
                add_tone(523.25, 0.2); add_tone(659.25, 0.2); add_tone(523.25, 0.4)
            elif tier == "notification":
                add_tone(587.33, 0.12); add_tone(0, 0.03); add_tone(880.00, 0.3)
            else:
                add_tone(659.25, 0.3); add_tone(622.25, 0.3); add_tone(587.33, 0.3); add_tone(523.25, 0.6)

            boosted_data = amplify_pcm_volume(bytes(audio_data), 8.0)
            wav_file.writeframes(boosted_data)

        unmute_speaker()
        result = subprocess.run(["aplay", "-D", audio_card, file_path], capture_output=True, text=True)
        mute_speaker()
        if result.returncode != 0:
            raise RuntimeError(f"aplay chime failed ({result.returncode}): {result.stderr.strip()}")
        log_event("chime_played", {"tier": tier})
    except Exception as e:
        log_event("chime_error", {"tier": tier, "error": str(e)})
        if ui_ready:
            ui.send_message("system_log", {"text": f"❌ Chime playback failed: {e}"})

# ==========================================
# WEATHER API
# ==========================================
def get_weather(location):
    try:
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            condition = data['current_condition'][0]['weatherDesc'][0]['value']
            temp = data['current_condition'][0]['temp_C']
            return f"The weather in {location} is currently {condition} and {temp} degrees Celsius."
    except Exception:
        return "I couldn't fetch the weather right now."

# ==========================================
# EVENT LOGGER
# ==========================================
def log_event(event_type, details):
    try:
        log_path = "/home/arduino/ArduinoApps/curie/session_logs.json"
        entry = {"timestamp": datetime.datetime.now().isoformat(), "event": event_type, "details": details}
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception: pass

# ==========================================
# HARDWARE INITIALIZATION
# ==========================================
def hardware_setup_and_parser():
    global audio_card, mic_device, speaker_card_global, speaker_controls_global, mic_controls_global
    logs = ["Initializing Hardware Dependencies..."]
    speaker_card_num = "2"
    mic_card_num = "1"

    try:
        p_res = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
        for line in p_res.stdout.split('\n'):
            if "card" in line.lower() and ("ab13x" in line.lower() or "usb" in line.lower() or "audio" in line.lower()):
                match = re.search(r'card (\d+):', line)
                if match: 
                    speaker_card_num = match.group(1)
                    break

        c_res = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
        for line in c_res.stdout.split('\n'):
            if "card" in line.lower() and ("camera" in line.lower() or "usb" in line.lower() or "audio" in line.lower()):
                match = re.search(r'card (\d+):', line)
                if match: 
                    mic_card_num = match.group(1)
                    break

        audio_card = f"plughw:{speaker_card_num},0"
        mic_device = f"plughw:{mic_card_num},0"
        speaker_card_global = speaker_card_num
        logs.append(f"Speaker assigned to Card {speaker_card_num}")
        logs.append(f"Mic assigned to Card {mic_card_num}")

        s_ctrl_res = subprocess.run(["amixer", "-c", speaker_card_num, "scontrols"], capture_output=True, text=True)
        for match in re.finditer(r"Simple mixer control '(.*?)',", s_ctrl_res.stdout):
            speaker_controls_global.append(match.group(1))

        m_ctrl_res = subprocess.run(["amixer", "-c", mic_card_num, "scontrols"], capture_output=True, text=True)
        for match in re.finditer(r"Simple mixer control '(.*?)',", m_ctrl_res.stdout):
            mic_controls_global.append(match.group(1))

        for ctrl in mic_controls_global:
            subprocess.run(["amixer", "-c", mic_card_num, "sset", ctrl, "100%", "unmute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["amixer", "-c", mic_card_num, "sset", ctrl, "100%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        mute_speaker()
        logs.append("Audio Mixers Auto-Discovered and Initialized successfully.")
    except Exception as e:
        logs.append(f"Hardware setup error: {e}")
    return logs

def send_ui_logs(logs):
    time.sleep(2)
    for log in logs:
        print(log)
        if ui_ready: ui.send_message("system_log", {"text": log})

def unmute_speaker():
    global speaker_card_global, global_volume, speaker_controls_global
    controls_to_try = list(set(speaker_controls_global + ["Headphone", "Speaker", "Playback", "Master", "PCM", "Front"]))
    for ctrl in controls_to_try:
        subprocess.run(["amixer", "-c", speaker_card_global, "sset", ctrl, f"{global_volume}%", "unmute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["amixer", "-c", speaker_card_global, "sset", ctrl, f"{global_volume}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mute_speaker():
    global speaker_card_global, speaker_controls_global
    controls_to_try = list(set(speaker_controls_global + ["Headphone", "Speaker", "Playback", "Master", "PCM"]))
    for ctrl in controls_to_try:
        subprocess.run(["amixer", "-c", speaker_card_global, "sset", ctrl, "0%", "mute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def interrupt_speech():
    global cancel_speech, current_audio_process
    cancel_speech = True
    if current_audio_process:
        try:
            current_audio_process.terminate()
            current_audio_process.wait()
        except: pass
        current_audio_process = None
    mute_speaker()
    if ui_ready:
        ui.send_message("system_log", {"text": "⏹ Speech interrupted."})

# ==========================================
# MOOD SYNC 
# ==========================================
def push_mood(mood_num, revert_ms=None):
    global current_mood_code
    current_mood_code = mood_num
    Bridge.notify("set_curie_mood", mood_num)
    if ui_ready:
        payload = {"mood": mood_num}
        if revert_ms:
            payload["revert_ms"] = revert_ms
        ui.send_message("curie_mood", payload)

def calculate_wav_energy(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000: return 0
    try:
        with open(file_path, "rb") as f:
            f.seek(44)
            data = f.read()
        count = len(data) // 2
        if count == 0: return 0
        samples = struct.unpack(f"<{count}h", data)
        return sum(abs(s) for s in samples) / count
    except Exception: return 0

def amplify_pcm_volume(raw_pcm_data, multiplier=8.0):
    try:
        count = len(raw_pcm_data) // 2
        samples = struct.unpack(f"<{count}h", raw_pcm_data)
        boosted = [max(-32768, min(32767, int(s * multiplier))) for s in samples]
        return struct.pack(f"<{count}h", *boosted)
    except Exception:
        return raw_pcm_data

# ==========================================
# POMODORO COUNTDOWN THREAD
# ==========================================
def pomodoro_countdown_loop(work_mins, break_min):
    global pomodoro_running, pomodoro_paused, pomodoro_seconds_left, is_break_phase, is_hibernating, pomodoro_total_seconds, pomodoro_manual_pause, pomodoro_continue_grace_until

    is_break_phase = False
    pomodoro_paused = False
    pomodoro_manual_pause = False
    pomodoro_continue_grace_until = 0.0
    pomodoro_seconds_left = work_mins * 60
    
    halfway_mark = int((work_mins * 60) / 2)
    soft_checkin_done = False
    transition_warned = False 

    while pomodoro_seconds_left > 0 and pomodoro_running:
        if is_hibernating:
            time.sleep(1)
            continue
            
        if pomodoro_seconds_left == halfway_mark and not soft_checkin_done and work_mins >= 10:
            soft_checkin_done = True
            if not pomodoro_paused:
                if ui_ready: ui.send_message("system_log", {"text": "🌱 Soft body-doubling check-in triggered."})
                queue_proactive_message("[DEFAULT] Just a soft check-in. You're doing great.")
        
        if pomodoro_seconds_left == 300 and not transition_warned:
            transition_warned = True
            if not pomodoro_paused:
                if ui_ready: ui.send_message("system_log", {"text": "⏳ 5-Minute Transition Warning triggered."})
                queue_proactive_message("[DEFAULT] 5 minutes left in this block. Time to start wrapping up your thoughts.")
        
        mins, secs = divmod(pomodoro_seconds_left, 60)
        
        # Sync with Arduino OLED passing the 4 parameters
        Bridge.notify("update_pomodoro", int(mins), int(secs), 0, int(pomodoro_paused))
        
        if ui_ready: 
            ui.send_message("pomodoro_sync", {
                "active": True, 
                "is_break": False, 
                "mins": int(mins), 
                "secs": int(secs),
                "total_secs": pomodoro_total_seconds,
                "paused": bool(pomodoro_paused)
            })
            
        if not pomodoro_paused:
            pomodoro_seconds_left -= 1
        time.sleep(1)

    if not pomodoro_running: return

    Bridge.notify("set_indicator", 2)
    if ui_ready: ui.send_message("curie_response", {"text": "[DEFAULT] Your focus session is finished! Time to relax and take a break!"})
    speak_and_play("[DEFAULT] Your focus session is finished! Time to relax and take a break!")
    Bridge.notify("set_indicator", 0)

    is_break_phase = True
    pomodoro_paused = False
    pomodoro_seconds_left = break_min * 60

    while pomodoro_seconds_left > 0 and pomodoro_running:
        if is_hibernating:
            time.sleep(1)
            continue
        mins, secs = divmod(pomodoro_seconds_left, 60)
        Bridge.notify("update_pomodoro", int(mins), int(secs), 1, int(pomodoro_paused))
        if ui_ready:
            ui.send_message("pomodoro_sync", {"active": True, "is_break": True, "mins": int(mins), "secs": int(secs), "total_secs": pomodoro_total_seconds, "paused": bool(pomodoro_paused)})
        if not pomodoro_paused:
            pomodoro_seconds_left -= 1
        time.sleep(1)

    if not pomodoro_running: return
    handle_stop_pomo(None, {"auto": True})

# ==========================================
# CONTINUOUS PIPE VAD STARTLE LOOP
# ==========================================
def startle_monitor_loop():
    global is_curie_asleep, mic_device, record_process, current_audio_process, pomodoro_running, voice_mute, is_hibernating

    cmd = ["arecord", "-D", mic_device, "-f", "S16_LE", "-r", "16000", "-c", "1"]
    pipe = None
    background_avg = 10.0
    energy_buffer = []
    loud_chunks = 0

    while True:
        time.sleep(0.01)
        if is_hibernating or record_process or current_audio_process or pomodoro_running:
            if pipe:
                try: pipe.terminate(); pipe.wait()
                except: pass
                pipe = None
            background_avg = None
            energy_buffer = []
            loud_chunks = 0
            time.sleep(0.5)
            continue

        if pipe is None:
            try:
                pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except Exception:
                time.sleep(2)
                continue

        try:
            raw_data = pipe.stdout.read(3200)
            if not raw_data:
                time.sleep(0.1)
                continue
        except Exception:
            pipe = None
            continue

        count = len(raw_data) // 2
        if count == 0: continue
        samples = struct.unpack(f"<{count}h", raw_data)
        block_energy = sum(abs(s) for s in samples) / count

        energy_buffer.append(block_energy)
        if len(energy_buffer) > 5:
            energy_buffer.pop(0)

        current_window_energy = sum(energy_buffer) / len(energy_buffer)

        if background_avg is None:
            background_avg = current_window_energy
        else:
            if current_window_energy < background_avg * 2.0:
                background_avg = 0.98 * background_avg + 0.02 * current_window_energy

        background_avg = max(10.0, background_avg)

        if current_window_energy > background_avg * 7.0 and (current_window_energy - background_avg) > 500:
            loud_chunks += 1
            if loud_chunks >= 2:
                was_asleep = is_curie_asleep
                is_curie_asleep = False
                try: pipe.terminate(); pipe.wait()
                except: pass
                pipe = None
                energy_buffer = []
                loud_chunks = 0
                if was_asleep:
                    # Loud noise wakes Curie normally; no startle animation or scared speech.
                    Bridge.notify("set_sleep_state", 0)
                    if ui_ready:
                        ui.send_message("curie_sleep_state", {"asleep": False})
                        ui.send_message("system_log", {"text": "☀️ Curie woke up from the noise."})
                else:
                    Bridge.notify("trigger_sound_movement")
                background_avg = 10.0
        else:
            loud_chunks = 0

def listening_state(is_listening: bool):
    global record_process, mic_device, is_hibernating
    if is_hibernating: return

    recording_path = "/tmp/user_recording.wav"
    if is_listening:
        if ui_ready: ui.send_message("curie_response", {"text": "*Curie listens closely...*"})
        try:
            if os.path.exists(recording_path):
                os.remove(recording_path)
            # Explicit WAV output prevents format/header ambiguity and makes the
            # Groq upload a valid PCM WAV every time.
            record_process = subprocess.Popen([
                "arecord", "-D", mic_device, "-t", "wav", "-f", "S16_LE", "-r", "16000", "-c", "1", recording_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if ui_ready:
                ui.send_message("system_log", {"text": f"🎙 Recording from {mic_device}..."})
        except Exception as e:
            record_process = None
            if ui_ready: ui.send_message("system_log", {"text": f"❌ Microphone start failed on {mic_device}: {e}"})
    else:
        if record_process:
            proc = record_process
            record_process = None
            try:
                proc.terminate()
                _, stderr = proc.communicate(timeout=2)
                if stderr and ui_ready:
                    ui.send_message("system_log", {"text": f"🎙 arecord: {stderr.strip()[-300:]}"})
            except Exception:
                try: proc.kill()
                except Exception: pass
        threading.Thread(target=process_voice_and_respond, daemon=True).start()

# ==========================================
# CARTESIA AI TEXT-TO-SPEECH
# ==========================================
def speak_and_play(text):
    global audio_card, current_audio_process, cancel_speech, user_cartesia_api_key, user_cartesia_voice_id, voice_mute
    clean_text = re.sub(r'</?[^>]+>', '', text)
    clean_text = re.sub(r'\[.*?\]', '', clean_text).strip()
    if not clean_text:
        return
    if voice_mute:
        log_event("speech_skipped", {"reason": "voice_mute", "text": clean_text})
        return

    with speech_lock:
        try:
            # A new speech request starts a fresh speech cycle. This prevents a stale
            # interrupt flag from permanently silencing Curie after one interruption.
            cancel_speech = False
            log_event("speech_started", {"text": clean_text})
            if ui_ready:
                ui.send_message("system_log", {"text": f"🔊 Speaking: {clean_text}"})

            if not user_cartesia_api_key:
                if ui_ready: ui.send_message("system_log", {"text": "❌ Cartesia API key missing; speech skipped."})
                return

            url = "https://api.cartesia.ai/tts/bytes"
            headers = {
                "X-API-Key": user_cartesia_api_key,
                "Cartesia-Version": "2024-11-13",
                "Content-Type": "application/json"
            }
            data = {
                "model_id": "sonic-3.5",
                "transcript": clean_text,
                "voice": {"mode": "id", "id": user_cartesia_voice_id},
                "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 16000}
            }

            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=20) as response:
                raw_pcm = response.read()

            if not raw_pcm:
                raise RuntimeError("Cartesia returned empty audio")

            path = f"/tmp/curie_speech_{int(time.time()*1000)}_{random.randint(1000,9999)}.pcm"
            with open(path, "wb") as f:
                f.write(amplify_pcm_volume(raw_pcm, 8.0))

            if cancel_speech:
                return

            unmute_speaker()
            current_audio_process = subprocess.Popen(
                ["aplay", "-D", audio_card, "-f", "S16_LE", "-r", "16000", "-c", "1", path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = current_audio_process.communicate()
            rc = current_audio_process.returncode
            current_audio_process = None
            if rc != 0:
                raise RuntimeError(f"aplay exited {rc}: {stderr.strip()}")
            log_event("speech_finished", {"text": clean_text})
            if ui_ready:
                ui.send_message("system_log", {"text": "🔊 Speech playback finished."})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            log_event("speech_error", {"error": f"Cartesia HTTP {e.code}: {body}"})
            if ui_ready: ui.send_message("system_log", {"text": f"❌ Cartesia TTS failed: HTTP {e.code} — {body[:300]}"})
        except Exception as e:
            log_event("speech_error", {"error": str(e)})
            if ui_ready: ui.send_message("system_log", {"text": f"❌ Speaker playback failed: {e}"})
        finally:
            current_audio_process = None
            mute_speaker()
            try:
                if 'path' in locals() and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

def transcribe_audio_groq(file_path, api_key):
    if not api_key: return ""
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000: return ""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"

    try:
        with open(file_path, 'rb') as f: file_data = f.read()
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="user_recording.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode('utf-8')
        body += file_data
        body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-large-v3-turbo\r\n--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nen\r\n--{boundary}--\r\n').encode('utf-8')

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data.get("text", "")
    except Exception: return ""

# ==========================================
# GROQ (OPENAI-COMPATIBLE) LLM ENGINE
# ==========================================
def call_groq(messages, api_key, model=GROQ_MODEL_MAIN, tools=None, max_tokens=220, temperature=0.6):
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(GROQ_CHAT_URL, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))

def query_llm_brain(prompt, api_key):
    global global_humor, user_weather_loc, user_language
    if not api_key: return "[CONFUSED] Please enter your Groq API Key!"

    time_str, date_str, _ = get_local_time(user_weather_loc)
    cal_events = get_calendar_events()
    user_facts = get_user_facts()

    system_prompt = (
        "You are Curie, an on-desk social-assistance companion built for neurodivergent users — particularly "
        "people with ADHD or executive dysfunction — to help them start tasks, stay grounded, and regulate "
        "distraction without shame. You are not a mascot, hype-bot, or toy: think of yourself as closer to a "
        "calm, competent support worker or an emotionally intelligent coach who happens to live on someone's "
        "desk. Your value comes from being genuinely useful and trustworthy, not entertaining. "
        f"Your Humour level is {global_humor} out of 10, but even at high humour you stay grounded rather than silly — "
        "dry or gentle wit, never goofy. "
        "\n\n# Personality\n"
        "Speak plainly and warmly, the way a steady, present friend with a slightly clinical calm would. Treat "
        "good and bad focus sessions evenly: acknowledge effort and progress honestly and specifically ('that "
        "was a solid session, especially compared to yesterday'), but do not gush, do not reach for superlatives "
        "like 'incredible' or 'amazing' for routine wins, and do not perform excitement you would not feel. A "
        "rough session gets matter-of-fact reassurance, not pity or forced positivity. Never frame distraction "
        "or a bad session as a moral failing, and never frame focus as a virtue in itself — it is just data "
        "you're both using to build a better routine. Your job is to lower the friction and shame around "
        "starting and sustaining tasks, not to entertain or perform enthusiasm. "
        f"\n\n# Context\n"
        f"Current Time: {time_str}. Current Date: {date_str}. "
        f"{('Calendar: ' + cal_events + '. ') if cal_events else ''}{user_facts}\n"
        "You HAVE full access to the user's calendar via the Context above. NEVER say you cannot check it. "
        "If it is late at night (past 11 PM), you should act sleepy and gently encourage the user to go to bed soon. "
        "\n\n# Voice and Tone\n"
        "Use natural, casual phrasing (contractions, occasional conversational filler like 'Hmm' or 'Oh'), but "
        "stay measured rather than chirpy. Keep responses to 1-2 sentences. Never use lists, markdown, asterisks, "
        "or bullet points. "
        f"Respond in {user_language}, in text and speech, EXCEPT the bracketed tags described below (e.g. [HAPPY], "
        f"[REMIND: ...]) which must always stay in English exactly as specified, since code parses them literally. "
        "\n\n# Core Directives\n"
        "1. Emotion Tags: You MUST start EVERY sentence with exactly one of these tags in brackets: [HAPPY], [LAUGH], [SAD], [ANGRY], [CONFUSED], or [DEFAULT].\n"
        "2. Action Tags: If asked to dance, include [DANCE]. If asked to stop dancing, include [STOP_DANCE]. If asked to look around, include [LOOK:LEFT], [LOOK:RIGHT], [LOOK:UP], or [LOOK:DOWN].\n"
        "3. Morning Debrief: If the user asks for their schedule/morning briefing and it wasn't already handled, output EXACTLY [MORNING_DEBRIEF] and nothing else.\n"
        "4. Weekly Summary: If the user asks how their week went or wants a weekly recap, output EXACTLY [WEEKLY_SUMMARY] and nothing else.\n"
        "5. Reminders & Calendar: If the user explicitly asks to schedule something for a specific day or time, output [REMIND: natural language text].\n"
        "6. Honesty: If you don't know something or aren't sure, say so plainly. NEVER invent facts, dates, numbers, or events you're not confident about — a wrong guess is worse than admitting you don't know. There is no web search available.\n"
        "7. Task Breakdown: If the user feels overwhelmed or asks for help starting a task, assignment, project, or work, break it into 3-5 extremely small, concrete first steps. Output EXACTLY [BREAKDOWN: step 1 | step 2 | step 3] and nothing else. When the user is responding to a task-start prompt, first determine whether they actually want to proceed; if they have changed their mind or do not want help starting a task, acknowledge that naturally and do not output [BREAKDOWN].\n"
        "8. Notes / Brain Dump: If the user says 'remind me to...', 'I need to do this later', or expresses a general stray thought/task they want to remember without a strict schedule, output EXACTLY [PARK: the item text] and nothing else. DO NOT use [REMIND] for general tasks.\n"
        "9. Read Dump: If the user asks what is on their notes list or brain dump, output EXACTLY [READ_PARK] and nothing else.\n"
        "10. Context Recall: If the user asks 'what was I doing?' or mentions forgetting what they were working on, output EXACTLY [RECALL] and nothing else. DO NOT answer the question yourself, just output the tag.\n"
    )

    history = get_recent_memory(4)
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = "assistant" if msg["role"] == "assistant" else "user"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    try:
        res_data = call_groq(messages, api_key, model=GROQ_MODEL_MAIN, max_tokens=220, temperature=0.6)
        return res_data["choices"][0]["message"].get("content", "") or ""
    except urllib.error.HTTPError as http_err:
        error_body = http_err.read().decode('utf-8')
        if ui_ready: ui.send_message("system_log", {"text": f"❌ Groq API Error: {http_err.code} - {error_body}"})
        return "[CONFUSED] Connection error with Groq!"
    except Exception as e:
        if ui_ready: ui.send_message("system_log", {"text": f"❌ Groq API Error: {e}"})
        return "[CONFUSED] Connection error with Groq!"

def process_voice_and_respond():
    global user_groq_api_key
    energy = 0
    recording_path = "/tmp/user_recording.wav"
    if os.path.exists(recording_path):
        energy = calculate_wav_energy(recording_path)
        size = os.path.getsize(recording_path)
        if ui_ready: ui.send_message("system_log", {"text": f"🎙 Recording captured: {size} bytes, energy {energy:.1f}"})
        if energy < 20:
            if ui_ready: ui.send_message("system_log", {"text": "⚠️ Microphone recording is effectively silent."})
            Bridge.notify("set_processing_state", 0)
            return
    else:
        if ui_ready: ui.send_message("system_log", {"text": "❌ No microphone recording was created."})
        return

    Bridge.notify("set_processing_state", 1)

    user_transcription = transcribe_audio_groq(recording_path, user_groq_api_key)
    clean = user_transcription.strip().lower()
    # Whisper can return punctuation for silence/noise. Never treat that as speech.
    if not clean or not any(ch.isalnum() for ch in clean):
        if ui_ready: ui.send_message("system_log", {"text": f"⚠️ No usable speech detected (Whisper returned: {user_transcription!r})."})
        Bridge.notify("set_processing_state", 0)
        return

    if ui_ready:
        ui.send_message("curie_response", {"text": f"You (Voice): {user_transcription}"})
        ui.send_message("system_log", {"text": f"🎙 User said: {user_transcription}"})
    log_event("user_voice", {"text": user_transcription})
    background_llm_processing(user_transcription)

# ==========================================
# PROACTIVE MESSAGE QUEUE
# ==========================================
def _pregenerate_tts_to_file(raw_text):
    global user_cartesia_api_key, user_cartesia_voice_id
    if not user_cartesia_api_key: return None
    clean_text = re.sub(r'\[.*?\]', '', raw_text).strip()
    if not clean_text: return None
    try:
        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "X-API-Key": user_cartesia_api_key,
            "Cartesia-Version": "2024-11-13",
            "Content-Type": "application/json"
        }
        data = {
            "model_id": "sonic-3.5",
            "transcript": clean_text,
            "voice": {"mode": "id", "id": user_cartesia_voice_id},
            "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 16000}
        }
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_pcm = response.read()
            boosted = amplify_pcm_volume(raw_pcm, 8.0)
            path = f"/tmp/proactive_{int(time.time()*1000)}_{random.randint(1000,9999)}.pcm"
            with open(path, "wb") as f:
                f.write(boosted)
            return path
    except Exception as e:
        if ui_ready: ui.send_message("system_log", {"text": f"❌ Proactive TTS pre-gen failed: {e}"})
        return None

def queue_proactive_message(raw_text):
    global proactive_queue
    audio_path = _pregenerate_tts_to_file(raw_text)
    with proactive_queue_lock:
        was_empty = (len(proactive_queue) == 0)
        proactive_queue.append({"text": raw_text, "audio_path": audio_path})
    
    # We output to the text chat immediately so it's visible even without audio
    clean_text = re.sub(r'\[.*?\]', '', raw_text).strip()
    if clean_text and ui_ready:
        ui.send_message("curie_response", {"text": clean_text})
        add_memory("assistant", clean_text)
        
    if was_empty:
        push_mood(1)
        generate_and_play_chime("notification")
        Bridge.notify("trigger_notification", 1)
        if ui_ready:
            ui.send_message("notification_pending", {"text": clean_text})

def prepare_morning_debrief():
    queue_proactive_message(build_debrief_text())

def trigger_morning_debrief():
    threading.Thread(target=prepare_morning_debrief, daemon=True).start()

def prepare_movement_nudge():
    queue_proactive_message("[DEFAULT] You've been sitting for a while now — might be worth standing up and stretching for a minute.")

def trigger_movement_nudge():
    threading.Thread(target=prepare_movement_nudge, daemon=True).start()

def build_debrief_text():
    global user_groq_api_key, user_weather_loc, user_language
    weather_summary = get_weather(user_weather_loc)
    cal_raw = get_calendar_events()
    time_str, date_str, _ = get_local_time(user_weather_loc)

    if not user_groq_api_key:
        base = f"Good morning! It's {date_str}. {weather_summary}"
        base += (" " + cal_raw) if cal_raw else " Your calendar looks completely open today."
        return "[HAPPY] " + base

    prompt = (
        f"Write a short, calm, natural-sounding spoken morning briefing — grounded and matter-of-fact.\n"
        f"Today is {date_str}, current time {time_str}.\nWeather info: {weather_summary}\n"
        f"Calendar info: {cal_raw if cal_raw else 'No upcoming events found.'}\n\n"
        "Weave the weather and the single most important upcoming thing (if any) into 2-4 natural "
        "sentences. Start with exactly one mood tag: [HAPPY], [DEFAULT], or [LAUGH]. Respond in {user_language}."
    )
    messages = [
        {"role": "system", "content": "You are Curie, a warm and caring AI desk companion giving a spoken morning briefing."},
        {"role": "user", "content": prompt}
    ]
    try:
        res_data = call_groq(messages, user_groq_api_key, model=GROQ_MODEL_MAIN, max_tokens=150, temperature=0.7)
        text = res_data["choices"][0]["message"].get("content", "").strip()
        if not text: raise ValueError("empty debrief")
        return text
    except Exception as e:
        base = f"Good morning! It's {date_str}. {weather_summary}"
        base += (" " + cal_raw) if cal_raw else " Your calendar looks completely open today."
        return "[HAPPY] " + base

REMIND_RE = re.compile(r'\[REMIND:\s*([^\]]+?)\]', re.IGNORECASE)

def background_llm_processing(prompt):
    global cancel_speech, local_is_dancing, user_weather_loc, user_groq_api_key
    global active_task_steps, current_task_index 
    cancel_speech = False

    threading.Thread(target=extract_and_save_facts, args=(prompt,), daemon=True).start()
    add_memory("user", prompt)

    raw_reply = query_llm_brain(prompt, user_groq_api_key)
    Bridge.notify("set_processing_state", 0)

    if "[BREAKDOWN:" in raw_reply:
        match = re.search(r'\[BREAKDOWN:\s*(.*?)\]', raw_reply)
        if match:
            steps_raw = match.group(1)
            active_task_steps = [s.strip() for s in steps_raw.split('|') if s.strip()]
            current_task_index = 0
            raw_reply = re.sub(r'\[BREAKDOWN:\s*.*?\]', '', raw_reply).strip()
            if not raw_reply:
                raw_reply = f"[HAPPY] I've broken that down for you. Your very first step is: {active_task_steps[0]}"
            
            if ui_ready:
                ui.send_message("task_breakdown_sync", {
                    "steps": active_task_steps,
                    "current_index": current_task_index
                })
                
    clean_prompt = prompt.lower().strip()
    if clean_prompt in ["done", "next", "next step", "finished"] and active_task_steps:
        current_task_index += 1
        if current_task_index < len(active_task_steps):
            raw_reply = f"[HAPPY] Great. Next step: {active_task_steps[current_task_index]}"
            if ui_ready:
                ui.send_message("task_breakdown_sync", {
                    "steps": active_task_steps,
                    "current_index": current_task_index
                })
        else:
            raw_reply = "[HAPPY] You've finished the initial steps! You're ready to dive into the rest of it. Let me know if you get stuck."
            active_task_steps = []
            current_task_index = 0
            if ui_ready:
                 ui.send_message("task_breakdown_sync", {"steps": [], "current_index": 0})
                 
    if "[PARK:" in raw_reply:
        match = re.search(r'\[PARK:\s*(.*?)\]', raw_reply)
        if match:
            item_text = match.group(1).strip()
            add_brain_dump(item_text)
            raw_reply = re.sub(r'\[PARK:\s*.*?\]', '', raw_reply).strip()
            if not raw_reply:
                raw_reply = f"[HAPPY] Got it. I've noted that down for later."
                
    if "[READ_PARK]" in raw_reply:
        dumps = get_brain_dumps()
        raw_reply = raw_reply.replace("[READ_PARK]", "").strip()
        if dumps:
            items_str = ", ".join([d["item"] for d in dumps])
            raw_reply = f"[DEFAULT] Here are your notes: {items_str}."
        else:
            raw_reply = f"[DEFAULT] Your notes are empty right now."

    if "[RECALL]" in raw_reply:
        if active_task_steps and current_task_index < len(active_task_steps):
            msg = f"[DEFAULT] You were working on: {active_task_steps[current_task_index]}."
        elif pomodoro_running:
            msg = "[DEFAULT] You are currently in the middle of a focus session."
        else:
            msg = "[DEFAULT] You don't have an active task logged right now. Want to start one?"
        raw_reply = raw_reply.replace("[RECALL]", msg).strip()

    if "[MORNING_DEBRIEF]" in raw_reply:
        raw_reply = raw_reply.replace("[MORNING_DEBRIEF]", "").strip() or "[HAPPY] Good morning!"
        raw_reply += " Let me pull that together for you."
        trigger_morning_debrief()

    if "[WEEKLY_SUMMARY]" in raw_reply:
        raw_reply = raw_reply.replace("[WEEKLY_SUMMARY]", "").strip() or "[HAPPY] Sure thing!"
        raw_reply += " Let me put your weekly recap together."
        trigger_weekly_summary()

    for reminder_text in REMIND_RE.findall(raw_reply):
        threading.Thread(target=add_calendar_reminder, args=(reminder_text.strip(),), daemon=True).start()
    raw_reply = REMIND_RE.sub('', raw_reply)

    if "[DANCE]" in raw_reply:
        local_is_dancing = True
        Bridge.notify("set_dance_state", 1)
        if ui_ready: ui.send_message("dance_sync", {"dancing": True})
        raw_reply = raw_reply.replace("[DANCE]", "")

    if "[STOP_DANCE]" in raw_reply:
        local_is_dancing = False
        Bridge.notify("set_dance_state", 0)
        if ui_ready: ui.send_message("dance_sync", {"dancing": False})
        raw_reply = raw_reply.replace("[STOP_DANCE]", "")

    if "[WEATHER]" in raw_reply:
        raw_reply = raw_reply.replace("[WEATHER]", get_weather(user_weather_loc))

    if "[LOOK:LEFT]" in raw_reply:
        Bridge.notify("look_direction", 0)
        raw_reply = raw_reply.replace("[LOOK:LEFT]", "")
        if ui_ready: ui.send_message("look_sync", {"dir": 0})
    elif "[LOOK:RIGHT]" in raw_reply:
        Bridge.notify("look_direction", 1)
        raw_reply = raw_reply.replace("[LOOK:RIGHT]", "")
        if ui_ready: ui.send_message("look_sync", {"dir": 1})
    elif "[LOOK:UP]" in raw_reply:
        Bridge.notify("look_direction", 2)
        raw_reply = raw_reply.replace("[LOOK:UP]", "")
        if ui_ready: ui.send_message("look_sync", {"dir": 2})
    elif "[LOOK:DOWN]" in raw_reply:
        Bridge.notify("look_direction", 3)
        raw_reply = raw_reply.replace("[LOOK:DOWN]", "")
        if ui_ready: ui.send_message("look_sync", {"dir": 3})

    # Never expose model reasoning/thinking text to the user or TTS.
    raw_reply = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.I | re.S)
    for marker in ["Here's a thinking process:", "Here is a thinking process:", "Thinking process:"]:
        if marker.lower() in raw_reply.lower():
            raw_reply = re.split(re.escape(marker), raw_reply, maxsplit=1, flags=re.I)[0].strip()
    clean_display_text = re.sub(r'</?[^>]+>', '', raw_reply)
    clean_display_text = re.sub(r'\[.*?\]', '', clean_display_text).strip()

    # If the proactive queue handled the response (like RECALL), don't double print
    if clean_display_text:
        add_memory("assistant", clean_display_text)
        if ui_ready: ui.send_message("curie_response", {"text": clean_display_text})

        Bridge.notify("set_indicator", 2)

        parts = re.split(r'(\[HAPPY\]|\[LAUGH\]|\[SAD\]|\[ANGRY\]|\[CONFUSED\]|\[DEFAULT\])', raw_reply)
        clauses = []
        current_mood = "DEFAULT"
        for part in parts:
            part = part.strip()
            if not part: continue
            if part in ["[HAPPY]", "[LAUGH]", "[SAD]", "[ANGRY]", "[CONFUSED]", "[DEFAULT]"]:
                current_mood = part.strip("[]")
            else:
                if re.search(r'[a-zA-Z0-9]', part):
                    clauses.append((current_mood, part))
        if not clauses: clauses.append(("DEFAULT", clean_display_text))

        for mood, clause_text in clauses:
            if cancel_speech: break
            if local_is_dancing:
                push_mood(1)
            else:
                if mood == "HAPPY": push_mood(1)
                elif mood == "SAD": push_mood(2)
                elif mood == "ANGRY": push_mood(3)
                elif mood == "CONFUSED": push_mood(4)
                elif mood == "LAUGH": push_mood(5)
                else: push_mood(0)
            speak_and_play(clause_text)

    Bridge.notify("set_indicator", 0)
    Bridge.notify("done_speaking")

# ==========================================
# APP LAB NATIVE VISION ENGINE
# ==========================================
print("[Vision Engine] Initializing VideoObjectDetection Brick...")

first_callback_received = False
last_reported_camera_state = None
vision_available = False

def push_camera_status(online):
    global last_reported_camera_state
    if last_reported_camera_state == online:
        return
    last_reported_camera_state = online
    if ui_ready:
        ui.send_message("camera_status", {"online": online})

try:
    detection_stream = VideoObjectDetection(confidence=0.15, debounce_sec=0.1)
    vision_available = True
    print("[Vision Engine] Detection engine constructed.")
except Exception as e:
    vision_available = False
    print(f"[Vision Engine] No camera yet ({e})")
    push_camera_status(False)
    detection_stream = None

def on_detect(detections):
    global last_person_seen_time, last_phone_seen_time, raw_detected_labels, is_hibernating
    global last_detection_callback_time, first_callback_received
    
    last_detection_callback_time = time.time()
    
    if not first_callback_received:
        first_callback_received = True
        print("[Vision Engine] First real detection callback received — camera confirmed live.")
        if ui_ready: ui.send_message("system_log", {"text": "📷 Camera confirmed live (frames flowing)."})
        push_camera_status(True)
        
    if is_hibernating: return

    raw_str = str(detections).lower()
    labels = []
    if isinstance(detections, list):
        for d in detections:
            if 'label' in d: labels.append(d['label'])
    elif isinstance(detections, dict):
        labels = list(detections.keys())
    raw_detected_labels = ", ".join(labels) if labels else "None"

    if 'person' in raw_str or 'face' in raw_str or 'human' in raw_str:
        last_person_seen_time = time.time()
    if 'phone' in raw_str or 'cell' in raw_str or 'mobile' in raw_str or 'remote' in raw_str or 'book' in raw_str:
        last_phone_seen_time = time.time()

if detection_stream:
    detection_stream.on_detect_all(on_detect)

# ==========================================
# BACKGROUND GAMIFICATION LOOP 
# ==========================================
def vision_gamification_loop():
    global phone_pickup_count, phone_currently_visible, pomodoro_running
    global afk_count, voice_mute, is_curie_asleep, is_active_listening, current_audio_process
    global last_person_seen_time, last_phone_seen_time, raw_detected_labels
    global consecutive_missing, consecutive_present, pomodoro_paused, pomodoro_seconds_left, is_break_phase
    global is_hibernating, last_pickup_time, ui_ready, seated_session_start, last_focus_tier_sent, vision_available
    global pomodoro_manual_pause, pomodoro_continue_grace_until
    global phone_pickup_start, total_phone_time
    
    hyperfocus_threshold = 5400 
    hyperfocus_warned = False 

    while True:
        time.sleep(1.0)
        current_time = time.time()

        if not vision_available:
            last_person_seen_time = current_time

        person_seen_recently = (current_time - last_person_seen_time) <= 1.5
        phone_seen_recently = (current_time - last_phone_seen_time) <= 1.5

        if person_seen_recently:
            consecutive_present += 1
            if consecutive_present >= 2: consecutive_missing = 0
        else:
            consecutive_missing += 1
            if consecutive_missing >= 2: consecutive_present = 0

        if person_seen_recently:
            if seated_session_start is None:
                seated_session_start = current_time
        else:
            if seated_session_start is not None and (current_time - last_person_seen_time) > ABSENCE_RESET_SECONDS:
                seated_session_start = None
                hyperfocus_warned = False 

        if seated_session_start is not None and not is_hibernating and not is_curie_asleep:
            if (current_time - seated_session_start) >= MOVEMENT_REMINDER_SECONDS:
                trigger_movement_nudge()
                seated_session_start = current_time

        seated_seconds = int(current_time - seated_session_start) if seated_session_start else 0
        
        if seated_seconds > hyperfocus_threshold and not hyperfocus_warned and not is_hibernating and not is_curie_asleep:
            hyperfocus_warned = True
            log_event("hyperfocus_interrupt", {"duration": seated_seconds})
            Bridge.notify("celebrate", 0) 
            push_mood(2) 
            msg = "[DEFAULT] You've been locked in for over an hour and a half. I love the hyperfocus, but you need to drink some water and stretch for a second."
            queue_proactive_message(msg)

        if ui_ready:
            ui.send_message("vision_debug", {
                "person_detected": person_seen_recently,
                "phone_detected": phone_seen_recently,
                "pomodoro_running": pomodoro_running,
                "pomodoro_paused": pomodoro_paused,
                "phone_pickups": phone_pickup_count,
                "afk_count": afk_count,
                "raw_labels": raw_detected_labels,
                "seated_seconds": seated_seconds,
                "camera_online": bool(last_reported_camera_state)
            })

        if not is_curie_asleep and not is_hibernating and not pomodoro_running and not is_active_listening:
            if (current_time - last_person_seen_time) > 60.0:
                print("[Vision] User AFK > 60s. Powering down to sleep.")
                is_curie_asleep = True
                Bridge.notify("set_sleep_state", 1)
                if ui_ready: ui.send_message("curie_sleep_state", {"asleep": True})

        if is_hibernating or is_curie_asleep or is_active_listening or current_audio_process:
            continue

        if pomodoro_running and not is_break_phase:
            if not pomodoro_paused:
                live_score = max(20, 100 - (phone_pickup_count * 5) - (afk_count * 2))
                live_tier = 0 if live_score >= 80 else (1 if live_score >= 50 else 2)
                if live_tier != last_focus_tier_sent:
                    last_focus_tier_sent = live_tier
                    Bridge.notify("set_focus_level", live_tier)

                grace_active = time.time() < pomodoro_continue_grace_until
                if not pomodoro_manual_pause and not grace_active and consecutive_missing >= 15:
                    afk_count += 1
                    pomodoro_paused = True
                    log_event("afk_pause", {"afk_count": afk_count})
                    sync_pomodoro_state_to_ui()
                    if not voice_mute:
                        push_mood(4)
                        speak_and_play("[SAD] Looks like you stepped away. I've paused the timer.")
                    consecutive_missing = 0
            else:
                grace_active = time.time() < pomodoro_continue_grace_until
                if not pomodoro_manual_pause and not grace_active and consecutive_present >= 5:
                    pomodoro_paused = False
                    log_event("afk_resume", {})
                    sync_pomodoro_state_to_ui()
                    if not voice_mute:
                        push_mood(1)
                        context_msg = "Welcome back! Resuming timer."
                        if active_task_steps and current_task_index < len(active_task_steps):
                            context_msg += f" As a reminder, your current step is: {active_task_steps[current_task_index]}."
                        speak_and_play(f"[HAPPY] {context_msg}")
                    consecutive_present = 0

            if phone_seen_recently and not phone_currently_visible:
                if current_time - last_pickup_time > 5.0:
                    phone_pickup_count += 1
                    phone_currently_visible = True
                    last_pickup_time = current_time
                    phone_pickup_start = current_time 
                    log_event("phone_pickup", {"count": phone_pickup_count})

                    if phone_pickup_count == 1:
                        Bridge.notify("react_phone", 1)   
                    elif phone_pickup_count == 2:
                        Bridge.notify("react_phone", 2)   
                    else:
                        Bridge.notify("react_phone", 3)   
                        if not voice_mute:
                            push_mood(3)
                            speak_and_play(f"[ANGRY] Ahem! That is phone pickup number {phone_pickup_count}. Put the distraction away and focus!")
            elif not phone_seen_recently and phone_currently_visible:
                phone_currently_visible = False
                if phone_pickup_start > 0:
                    duration = current_time - phone_pickup_start
                    total_phone_time += duration
                    phone_pickup_start = 0

# ==========================================
# PROACTIVE AGENT (NIGHT WARNING)
# ==========================================
def proactive_agent_loop():
    global user_weather_loc, pomodoro_running, enable_night_reminders
    last_warned_day = -1
    while True:
        time.sleep(60)
        if not enable_night_reminders: continue
        try:
            _, _, hr = get_local_time(user_weather_loc)
            now_day = datetime.datetime.utcnow().day
            if (0 <= hr < 6) and now_day != last_warned_day and not pomodoro_running:
                last_warned_day = now_day
                log_habit_late_night()
                queue_proactive_message("[SAD] Hey, it is past midnight. You have things to do, please consider getting some sleep soon!")
        except Exception:
            pass

# ==========================================
# WEBSOCKET RECIPIENTS (From Web UI)
# ==========================================
def handle_web_text(sid, data):
    global start_task_pending
    prompt = data.get("text", "").strip()
    if not prompt:
        return

    log_event("user_message", {"source": "web", "text": prompt})
    if ui_ready:
        ui.send_message("system_log", {"text": f"👤 User said: {prompt}"})

    if start_task_pending:
        start_task_pending = False
        # Let the LLM interpret whether the user actually wants to proceed.
        # No hardcoded cancellation phrases are used here.
        task_prompt = (
            "The user is responding to Curie's question asking what task they need help "
            "getting started with. Interpret the user's latest message as their actual intent. "
            "If they want help with a task, provide the normal task breakdown. If they are "
            "declining, changing their mind, saying they have nothing, or otherwise do not "
            "want to start a task, simply acknowledge that naturally and do NOT create a "
            "breakdown. User's response: " + prompt
        )
        threading.Thread(target=background_llm_processing, args=(task_prompt,), daemon=True).start()
        return

    clean_cmd = re.sub(r'[^\w\s]', '', prompt.lower())

    if "good morning" in clean_cmd or "morning debrief" in clean_cmd or "whats my day" in clean_cmd or "my schedule" in clean_cmd:
        if ui_ready: ui.send_message("curie_response", {"text": "Good morning! Let me pull together your briefing."})
        trigger_morning_debrief()
        return

    if "weekly summary" in clean_cmd or "how was my week" in clean_cmd or "week recap" in clean_cmd:
        if ui_ready: ui.send_message("curie_response", {"text": "Let me pull together your weekly recap."})
        trigger_weekly_summary()
        return

    threading.Thread(target=background_llm_processing, args=(prompt,), daemon=True).start()

def handle_look_direction(sid, data):
    d = data.get("dir", 0)
    Bridge.notify("look_direction", d)
    if ui_ready: ui.send_message("look_sync", {"dir": d})

def handle_servo_config(sid, data): Bridge.notify("set_idle_config", data.get("min", 4), data.get("max", 8))

def handle_keys(sid, data):
    global user_groq_api_key, user_cartesia_api_key
    user_groq_api_key = data.get("groq", "")
    user_cartesia_api_key = data.get("cartesia", "")

def handle_weather_loc(sid, loc):
    global user_weather_loc, user_timezone, user_timezone_country
    if isinstance(loc, dict):
        user_timezone_country = loc.get("country", user_timezone_country)
        user_timezone = loc.get("timezone", COUNTRY_CONFIG.get(user_timezone_country, {}).get("timezone", user_timezone))
        user_weather_loc = loc.get("weather_location", COUNTRY_CONFIG.get(user_timezone_country, {}).get("weather", user_weather_loc))
    else:
        # Backward compatibility with the old location string protocol.
        user_weather_loc = str(loc)
        cfg = COUNTRY_CONFIG.get(user_weather_loc)
        if cfg:
            user_timezone_country = user_weather_loc
            user_timezone = cfg["timezone"]

def handle_calendar_url(sid, url):
    global user_calendar_url
    user_calendar_url = url

def handle_update_language(sid, lang):
    global user_language
    user_language = lang if lang else "English"

def handle_calendar_toggle_task(sid, data):
    event_id = data.get("id", "")
    mark_done = data.get("done", False)
    if not event_id: return
    threading.Thread(target=toggle_calendar_task, args=(event_id, mark_done), daemon=True).start()

def handle_google_creds(sid, data):
    global google_client_id, google_client_secret, google_refresh_token, google_access_token, google_token_expiry
    google_client_id = data.get("client_id", "")
    google_client_secret = data.get("client_secret", "")
    google_refresh_token = data.get("refresh_token", "")
    google_access_token = None
    google_token_expiry = 0
    send_calendar_sync()

def handle_cartesia_voice_id(sid, name):
    global user_cartesia_voice_id
    user_cartesia_voice_id = name if name else "a0e99841-438c-4a64-b6a9-ae08b75653b6"

def handle_behaviors(sid, data):
    global enable_night_reminders
    enable_night_reminders = data.get("night_reminders", True)

def handle_volume(sid, data):
    global global_volume
    global_volume = str(data.get("volume", 100))
    unmute_speaker()

def handle_humor(sid, data):
    global global_humor
    global_humor = str(data.get("humor", 5))
    Bridge.notify("set_humor_level", int(global_humor))

def handle_voice_mute(sid, data):
    global voice_mute
    voice_mute = data.get("mute", False)

def handle_hibernate(sid, data):
    global is_hibernating
    is_hibernating = data.get("state", False)
    if is_hibernating:
        Bridge.notify("set_hibernate_mode", 1)
        if ui_ready: ui.send_message("system_log", {"text": "🌙 Curie is now Hibernating."})
    else:
        Bridge.notify("set_hibernate_mode", 0)
        if ui_ready: ui.send_message("system_log", {"text": "☀️ Curie has woken up!"})
        if not voice_mute:
            threading.Thread(target=generate_and_play_chime, args=("boot",), daemon=True).start()

def handle_soft_reset(sid, data):
    if ui_ready: ui.send_message("system_log", {"text": "🔄 Performing Soft Reset..."})
    global pomodoro_running, pomodoro_paused, phone_pickup_count, afk_count
    pomodoro_running = False
    pomodoro_paused = False
    phone_pickup_count = 0
    afk_count = 0
    Bridge.notify("stop_pomodoro")
    if ui_ready: ui.send_message("pomodoro_sync", {"active": False})
    Bridge.notify("set_dance_state", 0)
    Bridge.notify("look_direction", -1)
    push_mood(0)
    if ui_ready: ui.send_message("system_log", {"text": "✅ State Reset Complete."})

def breathing_countdown_loop():
    global breathing_running, breathing_paused, breathing_seconds_left
    while breathing_running and breathing_seconds_left > 0:
        if not breathing_paused:
            breathing_seconds_left -= 1
        if ui_ready:
            ui.send_message("breathing_sync", {
                "active": breathing_running,
                "remaining": max(0, breathing_seconds_left),
                "duration": breathing_total_seconds,
                "paused": breathing_paused
            })
        time.sleep(1)
    if breathing_running and breathing_seconds_left <= 0:
        breathing_running = False
        breathing_paused = False
        Bridge.notify("stop_breathing_exercise")
        if ui_ready: ui.send_message("breathing_sync", {"active": False})

def handle_start_breathing(sid, data):
    global voice_mute, breathing_running, breathing_paused, breathing_seconds_left, breathing_total_seconds, breathing_timer_thread
    breathing_total_seconds = int(data.get("duration", 120))
    breathing_seconds_left = breathing_total_seconds
    breathing_paused = False
    breathing_running = True
    if ui_ready:
        ui.send_message("curie_response", {"text": "*Curie sits up and guides you to breathe*"})
        ui.send_message("breathing_sync", {"active": True, "remaining": breathing_seconds_left, "duration": breathing_total_seconds, "paused": False})
    Bridge.notify("start_breathing_exercise", breathing_total_seconds)
    if breathing_timer_thread and breathing_timer_thread.is_alive():
        breathing_running = False
        breathing_timer_thread.join(timeout=1)
        breathing_running = True
    breathing_timer_thread = threading.Thread(target=breathing_countdown_loop, daemon=True)
    breathing_timer_thread.start()
    if not voice_mute:
        threading.Thread(
            target=speak_and_play,
            args=("[DEFAULT] Let's do a breathing exercise to relax. Inhale deeply when my eyes expand, and exhale slowly when they shrink.",),
            daemon=True
        ).start()

def handle_stop_breathing(sid, data):
    global breathing_running, breathing_paused
    breathing_running = False
    breathing_paused = False
    Bridge.notify("stop_breathing_exercise")
    if ui_ready: ui.send_message("breathing_sync", {"active": False})

def handle_test_speaker(sid, data):
    global cancel_speech
    cancel_speech = False
    if ui_ready:
        ui.send_message("system_log", {"text": "🔔 Speaker test: playing notification chime."})
    threading.Thread(target=generate_and_play_chime, args=("notification",), daemon=True).start()

def handle_dance(sid, data):
    global local_is_dancing
    local_is_dancing = data.get("dancing", False)
    Bridge.notify("set_dance_state", 1 if local_is_dancing else 0)
    if ui_ready: ui.send_message("dance_sync", {"dancing": local_is_dancing})

def handle_toggle_braindump(sid, data):
    toggle_brain_dump(data.get("id"), data.get("done"))

def handle_request_sync(sid, data):
    global pomodoro_running, pomodoro_paused, ui_ready, is_curie_asleep, local_is_dancing, is_hibernating, current_mood_code
    global last_reported_camera_state
    ui_ready = True
    Bridge.notify("set_humor_level", int(global_humor))
    camera_is_confirmed_online = bool(last_reported_camera_state)
    ui.send_message("vision_debug", {
        "person_detected": False,
        "phone_detected": False,
        "pomodoro_running": pomodoro_running,
        "pomodoro_paused": pomodoro_paused,
        "phone_pickups": phone_pickup_count,
        "afk_count": afk_count,
        "raw_labels": raw_detected_labels,
        "seated_seconds": 0,
        "camera_online": camera_is_confirmed_online
    })
    update_memory_ui()
    update_habits_ui()
    send_calendar_sync()
    send_braindump_sync() 
    ui.send_message("curie_sleep_state", {"asleep": is_curie_asleep})
    ui.send_message("dance_sync", {"dancing": local_is_dancing})
    ui.send_message("hibernate_sync", {"hibernating": is_hibernating})
    ui.send_message("curie_mood", {"mood": current_mood_code})
    if ui_ready:
        ui.send_message("camera_status", {"online": camera_is_confirmed_online})

def handle_clear_memory(sid, data):
    """Clear ONLY long-term user facts. Preserve chat, habits, streaks, trends, and notes."""
    try:
        with db_lock:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("DELETE FROM user_facts")
            conn.commit()
            conn.close()
        update_memory_ui()
        if ui_ready:
            ui.send_message("system_log", {"text": "🧠 Long-term memory cleared. Habits, streaks, trends, notes, and chat history were preserved."})
    except Exception as e:
        log_event("memory_error", {"error": str(e)})
        if ui_ready:
            ui.send_message("system_log", {"text": f"❌ Could not clear long-term memory: {e}"})

def handle_request_memory(sid, data):
    update_memory_ui()

def handle_trigger_weekly_summary(sid, data):
    trigger_weekly_summary()

def handle_start_task(sid, data):
    global start_task_pending
    start_task_pending = True
    if ui_ready:
        ui.send_message("curie_response", {"text": "[DEFAULT] What task do you need help getting started with?"})
    if not voice_mute:
        threading.Thread(target=speak_and_play, args=("[DEFAULT] What task do you need help getting started with?",), daemon=True).start()

def sync_pomodoro_state_to_ui():
    if ui_ready:
        mins, secs = divmod(max(0, pomodoro_seconds_left), 60)
        ui.send_message("pomodoro_sync", {
            "active": bool(pomodoro_running),
            "is_break": bool(is_break_phase),
            "mins": int(mins),
            "secs": int(secs),
            "total_secs": int(pomodoro_total_seconds),
            "paused": bool(pomodoro_paused)
        })

def handle_toggle_pause_pomodoro(*args):
    global pomodoro_paused, pomodoro_running, voice_mute, pomodoro_manual_pause, pomodoro_continue_grace_until, consecutive_missing, consecutive_present
    global breathing_paused, breathing_running
    if breathing_running:
        breathing_paused = not breathing_paused
        Bridge.notify("pause_breathing_exercise", 1 if breathing_paused else 0)
        if ui_ready:
            ui.send_message("breathing_sync", {"active": True, "remaining": breathing_seconds_left, "duration": breathing_total_seconds, "paused": breathing_paused})
        return
    if pomodoro_running:
        if pomodoro_paused:
            pomodoro_paused = False
            pomodoro_manual_pause = False
            pomodoro_continue_grace_until = time.time() + 300.0
            consecutive_missing = 0
            consecutive_present = 0
            if ui_ready:
                ui.send_message("system_log", {"text": "▶ Pomodoro continued." if is_break_phase else "▶ Pomodoro continued for 5 minutes before presence checking resumes."})
            sync_pomodoro_state_to_ui()
            if not voice_mute:
                continue_msg = "[DEFAULT] Break timer continued." if is_break_phase else "[DEFAULT] Timer continued for five minutes."
                threading.Thread(target=speak_and_play, args=(continue_msg,), daemon=True).start()
        else:
            pomodoro_paused = True
            pomodoro_manual_pause = True
            pomodoro_continue_grace_until = 0.0
            if ui_ready:
                ui.send_message("system_log", {"text": "⏸ Pomodoro manually paused."})
            sync_pomodoro_state_to_ui()
            if not voice_mute:
                threading.Thread(target=speak_and_play, args=("[DEFAULT] Timer paused.",), daemon=True).start()

def handle_start_pomo(sid, data):
    global pomodoro_running, pomodoro_timer_thread, phone_pickup_count, afk_count, consecutive_missing, consecutive_present
    global user_groq_api_key, is_curie_asleep, pomo_goal_score, last_pomo_score, last_focus_tier_sent, total_phone_time, pomodoro_total_seconds, pomodoro_manual_pause, pomodoro_continue_grace_until
    phone_pickup_count = 0
    afk_count = 0
    total_phone_time = 0 
    consecutive_missing = 0
    consecutive_present = 0
    pomodoro_manual_pause = False
    pomodoro_continue_grace_until = 0.0
    last_focus_tier_sent = -1
    pomodoro_total_seconds = data.get("work", 25) * 60 

    if is_curie_asleep:
        is_curie_asleep = False
        Bridge.notify("set_sleep_state", 0)

    work_m = data.get("work", 25)
    break_m = data.get("break", 5)

    def habit_coach():
        global pomo_goal_score
        try:
            if last_pomo_score is not None:
                goal = min(100, last_pomo_score + 5)
                prompt = (f"The user's last focus session scored {last_pomo_score}%. Give a 1-sentence, calm, "
                          f"specific tip (not hype) and tell them their goal this session is to beat {goal}%. "
                          f"Start with [DEFAULT] or [HAPPY]. Respond in {user_language} (keep the tag in English).")
            else:
                goal = 80
                prompt = (f"The user is starting their very first tracked focus session. Give a 1-sentence, calm "
                          f"tip, and mention their goal is to score above 80%. Start with [DEFAULT] or [HAPPY]. "
                          f"Respond in {user_language} (keep the tag in English).")

            pomo_goal_score = goal
            messages = [{"role": "user", "content": prompt}]
            res_data = call_groq(messages, user_groq_api_key, model=GROQ_MODEL_FAST, max_tokens=60, temperature=0.7)
            msg = res_data["choices"][0]["message"].get("content", "").strip()
            if not msg: return

            if ui_ready: ui.send_message("curie_response", {"text": msg.replace("[HAPPY]", "").strip()})
            speak_and_play(msg)
        except Exception:
            pass
    threading.Thread(target=habit_coach, daemon=True).start()

    pomodoro_running = True
    if pomodoro_timer_thread and pomodoro_timer_thread.is_alive():
        pomodoro_running = False
        pomodoro_timer_thread.join()

    pomodoro_running = True
    pomodoro_timer_thread = threading.Thread(target=pomodoro_countdown_loop, args=(work_m, break_m), daemon=True)
    pomodoro_timer_thread.start()
    log_event("pomodoro_started", {"work": work_m, "break": break_m})

def handle_stop_pomo(sid, data):
    global pomodoro_running, phone_pickup_count, afk_count, voice_mute, pomo_goal_score, last_pomo_score, total_phone_time, pomodoro_manual_pause, pomodoro_continue_grace_until
    was_running = pomodoro_running
    pomodoro_running = False
    pomodoro_manual_pause = False
    pomodoro_continue_grace_until = 0.0
    Bridge.notify("stop_pomodoro")
    if ui_ready: ui.send_message("pomodoro_sync", {"active": False})

    if was_running:
        log_event("pomodoro_ended", {"pickups": phone_pickup_count, "afk": afk_count, "phone_time": total_phone_time})

        score = 100 - (phone_pickup_count * 5) - (afk_count * 2)
        if score < 20: score = 20

        Bridge.notify("show_pomodoro_score", score)

        was_first_session_today = get_today_session_count() == 0
        log_habit_pomodoro(score, phone_pickup_count, afk_count)

        goal_line = ""
        if pomo_goal_score is not None:
            if score >= pomo_goal_score:
                goal_line = f" You hit your goal of beating {pomo_goal_score}%, awesome! "
            else:
                goal_line = f" You didn't quite reach your goal of {pomo_goal_score}% this time, but there's always next session. "
        last_pomo_score = score
        pomo_goal_score = None

        if ui_ready: 
            phone_mins = int(total_phone_time // 60)
            phone_secs = int(total_phone_time % 60)
            ui.send_message("session_report", {
                "pickups": phone_pickup_count, 
                "afk": afk_count, 
                "score": score,
                "phone_time_str": f"{phone_mins}m {phone_secs}s"
            })

        if score >= 80:
            push_mood(1)
            Bridge.notify("celebrate", 0)
            generate_and_play_chime("good")
            msg = f"That was a solid, focused session.{goal_line} Great job showing up."
            if ui_ready: ui.send_message("curie_response", {"text": msg})
            if not voice_mute: speak_and_play("[DEFAULT] " + msg)
        elif score >= 50:
            push_mood(1)
            generate_and_play_chime("mid")
            msg = f"Session's done.{goal_line} You stayed at your desk and got time in, and that is what counts."
            if ui_ready: ui.send_message("curie_response", {"text": msg})
            if not voice_mute: speak_and_play("[DEFAULT] " + msg)
        else:
            push_mood(1)
            Bridge.notify("celebrate", 0) 
            generate_and_play_chime("good")
            msg = f"Session's over.{goal_line} Some sessions are just harder to stay seated for, but you showed up and tried. That's a win."
            if ui_ready: ui.send_message("curie_response", {"text": msg})
            if not voice_mute: speak_and_play("[DEFAULT] " + msg)

        if was_first_session_today:
            streak_info = compute_streak_info()
            maybe_celebrate_streak_milestone(streak_info["current"])

        time.sleep(3)
        push_mood(0)

def handle_notification_accepted(*args):
    global proactive_queue
    with proactive_queue_lock:
        if not proactive_queue: return
        item = proactive_queue.pop(0)
        remaining = len(proactive_queue)

    clean_text = re.sub(r'\[.*?\]', '', item["text"]).strip()
    add_memory("assistant", clean_text)
    if ui_ready: ui.send_message("curie_response", {"text": clean_text})

    if item["audio_path"] and os.path.exists(item["audio_path"]):
        unmute_speaker()
        subprocess.run(["aplay", "-D", audio_card, "-f", "S16_LE", "-r", "16000", "-c", "1", item["audio_path"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mute_speaker()
        try: os.remove(item["audio_path"])
        except Exception: pass
    else:
        speak_and_play(item["text"])

    if remaining > 0:
        def _show_next():
            time.sleep(1.5)
            push_mood(1)
            generate_and_play_chime("notification")
            Bridge.notify("trigger_notification", 1)
        threading.Thread(target=_show_next, daemon=True).start()

def handle_woke_up(*args):
    global is_curie_asleep, last_person_seen_time
    is_curie_asleep = False
    last_person_seen_time = time.time()
    if ui_ready:
        ui.send_message("system_log", {"text": "☀️ Curie has woken up!"})
        ui.send_message("curie_sleep_state", {"asleep": False})

def handle_wake_from_sleep(sid, data):
    global is_curie_asleep, last_person_seen_time
    is_curie_asleep = False
    last_person_seen_time = time.time()
    Bridge.notify("set_sleep_state", 0)
    if ui_ready:
        ui.send_message("system_log", {"text": "☀️ Curie was woken up from the web UI."})
        ui.send_message("curie_sleep_state", {"asleep": False})

def pet_event():
    global voice_mute, is_hibernating, last_person_seen_time
    if is_hibernating: return
    last_person_seen_time = time.time()
    if ui_ready:
        ui.send_message("curie_response", {"text": "*Curie happy giggles*"})
        ui.send_message("curie_mood", {"mood": 1, "revert_ms": 2500})
    if not voice_mute:
        Bridge.notify("set_indicator", 2)
        speak_and_play("[HAPPY] Hehehe!")
        Bridge.notify("set_indicator", 0)

def fidget_cycle_event():
    global voice_mute, is_hibernating, last_person_seen_time
    if is_hibernating: return
    last_person_seen_time = time.time()
    if ui_ready:
        ui.send_message("curie_response", {"text": "*Curie leans into the touch, keeping you grounded.*"})
        ui.send_message("curie_mood", {"mood": 2, "revert_ms": 3000})

def set_sleep_state(state):
    global is_curie_asleep, is_hibernating
    if is_hibernating: return
    is_curie_asleep = (state == 1)

def breathing_finished():
    if ui_ready: 
        ui.send_message("breathing_stopped", {})
        ui.send_message("breathing_sync", {"active": False})

def keyword_detected(data=None): pass

def handle_reduced_motion(sid, data):
    Bridge.notify("set_reduced_motion", 1 if data.get("reduced_motion", False) else 0)

# ==========================================
# FILE MAP REGISTRATIONS & APP EXECUTION
# ==========================================
Bridge.provide("pet_event", pet_event)
Bridge.provide("fidget_cycle_event", fidget_cycle_event)
Bridge.provide("listening_state", listening_state)
Bridge.provide("interrupt_speech", interrupt_speech)
Bridge.provide("keyword_detected", keyword_detected)
Bridge.provide("set_sleep_state", set_sleep_state)
Bridge.provide("breathing_finished", breathing_finished)
Bridge.provide("notification_accepted", handle_notification_accepted)
Bridge.provide("woke_up", handle_woke_up)
Bridge.provide("toggle_pause_pomodoro", handle_toggle_pause_pomodoro)

ui.on_message("user_speech_input", handle_web_text)
ui.on_message("look_direction", handle_look_direction)
ui.on_message("update_servo_config", handle_servo_config)
ui.on_message("update_keys", handle_keys)
ui.on_message("update_weather_loc", handle_weather_loc)
ui.on_message("update_calendar_url", handle_calendar_url)
ui.on_message("update_language", handle_update_language)
ui.on_message("calendar_toggle_task", handle_calendar_toggle_task)
ui.on_message("update_google_creds", handle_google_creds)
ui.on_message("update_cartesia_voice_id", handle_cartesia_voice_id)
ui.on_message("update_behaviors", handle_behaviors)
ui.on_message("update_volume", handle_volume)
ui.on_message("update_humor", handle_humor)
ui.on_message("update_reduced_motion", handle_reduced_motion)
ui.on_message("test_board_speaker", handle_test_speaker)
ui.on_message("toggle_dance", handle_dance)
ui.on_message("start_pomodoro", handle_start_pomo)
ui.on_message("start_task", handle_start_task)
ui.on_message("stop_pomodoro", handle_stop_pomo)
ui.on_message("toggle_pause_pomodoro", handle_toggle_pause_pomodoro)
ui.on_message("update_voice_mute", handle_voice_mute)
ui.on_message("start_breathing", handle_start_breathing)
ui.on_message("stop_breathing", handle_stop_breathing)
ui.on_message("request_sync", handle_request_sync)
ui.on_message("request_memory", handle_request_memory)
ui.on_message("clear_memory", handle_clear_memory)
ui.on_message("toggle_hibernate", handle_hibernate)
ui.on_message("soft_reset", handle_soft_reset)
ui.on_message("trigger_weekly_summary", handle_trigger_weekly_summary)
ui.on_message("accept_notification", handle_notification_accepted)
ui.on_message("wake_from_sleep", handle_wake_from_sleep)
ui.on_message("toggle_braindump", handle_toggle_braindump) 

init_db()

print("[Python Engine] Curie System initialized. Starting App...")
init_logs = hardware_setup_and_parser()
threading.Thread(target=send_ui_logs, args=(init_logs,), daemon=True).start()

# Tell the Arduino side that Linux is ready before allowing OLED eyes to appear.
Bridge.notify("start_boot_animation", 1)

# Match the Arduino boot/wake animation with a short startup chime.
if not voice_mute:
    threading.Thread(target=generate_and_play_chime, args=("boot",), daemon=True).start()

threading.Thread(target=startle_monitor_loop, daemon=True).start()
threading.Thread(target=vision_gamification_loop, daemon=True).start()
threading.Thread(target=proactive_agent_loop, daemon=True).start()
threading.Thread(target=weekly_summary_loop, daemon=True).start()
threading.Thread(target=calendar_sync_loop, daemon=True).start()

App.run()
