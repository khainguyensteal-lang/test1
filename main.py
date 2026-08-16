#!/usr/bin/env python3
"""
CTDOTEAM - Discord Quest Auto-Completer Bot - Components V2 Style
"""

import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import requests
import time
import json
import random
import re
import base64
import traceback
from datetime import datetime, timezone
from typing import Optional
import os

# ── Configuration ──────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "")
OWNER_ID = int(os.getenv("BOT_OWNER_ID", ""))

API_BASE = "https://discord.com/api/v9"
POLL_INTERVAL = 60
HEARTBEAT_INTERVAL = 20
AUTO_ACCEPT = True
LOG_PROGRESS = True
DEBUG = False

SUPPORTED_TASKS = [
    "WATCH_VIDEO",
    "PLAY_ON_DESKTOP",
    "STREAM_ON_DESKTOP",
    "PLAY_ACTIVITY",
    "WATCH_VIDEO_ON_MOBILE",
]

UNSUPPORTED_TASKS = [
    "STREAM_NOW",
    "LAUNCH_QUEST",
]

# ── Components V2 Helpers ─────────────────────────────────────────────────────
def build_v2_view(title: str, lines: list[str], color: discord.Color = discord.Color.gold()) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(
        ui.TextDisplay(f"## {title}"),
        ui.Separator(spacing=discord.SeparatorSpacing.small),
        ui.TextDisplay("\n".join(lines)),
        accent_color=color,
    )
    view.add_item(container)
    return view

def build_status_view(title: str, fields: dict, color: discord.Color = discord.Color.gold()) -> ui.LayoutView:
    view = ui.LayoutView()
    items = [ui.TextDisplay(f"## {title}"), ui.Separator(spacing=discord.SeparatorSpacing.small)]
    
    for key, value in fields.items():
        items.append(ui.TextDisplay(f"**{key}**\n{value}"))
        items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
    
    container = ui.Container(*items, accent_color=color)
    view.add_item(container)
    return view

# ── Logging ────────────────────────────────────────────────────────────────────
class Colors:
    RESET  = "\033[0m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"

def log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "info":     f"{Colors.CYAN}[INFO]{Colors.RESET}",
        "ok":       f"{Colors.GREEN}[  OK]{Colors.RESET}",
        "warn":     f"{Colors.YELLOW}[WARN]{Colors.RESET}",
        "error":    f"{Colors.RED}[ ERR]{Colors.RESET}",
        "progress": f"{Colors.DIM}[PROG]{Colors.RESET}",
        "debug":    f"{Colors.DIM}[DBG ]{Colors.RESET}",
    }.get(level, f"[{level.upper()}]")

    if level == "debug" and not DEBUG:
        return
    if LOG_PROGRESS or level != "progress":
        print(f"{Colors.DIM}{ts}{Colors.RESET} {prefix} {msg}")

# ── Build Number Fetcher ──────────────────────────────────────────────────────
def fetch_latest_build_number() -> int:
    FALLBACK = 504649
    try:
        log("Fetching latest build number from Discord...", "info")
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        r = requests.get("https://discord.com/app", headers={"User-Agent": ua}, timeout=15)
        if r.status_code != 200:
            log(f"Failed to fetch Discord page ({r.status_code}), using fallback", "warn")
            return FALLBACK

        scripts = re.findall(r'/assets/([a-f0-9]+)\.js', r.text)
        if not scripts:
            scripts_alt = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
            scripts = [s.split('/')[-1].replace('.js', '') for s in scripts_alt]

        if not scripts:
            log("No JS assets found, using fallback", "warn")
            return FALLBACK

        for asset_hash in scripts[-5:]:
            try:
                ar = requests.get(
                    f"https://discord.com/assets/{asset_hash}.js",
                    headers={"User-Agent": ua}, timeout=15
                )
                m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar.text)
                if m:
                    bn = int(m.group(1))
                    log(f"Build number: {Colors.BOLD}{bn}{Colors.RESET}", "ok")
                    return bn
            except Exception:
                continue

        log(f"Build number not found, using fallback {FALLBACK}", "warn")
        return FALLBACK
    except Exception as e:
        log(f"Error fetching build number: {e}, using fallback {FALLBACK}", "warn")
        return FALLBACK

def make_super_properties(build_number: int) -> str:
    obj = {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": "1.0.9175",
        "os_version": "10.0.26100",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "browser_user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        ),
        "browser_version": "32.2.7",
        "client_build_number": build_number,
        "native_build_number": 59498,
        "client_event_source": None,
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()

# ── HTTP Helpers ──────────────────────────────────────────────────────────────
class DiscordAPI:
    def __init__(self, token: str, build_number: int):
        self.token = token
        self.session = requests.Session()
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        )
        sp = make_super_properties(build_number)
        self.session.headers.update({
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": ua,
            "X-Super-Properties": sp,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
        })

    def get(self, path: str, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        log(f"GET {path}", "debug")
        r = self.session.get(url, **kwargs)
        log(f"  -> {r.status_code} ({len(r.content)} bytes)", "debug")
        return r

    def post(self, path: str, payload: Optional[dict] = None, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        log(f"POST {path}", "debug")
        r = self.session.post(url, json=payload, **kwargs)
        log(f"  -> {r.status_code} ({len(r.content)} bytes)", "debug")
        return r

    def validate_token(self) -> bool:
        try:
            r = self.get("/users/@me")
            if r.status_code == 200:
                user = r.json()
                name = user.get("username", "?")
                log(f"Logged in: {Colors.BOLD}{name}{Colors.RESET} (ID: {user['id']})", "ok")
                return True
            else:
                log(f"Invalid token (status {r.status_code})", "error")
                return False
        except Exception as e:
            log(f"Cannot connect to Discord: {e}", "error")
            return False

# ── Quest Helpers ─────────────────────────────────────────────────────────────
def _get(d: Optional[dict], *keys):
    if d is None:
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None

def get_task_config(quest: dict) -> Optional[dict]:
    cfg = quest.get("config", {})
    return _get(cfg, "taskConfig", "task_config", "taskConfigV2", "task_config_v2")

def get_quest_name(quest: dict) -> str:
    cfg = quest.get("config", {})
    msgs = cfg.get("messages", {})
    name = _get(msgs, "questName", "quest_name")
    if name:
        return name.strip()
    game = _get(msgs, "gameTitle", "game_title")
    if game:
        return game.strip()
    app_name = cfg.get("application", {}).get("name")
    if app_name:
        return app_name
    return f"Quest#{quest.get('id', '?')}"

def get_expires_at(quest: dict) -> Optional[str]:
    cfg = quest.get("config", {})
    return _get(cfg, "expiresAt", "expires_at")

def get_user_status(quest: dict) -> dict:
    us = _get(quest, "userStatus", "user_status")
    return us if isinstance(us, dict) else {}

def is_completable(quest: dict) -> bool:
    expires = get_expires_at(quest)
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return False
        except Exception:
            pass

    tc = get_task_config(quest)
    if not tc or "tasks" not in tc:
        return False

    tasks = tc["tasks"]
    for t in tasks:
        if t in UNSUPPORTED_TASKS:
            return False
    return any(tasks.get(t) is not None for t in SUPPORTED_TASKS)

def is_enrolled(quest: dict) -> bool:
    us = get_user_status(quest)
    return bool(_get(us, "enrolledAt", "enrolled_at"))

def is_completed(quest: dict) -> bool:
    us = get_user_status(quest)
    return bool(_get(us, "completedAt", "completed_at"))

def get_task_type(quest: dict) -> Optional[str]:
    tc = get_task_config(quest)
    if not tc or "tasks" not in tc:
        return None
    for t in SUPPORTED_TASKS:
        if tc["tasks"].get(t) is not None:
            return t
    return None

def get_seconds_needed(quest: dict) -> int:
    tc = get_task_config(quest)
    task_type = get_task_type(quest)
    if not tc or not task_type:
        return 0
    return tc["tasks"][task_type].get("target", 0)

def get_seconds_done(quest: dict) -> float:
    task_type = get_task_type(quest)
    if not task_type:
        return 0
    us = get_user_status(quest)
    progress = us.get("progress", {})
    if not progress:
        progress = {}
    return progress.get(task_type, {}).get("value", 0)

def get_enrolled_at(quest: dict) -> Optional[str]:
    us = get_user_status(quest)
    return _get(us, "enrolledAt", "enrolled_at")

def is_quest_expired(quest: dict) -> bool:
    expires = get_expires_at(quest)
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            return exp_dt <= datetime.now(timezone.utc)
        except Exception:
            return False
    return False

# ── Core Logic ─────────────────────────────────────────────────────────────────
class QuestAutocompleter:
    def __init__(self, api: DiscordAPI, user_id: str, discord_user_id: int):
        self.api = api
        self.completed_ids: set = set()
        self.user_id = user_id
        self.discord_user_id = discord_user_id
        self.running = False
        self.status_message = None
        self.quests = []
        self.total_quests = 0
        self.completed_quests = 0
        self.enrolled_quests = 0
        self.current_quest = ""
        self.current_progress = 0
        self.current_total = 0
        self.quest_list = []
        self.completed_quests_list = []
        self.expired_quests_list = []
        self.all_quests_completed = False
        self.dm_sent = False
        self.bot = None

    # ── Update Quest List Real-time ──────────────────────────────────────────
    def update_quest_progress(self, name: str, progress: float):
        for q in self.quest_list:
            if q["name"] == name:
                q["progress"] = progress
                break

    # ── Send DM Notification ──────────────────────────────────────────────────
    async def send_dm_notification(self):
        try:
            user = await self.bot.fetch_user(self.discord_user_id)
            
            fields = {
                "📊 Summary": f"✅ Total Completed: {self.completed_quests}\n📋 Total Quests: {self.total_quests}\n⌛ Expired Quests: {len(self.expired_quests_list)}"
            }
            
            if self.completed_quests_list:
                completed_text = ""
                for i, q in enumerate(self.completed_quests_list[-10:], 1):
                    completed_text += f"✅ {q['name'][:30]} — ⏰ {q['completed_at']}\n"
                fields["🏆 Completed Quests"] = completed_text[:1024]
            
            view = build_status_view("🎉 All Quests Completed!", fields, color=discord.Color.gold())
            
            await user.send(view=view)
            log(f"DM notification sent to user {self.discord_user_id}", "ok")
            self.dm_sent = True
            
        except discord.Forbidden:
            log(f"Cannot send DM to user {self.discord_user_id} (DMs disabled)", "warn")
        except Exception as e:
            log(f"Error sending DM: {e}", "error")

    async def send_no_quests_notification(self):
        try:
            user = await self.bot.fetch_user(self.discord_user_id)
            
            fields = {
                "📊 Status": f"📭 No quests available",
                "📋 Statistics": f"Total Quests: {self.total_quests}\n"
                                f"Completed: {self.completed_quests}\n"
                                f"Expired: {len(self.expired_quests_list)}\n"
                                f"Available: 0"
            }
            
            view = build_status_view("📭 No Quests Available", fields, color=discord.Color.gold())
            
            await user.send(view=view)
            log(f"DM notification sent to user {self.discord_user_id} (No quests)", "ok")
            self.dm_sent = True
            
        except discord.Forbidden:
            log(f"Cannot send DM to user {self.discord_user_id} (DMs disabled)", "warn")
        except Exception as e:
            log(f"Error sending DM: {e}", "error")

    # ── Fetch Quests ──────────────────────────────────────────────────────────
    def fetch_quests(self) -> list:
        try:
            r = self.api.get("/quests/@me")

            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    quests = data.get("quests", [])
                    excluded = data.get("excluded_quests", [])
                    blocked = _get(data, "quest_enrollment_blocked_until")
                    if blocked:
                        log(f"Enrollment blocked until: {blocked}", "warn")
                    if excluded:
                        log(f"{len(excluded)} quest(s) excluded", "debug")
                    return quests
                elif isinstance(data, list):
                    return data
                return []

            elif r.status_code == 429:
                retry_after = r.json().get("retry_after", 10)
                log(f"Rate limited – waiting {retry_after}s", "warn")
                time.sleep(retry_after)
                return self.fetch_quests()
            else:
                log(f"Quest fetch error ({r.status_code}): {r.text[:200]}", "warn")
                return []

        except Exception as e:
            log(f"Error fetching quests: {e}", "error")
            if DEBUG:
                traceback.print_exc()
            return []

    # ── Enroll Quest ──────────────────────────────────────────────────────────
    def enroll_quest(self, quest: dict) -> bool:
        name = get_quest_name(quest)
        qid = quest["id"]

        for attempt in range(1, 4):
            try:
                r = self.api.post(f"/quests/{qid}/enroll", {
                    "location": 11,
                    "is_targeted": False,
                    "metadata_raw": None,
                    "metadata_sealed": None,
                    "traffic_metadata_raw": quest.get("traffic_metadata_raw"),
                    "traffic_metadata_sealed": quest.get("traffic_metadata_sealed"),
                })

                if r.status_code == 429:
                    retry_after = r.json().get("retry_after", 5)
                    wait = retry_after + 1
                    log(f"Rate limited enrolling \"{name}\" (attempt {attempt}/3) – waiting {wait}s", "warn")
                    time.sleep(wait)
                    continue

                if r.status_code in (200, 201, 204):
                    log(f"Enrolled: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                    return True

                log(f"Enroll \"{name}\" failed ({r.status_code}): {r.text[:200]}", "warn")
                return False

            except Exception as e:
                log(f"Error enrolling \"{name}\": {e}", "error")
                return False

        log(f"Skipping \"{name}\" after 3 rate limits", "warn")
        return False

    def auto_accept(self, quests: list) -> list:
        if not AUTO_ACCEPT:
            return quests

        unaccepted = [
            q for q in quests
            if not is_enrolled(q) and not is_completed(q) and is_completable(q)
        ]

        if not unaccepted:
            return quests

        log(f"Found {len(unaccepted)} unaccepted quests – auto-accepting...", "info")

        for q in unaccepted:
            self.enroll_quest(q)
            time.sleep(3)

        time.sleep(2)
        return self.fetch_quests()

    # ── Complete Video ────────────────────────────────────────────────────────
    async def complete_video(self, quest: dict):
        name = get_quest_name(quest)
        qid = quest["id"]
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)
        enrolled_at_str = get_enrolled_at(quest)

        if enrolled_at_str:
            enrolled_ts = datetime.fromisoformat(enrolled_at_str.replace("Z", "+00:00")).timestamp()
        else:
            enrolled_ts = time.time()

        log(f"🎬 Video: {Colors.BOLD}{name}{Colors.RESET} ({seconds_done:.0f}/{seconds_needed}s)", "info")

        self.current_progress = seconds_done
        self.current_total = seconds_needed

        max_future = 10
        speed = 7
        interval = 1

        while seconds_done < seconds_needed and self.running:
            max_allowed = (time.time() - enrolled_ts) + max_future
            diff = max_allowed - seconds_done
            timestamp = seconds_done + speed

            if diff >= speed:
                try:
                    r = self.api.post(f"/quests/{qid}/video-progress", {
                        "timestamp": min(seconds_needed, timestamp + random.random())
                    })
                    if r.status_code == 200:
                        body = r.json()
                        if body.get("completed_at"):
                            log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                            self.current_progress = seconds_needed
                            self.update_quest_progress(name, seconds_needed)
                            await self.update_status()
                            return
                        seconds_done = min(seconds_needed, timestamp)
                        self.current_progress = seconds_done
                        self.update_quest_progress(name, seconds_done)
                        log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                        await self.update_status()
                    elif r.status_code == 429:
                        retry_after = r.json().get("retry_after", 5)
                        log(f"  Rate limited – waiting {retry_after + 1}s", "warn")
                        await asyncio.sleep(retry_after + 1)
                        continue
                    else:
                        log(f"  Video progress error ({r.status_code}): {r.text[:200]}", "warn")
                except Exception as e:
                    log(f"  Error: {e}", "error")

            if timestamp >= seconds_needed:
                break
            await asyncio.sleep(interval)

        try:
            self.api.post(f"/quests/{qid}/video-progress", {"timestamp": seconds_needed})
        except Exception:
            pass
        self.current_progress = seconds_needed
        self.update_quest_progress(name, seconds_needed)
        log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
        await self.update_status()

    # ── Complete Heartbeat ────────────────────────────────────────────────────
    async def complete_heartbeat(self, quest: dict):
        name = get_quest_name(quest)
        qid = quest["id"]
        task_type = get_task_type(quest)
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)

        self.current_progress = seconds_done
        self.current_total = seconds_needed

        remaining = max(0, seconds_needed - seconds_done)
        log(
            f"🎮 {task_type}: {Colors.BOLD}{name}{Colors.RESET} "
            f"(~{remaining // 60} minutes remaining)",
            "info"
        )

        pid = random.randint(1000, 30000)

        while seconds_done < seconds_needed and self.running:
            try:
                r = self.api.post(f"/quests/{qid}/heartbeat", {
                    "stream_key": f"call:0:{pid}",
                    "terminal": False,
                })

                if r.status_code == 200:
                    body = r.json()
                    progress_data = body.get("progress", {})
                    if progress_data and task_type in progress_data:
                        seconds_done = progress_data[task_type].get("value", seconds_done)
                        self.current_progress = seconds_done
                        self.update_quest_progress(name, seconds_done)
                    log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                    await self.update_status()

                    if body.get("completed_at") or seconds_done >= seconds_needed:
                        log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                        self.current_progress = seconds_needed
                        self.update_quest_progress(name, seconds_needed)
                        await self.update_status()
                        return

                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 10)
                    log(f"  Rate limited – waiting {retry_after + 1}s", "warn")
                    await asyncio.sleep(retry_after + 1)
                    continue
                else:
                    log(f"  Heartbeat error ({r.status_code}): {r.text[:200]}", "warn")

            except Exception as e:
                log(f"  Heartbeat error: {e}", "error")

            await asyncio.sleep(HEARTBEAT_INTERVAL)

        try:
            self.api.post(f"/quests/{qid}/heartbeat", {
                "stream_key": f"call:0:{pid}",
                "terminal": True,
            })
        except Exception:
            pass
        self.current_progress = seconds_needed
        self.update_quest_progress(name, seconds_needed)
        log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
        await self.update_status()

    # ── Complete Activity ─────────────────────────────────────────────────────
    async def complete_activity(self, quest: dict):
        name = get_quest_name(quest)
        qid = quest["id"]
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)

        self.current_progress = seconds_done
        self.current_total = seconds_needed

        remaining = max(0, seconds_needed - seconds_done)
        log(
            f"🕹️ Activity: {Colors.BOLD}{name}{Colors.RESET} "
            f"(~{remaining // 60} minutes remaining)",
            "info"
        )

        stream_key = "call:0:1"

        while seconds_done < seconds_needed and self.running:
            try:
                r = self.api.post(f"/quests/{qid}/heartbeat", {
                    "stream_key": stream_key,
                    "terminal": False,
                })

                if r.status_code == 200:
                    body = r.json()
                    progress_data = body.get("progress", {})
                    if progress_data and "PLAY_ACTIVITY" in progress_data:
                        seconds_done = progress_data["PLAY_ACTIVITY"].get("value", seconds_done)
                        self.current_progress = seconds_done
                        self.update_quest_progress(name, seconds_done)
                    log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                    await self.update_status()

                    if body.get("completed_at") or seconds_done >= seconds_needed:
                        break
                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 10)
                    log(f"  Rate limited – waiting {retry_after + 1}s", "warn")
                    await asyncio.sleep(retry_after + 1)
                    continue
                else:
                    log(f"  Heartbeat error ({r.status_code}): {r.text[:200]}", "warn")
            except Exception as e:
                log(f"  Error: {e}", "error")

            await asyncio.sleep(HEARTBEAT_INTERVAL)

        try:
            self.api.post(f"/quests/{qid}/heartbeat", {
                "stream_key": stream_key,
                "terminal": True,
            })
        except Exception:
            pass
        self.current_progress = seconds_needed
        self.update_quest_progress(name, seconds_needed)
        log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
        await self.update_status()

    # ── Process Quest ────────────────────────────────────────────────────────
    async def process_quest(self, quest: dict):
        qid = quest.get("id")
        name = get_quest_name(quest)
        task_type = get_task_type(quest)

        if not task_type:
            log(f"\"{name}\" – unsupported task, skipping", "warn")
            return

        if task_type in UNSUPPORTED_TASKS:
            log(f"⚠️ \"{name}\" – {task_type} not supported (requires real interaction)", "warn")
            return

        if qid in self.completed_ids:
            return

        self.current_quest = name
        self.current_progress = 0
        self.current_total = 0
        log(f"━━━ Starting: {Colors.BOLD}{name}{Colors.RESET} (task: {task_type}) ━━━", "info")

        if task_type in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"):
            await self.complete_video(quest)
        elif task_type in ("PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP"):
            await self.complete_heartbeat(quest)
        elif task_type == "PLAY_ACTIVITY":
            await self.complete_activity(quest)

        self.completed_ids.add(qid)
        self.completed_quests += 1

        self.completed_quests_list.append({
            "name": name,
            "task": task_type,
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        self.current_quest = ""
        self.current_progress = 0
        self.current_total = 0
        await self.update_status()

    # ── Run Quests ────────────────────────────────────────────────────────────
    async def run_quests(self):
        self.running = True
        self.completed_quests = 0
        self.completed_ids = set()
        self.completed_quests_list = []
        self.expired_quests_list = []
        self.all_quests_completed = False
        self.dm_sent = False

        log("=" * 60, "info")
        log(f"{Colors.BOLD}Discord Quest Auto-Completer v3.0{Colors.RESET}", "info")
        log(f"Auto-accept: {'ON' if AUTO_ACCEPT else 'OFF'}  |  Poll: {POLL_INTERVAL}s", "info")
        log("=" * 60, "info")

        cycle = 0
        while self.running:
            cycle += 1
            log(f"── Scan #{cycle} ──", "info")

            self.quests = self.fetch_quests()
            total = len(self.quests)
            self.total_quests = total

            self.quest_list = []
            self.expired_quests_list = []
            
            for q in self.quests:
                name = get_quest_name(q)
                task = get_task_type(q) or "?"
                status = "✅ Completed" if is_completed(q) else "▶ Enrolled" if is_enrolled(q) else "⭕ Available"
                
                if task in UNSUPPORTED_TASKS:
                    status = "🚫 Unsupported"
                
                if is_quest_expired(q):
                    status = "⌛ Expired"
                    self.expired_quests_list.append({
                        "name": name,
                        "task": task,
                        "expires": get_expires_at(q)
                    })
                
                progress = 0
                total_time = 0
                if is_enrolled(q) and not is_completed(q) and task not in UNSUPPORTED_TASKS and not is_quest_expired(q):
                    total_time = get_seconds_needed(q)
                    progress = get_seconds_done(q)
                
                self.quest_list.append({
                    "name": name,
                    "task": task,
                    "status": status,
                    "progress": progress,
                    "total": total_time,
                    "is_expired": is_quest_expired(q)
                })

            if not self.quests:
                log("No quests found", "info")
                await self.update_status("No quests found")
            else:
                enrolled_count = sum(1 for q in self.quests if is_enrolled(q))
                completed_count = sum(1 for q in self.quests if is_completed(q))
                completable_count = sum(1 for q in self.quests if is_completable(q))
                expired_count = len(self.expired_quests_list)
                self.enrolled_quests = enrolled_count

                log(
                    f"Total: {total} quests | Enrolled: {enrolled_count} | "
                    f"Completed: {completed_count} | Completable: {completable_count} | Expired: {expired_count}",
                    "info"
                )

                self.quests = self.auto_accept(self.quests)

                actionable = [
                    q for q in self.quests
                    if is_enrolled(q) and not is_completed(q) and is_completable(q)
                    and q.get("id") not in self.completed_ids
                    and not is_quest_expired(q)
                ]

                if actionable:
                    log(f"\n{len(actionable)} quest(s) need completion:", "info")
                    for q in actionable:
                        if not self.running:
                            break
                        await self.process_quest(q)
                else:
                    log("No quests need completion at this time", "info")
                    await self.update_status("No quests need completion")
                    
                    # ── KIỂM TRA VÀ GỬI DM ──
                    if not self.dm_sent:
                        # Đếm số quest còn lại có thể làm
                        remaining_quests = [
                            q for q in self.quests
                            if not is_completed(q) and not is_quest_expired(q) and is_completable(q)
                        ]
                        
                        log(f"Remaining completable quests: {len(remaining_quests)}", "info")
                        
                        # Nếu không còn quest nào có thể làm
                        if len(remaining_quests) == 0:
                            if self.completed_quests > 0:
                                # Đã hoàn thành tất cả quest
                                self.all_quests_completed = True
                                log("🎉 All quests completed! Sending DM notification...", "ok")
                                await self.send_dm_notification()
                            else:
                                # Chưa có quest nào hoàn thành, không có quest để làm
                                log("📭 No quests available to complete", "info")
                                await self.send_no_quests_notification()

            if not self.running:
                break

            log(f"\nWaiting {POLL_INTERVAL}s...\n", "info")
            for _ in range(POLL_INTERVAL):
                if not self.running:
                    break
                await asyncio.sleep(1)

        log("Stopped auto quest completion.", "info")
        await self.update_status("Stopped")

    # ── Progress Bar ──────────────────────────────────────────────────────────
    def create_progress_bar(self, progress: float, total: float, length: int = 15) -> str:
        if total <= 0:
            return "⬜" * length
        percentage = min(progress / total, 1.0)
        filled = int(percentage * length)
        empty = length - filled
        return "🟧" * filled + "⬜" * empty

    # ── Create Status View ────────────────────────────────────────────────────
    def create_status_view(self) -> ui.LayoutView:
        view = ui.LayoutView()
        items = [
            ui.TextDisplay("## 📊 Quest Status"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"**Status:** {'🟢 Running' if self.running else '🔴 Stopped'}"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                f"**📋 Statistics**\n"
                f"Total Quests: {self.total_quests}\n"
                f"Enrolled: {self.enrolled_quests}\n"
                f"Completed: {self.completed_quests}\n"
                f"Expired: {len(self.expired_quests_list)}"
            ),
        ]
        
        # ── Currently Doing ──────────────────────────────────────────────────
        if self.current_quest and self.current_total > 0:
            percentage = (self.current_progress / self.current_total) * 100
            bar = self.create_progress_bar(self.current_progress, self.current_total)
            items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
            items.append(ui.TextDisplay(
                f"**🔄 Currently Doing**\n"
                f"**{self.current_quest}**\n"
                f"`{bar}` {percentage:.1f}%\n"
                f"⏱️ {self.current_progress:.0f}/{self.current_total}s"
            ))

        # ── Active Quests ────────────────────────────────────────────────────
        if self.quest_list:
            quest_text = ""
            active_count = 0
            for q in self.quest_list[:20]:
                if q["status"] == "▶ Enrolled" and not q["is_expired"] and q["total"] > 0:
                    active_count += 1
                    bar = self.create_progress_bar(q["progress"], q["total"])
                    percent = int((q["progress"] / q["total"]) * 100)
                    quest_text += f"▶ **{q['name'][:30]}**\n"
                    quest_text += f"   `{bar}` {percent}% ({q['progress']:.0f}/{q['total']}s)\n"
            
            if quest_text:
                items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
                items.append(ui.TextDisplay(f"**📋 Active Quests ({active_count})**\n{quest_text[:1500]}"))

        # ── Recently Completed ──────────────────────────────────────────────
        if self.completed_quests_list:
            completed_text = ""
            for i, q in enumerate(self.completed_quests_list[-5:], 1):
                completed_text += f"✅ {q['name'][:25]} — ⏰ {q['completed_at']}\n"
            
            if completed_text:
                items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
                items.append(ui.TextDisplay(f"**🏆 Recently Completed ({len(self.completed_quests_list)})**\n{completed_text[:1024]}"))

        if self.all_quests_completed:
            items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
            items.append(ui.TextDisplay("**🎉 All quests completed! 🎊**\nDM notification sent!"))

        items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
        items.append(ui.TextDisplay(
            "🔄 Running... Click Stop to stop" if self.running else "⏹️ Stopped"
        ))

        color = discord.Color.gold()
        container = ui.Container(*items, accent_color=color)
        view.add_item(container)
        return view

    # ── Update Status ─────────────────────────────────────────────────────────
    async def update_status(self, custom_status: str = None):
        if not self.status_message:
            return

        view = self.create_status_view()

        try:
            await self.status_message.edit(view=view)
        except discord.errors.NotFound:
            log("Status message deleted, cannot update!", "warn")
        except discord.errors.HTTPException as e:
            if "401" in str(e) or "50027" in str(e):
                log("Cannot update status due to webhook error. Bot still running normally!", "warn")
            else:
                raise e

    def stop(self):
        self.running = False

# ── Bot ────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, owner_id=OWNER_ID)

active_completers = {}

def is_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != bot.owner_id:
            raise app_commands.CheckFailure("Owner Only")
        return True
    return app_commands.check(predicate)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        text = "Only The Bot Owner Can Use This Command."
    else:
        text = f"Something Went Wrong: {error}"
    view = build_v2_view("❌ Error", [text], color=discord.Color.gold())
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)

# ── Quest View ──────────────────────────────────────────────────────────────────
class QuestView(ui.LayoutView):
    def __init__(self, completer: QuestAutocompleter = None, user_id: str = None):
        super().__init__(timeout=None)
        self.completer = completer
        self.user_id = user_id
        self.status_message = None

        container = ui.Container(
            ui.TextDisplay("## 🎮 Quest Auto-Completer"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                "Automatically scan, enroll, and complete Discord quests!\n\n"
                "**📋 Instructions**\n"
                "1. Click **Start** to begin\n"
                "2. Enter your Discord token\n"
                "3. Bot will automatically complete quests for you\n"
                "4. Click **Status** to view progress\n"
                "5. Get **DM notification** when all quests are done!\n\n"
                "**⚠️ Notes**\n"
                "• Token is only used in this session\n"
                "• Bot will auto-enroll and complete quests\n"
                "• Use **Stop** button to stop anytime\n"
                "• DM will be sent when all quests are completed"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.ActionRow(
                ui.Button(label="▶️ Start", style=discord.ButtonStyle.green, custom_id="quest_start"),
                ui.Button(label="⏹️ Stop", style=discord.ButtonStyle.red, custom_id="quest_stop"),
                ui.Button(label="📊 Status", style=discord.ButtonStyle.blurple, custom_id="quest_status"),
            ),
            accent_color=discord.Color.gold(),
        )
        self.add_item(container)

# ── Token Modal ──────────────────────────────────────────────────────────────
class TokenModal(discord.ui.Modal, title="Enter Discord Token"):
    token_input = discord.ui.TextInput(
        label="Discord Token",
        placeholder="Enter your Discord token...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        
        if not token:
            view = build_v2_view("❌ Error", ["Token cannot be empty!"], color=discord.Color.gold())
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            build_number = fetch_latest_build_number()
            api = DiscordAPI(token, build_number)
            
            if not api.validate_token():
                view = build_v2_view("❌ Error", ["Invalid token! Please check and try again."], color=discord.Color.gold())
                await interaction.followup.send(view=view, ephemeral=True)
                return

            r = api.get("/users/@me")
            user_data = r.json()
            token_username = user_data.get("username", "Unknown")
            token_user_id = user_data.get("id", "Unknown")

            completer = QuestAutocompleter(api, token_user_id, interaction.user.id)
            completer.bot = bot
            active_completers[str(interaction.user.id)] = completer

            view = build_v2_view(
                "✅ Success",
                [
                    f"Successfully logged in with token of **{token_username}**!",
                    "",
                    "Click **📊 Status** to view quest progress.",
                    "You will receive a **DM notification** when all quests are completed! 📬"
                ],
                color=discord.Color.gold()
            )
            
            await interaction.followup.send(view=view, ephemeral=True)

            asyncio.create_task(completer.run_quests())

            new_view = QuestView(completer, str(interaction.user.id))
            await interaction.edit_original_response(view=new_view)

        except Exception as e:
            view = build_v2_view("❌ Error", [str(e)], color=discord.Color.gold())
            await interaction.followup.send(view=view, ephemeral=True)

# ── Bot Events ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f'✅ Bot logged in successfully!')
    print(f'📊 Bot Name: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👑 Owner ID: {bot.owner_id}')
    print('─' * 40)
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} slash commands!')
    except Exception as e:
        print(f'❌ Error syncing slash commands: {e}')

# ── Interaction Handler ──────────────────────────────────────────────────────
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    
    custom_id = interaction.data.get("custom_id", "")
    
    if custom_id == "quest_start":
        if interaction.user.id != OWNER_ID:
            view = build_v2_view("❌ Permission Denied", ["Only the bot owner can start quests!"], color=discord.Color.gold())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        modal = TokenModal()
        await interaction.response.send_modal(modal)
    
    elif custom_id == "quest_stop":
        completer = active_completers.get(str(interaction.user.id))
        
        if not completer:
            view = build_v2_view("❌ Error", ["No active quest session found!"], color=discord.Color.gold())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        if not completer.running:
            view = build_v2_view("⚠️ Warning", ["Quest is not running!"], color=discord.Color.gold())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        completer.stop()
        view = build_v2_view("✅ Stopped", ["Stopped auto quest completion."], color=discord.Color.gold())
        await interaction.response.send_message(view=view, ephemeral=True)
    
    elif custom_id == "quest_status":
        completer = active_completers.get(str(interaction.user.id))
        
        if not completer:
            view = build_v2_view("❌ Error", ["No active quest session found!"], color=discord.Color.gold())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        view = completer.create_status_view()
        
        message_exists = False
        if completer.status_message:
            try:
                await completer.status_message.fetch()
                message_exists = True
            except discord.errors.NotFound:
                completer.status_message = None
                message_exists = False
            except Exception as e:
                log(f"Error checking message: {e}", "warn")
                message_exists = False
        
        if message_exists:
            try:
                await completer.status_message.edit(view=view)
                await interaction.response.defer()
                return
            except Exception as e:
                log(f"Error editing status message: {e}", "warn")
                completer.status_message = None
        
        await interaction.response.send_message(view=view, ephemeral=True)
        msg = await interaction.original_response()
        completer.status_message = msg

# ── Slash Commands ─────────────────────────────────────────────────────────────
@bot.tree.command(name="quest", description="[Owner] Auto complete Discord quests")
@is_owner()
async def quest_command(interaction: discord.Interaction):
    view = QuestView()
    await interaction.response.send_message(view=view, ephemeral=False)

@bot.tree.command(name="ping", description="[Owner] Check bot latency")
@is_owner()
async def ping_command(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = discord.Color.gold()
    view = build_v2_view(
        "🏓 Pong!",
        [
            f"**📡 Latency:** `{latency}ms`",
            f"**🔄 Status:** {'🟢 Online' if latency < 200 else '🟡 Slow' if latency < 400 else '🔴 Very Slow'}"
        ],
        color=color
    )
    await interaction.response.send_message(view=view, ephemeral=True)

# ── Normal Commands ──────────────────────────────────────────────────────────
@bot.command(name="sync")
@commands.is_owner()
async def sync_command(ctx: commands.Context):
    try:
        synced = await bot.tree.sync()
        view = build_v2_view("✅ Success", [f"Synced {len(synced)} slash commands!"], color=discord.Color.gold())
        await ctx.send(view=view)
    except Exception as e:
        view = build_v2_view("❌ Error", [str(e)], color=discord.Color.gold())
        await ctx.send(view=view)

@sync_command.error
async def sync_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.NotOwner):
        view = build_v2_view("❌ Permission Denied", ["Only the bot owner can use this command!"], color=discord.Color.gold())
        await ctx.send(view=view)
    else:
        view = build_v2_view("❌ Error", [str(error)], color=discord.Color.gold())
        await ctx.send(view=view)

# ── Main Entry ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please replace TOKEN with your bot token!")
        print("📝 Open file and edit: TOKEN = 'YOUR_BOT_TOKEN_HERE'")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid bot token! Please check and try again.")
    except Exception as e:
        print(f"❌ Error: {e}")
