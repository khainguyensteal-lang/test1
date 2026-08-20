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
def BuildV2View(title: str, lines: list[str]) -> ui.LayoutView:
    """Build A Simple Components V2 Message"""
    view = ui.LayoutView()
    container = ui.Container(
        ui.TextDisplay(f"## {title}"),
        ui.Separator(spacing=discord.SeparatorSpacing.small),
        ui.TextDisplay("\n".join(lines)),
    )
    view.add_item(container)
    return view

def BuildStatusView(title: str, fields: dict) -> ui.LayoutView:
    """Build A Components V2 View With Multiple Fields"""
    view = ui.LayoutView()
    items = [ui.TextDisplay(f"## {title}"), ui.Separator(spacing=discord.SeparatorSpacing.small)]
    
    for key, value in fields.items():
        items.append(ui.TextDisplay(f"**{key}**\n{value}"))
        items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
    
    container = ui.Container(*items)
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
                "📊 Tóm Tắt": f"✅ Đã Hoàn Thành: {self.completed_quests}\n📋 Tổng Quest: {self.total_quests}\n⌛ Quest Hết Hạn: {len(self.expired_quests_list)}"
            }
            
            if self.completed_quests_list:
                completed_text = ""
                for i, q in enumerate(self.completed_quests_list[-10:], 1):
                    completed_text += f"✅ {q['name'][:30]} — ⏰ {q['completed_at']}\n"
                fields["🏆 Quest Đã Hoàn Thành"] = completed_text[:1024]
            
            view = BuildStatusView("🎉 Tất Cả Quest Đã Hoàn Thành!", fields)
            
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
                "📊 Trạng Thái": f"📭 Không Có Quest Nào",
                "📋 Thống Kê": f"Tổng Quest: {self.total_quests}\n"
                                f"Đã Hoàn Thành: {self.completed_quests}\n"
                                f"Đã Hết Hạn: {len(self.expired_quests_list)}\n"
                                f"Có Sẵn: 0"
            }
            
            view = BuildStatusView("📭 Không Có Quest Nào", fields)
            
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
                status = "✅ Đã Hoàn Thành" if IsCompleted(q) else "▶ Đã Nhận" if IsEnrolled(q) else "⭕ Có Sẵn"
                
                if task in UNSUPPORTED_TASKS:
                    status = "🚫 Không Hỗ Trợ"
                
                if IsQuestExpired(q):
                    status = "⌛ Đã Hết Hạn"
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
                self.stopped_reason = "📭 Không Có Quest Nào"
                self.should_stop = True
                self.running = False
                if self.bot:
                    active_completers.pop(str(self.discord_user_id), None)
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
                    
                    if not self.dm_sent:
                        remaining_quests = [
                            q for q in self.quests
                            if not IsCompleted(q) and not IsQuestExpired(q) and IsCompletable(q)
                        ]
                        
                        Log(f"Remaining Completable Quests: {len(remaining_quests)}", "info")
                        
                        if len(remaining_quests) == 0:
                            any_quests_left = any(
                                not IsCompleted(q) and not IsQuestExpired(q)
                                for q in self.quests
                            )
                            
                            if not any_quests_left:
                                if self.completed_quests > 0:
                                    self.all_quests_completed = True
                                    Log("🎉 All Quests Completed! Sending DM Notification...", "ok")
                                    await self.SendDMNotification()
                                    self.stopped_reason = "🎉 Tất Cả Quest Đã Hoàn Thành!"
                                else:
                                    Log("📭 No Quests Available To Complete", "info")
                                    await self.SendNoQuestsNotification()
                                    self.stopped_reason = "📭 Không Có Quest Nào"
                            else:
                                Log("⚠️ Some quests are available but cannot be auto-accepted (unsupported tasks)", "warn")
                                self.stopped_reason = "⚠️ Quest Không Hỗ Trợ Còn Lại"
                            
                            if not any_quests_left:
                                self.should_stop = True
                                self.running = False
                                if self.bot:
                                    active_completers.pop(str(self.discord_user_id), None)
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
        
        if self.should_stop or not self.running:
            items = [
                ui.TextDisplay(f"## {self.stopped_reason if self.stopped_reason else '📭 Không Có Quest Nào'}"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    f"**📊 Thống Kê**\n"
                    f"Tổng Quest: {self.total_quests}\n"
                    f"Đã Hoàn Thành: {self.completed_quests}\n"
                    f"Đã Hết Hạn: {len(self.expired_quests_list)}\n"
                    f"Có Sẵn: 0"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("⏹️ Đã Dừng")
            ]
            
            if self.all_quests_completed:
                items.insert(2, ui.TextDisplay("**🎉 Tất Cả Quest Đã Hoàn Thành! Đã Gửi DM Thông Báo!**"))
            
            container = ui.Container(*items)
            view.add_item(container)
            return view
        
        items = [
            ui.TextDisplay("## 📊 Trạng Thái Quest"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"**Trạng Thái:** {'🟢 Đang Chạy' if self.running else '🔴 Đã Dừng'}"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                f"**📋 Thống Kê**\n"
                f"Tổng Quest: {self.total_quests}\n"
                f"Đã Nhận: {self.enrolled_quests}\n"
                f"Đã Hoàn Thành: {self.completed_quests}\n"
                f"Đã Hết Hạn: {len(self.expired_quests_list)}"
            ),
        ]
        
        if self.current_quest and self.current_total > 0:
            percentage = (self.current_progress / self.current_total) * 100
            bar = self.CreateProgressBar(self.current_progress, self.current_total)
            items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
            items.append(ui.TextDisplay(
                f"**🔄 Đang Làm**\n"
                f"**{self.current_quest}**\n"
                f"`{bar}` {percentage:.1f}%\n"
                f"⏱️ {self.current_progress:.0f}/{self.current_total}s"
            ))

        if self.quest_list:
            quest_text = ""
            active_count = 0
            for q in self.quest_list[:20]:
                if q["status"] == "▶ Đã Nhận" and not q["is_expired"] and q["total"] > 0:
                    active_count += 1
                    bar = self.CreateProgressBar(q["progress"], q["total"])
                    percent = int((q["progress"] / q["total"]) * 100)
                    quest_text += f"▶ **{q['name'][:30]}**\n"
                    quest_text += f"   `{bar}` {percent}% ({q['progress']:.0f}/{q['total']}s)\n"
            
            if quest_text:
                items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
                items.append(ui.TextDisplay(f"**📋 Quest Đang Làm ({active_count})**\n{quest_text[:1500]}"))

        if self.completed_quests_list:
            completed_text = ""
            for i, q in enumerate(self.completed_quests_list[-5:], 1):
                completed_text += f"✅ {q['name'][:25]} — ⏰ {q['completed_at']}\n"
            
            if completed_text:
                items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
                items.append(ui.TextDisplay(f"**🏆 Gần Đây Đã Hoàn Thành ({len(self.completed_quests_list)})**\n{completed_text[:1024]}"))

        if self.all_quests_completed:
            items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
            items.append(ui.TextDisplay("**🎉 Tất Cả Quest Đã Hoàn Thành! 🎊**\nĐã Gửi DM Thông Báo!"))

        items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
        items.append(ui.TextDisplay(
            "🔄 Đang Chạy... Nhấn Dừng Để Dừng" if self.running else "⏹️ Đã Dừng"
        ))

        container = ui.Container(*items)
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
        text = "❌ Chỉ Chủ Bot Mới Có Thể Dùng Lệnh Này."
    else:
        text = f"❌ Đã Xảy Ra Lỗi: {error}"
    view = BuildV2View("❌ Lỗi", [text])
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)

# ── Guide View ──────────────────────────────────────────────────────────────────
class GuideView(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.current_page = 0
        self.current_device = "pc"
        self.pc_pages = [
            {
                "title": "Hướng Dẫn Lấy Token Trên PC (Bước 1/3)",
                "content": "**Bước 1:** Vào Google Chrome, Cài Extension **Discord Get User Token**\n\n📂 [Link Extension Get Token](https://chrome.google.com/webstore/detail/discord-get-user-token)\n\n⭐ Bấm Nút \"Add To Chrome\" (Thêm Vào Chrome) Để Cài Đặt Tiện Ích."
            },
            {
                "title": "Hướng Dẫn Lấy Token Trên PC (Bước 2/3)",
                "content": "**Bước 2:** Vào Discord Web, Đăng Nhập Tài Khoản Của Bạn, F5 Lại Trang Web, Chọn Biểu Tượng Tiện Ích (Extension) Góc Trên Bên Phải Và Chọn **Discord Get User Token**.\n\n🔗 [Discord Web](https://discord.com/app)"
            },
            {
                "title": "Hướng Dẫn Lấy Token Trên PC (Bước 3/3)",
                "content": "**Bước 3:** Nhấn Vào Nút **Get Token** Để Tự Động Sao Chép Mã Token.\n\nQuay Lại Panel Trên Discord, Nhấn Nút **Bắt Đầu** Và Dán Token Vào Để Bắt Đầu Chạy Quest!"
            }
        ]
        self.mobile_pages = [
            {
                "title": "Hướng Dẫn Lấy Token Trên Điện Thoại (Bước 1/5)",
                "content": "**Bước 1:** Tải Và Cài Đặt Trình Duyệt **Kiwi Browser** Trên Điện Thoại Android.\n\n📂 [Link Tải Kiwi Browser](https://play.google.com/store/apps/details?id=com.kiwibrowser.browser)\n\n⚠️ **Lưu Ý:** Kiwi Browser Là Trình Duyệt Điện Thoại Hỗ Trợ Cài Đặt Các Extension Của Chrome Web Store."
            },
            {
                "title": "Hướng Dẫn Lấy Token Trên Điện Thoại (Bước 2/5)",
                "content": "**Bước 2:** Mở Kiwi Browser Và Đăng Nhập Vào Tài Khoản Discord Của Bạn.\n\n🔗 [Trang Đăng Nhập Discord](https://discord.com/app)\n\n✅ Đảm Bảo Bạn Đã Đăng Nhập Thành Công Vào Discord Trên Trình Duyệt."
            },
            {
                "title": "Hướng Dẫn Lấy Token Trên Điện Thoại (Bước 3/5)",
                "content": "**Bước 3:** Tải Extension **Get Token** Trên Chrome Web Store Trong Kiwi Browser.\n\n📂 [Link Extension Get Token](https://chrome.google.com/webstore/detail/discord-get-user-token)\n\n⚠️ **Nhấn \"Thêm Vào Chrome\" (Add To Chrome)** Để Cài Đặt Extension Vào Kiwi Browser."
            },
            {
                "title": "Hướng Dẫn Lấy Token Trên Điện Thoại (Bước 4/5)",
                "content": "**Bước 4:** Quay Lại Trang Web Discord.\n\n🔗 [Discord Web](https://discord.com/app)\n\n**Bước 5:** Chọn Vào Dấu **3 Chấm** Ở Góc Trên Trình Duyệt Kiwi Browser → Bật **Desktop Site** (Trang Web Cho Máy Tính) → Kéo Xuống Dưới Cùng Và Bấm Vào Tiện Ích **Get Token**."
            },
            {
                "title": "Hướng Dẫn Lấy Token Trên Điện Thoại (Bước 5/5)",
                "content": "**Bước 6:** Bấm Nút **Get Token** Trên Màn Hình Extension. Mã Token Của Bạn Sẽ Được Tự Động Sao Chép!\n\n✅ **Hoàn Tất:** Quay Lại Discord Và Bấm Nút **▶️ Bắt Đầu** Trên Panel Để Dán Token Vào Làm Quest!"
            }
        ]

    def get_current_page_data(self):
        if self.current_device == "pc":
            pages = self.pc_pages
        else:
            pages = self.mobile_pages
        return pages[self.current_page]

    def get_total_pages(self):
        return len(self.pc_pages) if self.current_device == "pc" else len(self.mobile_pages)

    def create_view(self):
        page_data = self.get_current_page_data()
        total_pages = self.get_total_pages()
        is_first = self.current_page == 0
        is_last = self.current_page == total_pages - 1
        
        container = ui.Container(
            ui.TextDisplay(f"## {page_data['title']}"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(page_data['content']),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(f"📄 Trang {self.current_page + 1}/{total_pages} - Meow Town Quest Service"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.ActionRow(
                ui.Button(
                    label="◀ Trang Trước", 
                    style=discord.ButtonStyle.secondary, 
                    custom_id=f"guide_prev_{self.current_device}_{self.current_page}",
                    disabled=is_first
                ),
                ui.Button(
                    label=f"📄 {self.current_page + 1}/{total_pages}", 
                    style=discord.ButtonStyle.secondary, 
                    custom_id=f"guide_page_{self.current_device}_{self.current_page}", 
                    disabled=True
                ),
                ui.Button(
                    label="Trang Sau ▶", 
                    style=discord.ButtonStyle.secondary, 
                    custom_id=f"guide_next_{self.current_device}_{self.current_page}",
                    disabled=is_last
                ),
            ),
        )
        return container

# ── Guide Select View ───────────────────────────────────────────────────────────
class GuideSelectView(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        container = ui.Container(
            ui.TextDisplay("## 📖 Hướng Dẫn Lấy Token Discord"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                "Vui Lòng Chọn Loại Thiết Bị Bạn Đang Sử Dụng Bên Dưới Để Xem Hướng Dẫn Chi Tiết Từng Bước:\n\n"
                "• **Máy Tính (PC / Laptop):** 3 Trang Minh Họa Từng Bước.\n"
                "• **Điện Thoại (iOS / Android):** 5 Trang Minh Họa Qua Kiwi Browser."
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.ActionRow(
                ui.Button(label="💻 Máy Tính (PC)", style=discord.ButtonStyle.blurple, custom_id="guide_select_pc"),
                ui.Button(label="📱 Điện Thoại (Mobile)", style=discord.ButtonStyle.blurple, custom_id="guide_select_mobile"),
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay("📌 **Meow Town Quest Service**"),
        )
        self.add_item(container)

# ── Quest View ──────────────────────────────────────────────────────────────────
class QuestView(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        gallery = ui.MediaGallery(
            discord.MediaGalleryItem(
                media="https://images-ext-1.discordapp.net/external/cjyVUThezXyzrlExw2GxU8vfRiXmLPTJLsfJfCf5RF4/%3Fh%3D67b51b7107cc2c10dbfb945f7f3b4dda/https/cdn.myportfolio.com/de8e521ad6e548b34ce66798c00c0e11/b5e5143e-d6de-406c-9d97-c0695f35d87a_rwc_0x0x599x338x599.gif"
            )
        )

        container = ui.Container(
            ui.TextDisplay("## 🎮 Tự Động Hoàn Thành Quest"),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                "**🔒 Cam Kết Bảo Mật**\n"
                "```\n"
                "• Token CHỈ Được Lưu Tạm Thời Trong RAM Khi Chạy Quest\n"
                "• Tự Động XÓA NGAY Sau Khi Hoàn Thành Hoặc Có Lỗi\n"
                "• Không Lưu Trữ Dưới Bất Kỳ Hình Thức Nào (Database, File Log Hay Disk)\n"
                "```"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                "## 📋 Hướng Dẫn Sử Dụng\n"
                "```yaml\n"
                "1️⃣  Nhấn \"▶️ Bắt Đầu\" Để Bắt Đầu\n"
                "2️⃣  Nhập Token Discord Của Bạn Vào Ô\n"
                "3️⃣  Bot Sẽ Tự Động Quét Và Hoàn Thành Quest\n"
                "4️⃣  Nhấn \"📊 Trạng Thái\" Để Xem Tiến Độ Real-Time\n"
                "5️⃣  Nhận DM Thông Báo Khi Hoàn Thành Tất Cả Quest!\n"
                "```"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.TextDisplay(
                "**⚠️ Lưu Ý Quan Trọng**\n"
                "```diff\n"
                "- Token Chỉ Được Sử Dụng Trong Phiên Làm Việc Này\n"
                "- Bot Sẽ Tự Động Nhận Và Hoàn Thành Quest\n"
                "- Nhấn \"⏹️ Dừng\" Để Dừng Bất Cứ Lúc Nào\n"
                "- DM Thông Báo Sẽ Được Gửi Khi Hoàn Thành Tất Cả Quest\n"
                "+ Đảm Bảo Token Có Quyền Truy Cập Discord\n"
                "```"
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            gallery,
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.ActionRow(
                ui.Button(label="▶️ Bắt Đầu", style=discord.ButtonStyle.green, custom_id="quest_start"),
                ui.Button(label="⏹️ Dừng", style=discord.ButtonStyle.red, custom_id="quest_stop"),
                ui.Button(label="📊 Trạng Thái", style=discord.ButtonStyle.blurple, custom_id="quest_status"),
            ),
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            ui.ActionRow(
                ui.Button(label="📖 Hướng Dẫn", style=discord.ButtonStyle.blurple, custom_id="guide_open"),
            ),
        )
        self.add_item(container)

# ── Token Modal ──────────────────────────────────────────────────────────────
class TokenModal(discord.ui.Modal, title="Nhập Token Discord"):
    token_input = discord.ui.TextInput(
        label="Token Discord",
        placeholder="Nhập Token Discord Của Bạn...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        
        if not token:
            view = BuildV2View("❌ Lỗi", ["Token Không Được Để Trống!"])
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            build_number = FetchLatestBuildNumber()
            api = DiscordAPI(token, build_number)
            
            if not api.ValidateToken():
                view = BuildV2View("❌ Lỗi", ["Token Không Hợp Lệ! Vui Lòng Kiểm Tra Lại."])
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
                "✅ Thành Công",
                [
                    f"Đã Đăng Nhập Thành Công Với Token Của **{token_username}**!",
                    "",
                    "Nhấn **📊 Trạng Thái** Để Xem Tiến Độ Quest.",
                    "Bạn Sẽ Nhận Được **DM Thông Báo** Khi Hoàn Thành Tất Cả Quest! 📬"
                ]
            )
            
            await interaction.followup.send(view=view, ephemeral=True)

            asyncio.create_task(completer.RunQuests())

        except Exception as e:
            view = BuildV2View("❌ Lỗi", [str(e)])
            await interaction.followup.send(view=view, ephemeral=True)

# ── Safe Send/Edit Helpers ──────────────────────────────────────────────────
async def SafeSend(interaction: discord.Interaction, view: ui.LayoutView, ephemeral: bool = True):
    try:
        await interaction.response.send_message(view=view, ephemeral=ephemeral)
        return await interaction.original_response()
    except discord.errors.NotFound:
        return await interaction.followup.send(view=view, ephemeral=ephemeral)
    except Exception as e:
        Log(f"SafeSend Error: {e}", "warn")
        return await interaction.followup.send(view=view, ephemeral=ephemeral)

async def SafeEdit(message: discord.Message, view: ui.LayoutView):
    try:
        await message.edit(view=view)
        return True
    except discord.errors.NotFound:
        return False
    except Exception as e:
        Log(f"SafeEdit Error: {e}", "warn")
        return False

# ── Bot Events ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f'✅ Bot Đã Đăng Nhập Thành Công!')
    print(f'📊 Tên Bot: {bot.user.name}')
    print(f'🆔 ID Bot: {bot.user.id}')
    print(f'👑 ID Chủ Sở Hữu: {bot.owner_id}')
    print('─' * 40)
    try:
        synced = await bot.tree.sync()
        print(f'✅ Đã Sync {len(synced)} Lệnh Slash!')
    except Exception as e:
        print(f'❌ Lỗi Sync Slash Commands: {e}')

# ── Interaction Handler ──────────────────────────────────────────────────────
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    
    custom_id = interaction.data.get("custom_id", "")
    
    # ── Guide Navigation ──────────────────────────────────────────────────
    if custom_id == "guide_open":
        view = GuideSelectView()
        await interaction.response.send_message(view=view, ephemeral=True)
        return
    
    elif custom_id == "guide_select_pc":
        guide = GuideView()
        guide.current_device = "pc"
        guide.current_page = 0
        view = ui.LayoutView()
        view.add_item(guide.create_view())
        await interaction.response.edit_message(view=view)
        return
    
    elif custom_id == "guide_select_mobile":
        guide = GuideView()
        guide.current_device = "mobile"
        guide.current_page = 0
        view = ui.LayoutView()
        view.add_item(guide.create_view())
        await interaction.response.edit_message(view=view)
        return
    
    elif custom_id.startswith("guide_prev"):
        parts = custom_id.split("_")
        device = parts[2] if len(parts) > 2 else "pc"
        current_page = int(parts[3]) if len(parts) > 3 else 0
        
        guide = GuideView()
        guide.current_device = device
        guide.current_page = current_page
        
        if guide.current_page > 0:
            guide.current_page -= 1
        
        view = ui.LayoutView()
        view.add_item(guide.create_view())
        await interaction.response.edit_message(view=view)
        return
    
    elif custom_id.startswith("guide_next"):
        parts = custom_id.split("_")
        device = parts[2] if len(parts) > 2 else "pc"
        current_page = int(parts[3]) if len(parts) > 3 else 0
        
        guide = GuideView()
        guide.current_device = device
        guide.current_page = current_page
        total_pages = guide.get_total_pages()
        
        if guide.current_page < total_pages - 1:
            guide.current_page += 1
        
        view = ui.LayoutView()
        view.add_item(guide.create_view())
        await interaction.response.edit_message(view=view)
        return
    
    # ── Quest Buttons ──────────────────────────────────────────────────────
    elif custom_id == "quest_start":
        modal = TokenModal()
        await interaction.response.send_modal(modal)
        return
    
    elif custom_id == "quest_stop":
        completer = active_completers.get(str(interaction.user.id))
        
        if not completer:
            view = BuildV2View("❌ Lỗi", ["Không Tìm Thấy Phiên Làm Việc!"])
            await SafeSend(interaction, view)
            return
        
        if not completer.running or completer.should_stop:
            active_completers.pop(str(interaction.user.id), None)
            view = BuildV2View(
                "⏹️ Phiên Đã Kết Thúc",
                [
                    "Phiên Làm Việc Đã Kết Thúc.",
                    "Vui Lòng Nhấn **Bắt Đầu** Để Bắt Đầu Phiên Mới."
                ]
            )
            await SafeSend(interaction, view)
            return
        
        completer.Stop()
        completer.should_stop = True
        completer.stopped_reason = "⏹️ Đã Dừng Bởi Người Dùng"
        
        view = completer.CreateStatusView()
        if completer.status_message:
            if await SafeEdit(completer.status_message, view):
                try:
                    await interaction.response.defer()
                except:
                    pass
            else:
                await SafeSend(interaction, view)
        else:
            await SafeSend(interaction, view)
        
        try:
            await interaction.followup.send("✅ Đã Dừng Tự Động Hoàn Thành Quest!", ephemeral=True)
        except:
            pass
        return
    
    elif custom_id == "quest_status":
        completer = active_completers.get(str(interaction.user.id))
        
        if not completer:
            view = BuildV2View("❌ Lỗi", ["Không Tìm Thấy Phiên Làm Việc!"])
            await SafeSend(interaction, view)
            return
        
        if completer.should_stop or not completer.running:
            view = BuildV2View(
                "⏹️ Phiên Đã Kết Thúc",
                [
                    "Không Có Phiên Làm Việc Nào Đang Hoạt Động.",
                    "Vui Lòng Nhấn **Bắt Đầu** Để Bắt Đầu Phiên Mới."
                ]
            )
            await SafeSend(interaction, view)
            return
        
        view = completer.CreateStatusView()
        
        if completer.status_message:
            if await SafeEdit(completer.status_message, view):
                try:
                    await interaction.response.defer()
                except:
                    pass
                return
            else:
                completer.status_message = None
        
        msg = await SafeSend(interaction, view)
        completer.status_message = msg
        return

# ── Slash Commands ─────────────────────────────────────────────────────────────
@bot.tree.command(name="quest", description="[Chủ Sở Hữu] Tự Động Hoàn Thành Quest Discord")
@IsOwner()
async def QuestCommand(interaction: discord.Interaction):
    view = QuestView()
    await interaction.response.send_message(view=view, ephemeral=False)

@bot.tree.command(name="ping", description="[Chủ Sở Hữu] Kiểm Tra Độ Trễ Của Bot")
@IsOwner()
async def PingCommand(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    view = BuildV2View(
        "🏓 Pong!",
        [
            f"**📡 Độ Trễ:** `{latency}ms`",
            f"**🔄 Trạng Thái:** {'🟢 Online' if latency < 200 else '🟡 Chậm' if latency < 400 else '🔴 Rất Chậm'}"
        ]
    )
    await interaction.response.send_message(view=view, ephemeral=True)

# ── Normal Commands ──────────────────────────────────────────────────────────
@bot.command(name="sync")
@commands.is_owner()
async def SyncCommand(ctx: commands.Context):
    try:
        synced = await bot.tree.sync()
        view = BuildV2View("✅ Thành Công", [f"Đã Sync {len(synced)} Lệnh Slash!"])
        await ctx.send(view=view)
    except Exception as e:
        view = BuildV2View("❌ Lỗi", [str(e)])
        await ctx.send(view=view)

@SyncCommand.error
async def SyncError(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.NotOwner):
        view = BuildV2View("❌ Từ Chối Quyền", ["Chỉ Chủ Bot Mới Có Thể Dùng Lệnh Này!"])
        await ctx.send(view=view)
    else:
        view = BuildV2View("❌ Lỗi", [str(error)])
        await ctx.send(view=view)

# ── Main Entry ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Vui Lòng Thay TOKEN Bằng Token Bot Của Bạn!")
        print("📝 Mở File Và Sửa: TOKEN = 'YOUR_BOT_TOKEN_HERE'")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Token Bot Không Hợp Lệ! Vui Lòng Kiểm Tra Lại.")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
