import logging
import asyncio
import time
import sys
import uuid
import os
import random
from collections import defaultdict
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ApplicationBuilder

import httpx
from groq import Groq

# ----------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------

# Токен Telegram – вставьте свой или используйте переменную окружения
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"  # Введите сюда токен или оставьте пустым для использования os.getenv
# TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # раскомментируйте, если хотите брать из переменной окружения

# Groq API ключ (изначально отсутствует, будет введён владельцем)
GROQ_API_KEY = None

# ID владельца (определится при первом запуске)
OWNER_CHAT_ID = None

# Глобальный клиент Groq
groq_client = None

# Флаг паузы бота
bot_paused = False
pause_reason = ""

# Настройки бота (доступны только владельцу)
bot_settings = {
    "default_model": "llama-3.1-8b-instant",
    "default_mode": "normal",
    "max_chats": 10,
    "max_saved_messages": 50,
    "default_requests_per_minute": 10,
    "default_requests_per_hour": 100,
    "default_requests_per_day": 500,
    "default_cooldown": 5,
    "max_warnings": 3,
    "max_adult_attempts": 3,
    "api_call_cooldown": 2,
    "welcome_message": "👋 **Привет, {name}!**\n\n💬 **Текущий чат:** {chat}\n\nВыбери действие в меню ниже:",
    "enable_18_plus_filter": True,
    "enable_user_notes": True,
    "enable_activity_tracking": True,
}

# Прокси (отключено)
USE_PROXY = False
PROXY_HOST = "195.74.72.111"
PROXY_PORT = 5678

# Лимиты Groq API (для информации)
GROQ_LIMITS = {
    "free_tier": {
        "requests_per_minute": 30,
        "requests_per_hour": 500,
        "requests_per_day": 1000,
        "tokens_per_minute": 6000,
        "max_tokens_per_request": 6000,
        "concurrent_requests": 4
    },
    "paid_tier": {
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "requests_per_day": 5000,
        "tokens_per_minute": 20000,
        "max_tokens_per_request": 8000,
        "concurrent_requests": 10
    }
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
MODELS = {
    "🚀 LLaMA 3.1 8B": "llama-3.1-8b-instant",
    "🔸 Gemma 2 9B": "gemma2-9b-it",
    "🎯 LLaMA 3.3 70B": "llama-3.3-70b-versatile",
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

# Список цитат для случайной вставки
QUOTES = [
    "🌟 *Цитата дня:* «Единственный способ делать великие дела — любить то, что вы делаете.» — Стив Джобс",
    "💡 *Мысль:* «Жизнь — это то, что с тобой происходит, пока ты строишь планы.» — Джон Леннон",
    "🌱 *Мудрость:* «Начинать всегда стоит с того, что сеет сомнения.» — Борис Стругацкий",
    "🔥 *Вдохновение:* «Падать — часть жизни, подниматься — её главная часть.»",
    "✨ *Совет:* «Делай сегодня то, что другие не хотят, завтра будешь жить так, как другие не могут.»",
    "📚 *Книжная полка:* «Читайте не затем, чтобы противоречить и опровергать, не затем, чтобы верить и принимать как должное, и не затем, чтобы найти тему для разговора; но чтобы мыслить и рассуждать.» — Фрэнсис Бэкон",
    "🎯 *Фокус:* «Секрет успеха в том, чтобы начать. Начать — это главное.» — Марк Твен",
    "💪 *Сила:* «Ты никогда не пересечёшь океан, если боишься потерять берег из виду.» — Христофор Колумб",
    "🤔 *Размышление:* «Вопрос не в том, кто мне разрешит, а в том, кто сможет мне запретить.» — Айн Рэнд",
    "🌈 *Оптимизм:* «После чёрной полосы всегда наступает белая, даже если кажется, что это просто полосатая зебра.»"
]

def get_random_quote():
    return random.choice(QUOTES)

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
user_warnings = defaultdict(int)
adult_content_attempts = defaultdict(int)
user_activity = {}
daily_active_users = set()
weekly_active_users = set()
monthly_active_users = set()
bot_start_time = time.time()

# Константы из настроек
MAX_CHATS = bot_settings["max_chats"]
MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
MAX_WARNINGS = bot_settings["max_warnings"]
MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]

# Ключевые слова для 18+ фильтра
ADULT_KEYWORDS = [
    'порно', 'porn', 'sex', 'секс', 'эротика', 'erotica', 'xxx',
    '18+', 'nsfw', 'порнография', 'pornography', 'hardcore',
    'интим', 'intimate', 'обнаженный', 'naked', 'голый',
    'разврат', 'depravity', 'извращение', 'perversion',
    'проститутк', 'prostitut', 'эскорт', 'escort',
    'минет', 'blowjob', 'анальный', 'anal', 'оральный', 'oral',
    'вагина', 'vagina', 'пенис', 'penis', 'член', 'cock',
    'сиськи', 'tits', 'грудь', 'breasts', 'попа', 'ass',
    'сексуальный', 'sexual', 'возбуждение', 'arousal',
    'мастурб', 'masturb', 'дрочить', 'fap',
    'инцест', 'incest', 'pedo', 'педофилия',
    'насилие', 'violence', 'изнасилование', 'rape',
    'садизм', 'sadism', 'мазохизм', 'masochism', 'bdsm'
]

# ----------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------
def init_user_data(user_id):
    """Инициализация данных пользователя"""
    if user_id not in user_data:
        user_data[user_id] = {
            "chats": [],
            "temp_chat": None,
            "current_chat_id": None,
            "current_chat": None,
            "chat_type": None,
            "in_dialog": False,
            "showing_action_buttons": False,
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
                "is_owner": False
            }

        user_activity[user_id] = {
            "last_active": time.time(),
            "total_messages": 0,
            "total_time": 0,
            "daily_stats": {},
            "weekly_stats": {},
            "monthly_stats": {}
        }

def check_adult_content(text):
    """Проверка на наличие 18+ контента"""
    if not bot_settings["enable_18_plus_filter"]:
        return False
    text_lower = text.lower()
    for keyword in ADULT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def update_user_activity(user_id):
    """Обновление активности пользователя"""
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
    """Проверка лимитов запросов для пользователя"""
    if bot_paused:
        return False, "Бот временно приостановлен. Попробуйте позже."
    if user_id in banned_users or (user_id in user_data and user_data[user_id].get("is_banned", False)):
        return False, "Вы забанены в боте. Обратитесь к администратору."
    if user_id not in user_limits:
        return True, "OK"
    limits = user_limits[user_id]
    now = time.time()
    if user_id not in user_requests:
        user_requests[user_id] = []
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 86400]
    if user_requests[user_id] and now - user_requests[user_id][-1] < limits["cooldown"]:
        wait = int(limits["cooldown"] - (now - user_requests[user_id][-1]))
        return False, f"Подождите {wait} сек между запросами"
    minute_ago = now - 60
    minute_req = len([t for t in user_requests[user_id] if t > minute_ago])
    if minute_req >= limits["requests_per_minute"]:
        return False, f"Лимит {limits['requests_per_minute']} запросов в минуту"
    hour_ago = now - 3600
    hour_req = len([t for t in user_requests[user_id] if t > hour_ago])
    if hour_req >= limits["requests_per_hour"]:
        return False, f"Лимит {limits['requests_per_hour']} запросов в час"
    day_ago = now - 86400
    day_req = len([t for t in user_requests[user_id] if t > day_ago])
    if day_req >= limits["requests_per_day"]:
        return False, f"Лимит {limits['requests_per_day']} запросов в день"
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
    if user_id in user_data:
        user_data[user_id]["last_active"] = time.time()
        user_data[user_id]["total_spent_time"] = time.time() - user_data[user_id]["first_seen"]

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

def delete_oldest_chat(user_id):
    if user_id not in user_data:
        return False
    permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
    if permanent_chats:
        oldest = min(permanent_chats, key=lambda x: x["created"])
        user_data[user_id]["chats"].remove(oldest)
        return True
    return False

def save_message(user_id, message_text, sender):
    if user_id not in saved_messages:
        saved_messages[user_id] = []
    if len(saved_messages[user_id]) >= user_data[user_id]["saved_messages_limit"]:
        saved_messages[user_id].pop(0)
    saved_messages[user_id].append({
        "text": message_text,
        "sender": sender,
        "timestamp": time.time(),
        "chat_name": user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Неизвестный чат"
    })
    return True

def delete_saved_message(user_id, index):
    if user_id in saved_messages and 0 <= index < len(saved_messages[user_id]):
        saved_messages[user_id].pop(index)
        return True
    return False

def set_user_limits(user_id, limits_dict):
    if user_id in user_limits:
        user_limits[user_id].update(limits_dict)
        return True
    return False

def ban_user(user_id, reason=""):
    banned_users.add(user_id)
    if user_id in user_data:
        user_data[user_id]["is_banned"] = True
        user_data[user_id]["ban_reason"] = reason
        user_data[user_id]["ban_time"] = time.time()
    return True

def unban_user(user_id):
    if user_id in banned_users:
        banned_users.remove(user_id)
    if user_id in user_data:
        user_data[user_id]["is_banned"] = False
        user_data[user_id].pop("ban_reason", None)
        user_data[user_id].pop("ban_time", None)
    return True

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

# ----------------------------------------------------------------------
# Асинхронная инициализация Groq клиента
# ----------------------------------------------------------------------
async def init_groq_client(api_key):
    global groq_client
    if not api_key:
        groq_client = None
        return False
    try:
        loop = asyncio.get_running_loop()
        if USE_PROXY:
            proxy_url = f"socks4://{PROXY_HOST}:{PROXY_PORT}"
            transport = httpx.AsyncHTTPTransport(proxy=proxy_url)
            http_client = httpx.AsyncClient(transport=transport)
        else:
            http_client = httpx.AsyncClient()

        client = Groq(api_key=api_key, http_client=http_client, timeout=30.0)

        # Проверка ключа через запрос списка моделей (менее затратно)
        await loop.run_in_executor(None, lambda: client.models.list())
        groq_client = client
        logger.info(f"Groq клиент инициализирован с ключом {api_key[:10]}...")
        return True
    except Exception as e:
        logger.error(f"Ошибка инициализации Groq клиента: {e}")
        groq_client = None
        return False

async def update_groq_api_key(new_api_key):
    global GROQ_API_KEY
    GROQ_API_KEY = new_api_key
    return await init_groq_client(new_api_key)

# ----------------------------------------------------------------------
# Уведомление владельца
# ----------------------------------------------------------------------
async def notify_owner(context, message):
    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"⚠️ **Уведомление владельцу**\n\n{message}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление владельцу: {e}")

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
    if user_limits.get(user_id, {}).get("is_owner"):
        keyboard.append([InlineKeyboardButton("👑 Панель владельца", callback_data="owner_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_dialog_navigation_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Управление чатами", callback_data="show_chats_from_dialog")],
        [InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]
    ])

def get_action_keyboard():
    return ReplyKeyboardMarkup(
        [["👤 СОХРАНИТЬ МОЁ", "🤖 СОХРАНИТЬ БОТА"]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# ----------------------------------------------------------------------
# Удаление меню и сообщений
# ----------------------------------------------------------------------
async def delete_menu(user_id, context):
    if user_id in menu_messages:
        try:
            await context.bot.delete_message(user_id, menu_messages[user_id])
        except:
            pass
        del menu_messages[user_id]

async def delete_dialog_messages(user_id, context):
    if user_id in dialog_messages:
        for msg_id in dialog_messages[user_id]:
            try:
                await context.bot.delete_message(user_id, msg_id)
            except:
                pass
        dialog_messages[user_id] = []

# ----------------------------------------------------------------------
# Команда /start
# ----------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    await delete_menu(user_id, context)

    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["username"] = username
        create_chat(user_id, "Основной чат", is_temporary=False)

        global OWNER_CHAT_ID
        if not OWNER_CHAT_ID:
            OWNER_CHAT_ID = user_id
            user_limits.setdefault(user_id, {})["is_owner"] = True
            logger.info(f"Владелец определён: {user_id}")
            await update.message.reply_text(
                "👑 **Вы назначены владельцем бота!**\n\n"
                "⚠️ **Для работы необходимо установить Groq API ключ.**\n"
                "Перейдите в панель владельца (кнопка ниже) и выберите «🔑 Сменить API ключ».",
                reply_markup=get_main_keyboard(user_id)
            )
            return

    current_chat_name = user_data[user_id]["current_chat"]["name"]
    welcome = bot_settings["welcome_message"].format(name=first_name, chat=current_chat_name)
    msg = await update.message.reply_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
    menu_messages[user_id] = msg.message_id
    user_data[user_id]["last_message_id"] = msg.message_id

# ----------------------------------------------------------------------
# Обработчик текстовых сообщений (основной диалог)
# ----------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    # Инициализация
    if user_id not in user_data:
        init_user_data(user_id)
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    dialog_messages[user_id].append(update.message.message_id)

    # Обработка кнопок сохранения
    if user_message in ("👤 СОХРАНИТЬ МОЁ", "🤖 СОХРАНИТЬ БОТА"):
        sender = "user" if "МОЁ" in user_message else "bot"
        if last_message_text.get(user_id, {}).get(sender):
            save_message(user_id, last_message_text[user_id][sender], sender)
            await update.message.reply_text("✅ Сообщение сохранено!")
        else:
            await update.message.reply_text("❌ Нет сообщения для сохранения")
        return

    # Обработка ожидаемого ввода (новый чат, настройки, ключ и т.д.)
    if user_id in awaiting_input:
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
                    await update.message.reply_text(
                        f"❌ Достигнут лимит постоянных чатов ({MAX_CHATS}).\n\nХотите удалить самый старый чат и создать новый?",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
                chat_id, error = create_chat(user_id, user_message[:50], is_temporary=False)
                if chat_id:
                    await update.message.reply_text(f"✅ Постоянный чат '{user_message[:50]}' создан!", reply_markup=get_main_keyboard(user_id))
                else:
                    await update.message.reply_text(f"❌ {error}")
            elif chat_type == "temporary":
                if user_data[user_id]["temp_chat"]:
                    keyboard = [
                        [InlineKeyboardButton("✅ Заменить", callback_data="replace_temp_chat")],
                        [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                    ]
                    await update.message.reply_text("У вас уже есть временный чат. Заменить его?", reply_markup=InlineKeyboardMarkup(keyboard))
                    awaiting_input[user_id] = {"action": "confirm_replace_temp", "name": user_message[:50]}
                else:
                    chat_id, error = create_chat(user_id, user_message[:50], is_temporary=True)
                    if chat_id:
                        await update.message.reply_text(f"✅ Временный чат '{user_message[:50]}' создан!", reply_markup=get_main_keyboard(user_id))
            return

        elif action_data.get("action") == "message_to_owner":
            del awaiting_input[user_id]
            if OWNER_CHAT_ID:
                try:
                    user_info = f"От: {update.effective_user.first_name}"
                    if update.effective_user.username:
                        user_info += f" (@{update.effective_user.username})"
                    user_info += f"\nID: `{user_id}`"
                    await context.bot.send_message(
                        chat_id=OWNER_CHAT_ID,
                        text=f"📨 **Сообщение от пользователя**\n\n{user_info}\n\n**Текст:**\n{user_message}",
                        parse_mode='Markdown'
                    )
                    await update.message.reply_text("✅ **Сообщение отправлено владельцу!**\n\nОн ответит вам, как только сможет.", reply_markup=get_main_keyboard(user_id))
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения владельцу: {e}")
                    await update.message.reply_text("❌ Не удалось отправить сообщение. Попробуйте позже.", reply_markup=get_main_keyboard(user_id))
            return

        elif action_data.get("action") == "set_limit":
            del awaiting_input[user_id]
            try:
                limit = int(user_message)
                if 1 <= limit <= 100:
                    user_data[user_id]["saved_messages_limit"] = limit
                    await update.message.reply_text(f"✅ Лимит сохраненных сообщений установлен: {limit}", reply_markup=get_main_keyboard(user_id))
                else:
                    await update.message.reply_text("❌ Лимит должен быть от 1 до 100")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
            return

        elif action_data.get("action") == "set_custom_note":
            del awaiting_input[user_id]
            user_custom_notes[user_id] = user_message
            user_data[user_id]["custom_note"] = user_message
            if user_data[user_id]["current_chat"]:
                custom_note = user_custom_notes.get(user_id, "")
                system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
                user_data[user_id]["current_chat"]["messages"][0]["content"] = system_prompt
            await update.message.reply_text(f"✅ Ваша приписка сохранена!\n\nТеперь бот будет учитывать: {user_message}", reply_markup=get_main_keyboard(user_id))
            return

        elif action_data.get("action") == "set_cooldown" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                cooldown = int(user_message)
                if cooldown >= 0:
                    for uid in user_limits:
                        user_limits[uid]["cooldown"] = cooldown
                    bot_settings["default_cooldown"] = cooldown
                    await update.message.reply_text(f"✅ Cooldown для всех установлен: {cooldown} сек")
                else:
                    await update.message.reply_text("❌ Cooldown должен быть >= 0")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
            return

        elif action_data.get("action") == "set_requests_per_minute" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                limit = int(user_message)
                if limit >= 0:
                    for uid in user_limits:
                        user_limits[uid]["requests_per_minute"] = limit
                    bot_settings["default_requests_per_minute"] = limit
                    await update.message.reply_text(f"✅ Лимит запросов/мин для всех установлен: {limit}")
                else:
                    await update.message.reply_text("❌ Лимит должен быть >= 0")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
            return

        elif action_data.get("action") == "set_max_chats" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                limit = int(user_message)
                if limit >= 1:
                    bot_settings["max_chats"] = limit
                    update_bot_settings({"max_chats": limit})
                    await update.message.reply_text(f"✅ Максимальное количество чатов установлено: {limit}")
                else:
                    await update.message.reply_text("❌ Лимит должен быть >= 1")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
            return

        elif action_data.get("action") == "set_max_saved" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                limit = int(user_message)
                if limit >= 1:
                    bot_settings["max_saved_messages"] = limit
                    update_bot_settings({"max_saved_messages": limit})
                    await update.message.reply_text(f"✅ Максимальное количество сохраненных сообщений установлено: {limit}")
                else:
                    await update.message.reply_text("❌ Лимит должен быть >= 1")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
            return

        elif action_data.get("action") == "set_welcome_message" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            bot_settings["welcome_message"] = user_message
            await update.message.reply_text(f"✅ Приветственное сообщение обновлено!", reply_markup=get_main_keyboard(user_id))
            return

        elif action_data.get("action") == "new_api_key" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            new_key = user_message.strip()
            if new_key.startswith("gsk_") and len(new_key) > 30:
                if await update_groq_api_key(new_key):
                    await update.message.reply_text(
                        "✅ **API ключ успешно обновлен!**\n\nНовый ключ активирован для всех пользователей.",
                        reply_markup=get_main_keyboard(user_id)
                    )
                    await notify_owner(context, "✅ API ключ успешно обновлен")
                else:
                    await update.message.reply_text(
                        "❌ Ошибка при обновлении API ключа. Проверьте ключ и попробуйте снова.\n\n"
                        "Ключ должен быть действительным и начинаться с 'gsk_'.",
                        reply_markup=get_main_keyboard(user_id)
                    )
            else:
                await update.message.reply_text(
                    "❌ Неверный формат API ключа. Ключ должен начинаться с 'gsk_' и быть длиннее 30 символов.",
                    reply_markup=get_main_keyboard(user_id)
                )
            return

        elif action_data.get("action") == "ban_user" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                target_id = int(user_message)
                ban_user(target_id, "Забанен администратором")
                await update.message.reply_text(f"✅ Пользователь {target_id} забанен")
            except ValueError:
                await update.message.reply_text("❌ Введите корректный ID пользователя")
            return

        elif action_data.get("action") == "unban_user" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                target_id = int(user_message)
                unban_user(target_id)
                await update.message.reply_text(f"✅ Пользователь {target_id} разбанен")
            except ValueError:
                await update.message.reply_text("❌ Введите корректный ID пользователя")
            return

        elif action_data.get("action") == "pause_reason" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            set_bot_pause(True, user_message)
            await update.message.reply_text(
                f"✅ Бот приостановлен.\nПричина: {user_message}",
                reply_markup=get_main_keyboard(user_id)
            )
            await notify_owner(context, f"Бот приостановлен. Причина: {user_message}")
            return

    await delete_menu(user_id, context)

    if user_id not in user_data:
        init_user_data(user_id)
        create_chat(user_id, "Основной чат", is_temporary=False)

    if not user_data[user_id]["current_chat"]:
        create_chat(user_id, "Временный чат", is_temporary=True)

    # Проверка спама
    now = time.time()
    if user_id in user_last_message and now - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = now

    # Лимиты запросов
    allowed, msg = check_request_limits(user_id)
    if not allowed:
        error_msg = await update.message.reply_text(
            f"⏱️ {msg}\n\n❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(error_msg.message_id)
        return

    # Фильтр 18+
    if check_adult_content(user_message):
        user_data[user_id]["adult_attempts"] = user_data[user_id].get("adult_attempts", 0) + 1
        adult_attempts = user_data[user_id]["adult_attempts"]
        if adult_attempts >= MAX_ADULT_ATTEMPTS:
            result, status = warn_user(user_id, "Попытка получить 18+ контент")
            if status == "user_banned":
                await update.message.reply_text(
                    "❌ **Вы забанены за многократные попытки получить 18+ контент!**\n\n"
                    "Обратитесь к администратору для разблокировки.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📨 Связаться с владельцем", callback_data="contact_owner")]])
                )
                return
            else:
                warnings_left = MAX_WARNINGS - user_data[user_id].get("warnings", 0)
                warning_msg = await update.message.reply_text(
                    f"⚠️ **Предупреждение {user_data[user_id].get('warnings', 0)}/{MAX_WARNINGS}**\n\n"
                    f"Ваш запрос содержит потенциально неприемлемый контент.\n"
                    f"Осталось предупреждений до бана: {warnings_left}\n\n"
                    f"❓ Хотите выйти из чата?",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
                )
                dialog_messages[user_id].append(warning_msg.message_id)
                return
        reject_msg = await update.message.reply_text(
            f"❌ **Запрос отклонен**\n\n"
            f"Бот не отвечает на запросы, содержащие 18+ контент.\n\n"
            f"Попытка {adult_attempts}/{MAX_ADULT_ATTEMPTS} (до предупреждения)\n\n"
            f"❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(reject_msg.message_id)
        return

    user_data[user_id]["in_dialog"] = True
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        if groq_client is None:
            error_msg = await update.message.reply_text(
                "❌ **Ошибка API**\n\n"
                "API клиент не инициализирован. Администратор уже уведомлен.\n\n"
                "❓ Хотите выйти из чата?",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]),
                parse_mode='Markdown'
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

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                model=user_data[user_id]["model"],
                messages=history,
                temperature=0.8,
                max_tokens=512
            )
        )

        assistant_message = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_message})
        last_message_text[user_id]["bot"] = assistant_message

        # С вероятностью 10% добавляем цитату
        if random.random() < 0.1:
            assistant_message += f"\n\n— — — — — — — — — — — — — — —\n{get_random_quote()}"

        sent = await update.message.reply_text(
            assistant_message,
            reply_markup=get_dialog_navigation_keyboard(user_id)
        )
        dialog_messages[user_id].append(sent.message_id)

        action_msg = await context.bot.send_message(
            user_id, "Действия с сообщениями:", reply_markup=get_action_keyboard()
        )
        dialog_messages[user_id].append(action_msg.message_id)
        user_data[user_id]["last_message_id"] = sent.message_id

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от {user_id}: {e}")
        error_count += 1
        last_error_time = time.time()
        error_users.add(user_id)
        if OWNER_CHAT_ID and len(error_users) >= 3:
            await notify_owner(context, f"⚠️ **Массовая ошибка API**\n\n• Количество ошибок: {error_count}\n• Затронуто пользователей: {len(error_users)}\n• Последняя ошибка: {str(e)[:100]}\n\nВозможно, требуется обновить API ключ.")
            error_users.clear()

        err_text = "❌ Ошибка при получении ответа от API. "
        if "timeout" in str(e).lower():
            err_text += "Превышено время ожидания."
        elif "connection" in str(e).lower():
            err_text += "Проблема с подключением."
        elif "api_key" in str(e).lower() or "authentication" in str(e).lower():
            err_text += "Проблема с API ключом. Администратор уже уведомлен."
        elif groq_client is None:
            err_text += "API клиент не инициализирован."
        else:
            err_text += "Попробуйте позже."

        error_msg = await update.message.reply_text(
            f"{err_text}\n\n❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(error_msg.message_id)

# ----------------------------------------------------------------------
# Обработчик фото
# ----------------------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await delete_menu(user_id, context)
    if user_id not in user_data:
        init_user_data(user_id)
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    msg = await update.message.reply_text(
        "📸 **Бот не умеет анализировать фото**\n\n"
        "Я работаю только с текстом. Отправь текстовое сообщение.\n\n"
        "❓ Хотите выйти из чата?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]),
        parse_mode='Markdown'
    )
    dialog_messages[user_id].append(msg.message_id)

# ----------------------------------------------------------------------
# Завершение диалога
# ----------------------------------------------------------------------
async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    await delete_menu(user_id, context)
    await delete_dialog_messages(user_id, context)

    if user_id in user_data:
        cur = user_data[user_id].get("current_chat")
        if cur and cur.get("is_temporary"):
            user_data[user_id]["temp_chat"] = None
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
            user_data[user_id]["showing_action_buttons"] = False
        else:
            user_data[user_id]["in_dialog"] = False
            user_data[user_id]["showing_action_buttons"] = False

    current_chat_name = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
    welcome = bot_settings["welcome_message"].format(name=first_name, chat=current_chat_name)
    if bot_paused:
        welcome = f"⏸️ **Бот временно приостановлен**\n\nПричина: {pause_reason}\n\n{welcome}"

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
            menu_messages[user_id] = update.callback_query.message.message_id
        except:
            msg = await context.bot.send_message(user_id, welcome, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
            menu_messages[user_id] = msg.message_id
    else:
        msg = await context.bot.send_message(user_id, welcome, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        menu_messages[user_id] = msg.message_id

# ----------------------------------------------------------------------
# Показ списка чатов
# ----------------------------------------------------------------------
async def show_chats_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, from_dialog=False):
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

    text = f"📋 **Мои чаты**\n\nВсего постоянных: {len(permanent_chats)}/{MAX_CHATS}"
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def get_model_name(model_id):
    for name, mid in MODELS.items():
        if mid == model_id:
            return name
    return model_id

# ----------------------------------------------------------------------
# Обработчик inline-кнопок (все callback'и)
# ----------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        username = query.from_user.username
        first_name = query.from_user.first_name

        if user_id not in user_data:
            init_user_data(user_id)
            user_data[user_id]["username"] = username
            create_chat(user_id, "Основной чат", is_temporary=False)

        data = query.data

        # ----- Навигация -----
        if data == "back_to_main":
            current_chat_name = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
            welcome = bot_settings["welcome_message"].format(name=first_name, chat=current_chat_name)
            if bot_paused:
                welcome = f"⏸️ **Бот временно приостановлен**\n\nПричина: {pause_reason}\n\n{welcome}"
            await query.edit_message_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
            menu_messages[user_id] = query.message.message_id
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
                await query.edit_message_text("🔄 **Возврат в диалог**\n\nПродолжай общение!", reply_markup=None, parse_mode="Markdown")
                await context.bot.send_message(user_id, "Ты вернулся в диалог. Можешь продолжать писать сообщения.", reply_markup=get_dialog_navigation_keyboard(user_id))
            else:
                await query.edit_message_text("❌ **Не найден активный диалог**", reply_markup=get_main_keyboard(user_id))
            return

        if data == "contact_owner":
            awaiting_input[user_id] = {"action": "message_to_owner"}
            await query.edit_message_text(
                "📝 **Напишите сообщение для владельца бота**\n\nОн получит его и сможет ответить вам.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode='Markdown'
            )
            return

        # ----- Информация -----
        if data == "show_info":
            uptime_seconds = int(time.time() - bot_start_time)
            uptime_str = str(timedelta(seconds=uptime_seconds))
            now = datetime.now()
            limits = GROQ_LIMITS["free_tier"] if now < datetime(2026, 4, 1) else GROQ_LIMITS["paid_tier"]
            total_users = len(user_data)
            active_now = sum(1 for d in user_data.values() if d.get("in_dialog"))
            total_req = global_request_count
            banned_cnt = len(banned_users)
            pause_status = "⏸️ **Приостановлен**" if bot_paused else "▶️ **Активен**"
            features = ""
            if bot_settings["enable_18_plus_filter"]:
                features += "• 🔞 Фильтр 18+ контента\n"
            if bot_settings["enable_user_notes"]:
                features += "• 📝 Пользовательские приписки\n"
            if bot_settings["enable_activity_tracking"]:
                features += "• 📊 Отслеживание активности\n"
            text = (
                f"ℹ️ **Информация о боте**\n\n"
                f"📅 **Текущая дата:** {now.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏱ **Аптайм:** {uptime_str}\n"
                f"{pause_status}\n\n"
                f"📊 **Статистика использования:**\n"
                f"• Всего пользователей: {total_users}\n"
                f"• Активных диалогов: {active_now}\n"
                f"• Забанено: {banned_cnt}\n"
                f"• Всего запросов: {total_req}\n\n"
                f"🚀 **Лимиты Groq API (Март 2026):**\n"
                f"• Запросов в минуту: {limits['requests_per_minute']}\n"
                f"• Запросов в час: {limits['requests_per_hour']}\n"
                f"• Запросов в день: {limits['requests_per_day']}\n"
                f"• Токенов в минуту: {limits['tokens_per_minute']}\n"
                f"• Макс. токенов/запрос: {limits['max_tokens_per_request']}\n"
                f"• Одновременных запросов: {limits['concurrent_requests']}\n\n"
                f"⚙️ **Текущие лимиты бота:**\n"
                f"• Сохраняемых сообщений: {user_data[user_id]['saved_messages_limit']}\n"
                f"• Постоянных чатов: {len([c for c in user_data[user_id]['chats'] if not c.get('is_temporary')])}/{MAX_CHATS}\n\n"
                f"🔧 **Доступные функции:**\n{features}\n"
                f"🔞 **Политика контента:**\n"
                f"• Фильтр 18+ контента: {'активен' if bot_settings['enable_18_plus_filter'] else 'отключен'}\n"
                f"• Макс. предупреждений: {MAX_WARNINGS}\n\n"
                f"📨 **Связь с владельцем:**\n"
                f"Нажмите кнопку ниже, чтобы отправить сообщение"
            )
            keyboard = [[InlineKeyboardButton("📨 Написать владельцу", callback_data="contact_owner")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        # ----- Настройки пользователя -----
        if data == "show_settings":
            saved_cnt = len(saved_messages.get(user_id, []))
            saved_lim = user_data[user_id]["saved_messages_limit"]
            warns = user_data[user_id].get("warnings", 0)
            adult_att = user_data[user_id].get("adult_attempts", 0)
            note = user_custom_notes.get(user_id, "Не установлена")
            text = (
                f"⚙️ **Настройки пользователя**\n\n"
                f"📊 **Ваши данные:**\n"
                f"• Сохранено сообщений: {saved_cnt}/{saved_lim}\n"
                f"• Всего сообщений: {user_data[user_id].get('total_messages', 0)}\n"
                f"• Предупреждений: {warns}/{MAX_WARNINGS}\n"
                f"• Попыток 18+ запросов: {adult_att}\n\n"
                f"📝 **Ваша приписка к запросам:**\n"
                f"«{note}»\n\n"
                f"🔧 **Управление:**\n"
                f"• Нажмите кнопку ниже, чтобы изменить лимит сохранения\n"
                f"• Нажмите кнопку ниже, чтобы установить приписку к запросам\n"
            )
            keyboard = [
                [InlineKeyboardButton("🔢 Изменить лимит сохранения", callback_data="set_limit")],
                [InlineKeyboardButton("📝 Установить приписку", callback_data="set_custom_note")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if data == "set_limit":
            awaiting_input[user_id] = {"action": "set_limit"}
            await query.edit_message_text(
                "🔢 **Введите новый лимит сохраненных сообщений** (от 1 до 100):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode='Markdown'
            )
            return

        if data == "set_custom_note":
            awaiting_input[user_id] = {"action": "set_custom_note"}
            await query.edit_message_text(
                "📝 **Введите вашу приписку к запросам**\n\n"
                "Эта приписка будет добавляться к каждому вашему запросу. "
                "Например, вы можете попросить бота отвечать кратко, использовать определенный стиль и т.д.\n\n"
                "Введите текст:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode='Markdown'
            )
            return

        # ----- Панель владельца -----
        if data == "owner_panel" and user_limits.get(user_id, {}).get("is_owner"):
            total_requests_today = len([t for t in sum(user_requests.values(), []) if time.time() - t < 86400])
            active_now = len([uid for uid, times in user_requests.items() if times and time.time() - times[-1] < 300])
            banned_cnt = len(banned_users)
            pause_status = "⏸️ **Приостановлен**" if bot_paused else "▶️ **Активен**"
            text = (
                f"👑 **Панель владельца**\n\n"
                f"📊 **Глобальная статистика:**\n"
                f"• Всего пользователей: {len(user_data)}\n"
                f"• Активных сейчас: {active_now}\n"
                f"• Запросов сегодня: {total_requests_today}\n"
                f"• Всего запросов: {global_request_count}\n"
                f"• Ошибок API: {error_count}\n"
                f"• Забанено пользователей: {banned_cnt}\n"
                f"• Статус бота: {pause_status}\n\n"
                f"🔞 **18+ статистика:**\n"
                f"• Всего попыток: {sum(d.get('adult_attempts', 0) for d in user_data.values())}\n"
                f"• Нарушителей: {len([uid for uid, d in user_data.items() if d.get('adult_attempts', 0) > 0])}\n\n"
                f"⚙️ **Текущие настройки:**\n"
                f"• Макс. чатов: {bot_settings['max_chats']}\n"
                f"• Макс. сохранений: {bot_settings['max_saved_messages']}\n"
                f"• Cooldown: {bot_settings['default_cooldown']} сек\n"
                f"• Запросов/мин: {bot_settings['default_requests_per_minute']}\n"
                f"• Фильтр 18+: {'вкл' if bot_settings['enable_18_plus_filter'] else 'выкл'}\n\n"
                f"🔧 **Управление системой:**\n"
            )
            keyboard = [
                [InlineKeyboardButton("🔑 Сменить API ключ", callback_data="owner_change_api")],
                [InlineKeyboardButton("⚙️ Глобальные настройки", callback_data="owner_global_settings")],
                [InlineKeyboardButton("⏱️ Cooldown", callback_data="owner_set_cooldown")],
                [InlineKeyboardButton("📊 Лимиты запросов", callback_data="owner_set_rpm")],
                [InlineKeyboardButton("🔨 Управление банами", callback_data="owner_ban_menu")],
                [InlineKeyboardButton("📊 Активность", callback_data="owner_activity")],
                [InlineKeyboardButton("⏸️ Управление паузой", callback_data="owner_pause_menu")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if data == "owner_change_api" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "new_api_key"}
            await query.edit_message_text(
                "🔑 **Введите новый API ключ Groq**\n\n"
                "Ключ должен начинаться с 'gsk_' и быть длиннее 30 символов.\n"
                "После замены ключ будет использоваться для всех пользователей.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_global_settings" and user_limits.get(user_id, {}).get("is_owner"):
            keyboard = [
                [InlineKeyboardButton("📁 Макс. чатов", callback_data="owner_set_max_chats")],
                [InlineKeyboardButton("💾 Макс. сохранений", callback_data="owner_set_max_saved")],
                [InlineKeyboardButton("📝 Приветствие", callback_data="owner_set_welcome")],
                [InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]
            ]
            await query.edit_message_text(
                "⚙️ **Глобальные настройки**\n\nВыберите параметр для изменения:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        if data == "owner_set_max_chats" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_max_chats"}
            await query.edit_message_text(
                "📁 **Введите максимальное количество постоянных чатов на пользователя** (целое число >=1):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_global_settings")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_set_max_saved" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_max_saved"}
            await query.edit_message_text(
                "💾 **Введите максимальное количество сохраняемых сообщений на пользователя** (целое число >=1):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_global_settings")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_set_welcome" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_welcome_message"}
            await query.edit_message_text(
                "📝 **Введите новое приветственное сообщение**\n\n"
                "Используйте {name} для имени пользователя и {chat} для названия текущего чата.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_global_settings")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_set_cooldown" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_cooldown"}
            await query.edit_message_text(
                "⏱️ **Введите новый cooldown между запросами (в секундах)** (целое число >=0):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_set_rpm" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_requests_per_minute"}
            await query.edit_message_text(
                "📊 **Введите лимит запросов в минуту для всех пользователей** (целое число >=0):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_ban_menu" and user_limits.get(user_id, {}).get("is_owner"):
            keyboard = [
                [InlineKeyboardButton("🔨 Забанить пользователя", callback_data="owner_ban")],
                [InlineKeyboardButton("🔓 Разбанить пользователя", callback_data="owner_unban")],
                [InlineKeyboardButton("📋 Список забаненных", callback_data="owner_ban_list")],
                [InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]
            ]
            await query.edit_message_text(
                "🔨 **Управление банами**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        if data == "owner_ban" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "ban_user"}
            await query.edit_message_text(
                "🔨 **Введите ID пользователя для бана:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_ban_menu")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_unban" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "unban_user"}
            await query.edit_message_text(
                "🔓 **Введите ID пользователя для разбана:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_ban_menu")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_ban_list" and user_limits.get(user_id, {}).get("is_owner"):
            if banned_users:
                text = "📋 **Список забаненных пользователей:**\n\n"
                for uid in banned_users:
                    reason = user_data.get(uid, {}).get("ban_reason", "Не указана")
                    time_ban = user_data.get(uid, {}).get("ban_time", 0)
                    time_str = datetime.fromtimestamp(time_ban).strftime('%d.%m.%Y %H:%M') if time_ban else "неизвестно"
                    text += f"• `{uid}` - {reason} ({time_str})\n"
            else:
                text = "📋 **Нет забаненных пользователей.**"
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="owner_ban_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if data == "owner_activity" and user_limits.get(user_id, {}).get("is_owner"):
            today = datetime.now().strftime('%Y-%m-%d')
            week = datetime.now().strftime('%Y-%W')
            month = datetime.now().strftime('%Y-%m')
            da = len(daily_active_users)
            wa = len(weekly_active_users)
            ma = len(monthly_active_users)
            text = (
                f"📊 **Активность пользователей**\n\n"
                f"• Активных сегодня: {da}\n"
                f"• Активных на этой неделе: {wa}\n"
                f"• Активных в этом месяце: {ma}\n\n"
                f"Детальная статистика по дням доступна в логах."
            )
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if data == "owner_pause_menu" and user_limits.get(user_id, {}).get("is_owner"):
            status = "⏸️ Приостановлен" if bot_paused else "▶️ Активен"
            reason = f"\nПричина: {pause_reason}" if bot_paused else ""
            keyboard = [
                [InlineKeyboardButton("⏸️ Приостановить", callback_data="owner_pause")],
                [InlineKeyboardButton("▶️ Возобновить", callback_data="owner_resume")],
                [InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]
            ]
            await query.edit_message_text(
                f"⏸️ **Управление паузой бота**\n\nТекущий статус: {status}{reason}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        if data == "owner_pause" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "pause_reason"}
            await query.edit_message_text(
                "⏸️ **Введите причину приостановки бота:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="owner_pause_menu")]]),
                parse_mode='Markdown'
            )
            return

        if data == "owner_resume" and user_limits.get(user_id, {}).get("is_owner"):
            set_bot_pause(False)
            await query.edit_message_text(
                "▶️ **Бот возобновлен!**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
            await notify_owner(context, "Бот возобновлен.")
            return

        # ----- Режимы и модели -----
        if data == "show_modes":
            keyboard = []
            for mid, info in MODES.items():
                mark = "✅ " if user_data[user_id]["mode"] == mid else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{info['name']}", callback_data=f"mode_{mid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            await query.edit_message_text("🎭 **Выбери режим:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if data.startswith("mode_"):
            mode_id = data.replace("mode_", "")
            user_data[user_id]["mode"] = mode_id
            if user_data[user_id]["current_chat"]:
                custom = user_custom_notes.get(user_id, "")
                system = MODES[mode_id]["system_prompt"].format(custom_note=custom)
                user_data[user_id]["current_chat"]["messages"] = [{"role": "system", "content": system}]
                user_data[user_id]["current_chat"]["mode"] = mode_id
            await query.edit_message_text(f"✅ Режим изменен на {MODES[mode_id]['name']}", reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            return

        if data == "show_models":
            keyboard = []
            for name, mid in MODELS.items():
                mark = "✅ " if user_data[user_id]["model"] == mid else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"model_{mid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            await query.edit_message_text("🚀 **Выбери модель:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if data.startswith("model_"):
            model_id = data.replace("model_", "")
            user_data[user_id]["model"] = model_id
            if user_data[user_id]["current_chat"]:
                user_data[user_id]["current_chat"]["model"] = model_id
            await query.edit_message_text(f"✅ Модель изменена на {get_model_name(model_id)}", reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            return

        # ----- Чаты -----
        if data == "show_chats":
            await show_chats_interface(update, context, user_id, from_dialog=False)
            return

        if data.startswith("view_chat_"):
            chat_id = data.replace("view_chat_", "")
            if switch_chat(user_id, chat_id):
                chat = user_data[user_id]["current_chat"]
                msgs = [m for m in chat["messages"] if m["role"] != "system"]
                if msgs:
                    text = f"📜 **История чата: {chat['name']}**\n\n"
                    for i, m in enumerate(msgs[-10:]):
                        emoji = "👤" if m["role"] == "user" else "🤖"
                        text += f"**{i+1}.** {emoji} {m['content'][:100]}\n\n"
                else:
                    text = f"📭 **История чата: {chat['name']}**\n\nНет сообщений."
                keyboard = [[InlineKeyboardButton("◀️ Назад к чатам", callback_data="show_chats")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
            await query.edit_message_text(
                "📝 **Введите название для нового постоянного чата:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode='Markdown'
            )
            return

        if data == "new_temp_chat":
            if user_data[user_id]["temp_chat"]:
                keyboard = [
                    [InlineKeyboardButton("✅ Да, заменить", callback_data="confirm_replace_temp")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                await query.edit_message_text("У вас уже есть временный чат. Заменить его?", reply_markup=InlineKeyboardMarkup(keyboard))
                return
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "temporary"}
            await query.edit_message_text(
                "📝 **Введите название для временного чата:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                parse_mode='Markdown'
            )
            return

        if data == "delete_oldest_and_create":
            if delete_oldest_chat(user_id):
                awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
                await query.edit_message_text(
                    "✅ Самый старый чат удален.\n\n📝 **Введите название для нового чата:**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]),
                    parse_mode='Markdown'
                )
            return

        if data == "confirm_replace_temp":
            if "name" in awaiting_input.get(user_id, {}):
                name = awaiting_input[user_id]["name"]
                del awaiting_input[user_id]
                chat_id, error = create_chat(user_id, name, is_temporary=True)
                if chat_id:
                    await query.edit_message_text(f"✅ Временный чат '{name}' создан!", reply_markup=get_main_keyboard(user_id))
            return

    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        try:
            cur_chat = user_data[user_id]["current_chat"]["name"] if user_data[user_id]["current_chat"] else "Нет чата"
            welcome = bot_settings["welcome_message"].format(name=first_name, chat=cur_chat)
            await query.edit_message_text(f"❌ Произошла ошибка. Возврат в главное меню.\n\n{welcome}", reply_markup=get_main_keyboard(user_id))
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
    if GROQ_API_KEY:
        await init_groq_client(GROQ_API_KEY)
    else:
        logger.info("Groq API ключ не задан. Ожидается ввод через панель владельца.")
    logger.info(f"Бот запущен. Версия Python: {sys.version.split()[0]}")

# ----------------------------------------------------------------------
# Точка входа
# ----------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан! Укажите токен в коде или через переменную окружения.")
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
