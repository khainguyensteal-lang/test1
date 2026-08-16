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
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.getenv("BOT_OWNER_ID", "1512303397120901191"))

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
def BuildV2View(title: str, lines: list[str], color: discord.Color = discord.Color.gold()) -> ui.LayoutView:
    """Build A Simple Components V2 Message"""
    view = ui.LayoutView()
    container = ui.Container(
        ui.TextDisplay(f"## {title}"),
        ui.Separator(spacing=discord.SeparatorSpacing.small),
        ui.TextDisplay("\n".join(lines)),
        accent_color=color,
    )
    view.add_item(container)
    return view

def BuildStatusView(title: str, fields: dict, color: discord.Color = discord.Color.gold()) -> ui.LayoutView:
    """Build A Components V2 View With Multiple Fields"""
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

def Log(msg: str, level: str = "info"):
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
def FetchLatestBuildNumber() -> int:
    FALLBACK = 504649
    try:
        Log("Fetching Latest Build Number From Discord...", "info")
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        r = requests.get("https://discord.com/app", headers={"User-Agent": ua}, timeout=15)
        if r.status_code != 200:
            Log(f"Failed To Fetch Discord Page ({r.status_code}), Using Fallback", "warn")
            return FALLBACK

        scripts = re.findall(r'/assets/([a-f0-9]+)\.js', r.text)
        if not scripts:
            scripts_alt = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
            scripts = [s.split('/')[-1].replace('.js', '') for s in scripts_alt]

        if not scripts:
            Log("No JS Assets Found, Using Fallback", "warn")
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
                    Log(f"Build Number: {Colors.BOLD}{bn}{Colors.RESET}", "ok")
                    return bn
            except Exception:
                continue

        Log(f"Build Number Not Found, Using Fallback {FALLBACK}", "warn")
        return FALLBACK
    except Exception as e:
        Log(f"Error Fetching Build Number: {e}, Using Fallback {FALLBACK}", "warn")
        return FALLBACK

def MakeSuperProperties(build_number: int) -> str:
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
        sp = MakeSuperProperties(build_number)
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

    def Get(self, path: str, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        Log(f"GET {path}", "debug")
        r = self.session.get(url, **kwargs)
        Log(f"  -> {r.status_code} ({len(r.content)} bytes)", "debug")
        return r

    def Post(self, path: str, payload: Optional[dict] = None, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        Log(f"POST {path}", "debug")
        r = self.session.post(url, json=payload, **kwargs)
        Log(f"  -> {r.status_code} ({len(r.content)} bytes)", "debug")
        return r

    def ValidateToken(self) -> bool:
        try:
            r = self.Get("/users/@me")
            if r.status_code == 200:
                user = r.json()
                name = user.get("username", "?")
                Log(f"Logged In: {Colors.BOLD}{name}{Colors.RESET} (ID: {user['id']})", "ok")
                return True
            else:
                Log(f"Invalid Token (Status {r.status_code})", "error")
                return False
        except Exception as e:
            Log(f"Cannot Connect To Discord: {e}", "error")
            return False

# ── Quest Helpers ─────────────────────────────────────────────────────────────
def _Get(d: Optional[dict], *keys):
    if d is None:
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None

def GetTaskConfig(quest: dict) -> Optional[dict]:
    cfg = quest.get("config", {})
    return _Get(cfg, "taskConfig", "task_config", "taskConfigV2", "task_config_v2")

def GetQuestName(quest: dict) -> str:
    cfg = quest.get("config", {})
    msgs = cfg.get("messages", {})
    name = _Get(msgs, "questName", "quest_name")
    if name:
        return name.strip()
    game = _Get(msgs, "gameTitle", "game_title")
    if game:
        return game.strip()
    app_name = cfg.get("application", {}).get("name")
    if app_name:
        return app_name
    return f"Quest#{quest.get('id', '?')}"

def GetExpiresAt(quest: dict) -> Optional[str]:
    cfg = quest.get("config", {})
    return _Get(cfg, "expiresAt", "expires_at")

def GetUserStatus(quest: dict) -> dict:
    us = _Get(quest, "userStatus", "user_status")
    return us if isinstance(us, dict) else {}

def IsCompletable(quest: dict) -> bool:
    expires = GetExpiresAt(quest)
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return False
        except Exception:
            pass

    tc = GetTaskConfig(quest)
    if not tc or "tasks" not in tc:
        return False

    tasks = tc["tasks"]
    for t in tasks:
        if t in UNSUPPORTED_TASKS:
            return False
    return any(tasks.get(t) is not None for t in SUPPORTED_TASKS)

def IsEnrolled(quest: dict) -> bool:
    us = GetUserStatus(quest)
    return bool(_Get(us, "enrolledAt", "enrolled_at"))

def IsCompleted(quest: dict) -> bool:
    us = GetUserStatus(quest)
    return bool(_Get(us, "completedAt", "completed_at"))

def GetTaskType(quest: dict) -> Optional[str]:
    tc = GetTaskConfig(quest)
    if not tc or "tasks" not in tc:
        return None
    for t in SUPPORTED_TASKS:
        if tc["tasks"].get(t) is not None:
            return t
    return None

def GetSecondsNeeded(quest: dict) -> int:
    tc = GetTaskConfig(quest)
    task_type = GetTaskType(quest)
    if not tc or not task_type:
        return 0
    return tc["tasks"][task_type].get("target", 0)

def GetSecondsDone(quest: dict) -> float:
    task_type = GetTaskType(quest)
    if not task_type:
        return 0
    us = GetUserStatus(quest)
    progress = us.get("progress", {})
    if not progress:
        progress = {}
    return progress.get(task_type, {}).get("value", 0)

def GetEnrolledAt(quest: dict) -> Optional[str]:
    us = GetUserStatus(quest)
    return _Get(us, "enrolledAt", "enrolled_at")

def IsQuestExpired(quest: dict) -> bool:
    expires = GetExpiresAt(quest)
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
        self.should_stop = False
        self.stopped_reason = ""
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

    # ── Update Quest List Real-Time ──────────────────────────────────────────
    def UpdateQuestProgress(self, name: str, progress: float):
        for q in self.quest_list:
            if q["name"] == name:
                q["progress"] = progress
                break

    # ── Send DM Notification ──────────────────────────────────────────────────
    async def SendDMNotification(self):
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
            
            view = BuildStatusView("🎉 All Quests Completed!", fields, color=discord.Color.gold())
            
            await user.send(view=view)
            Log(f"DM Notification Sent To User {self.discord_user_id}", "ok")
            self.dm_sent = True
            
        except discord.Forbidden:
            Log(f"Cannot Send DM To User {self.discord_user_id} (DMs Disabled)", "warn")
        except Exception as e:
            Log(f"Error Sending DM: {e}", "error")

    async def SendNoQuestsNotification(self):
        try:
            user = await self.bot.fetch_user(self.discord_user_id)
            
            fields = {
                "📊 Status": f"📭 No Quests Available",
                "📋 Statistics": f"Total Quests: {self.total_quests}\n"
                                f"Completed: {self.completed_quests}\n"
                                f"Expired: {len(self.expired_quests_list)}\n"
                                f"Available: 0"
            }
            
            view = BuildStatusView("📭 No Quests Available", fields, color=discord.Color.gold())
            
            await user.send(view=view)
            Log(f"DM Notification Sent To User {self.discord_user_id} (No Quests)", "ok")
            self.dm_sent = True
            
        except discord.Forbidden:
            Log(f"Cannot Send DM To User {self.discord_user_id} (DMs Disabled)", "warn")
        except Exception as e:
            Log(f"Error Sending DM: {e}", "error")

    # ── Fetch Quests ──────────────────────────────────────────────────────────
    def FetchQuests(self) -> list:
        try:
            r = self.api.Get("/quests/@me")

            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    quests = data.get("quests", [])
                    excluded = data.get("excluded_quests", [])
                    blocked = _Get(data, "quest_enrollment_blocked_until")
                    if blocked:
                        Log(f"Enrollment Blocked Until: {blocked}", "warn")
                    if excluded:
                        Log(f"{len(excluded)} Quest(s) Excluded", "debug")
                    return quests
                elif isinstance(data, list):
                    return data
                return []

            elif r.status_code == 429:
                retry_after = r.json().get("retry_after", 10)
                Log(f"Rate Limited – Waiting {retry_after}s", "warn")
                time.sleep(retry_after)
                return self.FetchQuests()
            else:
                Log(f"Quest Fetch Error ({r.status_code}): {r.text[:200]}", "warn")
                return []

        except Exception as e:
            Log(f"Error Fetching Quests: {e}", "error")
            if DEBUG:
                traceback.print_exc()
            return []

    # ── Enroll Quest ──────────────────────────────────────────────────────────
    def EnrollQuest(self, quest: dict) -> bool:
        name = GetQuestName(quest)
        qid = quest["id"]

        for attempt in range(1, 4):
            try:
                r = self.api.Post(f"/quests/{qid}/enroll", {
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
                    Log(f"Rate Limited Enrolling \"{name}\" (Attempt {attempt}/3) – Waiting {wait}s", "warn")
                    time.sleep(wait)
                    continue

                if r.status_code in (200, 201, 204):
                    Log(f"Enrolled: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                    return True

                Log(f"Enroll \"{name}\" Failed ({r.status_code}): {r.text[:200]}", "warn")
                return False

            except Exception as e:
                Log(f"Error Enrolling \"{name}\": {e}", "error")
                return False

        Log(f"Skipping \"{name}\" After 3 Rate Limits", "warn")
        return False

    def AutoAccept(self, quests: list) -> list:
        if not AUTO_ACCEPT:
            return quests

        unaccepted = [
            q for q in quests
            if not IsEnrolled(q) and not IsCompleted(q) and IsCompletable(q)
        ]

        if not unaccepted:
            return quests

        Log(f"Found {len(unaccepted)} Unaccepted Quests – Auto-Accepting...", "info")

        for q in unaccepted:
            self.EnrollQuest(q)
            time.sleep(3)

        time.sleep(2)
        return self.FetchQuests()

    # ── Complete Video ────────────────────────────────────────────────────────
    async def CompleteVideo(self, quest: dict):
        name = GetQuestName(quest)
        qid = quest["id"]
        seconds_needed = GetSecondsNeeded(quest)
        seconds_done = GetSecondsDone(quest)
        enrolled_at_str = GetEnrolledAt(quest)

        if enrolled_at_str:
            enrolled_ts = datetime.fromisoformat(enrolled_at_str.replace("Z", "+00:00")).timestamp()
        else:
            enrolled_ts = time.time()

        Log(f"🎬 Video: {Colors.BOLD}{name}{Colors.RESET} ({seconds_done:.0f}/{seconds_needed}s)", "info")

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
                    r = self.api.Post(f"/quests/{qid}/video-progress", {
                        "timestamp": min(seconds_needed, timestamp + random.random())
                    })
                    if r.status_code == 200:
                        body = r.json()
                        if body.get("completed_at"):
                            Log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                            self.current_progress = seconds_needed
                            self.UpdateQuestProgress(name, seconds_needed)
                            await self.UpdateStatus()
                            return
                        seconds_done = min(seconds_needed, timestamp)
                        self.current_progress = seconds_done
                        self.UpdateQuestProgress(name, seconds_done)
                        Log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                        await self.UpdateStatus()
                    elif r.status_code == 429:
                        retry_after = r.json().get("retry_after", 5)
                        Log(f"  Rate Limited – Waiting {retry_after + 1}s", "warn")
                        await asyncio.sleep(retry_after + 1)
                        continue
                    else:
                        Log(f"  Video Progress Error ({r.status_code}): {r.text[:200]}", "warn")
                except Exception as e:
                    Log(f"  Error: {e}", "error")

            if timestamp >= seconds_needed:
                break
            await asyncio.sleep(interval)

        try:
            self.api.Post(f"/quests/{qid}/video-progress", {"timestamp": seconds_needed})
        except Exception:
            pass
        self.current_progress = seconds_needed
        self.UpdateQuestProgress(name, seconds_needed)
        Log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
        await self.UpdateStatus()

    # ── Complete Heartbeat ────────────────────────────────────────────────────
    async def CompleteHeartbeat(self, quest: dict):
        name = GetQuestName(quest)
        qid = quest["id"]
        task_type = GetTaskType(quest)
        seconds_needed = GetSecondsNeeded(quest)
        seconds_done = GetSecondsDone(quest)

        self.current_progress = seconds_done
        self.current_total = seconds_needed

        remaining = max(0, seconds_needed - seconds_done)
        Log(
            f"🎮 {task_type}: {Colors.BOLD}{name}{Colors.RESET} "
            f"(~{remaining // 60} Minutes Remaining)",
            "info"
        )

        pid = random.randint(1000, 30000)

        while seconds_done < seconds_needed and self.running:
            try:
                r = self.api.Post(f"/quests/{qid}/heartbeat", {
                    "stream_key": f"call:0:{pid}",
                    "terminal": False,
                })

                if r.status_code == 200:
                    body = r.json()
                    progress_data = body.get("progress", {})
                    if progress_data and task_type in progress_data:
                        seconds_done = progress_data[task_type].get("value", seconds_done)
                        self.current_progress = seconds_done
                        self.UpdateQuestProgress(name, seconds_done)
                    Log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                    await self.UpdateStatus()

                    if body.get("completed_at") or seconds_done >= seconds_needed:
                        Log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
                        self.current_progress = seconds_needed
                        self.UpdateQuestProgress(name, seconds_needed)
                        await self.UpdateStatus()
                        return

                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 10)
                    Log(f"  Rate Limited – Waiting {retry_after + 1}s", "warn")
                    await asyncio.sleep(retry_after + 1)
                    continue
                else:
                    Log(f"  Heartbeat Error ({r.status_code}): {r.text[:200]}", "warn")

            except Exception as e:
                Log(f"  Heartbeat Error: {e}", "error")

            await asyncio.sleep(HEARTBEAT_INTERVAL)

        try:
            self.api.Post(f"/quests/{qid}/heartbeat", {
                "stream_key": f"call:0:{pid}",
                "terminal": True,
            })
        except Exception:
            pass
        self.current_progress = seconds_needed
        self.UpdateQuestProgress(name, seconds_needed)
        Log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
        await self.UpdateStatus()

    # ── Complete Activity ─────────────────────────────────────────────────────
    async def CompleteActivity(self, quest: dict):
        name = GetQuestName(quest)
        qid = quest["id"]
        seconds_needed = GetSecondsNeeded(quest)
        seconds_done = GetSecondsDone(quest)

        self.current_progress = seconds_done
        self.current_total = seconds_needed

        remaining = max(0, seconds_needed - seconds_done)
        Log(
            f"🕹️ Activity: {Colors.BOLD}{name}{Colors.RESET} "
            f"(~{remaining // 60} Minutes Remaining)",
            "info"
        )

        stream_key = "call:0:1"

        while seconds_done < seconds_needed and self.running:
            try:
                r = self.api.Post(f"/quests/{qid}/heartbeat", {
                    "stream_key": stream_key,
                    "terminal": False,
                })

                if r.status_code == 200:
                    body = r.json()
                    progress_data = body.get("progress", {})
                    if progress_data and "PLAY_ACTIVITY" in progress_data:
                        seconds_done = progress_data["PLAY_ACTIVITY"].get("value", seconds_done)
                        self.current_progress = seconds_done
                        self.UpdateQuestProgress(name, seconds_done)
                    Log(f"  [{name}] {seconds_done:.0f}/{seconds_needed}s", "progress")
                    await self.UpdateStatus()

                    if body.get("completed_at") or seconds_done >= seconds_needed:
                        break
                elif r.status_code == 429:
                    retry_after = r.json().get("retry_after", 10)
                    Log(f"  Rate Limited – Waiting {retry_after + 1}s", "warn")
                    await asyncio.sleep(retry_after + 1)
                    continue
                else:
                    Log(f"  Heartbeat Error ({r.status_code}): {r.text[:200]}", "warn")
            except Exception as e:
                Log(f"  Error: {e}", "error")

            await asyncio.sleep(HEARTBEAT_INTERVAL)

        try:
            self.api.Post(f"/quests/{qid}/heartbeat", {
                "stream_key": stream_key,
                "terminal": True,
            })
        except Exception:
            pass
        self.current_progress = seconds_needed
        self.UpdateQuestProgress(name, seconds_needed)
        Log(f"✅ Completed: {Colors.BOLD}{name}{Colors.RESET}", "ok")
        await self.UpdateStatus()

    # ── Process Quest ────────────────────────────────────────────────────────
    async def ProcessQuest(self, quest: dict):
        qid = quest.get("id")
        name = GetQuestName(quest)
        task_type = GetTaskType(quest)

        if not task_type:
            Log(f"\"{name}\" – Unsupported Task, Skipping", "warn")
            return

        if task_type in UNSUPPORTED_TASKS:
            Log(f"⚠️ \"{name}\" – {task_type} Not Supported (Requires Real Interaction)", "warn")
            return

        if qid in self.completed_ids:
            return

        self.current_quest = name
        self.current_progress = 0
        self.current_total = 0
        Log(f"━━━ Starting: {Colors.BOLD}{name}{Colors.RESET} (Task: {task_type}) ━━━", "info")

        if task_type in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"):
            await self.CompleteVideo(quest)
        elif task_type in ("PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP"):
            await self.CompleteHeartbeat(quest)
        elif task_type == "PLAY_ACTIVITY":
            await self.CompleteActivity(quest)

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
        await self.UpdateStatus()

    # ── Run Quests ────────────────────────────────────────────────────────────
    async def RunQuests(self):
        self.running = True
        self.should_stop = False
        self.stopped_reason = ""
        self.completed_quests = 0
        self.completed_ids = set()
        self.completed_quests_list = []
        self.expired_quests_list = []
        self.all_quests_completed = False
        self.dm_sent = False

        Log("=" * 60, "info")
        Log(f"{Colors.BOLD}Discord Quest Auto-Completer V3.0{Colors.RESET}", "info")
        Log(f"Auto-Accept: {'ON' if AUTO_ACCEPT else 'OFF'}  |  Poll: {POLL_INTERVAL}s", "info")
        Log("=" * 60, "info")

        cycle = 0
        while self.running and not self.should_stop:
            cycle += 1
            Log(f"── Scan #{cycle} ──", "info")

            self.quests = self.FetchQuests()
            total = len(self.quests)
            self.total_quests = total

            self.quest_list = []
            self.expired_quests_list = []
            
            for q in self.quests:
                name = GetQuestName(q)
                task = GetTaskType(q) or "?"
                status = "✅ Completed" if IsCompleted(q) else "▶ Enrolled" if IsEnrolled(q) else "⭕ Available"
                
                if task in UNSUPPORTED_TASKS:
                    status = "🚫 Unsupported"
                
                if IsQuestExpired(q):
                    status = "⌛ Expired"
                    self.expired_quests_list.append({
                        "name": name,
                        "task": task,
                        "expires": GetExpiresAt(q)
                    })
                
                progress = 0
                total_time = 0
                if IsEnrolled(q) and not IsCompleted(q) and task not in UNSUPPORTED_TASKS and not IsQuestExpired(q):
                    total_time = GetSecondsNeeded(q)
                    progress = GetSecondsDone(q)
                
                self.quest_list.append({
                    "name": name,
                    "task": task,
                    "status": status,
                    "progress": progress,
                    "total": total_time,
                    "is_expired": IsQuestExpired(q)
                })

            if not self.quests:
                Log("No Quests Found", "info")
                self.stopped_reason = "📭 No Quests Available"
                self.should_stop = True
                await self.UpdateStatus()
                break
            else:
                enrolled_count = sum(1 for q in self.quests if IsEnrolled(q))
                completed_count = sum(1 for q in self.quests if IsCompleted(q))
                completable_count = sum(1 for q in self.quests if IsCompletable(q))
                expired_count = len(self.expired_quests_list)
                self.enrolled_quests = enrolled_count
                self.completed_quests = completed_count

                Log(
                    f"Total: {total} Quests | Enrolled: {enrolled_count} | "
                    f"Completed: {completed_count} | Completable: {completable_count} | Expired: {expired_count}",
                    "info"
                )

                self.quests = self.AutoAccept(self.quests)

                actionable = [
                    q for q in self.quests
                    if IsEnrolled(q) and not IsCompleted(q) and IsCompletable(q)
                    and q.get("id") not in self.completed_ids
                    and not IsQuestExpired(q)
                ]

                if actionable:
                    Log(f"\n{len(actionable)} Quest(s) Need Completion:", "info")
                    for q in actionable:
                        if not self.running or self.should_stop:
                            break
                        await self.ProcessQuest(q)
                else:
                    Log("No Quests Need Completion At This Time", "info")
                    
                    # ── Check And Send DM ──
                    if not self.dm_sent:
                        remaining_quests = [
                            q for q in self.quests
                            if not IsCompleted(q) and not IsQuestExpired(q) and IsCompletable(q)
                        ]
                        
                        Log(f"Remaining Completable Quests: {len(remaining_quests)}", "info")
                        
                        if len(remaining_quests) == 0:
                            # Kiểm tra xem còn quest nào không (kể cả unsupported)
                            any_quests_left = any(
                                not IsCompleted(q) and not IsQuestExpired(q)
                                for q in self.quests
                            )
                            
                            if not any_quests_left:
                                if self.completed_quests > 0:
                                    self.all_quests_completed = True
                                    Log("🎉 All Quests Completed! Sending DM Notification...", "ok")
                                    await self.SendDMNotification()
                                    self.stopped_reason = "🎉 All Quests Completed!"
                                else:
                                    Log("📭 No Quests Available To Complete", "info")
                                    await self.SendNoQuestsNotification()
                                    self.stopped_reason = "📭 No Quests Available"
                            else:
                                # Vẫn còn quest nhưng không thể auto-accept (unsupported)
                                Log("⚠️ Some quests are available but cannot be auto-accepted (unsupported tasks)", "warn")
                                self.stopped_reason = "⚠️ Unsupported quests remaining"
                                # Không dừng scan, tiếp tục chờ
                            
                            # Dừng scan nếu không còn quest nào
                            if not any_quests_left:
                                self.should_stop = True
                                await self.UpdateStatus()
                                break

            if not self.running or self.should_stop:
                break

            Log(f"\nWaiting {POLL_INTERVAL}s...\n", "info")
            for _ in range(POLL_INTERVAL):
                if not self.running or self.should_stop:
                    break
                await asyncio.sleep(1)

        Log("Stopped Auto Quest Completion.", "info")
        await self.UpdateStatus()

    # ── Progress Bar ──────────────────────────────────────────────────────────
    def CreateProgressBar(self, progress: float, total: float, length: int = 15) -> str:
        if total <= 0:
            return "⬜" * length
        percentage = min(progress / total, 1.0)
        filled = int(percentage * length)
        empty = length - filled
        return "🟧" * filled + "⬜" * empty

    # ── Create Status View ────────────────────────────────────────────────────
    def CreateStatusView(self) -> ui.LayoutView:
        view = ui.LayoutView()
        
        # ── Nếu đã dừng hoặc không còn quest ──────────────────────────────────
        if self.should_stop or not self.running:
            items = [
                ui.TextDisplay(f"## {self.stopped_reason if self.stopped_reason else '📭 No Quests Available'}"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    f"**📊 Statistics**\n"
                    f"Total Quests: {self.total_quests}\n"
                    f"Completed: {self.completed_quests}\n"
                    f"Expired: {len(self.expired_quests_list)}\n"
                    f"Available: 0"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("⏹️ Stopped")
            ]
            
            if self.all_quests_completed:
                items.insert(2, ui.TextDisplay("**🎉 All quests completed! DM notification sent!**"))
            
            color = discord.Color.gold()
            container = ui.Container(*items, accent_color=color)
            view.add_item(container)
            return view
        
        # ── Bình thường ──────────────────────────────────────────────────────────
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
            bar = self.CreateProgressBar(self.current_progress, self.current_total)
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
                    bar = self.CreateProgressBar(q["progress"], q["total"])
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
            items.append(ui.TextDisplay("**🎉 All Quests Completed! 🎊**\nDM Notification Sent!"))

        items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
        items.append(ui.TextDisplay(
            "🔄 Running... Click Stop To Stop" if self.running else "⏹️ Stopped"
        ))

        color = discord.Color.gold()
        container = ui.Container(*items, accent_color=color)
        view.add_item(container)
        return view

    # ── Update Status ─────────────────────────────────────────────────────────
    async def UpdateStatus(self, custom_status: str = None):
        if not self.status_message:
            return

        view = self.CreateStatusView()

        try:
            await self.status_message.edit(view=view)
        except discord.errors.NotFound:
            Log("Status Message Deleted, Cannot Update!", "warn")
        except discord.errors.HTTPException as e:
            if "401" in str(e) or "50027" in str(e):
                Log("Cannot Update Status Due To Webhook Error. Bot Still Running Normally!", "warn")
            else:
                raise e

    def Stop(self):
        self.running = False

# ── Bot ────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, owner_id=OWNER_ID)

active_completers = {}

def IsOwner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != bot.owner_id:
            raise app_commands.CheckFailure("Owner Only")
        return True
    return app_commands.check(predicate)

@bot.tree.error
async def OnAppCommandError(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        text = "❌ Only The Bot Owner Can Use This Command."
    else:
        text = f"❌ Something Went Wrong: {error}"
    view = BuildV2View("❌ Error", [text], color=discord.Color.red())
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)

# ── Quest View ──────────────────────────────────────────────────────────────────
class QuestView(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        # ── Media Gallery For Banner Image ──────────────────────────────────
        gallery = ui.MediaGallery(
            discord.MediaGalleryItem(
                media="https://images-ext-1.discordapp.net/external/cjyVUThezXyzrlExw2GxU8vfRiXmLPTJLsfJfCf5RF4/%3Fh%3D67b51b7107cc2c10dbfb945f7f3b4dda/https/cdn.myportfolio.com/de8e521ad6e548b34ce66798c00c0e11/b5e5143e-d6de-406c-9d97-c0695f35d87a_rwc_0x0x599x338x599.gif"
            )
        )

        container = ui.Container(
            ui.TextDisplay("## 🎮 Quest Auto-Completer"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            # ── Security Commitment ──────────────────────────────────────────
            ui.TextDisplay(
                "**🔒 Security Commitment**\n"
                "```\n"
                "• Token Is ONLY Temporarily Stored In RAM While Running Quest\n"
                "• Automatically Deleted Immediately After Completion Or Error\n"
                "• Never Stored In Any Form (Database, Log Files Or Disk)\n"
                "```"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            # ── Instructions ──────────────────────────────────────────────────
            ui.TextDisplay(
                "## 📋 Instructions\n"
                "```yaml\n"
                "1️⃣  Click \"▶️ Start\" To Begin\n"
                "2️⃣  Enter Your Discord Token In The Modal\n"
                "3️⃣  Bot Will Automatically Scan And Complete Quests\n"
                "4️⃣  Click \"📊 Status\" To View Real-Time Progress\n"
                "5️⃣  Receive DM Notification When All Quests Are Done!\n"
                "```"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            # ── Important Notes ──────────────────────────────────────────────
            ui.TextDisplay(
                "**⚠️ Important Notes**\n"
                "```diff\n"
                "- Token Is Only Used In This Session\n"
                "- Bot Will Auto-Enroll And Complete Quests\n"
                "- Click \"⏹️ Stop\" To Stop Anytime\n"
                "- DM Notification Will Be Sent When All Quests Are Completed\n"
                "+ Make Sure Token Has Discord Access Permissions\n"
                "```"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            # ── Banner Image ──────────────────────────────────────────────────
            gallery,
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            # ── Buttons ──────────────────────────────────────────────────────
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
        placeholder="Enter Your Discord Token...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        
        if not token:
            view = BuildV2View("❌ Error", ["Token Cannot Be Empty!"], color=discord.Color.red())
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            build_number = FetchLatestBuildNumber()
            api = DiscordAPI(token, build_number)
            
            if not api.ValidateToken():
                view = BuildV2View("❌ Error", ["Invalid Token! Please Check And Try Again."], color=discord.Color.red())
                await interaction.followup.send(view=view, ephemeral=True)
                return

            r = api.Get("/users/@me")
            user_data = r.json()
            token_username = user_data.get("username", "Unknown")
            token_user_id = user_data.get("id", "Unknown")

            completer = QuestAutocompleter(api, token_user_id, interaction.user.id)
            completer.bot = bot
            active_completers[str(interaction.user.id)] = completer

            view = BuildV2View(
                "✅ Success",
                [
                    f"Successfully Logged In With Token Of **{token_username}**!",
                    "",
                    "Click **📊 Status** To View Quest Progress.",
                    "You Will Receive A **DM Notification** When All Quests Are Completed! 📬"
                ],
                color=discord.Color.green()
            )
            
            await interaction.followup.send(view=view, ephemeral=True)

            asyncio.create_task(completer.RunQuests())

        except Exception as e:
            view = BuildV2View("❌ Error", [str(e)], color=discord.Color.red())
            await interaction.followup.send(view=view, ephemeral=True)

# ── Bot Events ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f'✅ Bot Logged In Successfully!')
    print(f'📊 Bot Name: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👑 Owner ID: {bot.owner_id}')
    print('─' * 40)
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} Slash Commands!')
    except Exception as e:
        print(f'❌ Error Syncing Slash Commands: {e}')

# ── Interaction Handler ──────────────────────────────────────────────────────
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    
    custom_id = interaction.data.get("custom_id", "")
    
    if custom_id == "quest_start":
        if interaction.user.id != OWNER_ID:
            view = BuildV2View("❌ Permission Denied", ["Only The Bot Owner Can Use This Button!"], color=discord.Color.red())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        modal = TokenModal()
        await interaction.response.send_modal(modal)
    
    elif custom_id == "quest_stop":
        if interaction.user.id != OWNER_ID:
            view = BuildV2View("❌ Permission Denied", ["Only The Bot Owner Can Use This Button!"], color=discord.Color.red())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        completer = active_completers.get(str(interaction.user.id))
        
        if not completer:
            view = BuildV2View("❌ Error", ["No Active Quest Session Found!"], color=discord.Color.red())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        if not completer.running:
            view = BuildV2View("⚠️ Warning", ["Quest Is Not Running!"], color=discord.Color.yellow())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        completer.Stop()
        completer.should_stop = True
        completer.stopped_reason = "⏹️ Stopped By User"
        view = BuildV2View("✅ Stopped", ["Stopped Auto Quest Completion."], color=discord.Color.green())
        await interaction.response.send_message(view=view, ephemeral=True)
        await completer.UpdateStatus()
    
    elif custom_id == "quest_status":
        if interaction.user.id != OWNER_ID:
            view = BuildV2View("❌ Permission Denied", ["Only The Bot Owner Can Use This Button!"], color=discord.Color.red())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        completer = active_completers.get(str(interaction.user.id))
        
        if not completer:
            view = BuildV2View("❌ Error", ["No Active Quest Session Found!"], color=discord.Color.red())
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        view = completer.CreateStatusView()
        
        # Kiểm tra tin nhắn cũ
        if completer.status_message:
            try:
                await completer.status_message.edit(view=view)
                await interaction.response.defer()
                return
            except discord.errors.NotFound:
                completer.status_message = None
            except Exception as e:
                Log(f"Error Editing Status Message: {e}", "warn")
                completer.status_message = None
        
        # Nếu không có tin nhắn hoặc edit thất bại, gửi mới
        await interaction.response.send_message(view=view, ephemeral=True)
        msg = await interaction.original_response()
        completer.status_message = msg

# ── Slash Commands ─────────────────────────────────────────────────────────────
@bot.tree.command(name="quest", description="[Owner] Auto Complete Discord Quests")
@IsOwner()
async def QuestCommand(interaction: discord.Interaction):
    view = QuestView()
    await interaction.response.send_message(view=view, ephemeral=False)

@bot.tree.command(name="ping", description="[Owner] Check Bot Latency")
@IsOwner()
async def PingCommand(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = discord.Color.green() if latency < 100 else discord.Color.yellow() if latency < 200 else discord.Color.red()
    view = BuildV2View(
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
async def SyncCommand(ctx: commands.Context):
    try:
        synced = await bot.tree.sync()
        view = BuildV2View("✅ Success", [f"Synced {len(synced)} Slash Commands!"], color=discord.Color.green())
        await ctx.send(view=view)
    except Exception as e:
        view = BuildV2View("❌ Error", [str(e)], color=discord.Color.red())
        await ctx.send(view=view)

@SyncCommand.error
async def SyncError(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.NotOwner):
        view = BuildV2View("❌ Permission Denied", ["Only The Bot Owner Can Use This Command!"], color=discord.Color.red())
        await ctx.send(view=view)
    else:
        view = BuildV2View("❌ Error", [str(error)], color=discord.Color.red())
        await ctx.send(view=view)

# ── Main Entry ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please Replace TOKEN With Your Bot Token!")
        print("📝 Open File And Edit: TOKEN = 'YOUR_BOT_TOKEN_HERE'")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid Bot Token! Please Check And Try Again.")
    except Exception as e:
        print(f"❌ Error: {e}")
