import logging
import asyncio
import time
import sys
import uuid
import os
import random
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ApplicationBuilder

from groq import Groq

# ----------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------

# Токен Telegram
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"

# Список Groq API ключей для распределения нагрузки
GROQ_API_KEYS = [
    "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",
    "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",
    "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",
    "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",
    "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",
    "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",
    "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",
    "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",
    "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",
    "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"
]

# ID владельца (определится при первом запуске)
OWNER_CHAT_ID = None

# Список администраторов (username'ы)
ADMINS = set()

# Глобальные клиенты Groq для каждого ключа
groq_clients = []
current_client_index = 0
client_lock = asyncio.Lock()

# Флаг паузы бота
bot_paused = False
pause_reason = ""

# Настройки бота
bot_settings = {
    "default_model": "llama-3.1-8b-instant",
    "default_mode": "normal",
    "max_chats": 10,
    "max_saved_messages": 50,
    "default_requests_per_minute": 30,
    "default_requests_per_hour": 500,
    "default_requests_per_day": 1000,
    "default_cooldown": 2,
    "max_warnings": 3,
    "max_adult_attempts": 3,
    "api_call_cooldown": 1,
    "welcome_message": "🌟 Добро пожаловать, {name}!\n\n✨ Я твой персональный AI-помощник на базе Groq.\n📌 Сейчас ты в чате: {chat}\n\n💡 Просто напиши мне сообщение, и я отвечу!\n🔽 Кнопки для управления всегда под строкой ввода.",
    "enable_18_plus_filter": True,
    "enable_user_notes": True,
    "enable_activity_tracking": True,
    "custom_greeting": "",
    "custom_info": "",
    "message_style": "standard",
    "api_key_rotation": "round_robin",
}

# ----------------------------------------------------------------------
# Логирование
# ----------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ----------------------------------------------------------------------
# Константы и данные
# ----------------------------------------------------------------------
GROQ_MODELS = {
    "🦙 LLaMA 3.1 8B": "llama-3.1-8b-instant",
    "🔸 Gemma 2 9B": "gemma2-9b-it",
    "🦙 LLaMA 3.3 70B": "llama-3.3-70b-versatile",
}

MESSAGE_STYLES = {
    "standard": {
        "name": "🌟 Стандартный",
        "template": "🌟 Добро пожаловать, {name}!\n\n✨ Я твой персональный AI-помощник на базе Groq.\n📌 Сейчас ты в чате: {chat}\n\n💡 Просто напиши мне сообщение, и я отвечу!\n🔽 Кнопки для управления всегда под строкой ввода."
    },
    "minimal": {
        "name": "🔹 Минимальный",
        "template": "👋 Привет, {name}!\n\n💬 Чат: {chat}\n✏️ Напиши сообщение..."
    },
    "detailed": {
        "name": "📋 Подробный",
        "template": "📋 Информация\n\n👤 Пользователь: {name}\n💬 Текущий чат: {chat}\n🤖 Модель: {model}\n🎭 Режим: {mode}\n📊 Статистика: {stats} сообщений\n\n🔽 Кнопки управления под строкой ввода"
    }
}

MODES = {
    "normal": {
        "name": "💬 Обычный",
        "emoji": "💬",
        "system_prompt": "Ты вежливый и полезный ассистент. Отвечай кратко и по делу. {custom_note}",
        "description": "Вежливые и полезные ответы"
    },
    "ham": {
        "name": "😈 Хам",
        "emoji": "😈",
        "system_prompt": "Ты грубый, саркастичный и дерзкий ассистент-хам. Отвечай с издевкой, используй сарказм, подкалывай пользователя. Будь максимально дерзким и язвительным. {custom_note}",
        "description": "Грубые и саркастичные ответы"
    },
    "swear": {
        "name": "🤬 Мат",
        "emoji": "🤬",
        "system_prompt": "Ты ассистент, который постоянно использует нецензурную лексику. Отвечай грубо, с матом через каждое слово. {custom_note}",
        "description": "Нецензурная лексика"
    }
}

QUOTES = [
    "🌟 Цитата дня: «Единственный способ делать великие дела — любить то, что вы делаете.» — Стив Джобс",
    "💡 Мысль: «Жизнь — это то, что с тобой происходит, пока ты строишь планы.» — Джон Леннон",
    "🌱 Мудрость: «Начинать всегда стоит с того, что сеет сомнения.» — Борис Стругацкий",
    "🔥 Вдохновение: «Падать — часть жизни, подниматься — её главная часть.»",
]

def get_random_quote():
    return random.choice(QUOTES)

# Статистика использования API ключей
api_key_stats = {key: {"success": 0, "error": 0, "last_error": None} for key in GROQ_API_KEYS}

# Структуры данных
user_data = {}
user_last_message = {}
menu_messages = {}
awaiting_input = {}
saved_messages = {}
dialog_messages = {}
last_message_text = {}
last_api_call_time = {}
user_custom_notes = {}
user_requests = defaultdict(list)
user_limits = {}
global_request_count = 0
error_count = 0
last_error_time = None
error_users = set()
banned_users = set()
banned_usernames = set()
muted_users = {}
violations = defaultdict(list)
user_warnings = defaultdict(int)
adult_content_attempts = defaultdict(int)
user_activity = {}
daily_active_users = set()
weekly_active_users = set()
monthly_active_users = set()
bot_start_time = time.time()

pending_save = {}  # {user_id: {"type": "user"/"bot", "messages": list}}

MAX_CHATS = bot_settings["max_chats"]
MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
MAX_WARNINGS = bot_settings["max_warnings"]
MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]

ADULT_KEYWORDS = [
    'порно', 'porn', 'sex', 'секс', 'эротика', 'erotica', 'xxx',
    '18+', 'nsfw', 'порнография', 'pornography', 'hardcore',
    'интим', 'intimate', 'обнаженный', 'naked', 'голый',
]

# ----------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------
def is_admin(user_id, username=None):
    if user_id == OWNER_CHAT_ID:
        return True
    if username and username.lower() in ADMINS:
        return True
    return False

def init_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "chats": [],
            "temp_chat": None,
            "current_chat_id": None,
            "current_chat": None,
            "chat_type": None,
            "in_dialog": False,
            "model": bot_settings["default_model"],
            "mode": bot_settings["default_mode"],
            "total_messages": 0,
            "saved_messages_limit": MAX_SAVED_MESSAGES,
            "username": None,
            "first_seen": time.time(),
            "last_active": time.time(),
            "notes": "",
            "total_spent_time": 0,
            "adult_attempts": 0,
            "warnings": 0,
            "is_banned": False,
            "last_message_id": None,
            "custom_note": "",
            "last_bot_message": None,
            "personal_limits": {
                "requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE,
                "cooldown": DEFAULT_COOLDOWN
            },
            "message_style": bot_settings["message_style"],
            "recent_messages": [],
            "save_mode": False,
            "current_menu": "main",
        }
        dialog_messages[user_id] = []
        saved_messages[user_id] = []
        last_message_text[user_id] = {"user": "", "bot": ""}
        last_api_call_time[user_id] = 0
        user_custom_notes[user_id] = ""

        if user_id not in user_limits:
            user_limits[user_id] = {
                "requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE,
                "requests_per_hour": DEFAULT_REQUESTS_PER_HOUR,
                "requests_per_day": DEFAULT_REQUESTS_PER_DAY,
                "cooldown": DEFAULT_COOLDOWN,
                "is_owner": (user_id == OWNER_CHAT_ID)
            }

        user_activity[user_id] = {
            "last_active": time.time(),
            "total_messages": 0,
            "total_time": 0,
            "daily_stats": {},
            "weekly_stats": {},
            "monthly_stats": {}
        }

def check_user_restrictions(user_id, username):
    if user_id in banned_users or (user_id in user_data and user_data[user_id].get("is_banned", False)):
        return False, "❌ Вы забанены в боте."
    if username and username.lower() in banned_usernames:
        return False, "❌ Этот username забанен в боте."
    if user_id in muted_users:
        mute_info = muted_users[user_id]
        if time.time() < mute_info["until"]:
            remaining = int(mute_info["until"] - time.time())
            return False, f"🔇 Вы в муте. Причина: {mute_info['reason']}\nОсталось: {remaining} сек"
        else:
            del muted_users[user_id]
    return True, "OK"

def add_violation(user_id, reason):
    violations[user_id].append({
        "time": time.time(),
        "reason": reason
    })
    if OWNER_CHAT_ID:
        username = user_data.get(user_id, {}).get("username", "нет username")
        return f"⚠️ Нарушение!\nПользователь: {user_id}\nUsername: @{username}\nПричина: {reason}"
    return None

def check_adult_content(text):
    if not bot_settings["enable_18_plus_filter"]:
        return False
    text_lower = text.lower()
    for keyword in ADULT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def update_user_activity(user_id):
    if not bot_settings["enable_activity_tracking"]:
        return
    now = time.time()
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    if user_id not in user_activity:
        user_activity[user_id] = {
            "last_active": now,
            "total_messages": 0,
            "total_time": 0,
            "daily_stats": {},
            "weekly_stats": {},
            "monthly_stats": {}
        }
    user_activity[user_id]["last_active"] = now
    user_activity[user_id]["total_messages"] += 1
    user_activity[user_id]["daily_stats"][today] = user_activity[user_id]["daily_stats"].get(today, 0) + 1
    user_activity[user_id]["weekly_stats"][week] = user_activity[user_id]["weekly_stats"].get(week, 0) + 1
    user_activity[user_id]["monthly_stats"][month] = user_activity[user_id]["monthly_stats"].get(month, 0) + 1
    daily_active_users.add(user_id)
    weekly_active_users.add(user_id)
    monthly_active_users.add(user_id)
    if user_id in user_data:
        user_data[user_id]["last_active"] = now
        user_data[user_id]["total_spent_time"] = now - user_data[user_id]["first_seen"]

def check_request_limits(user_id):
    if bot_paused:
        return False, "⏸️ Бот временно приостановлен. Попробуйте позже."
    if user_limits.get(user_id, {}).get("is_owner") or is_admin(user_id):
        return True, "OK"
    personal = user_data[user_id].get("personal_limits", {})
    limits = user_limits[user_id].copy()
    if personal.get("requests_per_minute"):
        limits["requests_per_minute"] = personal["requests_per_minute"]
    if personal.get("cooldown"):
        limits["cooldown"] = personal["cooldown"]
    now = time.time()
    if user_id not in user_requests:
        user_requests[user_id] = []
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 86400]
    if user_requests[user_id] and now - user_requests[user_id][-1] < limits["cooldown"]:
        wait = int(limits["cooldown"] - (now - user_requests[user_id][-1]))
        return False, f"⏱️ Подождите {wait} сек"
    minute_ago = now - 60
    minute_req = len([t for t in user_requests[user_id] if t > minute_ago])
    if minute_req >= limits["requests_per_minute"]:
        return False, f"📊 Ваш лимит {limits['requests_per_minute']} запросов/мин"
    return True, "OK"

def can_call_api(user_id):
    now = time.time()
    last = last_api_call_time.get(user_id, 0)
    if now - last < API_CALL_COOLDOWN:
        return False
    last_api_call_time[user_id] = now
    return True

def record_request(user_id):
    if user_id not in user_requests:
        user_requests[user_id] = []
    user_requests[user_id].append(time.time())
    global global_request_count
    global_request_count += 1
    update_user_activity(user_id)

def create_chat(user_id, name, is_temporary=False):
    if user_id not in user_data:
        init_user_data(user_id)
    chat_id = str(uuid.uuid4())[:8]
    custom_note = user_custom_notes.get(user_id, "")
    system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
    new_chat = {
        "id": chat_id,
        "name": name,
        "messages": [{"role": "system", "content": system_prompt}],
        "created": time.time(),
        "model": user_data[user_id]["model"],
        "mode": user_data[user_id]["mode"],
        "is_temporary": is_temporary,
    }
    if is_temporary:
        user_data[user_id]["temp_chat"] = new_chat
        user_data[user_id]["current_chat"] = new_chat
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "temporary"
    else:
        permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
        if len(permanent_chats) >= MAX_CHATS:
            return None, "Достигнут лимит чатов. Нужно удалить старый."
        user_data[user_id]["chats"].append(new_chat)
        user_data[user_id]["current_chat"] = new_chat
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "permanent"
    return chat_id, None

def switch_chat(user_id, chat_id):
    if user_id not in user_data:
        return False
    if user_data[user_id]["temp_chat"] and user_data[user_id]["temp_chat"]["id"] == chat_id:
        user_data[user_id]["current_chat"] = user_data[user_id]["temp_chat"]
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "temporary"
        return True
    for chat in user_data[user_id]["chats"]:
        if chat["id"] == chat_id:
            user_data[user_id]["current_chat"] = chat
            user_data[user_id]["current_chat_id"] = chat_id
            user_data[user_id]["chat_type"] = "permanent" if not chat.get("is_temporary") else "temporary"
            user_data[user_id]["model"] = chat.get("model", bot_settings["default_model"])
            user_data[user_id]["mode"] = chat.get("mode", bot_settings["default_mode"])
            return True
    return False

def delete_chat(user_id, chat_id):
    if user_id not in user_data:
        return False
    if user_data[user_id]["temp_chat"] and user_data[user_id]["temp_chat"]["id"] == chat_id:
        user_data[user_id]["temp_chat"] = None
        if user_data[user_id]["current_chat_id"] == chat_id:
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
        return True
    for i, chat in enumerate(user_data[user_id]["chats"]):
        if chat["id"] == chat_id:
            del user_data[user_id]["chats"][i]
            if user_data[user_id]["current_chat_id"] == chat_id:
                if user_data[user_id]["chats"]:
                    user_data[user_id]["current_chat"] = user_data[user_id]["chats"][0]
                    user_data[user_id]["current_chat_id"] = user_data[user_id]["chats"][0]["id"]
                elif user_data[user_id]["temp_chat"]:
                    user_data[user_id]["current_chat"] = user_data[user_id]["temp_chat"]
                    user_data[user_id]["current_chat_id"] = user_data[user_id]["temp_chat"]["id"]
                else:
                    user_data[user_id]["current_chat"] = None
                    user_data[user_id]["current_chat_id"] = None
            return True
    return False

def delete_oldest_chat(user_id):
    if user_id not in user_data:
        return False
    permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
    if permanent_chats:
        oldest = min(permanent_chats, key=lambda x: x["created"])
        user_data[user_id]["chats"].remove(oldest)
        return True
    return False

def save_message(user_id, message_text, sender, chat_name=None):
    if user_id not in saved_messages:
        saved_messages[user_id] = []
    if len(saved_messages[user_id]) >= user_data[user_id]["saved_messages_limit"]:
        saved_messages[user_id].pop(0)
    if not chat_name and user_data[user_id]["current_chat"]:
        chat_name = user_data[user_id]["current_chat"]["name"]
    saved_messages[user_id].append({
        "text": message_text,
        "sender": sender,
        "timestamp": time.time(),
        "chat_name": chat_name or "Неизвестный чат"
    })
    return True

def ban_user(user_id, reason="", username=None):
    banned_users.add(user_id)
    if username:
        banned_usernames.add(username.lower())
    if user_id in user_data:
        user_data[user_id]["is_banned"] = True
        user_data[user_id]["ban_reason"] = reason
        user_data[user_id]["ban_time"] = time.time()
    return True

def unban_user(user_id, username=None):
    if user_id in banned_users:
        banned_users.remove(user_id)
    if username and username.lower() in banned_usernames:
        banned_usernames.remove(username.lower())
    if user_id in user_data:
        user_data[user_id]["is_banned"] = False
        user_data[user_id].pop("ban_reason", None)
        user_data[user_id].pop("ban_time", None)
    return True

def mute_user(user_id, duration_seconds, reason=""):
    muted_users[user_id] = {
        "until": time.time() + duration_seconds,
        "reason": reason,
        "username": user_data.get(user_id, {}).get("username")
    }
    return True

def unmute_user(user_id):
    if user_id in muted_users:
        del muted_users[user_id]
        return True
    return False

def warn_user(user_id, reason=""):
    user_warnings[user_id] += 1
    if user_id in user_data:
        user_data[user_id]["warnings"] = user_data[user_id].get("warnings", 0) + 1
        if user_data[user_id]["warnings"] >= MAX_WARNINGS:
            ban_user(user_id, f"Превышен лимит предупреждений ({MAX_WARNINGS})")
            return True, "user_banned"
    return True, "warned"

def set_bot_pause(paused, reason=""):
    global bot_paused, pause_reason
    bot_paused = paused
    pause_reason = reason

def update_bot_settings(new_settings):
    global bot_settings, MAX_CHATS, MAX_SAVED_MESSAGES, DEFAULT_REQUESTS_PER_MINUTE
    global DEFAULT_REQUESTS_PER_HOUR, DEFAULT_REQUESTS_PER_DAY, DEFAULT_COOLDOWN
    global MAX_WARNINGS, MAX_ADULT_ATTEMPTS, API_CALL_COOLDOWN
    bot_settings.update(new_settings)
    MAX_CHATS = bot_settings["max_chats"]
    MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
    DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
    DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
    DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
    DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
    MAX_WARNINGS = bot_settings["max_warnings"]
    MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
    API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]

def format_welcome_message(user_id, first_name, chat_name):
    if user_id in user_data and "message_style" in user_data[user_id]:
        style = user_data[user_id]["message_style"]
    else:
        style = bot_settings.get("message_style", "standard")
    template = MESSAGE_STYLES[style]["template"]
    model_name = get_model_name(user_data[user_id]["model"])
    mode_name = MODES[user_data[user_id]["mode"]]["name"]
    stats = user_data[user_id].get("total_messages", 0)
    if bot_settings["custom_greeting"]:
        base = bot_settings["custom_greeting"].format(name=first_name, chat=chat_name)
    else:
        base = template.format(
            name=first_name,
            chat=chat_name,
            model=model_name,
            mode=mode_name,
            stats=stats
        )
    if bot_settings["custom_info"]:
        base += f"\n\n{bot_settings['custom_info']}"
    return base

async def delete_all_messages(user_id, context, except_last=None):
    if user_id in dialog_messages:
        messages_to_delete = []
        for msg_id in dialog_messages[user_id]:
            if msg_id != except_last:
                messages_to_delete.append(msg_id)
        for msg_id in messages_to_delete:
            try:
                await context.bot.delete_message(user_id, msg_id)
                await asyncio.sleep(0.05)
            except:
                pass
        if except_last:
            dialog_messages[user_id] = [except_last]
        else:
            dialog_messages[user_id] = []

async def delete_menu(user_id, context):
    if user_id in menu_messages:
        try:
            await context.bot.delete_message(user_id, menu_messages[user_id])
        except:
            pass
        del menu_messages[user_id]

# ----------------------------------------------------------------------
# Инициализация Groq клиентов с несколькими ключами
# ----------------------------------------------------------------------
async def init_groq_clients():
    """Инициализация нескольких Groq клиентов для распределения нагрузки"""
    global groq_clients
    
    valid_clients = []
    for api_key in GROQ_API_KEYS:
        try:
            client = Groq(api_key=api_key, timeout=30.0, max_retries=2)
            # Проверка ключа
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: client.models.list())
            valid_clients.append(client)
            logger.info(f"✅ Groq клиент с ключом {api_key[:10]}... инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Groq клиента с ключом {api_key[:10]}...: {e}")
    
    groq_clients = valid_clients
    logger.info(f"✅ Всего активно Groq клиентов: {len(groq_clients)} из {len(GROQ_API_KEYS)}")
    return len(groq_clients) > 0

async def get_next_groq_client():
    """Получение следующего клиента по круговой схеме с блокировкой"""
    global current_client_index
    
    if not groq_clients:
        return None
    
    async with client_lock:
        if bot_settings["api_key_rotation"] == "random":
            return random.choice(groq_clients)
        else:  # round_robin
            client = groq_clients[current_client_index]
            current_client_index = (current_client_index + 1) % len(groq_clients)
            return client

async def call_groq_with_failover(model, messages, temperature=0.8, max_tokens=1024, timeout=30):
    """Вызов Groq API с автоматическим переключением при ошибке"""
    if not groq_clients:
        raise Exception("Нет доступных Groq клиентов")
    
    errors = []
    for attempt in range(len(groq_clients)):
        client = await get_next_groq_client()
        
        # Находим индекс клиента для статистики
        try:
            client_index = groq_clients.index(client) if client in groq_clients else -1
            api_key = GROQ_API_KEYS[client_index] if client_index >= 0 else "unknown"
        except:
            api_key = "unknown"
        
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout
                )
            )
            # Обновляем статистику успеха
            if api_key in api_key_stats:
                api_key_stats[api_key]["success"] += 1
            return response
            
        except Exception as e:
            # Обновляем статистику ошибок
            if api_key in api_key_stats:
                api_key_stats[api_key]["error"] += 1
                api_key_stats[api_key]["last_error"] = str(e)
            
            error_msg = f"Ошибка при использовании ключа {api_key[:10]}...: {e}"
            errors.append(error_msg)
            logger.warning(f"{error_msg}. Попытка {attempt + 1}/{len(groq_clients)}")
            
            if attempt == len(groq_clients) - 1:
                # Последняя попытка - пробрасываем исключение
                raise Exception(f"Все Groq клиенты недоступны. Ошибки: {', '.join(errors)}")
    
    raise Exception("Все Groq клиенты недоступны")

# ----------------------------------------------------------------------
# Уведомления
# ----------------------------------------------------------------------
async def notify_owner(context, message):
    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"⚠️ Уведомление владельцу\n\n{message}",
                parse_mode=None
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление владельцу: {e}")

async def notify_admins(context, message):
    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"📢 Уведомление администраторам\n\n{message}",
                parse_mode=None
            )
        except:
            pass

# ----------------------------------------------------------------------
# Клавиатуры
# ----------------------------------------------------------------------
def get_main_keyboard(user_id):
    mode_emoji = MODES[user_data.get(user_id, {}).get("mode", "normal")]["emoji"]
    keyboard = [
        [InlineKeyboardButton(f"{mode_emoji} Режим", callback_data="show_modes"),
         InlineKeyboardButton("🚀 Модель", callback_data="show_models")],
        [InlineKeyboardButton("📋 Чаты", callback_data="show_chats"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="show_settings")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="show_info")]
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Панель администратора", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_dialog_reply_keyboard():
    """Обычная клавиатура диалога"""
    keyboard = [
        ["💾 Сохранить", "❌ Завершить диалог"],
        ["📊 Статистика"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_navigation_reply_keyboard():
    """Навигационная клавиатура для режима сохранения"""
    keyboard = [
        ["↩️ Вернуться в диалог", "🏠 Выйти в меню"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_save_menu_inline_keyboard():
    """Меню выбора что сохранить (inline)"""
    keyboard = [
        [InlineKeyboardButton("🤖 Сохранить ответ бота", callback_data="save_bot_response")],
        [InlineKeyboardButton("👤 Сохранить мой запрос", callback_data="save_user_request")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_save")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------------------------------------------------------------
# Команда /start
# ----------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    allowed, msg = check_user_restrictions(user_id, username)
    if not allowed:
        await update.message.reply_text(msg)
        return

    await delete_all_messages(user_id, context)

    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["username"] = username
        create_chat(user_id, "Основной чат", is_temporary=False)

        global OWNER_CHAT_ID
        if not OWNER_CHAT_ID:
            OWNER_CHAT_ID = user_id
            user_limits.setdefault(user_id, {})["is_owner"] = True
            logger.info(f"Владелец определён: {user_id}")
            
            # Инициализируем Groq клиенты с несколькими ключами
            success = await init_groq_clients()
            if success:
                logger.info("✅ Groq клиенты успешно активированы")
            else:
                logger.error("❌ Ошибка активации Groq клиентов")
            
            welcome_text = (
                "👑 Вы назначены владельцем бота!\n\n"
                "✅ Бот успешно запущен!\n\n"
                "✨ Доступные модели:\n"
                "• 🦙 LLaMA 3.1 8B\n• 🔸 Gemma 2 9B\n• 🦙 LLaMA 3.3 70B\n\n"
                f"🔑 Активно API ключей: {len(groq_clients)} из {len(GROQ_API_KEYS)}\n"
                "• Нагрузка распределяется автоматически\n\n"
                "👥 Управление администраторами:\n"
                "• В панели администратора вы можете добавлять/удалять админов по username\n"
                "• Главный администратор (вы) не может быть удален"
            )
            msg = await update.message.reply_text(
                welcome_text,
                reply_markup=get_main_keyboard(user_id),
                parse_mode=None
            )
            menu_messages[user_id] = msg.message_id
            dialog_messages[user_id] = [msg.message_id]
            return

    current_chat_name = user_data[user_id]["current_chat"]["name"]
    welcome = format_welcome_message(user_id, first_name, current_chat_name)
    msg = await update.message.reply_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
    menu_messages[user_id] = msg.message_id
    dialog_messages[user_id] = [msg.message_id]
    user_data[user_id]["last_message_id"] = msg.message_id
    user_data[user_id]["save_mode"] = False
    user_data[user_id]["current_menu"] = "main"

# ----------------------------------------------------------------------
# Обработчик текстовых сообщений
# ----------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    user_message = update.message.text

    allowed, msg = check_user_restrictions(user_id, username)
    if not allowed:
        await update.message.reply_text(msg)
        return

    if user_id not in user_data:
        init_user_data(user_id)
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    dialog_messages[user_id].append(update.message.message_id)

    if "recent_messages" not in user_data[user_id]:
        user_data[user_id]["recent_messages"] = []
    user_data[user_id]["recent_messages"].append({
        "text": user_message,
        "sender": "user",
        "timestamp": time.time()
    })
    if len(user_data[user_id]["recent_messages"]) > 20:
        user_data[user_id]["recent_messages"] = user_data[user_id]["recent_messages"][-20:]

    # Обработка навигационных кнопок
    if user_message == "↩️ Вернуться в диалог":
        user_data[user_id]["save_mode"] = False
        if user_id in pending_save:
            del pending_save[user_id]
        await context.bot.send_message(
            user_id,
            "🔹🔹🔹 ВЫ В ДИАЛОГЕ 🔹🔹🔹\n\nМожете продолжать общение с ботом. Кнопки управления под строкой ввода.",
            reply_markup=get_dialog_reply_keyboard()
        )
        return

    if user_message == "🏠 Выйти в меню":
        await show_main_menu(update, context, user_id)
        return

    # Обработка выбора номера сообщения для сохранения
    if user_id in pending_save:
        await handle_save_number_selection(update, context, user_id, user_message)
        return

    # Обработка ожидаемого ввода
    if user_id in awaiting_input:
        await handle_awaiting_input(update, context, user_id, user_message)
        return

    # Обработка кнопок обычной клавиатуры
    if user_message == "💾 Сохранить":
        user_data[user_id]["save_mode"] = True
        await context.bot.send_message(
            user_id,
            "💾 Режим сохранения сообщений\n\nВыберите, что хотите сохранить:",
            reply_markup=get_navigation_reply_keyboard()
        )
        save_menu_msg = await update.message.reply_text(
            "👇 Выберите тип сообщения:",
            reply_markup=get_save_menu_inline_keyboard(),
            parse_mode=None
        )
        dialog_messages[user_id].append(save_menu_msg.message_id)
        return

    if user_message == "❌ Завершить диалог":
        await end_dialog(update, context)
        return

    if user_message == "📊 Статистика":
        saved_cnt = len(saved_messages.get(user_id, []))
        total_msgs = user_data[user_id].get("total_messages", 0)
        personal = user_data[user_id].get("personal_limits", {})
        rpm = personal.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
        cd = personal.get("cooldown", DEFAULT_COOLDOWN)
        stats_text = (
            f"📊 Ваша статистика:\n\n"
            f"• Всего сообщений: {total_msgs}\n"
            f"• Сохранено: {saved_cnt}\n"
            f"• Ваш лимит: {rpm} запросов/мин\n"
            f"• Ваш cooldown: {cd} сек\n"
            f"• Модель: {get_model_name(user_data[user_id]['model'])}\n"
            f"• Режим: {MODES[user_data[user_id]['mode']]['name']}"
        )
        msg = await update.message.reply_text(stats_text, parse_mode=None)
        dialog_messages[user_id].append(msg.message_id)
        return

    # Проверяем, находится ли пользователь в режиме сохранения
    if user_data[user_id].get("save_mode", False):
        await update.message.reply_text(
            "❌ Вы находитесь в режиме сохранения сообщений.\n\n"
            "Чтобы задать вопрос боту, сначала завершите сохранение:\n"
            "• Введите номер сообщения для сохранения\n"
            "• Нажмите '↩️ Вернуться в диалог'\n"
            "• Нажмите '🏠 Выйти в меню'",
            reply_markup=get_navigation_reply_keyboard()
        )
        return

    # Проверяем, находится ли пользователь в меню (не в диалоге)
    if user_data[user_id].get("current_menu") != "main" and user_data[user_id].get("current_menu") != "dialog":
        # Пользователь в каком-то меню (настройки, чаты и т.д.) - не отвечаем на вопросы
        await update.message.reply_text(
            "❌ Вы находитесь в меню. Чтобы задать вопрос боту, сначала вернитесь в диалог.\n\n"
            "Используйте кнопку '↩️ Вернуться в диалог' или '🏠 Выйти в меню' для навигации.",
            reply_markup=get_navigation_reply_keyboard() if user_data[user_id].get("save_mode") else get_dialog_reply_keyboard()
        )
        return

    # Основной диалог с ботом
    await delete_menu(user_id, context)

    if not user_data[user_id]["current_chat"]:
        create_chat(user_id, "Временный чат", is_temporary=True)

    now = time.time()
    if user_id in user_last_message and now - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = now

    allowed, msg = check_request_limits(user_id)
    if not allowed:
        error_msg = await update.message.reply_text(
            f"{msg}\n\n❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(error_msg.message_id)
        return

    if check_adult_content(user_message):
        user_data[user_id]["adult_attempts"] = user_data[user_id].get("adult_attempts", 0) + 1
        adult_attempts = user_data[user_id]["adult_attempts"]
        violation_msg = add_violation(user_id, "Попытка получить 18+ контент")
        if violation_msg:
            await notify_owner(context, violation_msg)
        if adult_attempts >= MAX_ADULT_ATTEMPTS:
            result, status = warn_user(user_id, "Попытка получить 18+ контент")
            if status == "user_banned":
                await update.message.reply_text(
                    "❌ Вы забанены за многократные попытки получить 18+ контент!\n\n"
                    "Обратитесь к администратору для разблокировки.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📨 Связаться с владельцем", callback_data="contact_owner")]])
                )
                return
            else:
                warnings_left = MAX_WARNINGS - user_data[user_id].get("warnings", 0)
                warning_msg = await update.message.reply_text(
                    f"⚠️ Предупреждение {user_data[user_id].get('warnings', 0)}/{MAX_WARNINGS}\n\n"
                    f"Ваш запрос содержит потенциально неприемлемый контент.\n"
                    f"Осталось предупреждений до бана: {warnings_left}\n\n"
                    f"❓ Хотите выйти из чата?",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
                )
                dialog_messages[user_id].append(warning_msg.message_id)
                return
        reject_msg = await update.message.reply_text(
            f"❌ Запрос отклонен\n\n"
            f"Бот не отвечает на запросы, содержащие 18+ контент.\n\n"
            f"Попытка {adult_attempts}/{MAX_ADULT_ATTEMPTS} (до предупреждения)\n\n"
            f"❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(reject_msg.message_id)
        return

    user_data[user_id]["in_dialog"] = True
    user_data[user_id]["current_menu"] = "dialog"
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        if not groq_clients:
            # Пробуем инициализировать клиенты, если их нет
            success = await init_groq_clients()
            if not success or not groq_clients:
                error_msg = await update.message.reply_text(
                    "❌ Ошибка API\n\nНет доступных Groq клиентов. Администратор уже уведомлен.\n\n❓ Хотите выйти из чата?",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]),
                    parse_mode=None
                )
                dialog_messages[user_id].append(error_msg.message_id)
                return

        current_chat = user_data[user_id]["current_chat"]
        history = current_chat["messages"]
        history.append({"role": "user", "content": user_message})
        user_data[user_id]["total_messages"] += 1
        last_message_text.setdefault(user_id, {})["user"] = user_message

        if len(history) > 51:
            history[:] = [history[0]] + history[-50:]

        record_request(user_id)

        if not can_call_api(user_id):
            cooldown_msg = await update.message.reply_text(
                "⏱️ Слишком частые запросы к API. Подождите немного.\n\n❓ Хотите выйти из чата?",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
            )
            dialog_messages[user_id].append(cooldown_msg.message_id)
            return

        # Используем распределение нагрузки
        response = await call_groq_with_failover(
            model=user_data[user_id]["model"],
            messages=history,
            temperature=0.8,
            max_tokens=1024,
            timeout=30
        )

        assistant_message = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_message})
        last_message_text[user_id]["bot"] = assistant_message
        user_data[user_id]["last_bot_message"] = assistant_message

        user_data[user_id]["recent_messages"].append({
            "text": assistant_message,
            "sender": "bot",
            "timestamp": time.time()
        })
        if len(user_data[user_id]["recent_messages"]) > 20:
            user_data[user_id]["recent_messages"] = user_data[user_id]["recent_messages"][-20:]

        if random.random() < 0.1:
            assistant_message += f"\n\n— — — — — — — — — — — — — — —\n{get_random_quote()}"

        await delete_all_messages(user_id, context, except_last=None)

        sent = await update.message.reply_text(
            assistant_message,
            reply_markup=get_dialog_reply_keyboard(),
            parse_mode=None
        )
        dialog_messages[user_id].append(sent.message_id)
        user_data[user_id]["last_message_id"] = sent.message_id
        user_data[user_id]["last_bot_message_id"] = sent.message_id

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от {user_id}: {e}")
        error_count += 1
        last_error_time = time.time()
        error_users.add(user_id)
        err_text = "❌ Ошибка при получении ответа от API. Все ключи могли быть временно недоступны."
        error_msg = await update.message.reply_text(
            f"{err_text}\n\n❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(error_msg.message_id)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    first_name = update.effective_user.first_name
    current_chat_name = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
    welcome = format_welcome_message(user_id, first_name, current_chat_name)
    if bot_paused:
        welcome = f"⏸️ Бот временно приостановлен\n\nПричина: {pause_reason}\n\n{welcome}"
    await delete_all_messages(user_id, context)
    msg = await context.bot.send_message(
        user_id,
        welcome,
        reply_markup=get_main_keyboard(user_id),
        parse_mode=None
    )
    menu_messages[user_id] = msg.message_id
    dialog_messages[user_id] = [msg.message_id]
    user_data[user_id]["save_mode"] = False
    user_data[user_id]["current_menu"] = "main"
    if user_id in pending_save:
        del pending_save[user_id]

# ----------------------------------------------------------------------
# Обработка выбора номера для сохранения
# ----------------------------------------------------------------------
async def handle_save_number_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_message: str):
    try:
        number = int(user_message.strip())
        save_info = pending_save[user_id]
        messages = save_info["messages"]
        if 1 <= number <= len(messages):
            selected_msg = messages[number - 1]
            sender = save_info["type"]
            save_message(user_id, selected_msg["text"], sender)
            await update.message.reply_text(
                f"✅ Сообщение сохранено!\n\nТекст: {selected_msg['text'][:100]}...",
                parse_mode=None
            )
            del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            user_data[user_id]["current_menu"] = "dialog"
            await context.bot.send_message(
                user_id,
                "🔹🔹🔹 ВЫ В ДИАЛОГЕ 🔹🔹🔹\n\nМожете продолжать общение с ботом. Кнопки управления под строкой ввода.",
                reply_markup=get_dialog_reply_keyboard()
            )
        else:
            await update.message.reply_text(
                f"❌ Неверный номер. Введите число от 1 до {len(messages)}",
                reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True)
            )
    except ValueError:
        if user_message.strip() == "◀️ Отмена":
            del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            user_data[user_id]["current_menu"] = "dialog"
            await update.message.reply_text(
                "❌ Сохранение отменено",
                reply_markup=get_dialog_reply_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Пожалуйста, введите номер сообщения или нажмите '◀️ Отмена'",
                reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True)
            )

# ----------------------------------------------------------------------
# Обработчик фото
# ----------------------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    allowed, msg = check_user_restrictions(user_id, username)
    if not allowed:
        await update.message.reply_text(msg)
        return
    
    if user_id not in user_data:
        init_user_data(user_id)
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    
    msg = await update.message.reply_text(
        "📸 Бот не умеет анализировать фото\n\nЯ работаю только с текстом. Отправь текстовое сообщение.\n\n❓ Хотите выйти из чата?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]),
        parse_mode=None
    )
    dialog_messages[user_id].append(msg.message_id)

# ----------------------------------------------------------------------
# Завершение диалога
# ----------------------------------------------------------------------
async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    await delete_all_messages(user_id, context)
    if user_id in user_data:
        cur = user_data[user_id].get("current_chat")
        if cur and cur.get("is_temporary"):
            user_data[user_id]["temp_chat"] = None
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
        else:
            user_data[user_id]["in_dialog"] = False
    current_chat_name = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
    welcome = format_welcome_message(user_id, first_name, current_chat_name)
    if bot_paused:
        welcome = f"⏸️ Бот временно приостановлен\n\nПричина: {pause_reason}\n\n{welcome}"
    await context.bot.send_message(
        user_id,
        "✅ Диалог завершен",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True, one_time_keyboard=False)
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
            menu_messages[user_id] = update.callback_query.message.message_id
            dialog_messages[user_id] = [update.callback_query.message.message_id]
        except:
            msg = await context.bot.send_message(user_id, welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
            menu_messages[user_id] = msg.message_id
            dialog_messages[user_id] = [msg.message_id]
    else:
        msg = await context.bot.send_message(user_id, welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
        menu_messages[user_id] = msg.message_id
        dialog_messages[user_id] = [msg.message_id]
    user_data[user_id]["save_mode"] = False
    user_data[user_id]["current_menu"] = "main"

# ----------------------------------------------------------------------
# Показ списка чатов
# ----------------------------------------------------------------------
async def show_chats_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, from_dialog=False):
    user_data[user_id]["current_menu"] = "chats"
    keyboard = []
    permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
    if permanent_chats:
        for chat in permanent_chats:
            mark = "✅ " if user_data[user_id]["current_chat_id"] == chat["id"] else ""
            msg_count = len([m for m in chat["messages"] if m["role"] != "system"])
            btn_text = f"{mark}{chat['name']} ({msg_count} сообщ.)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_chat_{chat['id']}")])
    if user_data[user_id]["temp_chat"]:
        temp = user_data[user_id]["temp_chat"]
        mark = "✅ " if user_data[user_id]["current_chat_id"] == temp["id"] else ""
        msg_count = len([m for m in temp["messages"] if m["role"] != "system"])
        btn_text = f"{mark}⏳ {temp['name']} ({msg_count} сообщ.)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_chat_{temp['id']}")])

    action_buttons = [
        InlineKeyboardButton("➕ Постоянный", callback_data="new_permanent_chat"),
        InlineKeyboardButton("⏳ Временный", callback_data="new_temp_chat")
    ]
    keyboard.append(action_buttons)

    if from_dialog:
        keyboard.append([InlineKeyboardButton("🔄 Вернуться в диалог", callback_data="back_to_dialog")])
    else:
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

    text = f"📋 Мои чаты\n\nВсего постоянных: {len(permanent_chats)}/{MAX_CHATS}"
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)

def get_model_name(model_id):
    for name, mid in GROQ_MODELS.items():
        if mid == model_id:
            return name
    return model_id

# ----------------------------------------------------------------------
# Обработчик ожидаемого ввода
# ----------------------------------------------------------------------
async def handle_awaiting_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_message: str):
    """Обработка ожидаемого ввода (для настроек, создания чатов и т.д.)"""
    action_data = awaiting_input[user_id]

    if action_data.get("action") == "new_chat_name":
        del awaiting_input[user_id]
        chat_type = action_data.get("chat_type")
        if chat_type == "permanent":
            permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
            if len(permanent_chats) >= MAX_CHATS:
                keyboard = [
                    [InlineKeyboardButton("🗑 Удалить самый старый чат", callback_data="delete_oldest_and_create")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                msg = await update.message.reply_text(
                    f"❌ Достигнут лимит постоянных чатов ({MAX_CHATS}).\n\nХотите удалить самый старый чат и создать новый?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                dialog_messages[user_id].append(msg.message_id)
                return
            chat_id, error = create_chat(user_id, user_message[:50], is_temporary=False)
            if chat_id:
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text(f"❌ {error}")
                dialog_messages[user_id].append(msg.message_id)
        elif chat_type == "temporary":
            if user_data[user_id]["temp_chat"]:
                keyboard = [
                    [InlineKeyboardButton("✅ Заменить", callback_data="replace_temp_chat")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                msg = await update.message.reply_text("У вас уже есть временный чат. Заменить его?", reply_markup=InlineKeyboardMarkup(keyboard))
                dialog_messages[user_id].append(msg.message_id)
                awaiting_input[user_id] = {"action": "confirm_replace_temp", "name": user_message[:50]}
            else:
                chat_id, error = create_chat(user_id, user_message[:50], is_temporary=True)
                if chat_id:
                    await show_main_menu(update, context, user_id)
        return

    elif action_data.get("action") == "message_to_owner":
        del awaiting_input[user_id]
        if OWNER_CHAT_ID:
            try:
                user_info = f"От: {update.effective_user.first_name}"
                if update.effective_user.username:
                    user_info += f" (@{update.effective_user.username})"
                user_info += f"\nID: {user_id}"
                await context.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=f"📨 Сообщение от пользователя\n\n{user_info}\n\nТекст:\n{user_message}",
                    parse_mode=None
                )
                await show_main_menu(update, context, user_id)
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения владельцу: {e}")
                msg = await update.message.reply_text("❌ Не удалось отправить сообщение. Попробуйте позже.", reply_markup=get_main_keyboard(user_id))
                menu_messages[user_id] = msg.message_id
                dialog_messages[user_id] = [msg.message_id]
        return

    elif action_data.get("action") == "set_custom_note":
        del awaiting_input[user_id]
        user_custom_notes[user_id] = user_message
        user_data[user_id]["custom_note"] = user_message
        if user_data[user_id]["current_chat"]:
            custom_note = user_custom_notes.get(user_id, "")
            system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
            user_data[user_id]["current_chat"]["messages"][0]["content"] = system_prompt
        
        await show_main_menu(update, context, user_id)
        return

    elif action_data.get("action") == "set_personal_rpm":
        del awaiting_input[user_id]
        try:
            limit = int(user_message)
            if 1 <= limit <= 60:
                user_data[user_id]["personal_limits"]["requests_per_minute"] = limit
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text("❌ Лимит должен быть от 1 до 60")
                dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            msg = await update.message.reply_text("❌ Введите число")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_personal_cooldown":
        del awaiting_input[user_id]
        try:
            cd = int(user_message)
            if 1 <= cd <= 10:
                user_data[user_id]["personal_limits"]["cooldown"] = cd
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text("❌ Cooldown должен быть от 1 до 10 сек")
                dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            msg = await update.message.reply_text("❌ Введите число")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_message_style":
        del awaiting_input[user_id]
        style = user_message.strip().lower()
        if style in MESSAGE_STYLES:
            user_data[user_id]["message_style"] = style
            await show_main_menu(update, context, user_id)
        else:
            styles_list = ", ".join([f"'{s}'" for s in MESSAGE_STYLES.keys()])
            msg = await update.message.reply_text(f"❌ Неверный стиль. Доступны: {styles_list}")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "add_admin" and is_admin(user_id):
        del awaiting_input[user_id]
        username = user_message.strip()
        if username.startswith('@'):
            username = username[1:]
        ADMINS.add(username.lower())
        await show_main_menu(update, context, user_id)
        await notify_owner(context, f"Администратор @{username} добавлен пользователем {user_id}")
        return

    elif action_data.get("action") == "remove_admin" and is_admin(user_id):
        del awaiting_input[user_id]
        username = user_message.strip()
        if username.startswith('@'):
            username = username[1:]
        if username.lower() in ADMINS:
            ADMINS.remove(username.lower())
            await show_main_menu(update, context, user_id)
        else:
            msg = await update.message.reply_text(f"❌ Пользователь @{username} не найден в списке администраторов")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_cooldown" and is_admin(user_id):
        del awaiting_input[user_id]
        try:
            cooldown = int(user_message)
            if cooldown >= 0:
                for uid in user_limits:
                    user_limits[uid]["cooldown"] = cooldown
                bot_settings["default_cooldown"] = cooldown
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text("❌ Cooldown должен быть >= 0")
                dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            msg = await update.message.reply_text("❌ Введите число")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_requests_per_minute" and is_admin(user_id):
        del awaiting_input[user_id]
        try:
            limit = int(user_message)
            if limit >= 0:
                for uid in user_limits:
                    user_limits[uid]["requests_per_minute"] = limit
                bot_settings["default_requests_per_minute"] = limit
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text("❌ Лимит должен быть >= 0")
                dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            msg = await update.message.reply_text("❌ Введите число")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_max_chats" and is_admin(user_id):
        del awaiting_input[user_id]
        try:
            limit = int(user_message)
            if limit >= 1:
                bot_settings["max_chats"] = limit
                update_bot_settings({"max_chats": limit})
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text("❌ Лимит должен быть >= 1")
                dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            msg = await update.message.reply_text("❌ Введите число")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_max_saved" and is_admin(user_id):
        del awaiting_input[user_id]
        try:
            limit = int(user_message)
            if limit >= 1:
                bot_settings["max_saved_messages"] = limit
                update_bot_settings({"max_saved_messages": limit})
                await show_main_menu(update, context, user_id)
            else:
                msg = await update.message.reply_text("❌ Лимит должен быть >= 1")
                dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            msg = await update.message.reply_text("❌ Введите число")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "set_welcome_message" and is_admin(user_id):
        del awaiting_input[user_id]
        bot_settings["welcome_message"] = user_message
        await show_main_menu(update, context, user_id)
        return

    elif action_data.get("action") == "set_custom_greeting" and is_admin(user_id):
        del awaiting_input[user_id]
        bot_settings["custom_greeting"] = user_message
        await show_main_menu(update, context, user_id)
        return

    elif action_data.get("action") == "set_custom_info" and is_admin(user_id):
        del awaiting_input[user_id]
        bot_settings["custom_info"] = user_message
        await show_main_menu(update, context, user_id)
        return

    elif action_data.get("action") == "set_message_style_default" and is_admin(user_id):
        del awaiting_input[user_id]
        style = user_message.strip().lower()
        if style in MESSAGE_STYLES:
            bot_settings["message_style"] = style
            await show_main_menu(update, context, user_id)
        else:
            styles_list = ", ".join([f"'{s}'" for s in MESSAGE_STYLES.keys()])
            msg = await update.message.reply_text(f"❌ Неверный стиль. Доступны: {styles_list}")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "ban_user" and is_admin(user_id):
        del awaiting_input[user_id]
        target = user_message.strip()
        try:
            target_id = int(target)
            ban_user(target_id, "Забанен администратором")
            msg = await update.message.reply_text(f"✅ Пользователь {target_id} забанен")
            dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            if target.startswith('@'):
                target = target[1:]
            ban_user(None, "Забанен администратором", username=target)
            msg = await update.message.reply_text(f"✅ Username @{target} забанен")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "unban_user" and is_admin(user_id):
        del awaiting_input[user_id]
        target = user_message.strip()
        try:
            target_id = int(target)
            unban_user(target_id)
            msg = await update.message.reply_text(f"✅ Пользователь {target_id} разбанен")
            dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            if target.startswith('@'):
                target = target[1:]
            unban_user(None, target)
            msg = await update.message.reply_text(f"✅ Username @{target} разбанен")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "mute_user" and is_admin(user_id):
        duration = action_data.get("duration", 3600)
        del awaiting_input[user_id]
        target = user_message.strip()
        try:
            target_id = int(target)
            mute_user(target_id, duration, "Мут администратором")
            msg = await update.message.reply_text(f"✅ Пользователь {target_id} в муте на {duration//60} минут")
            dialog_messages[user_id].append(msg.message_id)
        except ValueError:
            if target.startswith('@'):
                target = target[1:]
            found = False
            for uid, data in user_data.items():
                if data.get("username") == target:
                    mute_user(uid, duration, "Мут администратором")
                    msg = await update.message.reply_text(f"✅ Пользователь @{target} в муте на {duration//60} минут")
                    found = True
                    break
            if not found:
                msg = await update.message.reply_text(f"❌ Пользователь @{target} не найден")
            dialog_messages[user_id].append(msg.message_id)
        return

    elif action_data.get("action") == "pause_reason" and is_admin(user_id):
        del awaiting_input[user_id]
        set_bot_pause(True, user_message)
        await show_main_menu(update, context, user_id)
        await notify_admins(context, f"Бот приостановлен. Причина: {user_message}")
        return

# ----------------------------------------------------------------------
# Обработчик inline-кнопок
# ----------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        username = query.from_user.username
        first_name = query.from_user.first_name

        allowed, msg = check_user_restrictions(user_id, username)
        if not allowed:
            await query.edit_message_text(msg)
            return

        if user_id not in user_data:
            init_user_data(user_id)
            user_data[user_id]["username"] = username
            create_chat(user_id, "Основной чат", is_temporary=False)

        data = query.data

        # Навигация
        if data == "back_to_main":
            current_chat_name = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
            welcome = format_welcome_message(user_id, first_name, current_chat_name)
            if bot_paused:
                welcome = f"⏸️ Бот временно приостановлен\n\nПричина: {pause_reason}\n\n{welcome}"
            await query.edit_message_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["save_mode"] = False
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "end_dialog":
            await end_dialog(update, context)
            return

        if data == "show_chats_from_dialog":
            await show_chats_interface(update, context, user_id, from_dialog=True)
            return

        if data == "back_to_dialog":
            last_id = user_data[user_id].get("last_message_id")
            if last_id:
                await query.edit_message_text("🔄 Возврат в диалог", reply_markup=None, parse_mode=None)
                await context.bot.send_message(
                    user_id,
                    "🔹🔹🔹 ВЫ В ДИАЛОГЕ 🔹🔹🔹\n\nМожете продолжать общение с ботом. Кнопки управления под строкой ввода.",
                    reply_markup=get_dialog_reply_keyboard()
                )
                user_data[user_id]["save_mode"] = False
                user_data[user_id]["current_menu"] = "dialog"
            else:
                await query.edit_message_text("❌ Не найден активный диалог", reply_markup=get_main_keyboard(user_id))
            return

        if data == "contact_owner":
            user_data[user_id]["current_menu"] = "info"
            awaiting_input[user_id] = {"action": "message_to_owner"}
            await query.edit_message_text(
                "📝 Напишите сообщение для владельца бота\n\nОн получит его и сможет ответить вам.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode=None
            )
            return

        # Сохранение сообщений
        if data == "save_bot_response":
            bot_messages = []
            if "recent_messages" in user_data[user_id]:
                bot_messages = [msg for msg in user_data[user_id]["recent_messages"] if msg["sender"] == "bot"]
            if bot_messages:
                text = "🤖 Выберите сообщение бота для сохранения:\n\n"
                messages_list = []
                for i, msg in enumerate(bot_messages[-10:], 1):
                    text += f"{i}. {msg['text'][:100]}...\n\n"
                    messages_list.append(msg)
                pending_save[user_id] = {"type": "bot", "messages": messages_list}
                await query.edit_message_text(
                    text + "\n📝 Введите номер сообщения:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_save")]]),
                    parse_mode=None
                )
            else:
                await query.edit_message_text("❌ Нет сообщений бота для сохранения")
            return

        if data == "save_user_request":
            user_messages = []
            if "recent_messages" in user_data[user_id]:
                user_messages = [msg for msg in user_data[user_id]["recent_messages"] if msg["sender"] == "user"]
            if user_messages:
                text = "👤 Выберите ваше сообщение для сохранения:\n\n"
                messages_list = []
                for i, msg in enumerate(user_messages[-10:], 1):
                    text += f"{i}. {msg['text'][:100]}...\n\n"
                    messages_list.append(msg)
                pending_save[user_id] = {"type": "user", "messages": messages_list}
                await query.edit_message_text(
                    text + "\n📝 Введите номер сообщения:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_save")]]),
                    parse_mode=None
                )
            else:
                await query.edit_message_text("❌ Нет ваших сообщений для сохранения")
            return

        if data == "cancel_save":
            if user_id in pending_save:
                del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            await query.edit_message_text("❌ Сохранение отменено")
            await context.bot.send_message(
                user_id,
                "🔹🔹🔹 ВЫ В ДИАЛОГЕ 🔹🔹🔹\n\nМожете продолжать общение с ботом. Кнопки управления под строкой ввода.",
                reply_markup=get_dialog_reply_keyboard()
            )
            return

        # Информация
        if data == "show_info":
            user_data[user_id]["current_menu"] = "info"
            uptime_seconds = int(time.time() - bot_start_time)
            uptime_str = str(timedelta(seconds=uptime_seconds))
            now = datetime.now()
            total_users = len(user_data)
            active_now = sum(1 for d in user_data.values() if d.get("in_dialog"))
            total_req = global_request_count
            banned_cnt = len(banned_users)
            muted_cnt = len(muted_users)
            violations_cnt = sum(len(v) for v in violations.values())
            pause_status = "⏸️ Приостановлен" if bot_paused else "▶️ Активен"
            text = (
                f"ℹ️ Информация о боте\n\n"
                f"📅 Текущая дата: {now.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏱ Аптайм: {uptime_str}\n"
                f"{pause_status}\n\n"
                f"📊 Статистика использования:\n"
                f"• Всего пользователей: {total_users}\n"
                f"• Активных диалогов: {active_now}\n"
                f"• Забанено: {banned_cnt}\n"
                f"• В муте: {muted_cnt}\n"
                f"• Нарушений: {violations_cnt}\n"
                f"• Всего запросов: {total_req}\n\n"
                f"🚀 Доступные модели:\n"
                f"• 🦙 LLaMA 3.1 8B\n• 🔸 Gemma 2 9B\n• 🦙 LLaMA 3.3 70B\n\n"
                f"📨 Связь с владельцем:\n"
                f"Нажмите кнопку ниже, чтобы отправить сообщение"
            )
            keyboard = [[InlineKeyboardButton("📨 Написать владельцу", callback_data="contact_owner")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        # Настройки пользователя
        if data == "show_settings":
            user_data[user_id]["current_menu"] = "settings"
            saved_cnt = len(saved_messages.get(user_id, []))
            saved_lim = user_data[user_id]["saved_messages_limit"]
            warns = user_data[user_id].get("warnings", 0)
            adult_att = user_data[user_id].get("adult_attempts", 0)
            note = user_custom_notes.get(user_id, "Не установлена")
            personal = user_data[user_id].get("personal_limits", {})
            rpm = personal.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
            cd = personal.get("cooldown", DEFAULT_COOLDOWN)
            current_style = user_data[user_id].get("message_style", bot_settings["message_style"])
            style_name = MESSAGE_STYLES[current_style]["name"]
            text = (
                f"⚙️ Настройки пользователя\n\n"
                f"📊 Ваши данные:\n"
                f"• Сохранено сообщений: {saved_cnt}/{saved_lim}\n"
                f"• Всего сообщений: {user_data[user_id].get('total_messages', 0)}\n"
                f"• Предупреждений: {warns}/{MAX_WARNINGS}\n"
                f"• Попыток 18+ запросов: {adult_att}\n\n"
                f"📝 Ваша приписка к запросам:\n"
                f"«{note}»\n\n"
                f"🎨 Ваш стиль сообщения:\n"
                f"{style_name}\n\n"
                f"⚡ Ваши лимиты:\n"
                f"• Запросов в минуту: {rpm}\n"
                f"• Cooldown: {cd} сек\n\n"
                f"🔧 Управление:\n"
            )
            keyboard = [
                [InlineKeyboardButton("📝 Установить приписку", callback_data="set_custom_note")],
                [InlineKeyboardButton("🎨 Выбрать стиль", callback_data="choose_message_style")],
                [InlineKeyboardButton("⚡ Мои лимиты", callback_data="my_limits")],
                [InlineKeyboardButton("💾 Сохраненные сообщения", callback_data="view_saved")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data == "choose_message_style":
            user_data[user_id]["current_menu"] = "settings"
            text = "🎨 Выберите ваш стиль главного сообщения:\n\n"
            for style_id, style_info in MESSAGE_STYLES.items():
                mark = "✅ " if user_data[user_id].get("message_style", bot_settings["message_style"]) == style_id else ""
                text += f"{mark}{style_info['name']}\n{style_info['template'][:50]}...\n\n"
            keyboard = []
            for style_id in MESSAGE_STYLES:
                keyboard.append([InlineKeyboardButton(f"Установить {MESSAGE_STYLES[style_id]['name']}", callback_data=f"set_user_style_{style_id}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="show_settings")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data.startswith("set_user_style_"):
            style = data.replace("set_user_style_", "")
            if style in MESSAGE_STYLES:
                user_data[user_id]["message_style"] = style
                await query.edit_message_text(f"✅ Ваш стиль сообщения изменен на {MESSAGE_STYLES[style]['name']}", reply_markup=get_main_keyboard(user_id), parse_mode=None)
                menu_messages[user_id] = query.message.message_id
                user_data[user_id]["current_menu"] = "main"
            return

        if data == "set_custom_note":
            user_data[user_id]["current_menu"] = "settings"
            awaiting_input[user_id] = {"action": "set_custom_note"}
            await query.edit_message_text(
                "📝 Введите вашу приписку к запросам\n\nЭта приписка будет добавляться к каждому вашему запросу.\n\nВведите текст:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode=None
            )
            return

        if data == "my_limits":
            user_data[user_id]["current_menu"] = "settings"
            personal = user_data[user_id].get("personal_limits", {})
            rpm = personal.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
            cd = personal.get("cooldown", DEFAULT_COOLDOWN)
            text = (
                f"⚡ Ваши лимиты\n\n"
                f"Текущие значения:\n"
                f"• Запросов в минуту: {rpm}\n"
                f"• Cooldown: {cd} сек\n\n"
                f"Вы можете изменить:\n"
                f"• Запросы/мин (1-60)\n"
                f"• Cooldown (1-10 сек)"
            )
            keyboard = [
                [InlineKeyboardButton("📊 Изменить запросы/мин", callback_data="set_personal_rpm")],
                [InlineKeyboardButton("⏱️ Изменить cooldown", callback_data="set_personal_cooldown")],
                [InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data == "set_personal_rpm":
            user_data[user_id]["current_menu"] = "settings"
            awaiting_input[user_id] = {"action": "set_personal_rpm"}
            await query.edit_message_text(
                "📊 Введите ваш лимит запросов в минуту (от 1 до 60):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="my_limits")]]),
                parse_mode=None
            )
            return

        if data == "set_personal_cooldown":
            user_data[user_id]["current_menu"] = "settings"
            awaiting_input[user_id] = {"action": "set_personal_cooldown"}
            await query.edit_message_text(
                "⏱️ Введите ваш cooldown между запросами (от 1 до 10 секунд):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="my_limits")]]),
                parse_mode=None
            )
            return

        if data == "view_saved":
            user_data[user_id]["current_menu"] = "settings"
            if user_id in saved_messages and saved_messages[user_id]:
                text = "💾 Ваши сохраненные сообщения:\n\n"
                for i, msg in enumerate(saved_messages[user_id][-10:], 1):
                    emoji = "👤" if msg["sender"] == "user" else "🤖"
                    time_str = datetime.fromtimestamp(msg["timestamp"]).strftime('%d.%m %H:%M')
                    text += f"{i}. {emoji} [{time_str}] {msg['text'][:100]}\n\n"
            else:
                text = "💾 У вас пока нет сохраненных сообщений"
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        # Панель администратора
        if data == "admin_panel" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            total_requests_today = len([t for t in sum(user_requests.values(), []) if time.time() - t < 86400])
            active_now = len([uid for uid, times in user_requests.items() if times and time.time() - times[-1] < 300])
            banned_cnt = len(banned_users)
            banned_usernames_cnt = len(banned_usernames)
            muted_cnt = len(muted_users)
            violations_cnt = sum(len(v) for v in violations.items())
            pause_status = "⏸️ Приостановлен" if bot_paused else "▶️ Активен"
            
            admin_list = ", ".join([f"@{admin}" for admin in ADMINS]) if ADMINS else "нет"
            
            # Статистика API ключей
            total_success = sum(stats["success"] for stats in api_key_stats.values())
            total_errors = sum(stats["error"] for stats in api_key_stats.values())
            active_keys = len(groq_clients)
            
            api_status = f"📊 Статистика API ключей:\n• Активно: {active_keys}/{len(GROQ_API_KEYS)}\n• Успешных запросов: {total_success}\n• Ошибок: {total_errors}\n"
            
            text = (
                f"👑 Панель администратора\n\n"
                f"{api_status}\n"
                f"📊 Статистика:\n"
                f"• Пользователей: {len(user_data)}\n"
                f"• Активных сейчас: {active_now}\n"
                f"• Запросов сегодня: {total_requests_today}\n"
                f"• Всего запросов: {global_request_count}\n"
                f"• Ошибок: {error_count}\n"
                f"• Нарушений: {violations_cnt}\n\n"
                f"🔨 Ограничения:\n"
                f"• Забанено ID: {banned_cnt}\n"
                f"• Забанено username: {banned_usernames_cnt}\n"
                f"• В муте: {muted_cnt}\n"
                f"• Статус: {pause_status}\n\n"
                f"👥 Администраторы:\n"
                f"{admin_list}\n\n"
                f"⚙️ Текущие настройки:\n"
                f"• Макс. чатов: {bot_settings['max_chats']}\n"
                f"• Макс. сохранений: {bot_settings['max_saved_messages']}\n"
                f"• Cooldown: {bot_settings['default_cooldown']} сек\n"
                f"• Запросов/мин: {bot_settings['default_requests_per_minute']}\n"
                f"• Ротация ключей: {bot_settings['api_key_rotation']}\n"
                f"• Стиль сообщения по умолчанию: {MESSAGE_STYLES[bot_settings['message_style']]['name']}\n\n"
                f"🔧 Управление:\n"
            )
            keyboard = [
                [InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage")],
                [InlineKeyboardButton("📝 Текст бота", callback_data="admin_text_settings")],
                [InlineKeyboardButton("🎨 Стиль сообщения (по умолч.)", callback_data="admin_message_style")],
                [InlineKeyboardButton("⚙️ Глобальные настройки", callback_data="admin_global_settings")],
                [InlineKeyboardButton("⏱️ Cooldown", callback_data="admin_set_cooldown")],
                [InlineKeyboardButton("📊 Лимиты запросов", callback_data="admin_set_rpm")],
                [InlineKeyboardButton("🔄 Ротация ключей", callback_data="admin_key_rotation")],
                [InlineKeyboardButton("🔨 Управление нарушениями", callback_data="admin_violations")],
                [InlineKeyboardButton("📊 Активность", callback_data="admin_activity")],
                [InlineKeyboardButton("⏸️ Управление паузой", callback_data="admin_pause_menu")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        # Управление администраторами
        if data == "admin_manage" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            admin_list = "\n".join([f"• @{admin}" for admin in ADMINS]) if ADMINS else "• нет администраторов"
            text = (
                f"👥 Управление администраторами\n\n"
                f"Текущие администраторы:\n{admin_list}\n\n"
                f"Главный администратор (владелец) не может быть удален."
            )
            keyboard = [
                [InlineKeyboardButton("➕ Добавить администратора", callback_data="admin_add")],
                [InlineKeyboardButton("➖ Удалить администратора", callback_data="admin_remove")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data == "admin_add" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "add_admin"}
            await query.edit_message_text(
                "👥 Введите username пользователя для добавления в администраторы\n\nНапример: username или @username",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_manage")]]),
                parse_mode=None
            )
            return

        if data == "admin_remove" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "remove_admin"}
            await query.edit_message_text(
                "👥 Введите username пользователя для удаления из администраторов\n\nНапример: username или @username\n\n⚠️ Главный администратор (владелец) не может быть удален.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_manage")]]),
                parse_mode=None
            )
            return

        # Режим ротации ключей
        if data == "admin_key_rotation" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            current = bot_settings["api_key_rotation"]
            text = (
                f"🔄 Текущий режим ротации ключей: {current}\n\n"
                f"Выберите новый режим:"
            )
            keyboard = [
                [InlineKeyboardButton("По кругу (round_robin)", callback_data="set_rotation_round_robin")],
                [InlineKeyboardButton("Случайно (random)", callback_data="set_rotation_random")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data.startswith("set_rotation_") and is_admin(user_id):
            mode = data.replace("set_rotation_", "")
            if mode in ["round_robin", "random"]:
                bot_settings["api_key_rotation"] = mode
                await query.edit_message_text(f"✅ Режим ротации ключей изменен на {mode}", reply_markup=get_main_keyboard(user_id), parse_mode=None)
                menu_messages[user_id] = query.message.message_id
                user_data[user_id]["current_menu"] = "main"
            return

        # Режимы и модели
        if data == "show_modes":
            user_data[user_id]["current_menu"] = "modes"
            keyboard = []
            for mid, info in MODES.items():
                mark = "✅ " if user_data[user_id]["mode"] == mid else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{info['name']}", callback_data=f"mode_{mid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            await query.edit_message_text("🎭 Выбери режим:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data.startswith("mode_"):
            mode_id = data.replace("mode_", "")
            user_data[user_id]["mode"] = mode_id
            if user_data[user_id]["current_chat"]:
                custom = user_custom_notes.get(user_id, "")
                system = MODES[mode_id]["system_prompt"].format(custom_note=custom)
                user_data[user_id]["current_chat"]["messages"] = [{"role": "system", "content": system}]
                user_data[user_id]["current_chat"]["mode"] = mode_id
            await query.edit_message_text(f"✅ Режим изменен на {MODES[mode_id]['name']}", reply_markup=get_main_keyboard(user_id), parse_mode=None)
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "show_models":
            user_data[user_id]["current_menu"] = "models"
            models = GROQ_MODELS
            keyboard = []
            for name, mid in models.items():
                mark = "✅ " if user_data[user_id]["model"] == mid else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"model_{mid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            await query.edit_message_text("🚀 Выбери модель:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data.startswith("model_"):
            model_id = data.replace("model_", "")
            user_data[user_id]["model"] = model_id
            if user_data[user_id]["current_chat"]:
                user_data[user_id]["current_chat"]["model"] = model_id
            await query.edit_message_text(f"✅ Модель изменена на {get_model_name(model_id)}", reply_markup=get_main_keyboard(user_id), parse_mode=None)
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        # Чаты
        if data == "show_chats":
            await show_chats_interface(update, context, user_id, from_dialog=False)
            return

        if data.startswith("view_chat_"):
            chat_id = data.replace("view_chat_", "")
            if switch_chat(user_id, chat_id):
                chat = user_data[user_id]["current_chat"]
                msgs = [m for m in chat["messages"] if m["role"] != "system"]
                if msgs:
                    text = f"📜 История чата: {chat['name']}\n\n"
                    for i, m in enumerate(msgs[-10:]):
                        emoji = "👤" if m["role"] == "user" else "🤖"
                        text += f"{i+1}. {emoji} {m['content'][:100]}\n\n"
                else:
                    text = f"📭 История чата: {chat['name']}\n\nНет сообщений."
                keyboard = [
                    [InlineKeyboardButton("🗑 Удалить чат", callback_data=f"delete_chat_{chat_id}")],
                    [InlineKeyboardButton("◀️ Назад к чатам", callback_data="show_chats")]
                ]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data.startswith("delete_chat_"):
            chat_id = data.replace("delete_chat_", "")
            chat_name = "Неизвестный чат"
            if user_data[user_id]["temp_chat"] and user_data[user_id]["temp_chat"]["id"] == chat_id:
                chat_name = user_data[user_id]["temp_chat"]["name"]
            else:
                for chat in user_data[user_id]["chats"]:
                    if chat["id"] == chat_id:
                        chat_name = chat["name"]
                        break
            if delete_chat(user_id, chat_id):
                await query.edit_message_text(f"✅ Чат '{chat_name}' успешно удален!", reply_markup=get_main_keyboard(user_id), parse_mode=None)
                menu_messages[user_id] = query.message.message_id
                user_data[user_id]["current_menu"] = "main"
            else:
                await query.edit_message_text("❌ Не удалось удалить чат", reply_markup=get_main_keyboard(user_id), parse_mode=None)
            return

        if data == "new_permanent_chat":
            permanent = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary")]
            if len(permanent) >= MAX_CHATS:
                keyboard = [
                    [InlineKeyboardButton("🗑 Удалить самый старый", callback_data="delete_oldest_and_create")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                await query.edit_message_text(
                    f"❌ Достигнут лимит постоянных чатов ({MAX_CHATS}).\n\nУдалить самый старый чат и создать новый?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=None
                )
                return
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
            await query.edit_message_text(
                "📝 Введите название для нового постоянного чата:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode=None
            )
            return

        if data == "new_temp_chat":
            if user_data[user_id]["temp_chat"]:
                keyboard = [
                    [InlineKeyboardButton("✅ Да, заменить", callback_data="confirm_replace_temp")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                await query.edit_message_text("У вас уже есть временный чат. Заменить его?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
                return
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "temporary"}
            await query.edit_message_text(
                "📝 Введите название для временного чата:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode=None
            )
            return

        if data == "delete_oldest_and_create":
            if delete_oldest_chat(user_id):
                awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
                await query.edit_message_text(
                    "✅ Самый старый чат удален.\n\n📝 Введите название для нового чата:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                    parse_mode=None
                )
            return

        if data == "confirm_replace_temp":
            if "name" in awaiting_input.get(user_id, {}):
                name = awaiting_input[user_id]["name"]
                del awaiting_input[user_id]
                chat_id, error = create_chat(user_id, name, is_temporary=True)
                if chat_id:
                    await show_main_menu(update, context, user_id)
            return

        # Остальные админские обработчики
        if data == "admin_text_settings" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            text = (
                f"📝 Настройка текстов бота\n\n"
                f"Текущие настройки:\n"
                f"• Приветствие по умолчанию: {bot_settings['welcome_message'][:50]}...\n"
                f"• Кастомное приветствие: {'✅' if bot_settings['custom_greeting'] else '❌'}\n"
                f"• Кастомная информация: {'✅' if bot_settings['custom_info'] else '❌'}\n\n"
                f"Выберите что изменить:"
            )
            keyboard = [
                [InlineKeyboardButton("📝 Изменить приветствие по умолч.", callback_data="set_welcome_message")],
                [InlineKeyboardButton("✨ Установить кастомное приветствие", callback_data="set_custom_greeting")],
                [InlineKeyboardButton("ℹ️ Установить кастомную информацию", callback_data="set_custom_info")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data == "admin_message_style" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            text = "🎨 Выберите стиль главного сообщения по умолчанию:\n\n"
            for style_id, style_info in MESSAGE_STYLES.items():
                mark = "✅ " if bot_settings['message_style'] == style_id else ""
                text += f"{mark}{style_info['name']}\n{style_info['template'][:50]}...\n\n"
            keyboard = []
            for style_id in MESSAGE_STYLES:
                keyboard.append([InlineKeyboardButton(f"Установить {MESSAGE_STYLES[style_id]['name']}", callback_data=f"set_default_style_{style_id}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data.startswith("set_default_style_") and is_admin(user_id):
            style = data.replace("set_default_style_", "")
            if style in MESSAGE_STYLES:
                bot_settings["message_style"] = style
                await query.edit_message_text(f"✅ Стиль сообщения по умолчанию изменен на {MESSAGE_STYLES[style]['name']}", reply_markup=get_main_keyboard(user_id), parse_mode=None)
                menu_messages[user_id] = query.message.message_id
                user_data[user_id]["current_menu"] = "main"
            return

        if data == "admin_global_settings" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            keyboard = [
                [InlineKeyboardButton("📁 Макс. чатов", callback_data="admin_set_max_chats")],
                [InlineKeyboardButton("💾 Макс. сохранений", callback_data="admin_set_max_saved")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
            ]
            await query.edit_message_text(
                "⚙️ Глобальные настройки",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=None
            )
            return

        if data == "admin_set_cooldown" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_cooldown"}
            await query.edit_message_text(
                "⏱️ Введите cooldown между запросами (сек) (>=0):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_panel")]]),
                parse_mode=None
            )
            return

        if data == "admin_set_rpm" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_requests_per_minute"}
            await query.edit_message_text(
                "📊 Введите лимит запросов в минуту (>=0):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_panel")]]),
                parse_mode=None
            )
            return

        if data == "admin_set_max_chats" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_max_chats"}
            await query.edit_message_text(
                "📁 Введите максимальное количество постоянных чатов (целое число >=1):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_global_settings")]]),
                parse_mode=None
            )
            return

        if data == "admin_set_max_saved" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_max_saved"}
            await query.edit_message_text(
                "💾 Введите максимальное количество сохраняемых сообщений (целое число >=1):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_global_settings")]]),
                parse_mode=None
            )
            return

        if data == "admin_violations" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            if not violations:
                text = "📋 Нет нарушений"
            else:
                text = "📋 Список нарушителей:\n\n"
                for uid, user_violations in list(violations.items())[:10]:
                    username = user_data.get(uid, {}).get("username", "нет username")
                    last_violation = user_violations[-1]
                    time_str = datetime.fromtimestamp(last_violation["time"]).strftime('%d.%m %H:%M')
                    text += f"• {uid} (@{username}) - {last_violation['reason']} ({time_str})\n"
                    text += f"  Всего нарушений: {len(user_violations)}\n\n"
            keyboard = [
                [InlineKeyboardButton("🔨 Забанить пользователя", callback_data="ban_user_from_violations")],
                [InlineKeyboardButton("🔇 Замутить пользователя", callback_data="mute_user_from_violations")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data == "admin_activity" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            da = len(daily_active_users)
            wa = len(weekly_active_users)
            ma = len(monthly_active_users)
            text = (
                f"📊 Активность пользователей\n\n"
                f"• Активных сегодня: {da}\n"
                f"• Активных на этой неделе: {wa}\n"
                f"• Активных в этом месяце: {ma}\n\n"
                f"Детальная статистика по дням доступна в логах."
            )
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
            return

        if data == "admin_pause_menu" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            status = "⏸️ Приостановлен" if bot_paused else "▶️ Активен"
            reason = f"\nПричина: {pause_reason}" if bot_paused else ""
            keyboard = [
                [InlineKeyboardButton("⏸️ Приостановить", callback_data="admin_pause")],
                [InlineKeyboardButton("▶️ Возобновить", callback_data="admin_resume")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
            ]
            await query.edit_message_text(
                f"⏸️ Управление паузой бота\n\nТекущий статус: {status}{reason}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=None
            )
            return

        if data == "admin_pause" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "pause_reason"}
            await query.edit_message_text(
                "⏸️ Введите причину приостановки бота:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_pause_menu")]]),
                parse_mode=None
            )
            return

        if data == "admin_resume" and is_admin(user_id):
            set_bot_pause(False)
            await query.edit_message_text(
                "▶️ Бот возобновлен!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]),
                parse_mode=None
            )
            await notify_admins(context, "Бот возобновлен.")
            return

        if data == "set_welcome_message" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_welcome_message"}
            await query.edit_message_text(
                "📝 Введите новое приветственное сообщение по умолчанию\n\nИспользуйте {name} и {chat}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_text_settings")]]),
                parse_mode=None
            )
            return

        if data == "set_custom_greeting" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_custom_greeting"}
            await query.edit_message_text(
                "✨ Введите кастомное приветствие\n\nИспользуйте {name} для имени пользователя и {chat} для названия чата.\nНапример: 'Привет, {name}! Добро пожаловать в {chat}'\n\nЕсли оставить пустым, будет использоваться стандартное приветствие.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_text_settings")]]),
                parse_mode=None
            )
            return

        if data == "set_custom_info" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "set_custom_info"}
            await query.edit_message_text(
                "ℹ️ Введите кастомную информацию\n\nЭта информация будет показываться после приветствия.\nНапример: '📢 Важное объявление: ...'\n\nМожно использовать Markdown разметку.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_text_settings")]]),
                parse_mode=None
            )
            return

        if data == "ban_user_from_violations" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            awaiting_input[user_id] = {"action": "ban_user"}
            await query.edit_message_text(
                "🔨 Введите ID или @username пользователя для бана:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_violations")]]),
                parse_mode=None
            )
            return

        if data == "mute_user_from_violations" and is_admin(user_id):
            user_data[user_id]["current_menu"] = "admin"
            keyboard = [
                [InlineKeyboardButton("⏱️ 1 час", callback_data="mute_duration_3600")],
                [InlineKeyboardButton("⏱️ 6 часов", callback_data="mute_duration_21600")],
                [InlineKeyboardButton("⏱️ 24 часа", callback_data="mute_duration_86400")],
                [InlineKeyboardButton("⏱️ 7 дней", callback_data="mute_duration_604800")],
                [InlineKeyboardButton("◀️ Отмена", callback_data="admin_violations")]
            ]
            await query.edit_message_text(
                "🔇 Выберите длительность мута:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=None
            )
            return

        if data.startswith("mute_duration_") and is_admin(user_id):
            duration = int(data.replace("mute_duration_", ""))
            awaiting_input[user_id] = {"action": "mute_user", "duration": duration}
            await query.edit_message_text(
                f"🔇 Введите ID или @username пользователя для мута на {duration//3600} часов:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_violations")]]),
                parse_mode=None
            )
            return

    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        try:
            cur_chat = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
            welcome = format_welcome_message(user_id, first_name, cur_chat)
            await query.edit_message_text(
                f"❌ Произошла ошибка. Возврат в главное меню.\n\n{welcome}",
                reply_markup=get_main_keyboard(user_id),
                parse_mode=None
            )
        except:
            pass

# ----------------------------------------------------------------------
# Обработчик ошибок
# ----------------------------------------------------------------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ Произошла внутренняя ошибка. Попробуйте позже.")
    except:
        pass

# ----------------------------------------------------------------------
# post_init
# ----------------------------------------------------------------------
async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand("start", "Запустить бота")])
    
    # Инициализируем Groq клиенты с несколькими ключами
    success = await init_groq_clients()
    if success:
        logger.info(f"✅ Groq клиенты успешно активированы: {len(groq_clients)} из {len(GROQ_API_KEYS)}")
    else:
        logger.error("❌ Ошибка активации Groq клиентов")
    
    logger.info(f"Бот запущен. Версия Python: {sys.version.split()[0]}")

# ----------------------------------------------------------------------
# Точка входа
# ----------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан!")
        return
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    logger.info("Бот запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
