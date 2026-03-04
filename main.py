import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.ext import ApplicationBuilder
import asyncio
import time
import socks
import socket
from groq import Groq
import datetime
import os
import sys
import uuid
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

# Токены
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"
GROQ_API_KEY = "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"

# ID владельца (будет определен при первом обращении)
OWNER_ID = None

# Глобальный клиент Groq (будет обновляться при смене ключа)
groq_client = None

# Флаг паузы бота
bot_paused = False
pause_reason = ""

# Глобальные настройки бота
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

# ============================================
# НАСТРОЙКА ПРОКСИ - ВЫКЛЮЧЕНО
# ============================================
USE_PROXY = False
PROXY_HOST = "195.74.72.111"
PROXY_PORT = 5678
PROXY_TYPE = socks.SOCKS4
# ============================================

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

if USE_PROXY:
    try:
        socks.set_default_proxy(PROXY_TYPE, PROXY_HOST, PROXY_PORT)
        socket.socket = socks.socksocket
        logger.info("Прокси настроен")
    except Exception as e:
        logger.error(f"Ошибка настройки прокси: {e}")

# Инициализация глобального клиента Groq
def init_groq_client(api_key):
    """Инициализация глобального клиента Groq"""
    global groq_client
    try:
        groq_client = Groq(api_key=api_key, timeout=30.0)
        logger.info("Groq клиент инициализирован")
        return True
    except Exception as e:
        logger.error(f"Ошибка инициализации Groq клиента: {e}")
        return False

# Инициализируем клиент при старте
init_groq_client(GROQ_API_KEY)

# Модели
MODELS = {
    "🚀 LLaMA 3.1 8B": "llama-3.1-8b-instant",
    "🔸 Gemma 2 9B": "gemma2-9b-it",
    "🎯 LLaMA 3.3 70B": "llama-3.3-70b-versatile",
}

# Режимы общения
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

DEFAULT_MODEL = bot_settings["default_model"]
DEFAULT_MODE = bot_settings["default_mode"]

# Информация о лимитах Groq
GROQ_LIMITS = {
    "free_tier": {
        "requests_per_minute": 30,
        "requests_per_hour": 500,
        "requests_per_day": 1000,
        "tokens_per_minute": 6000,
        "max_tokens_per_request": 4096,
        "concurrent_requests": 3
    },
    "paid_tier": {
        "requests_per_minute": 100,
        "requests_per_hour": 2000,
        "requests_per_day": 10000,
        "tokens_per_minute": 20000,
        "max_tokens_per_request": 8192,
        "concurrent_requests": 10
    }
}

# Структура данных пользователя
user_data = {}
user_last_message = {}
menu_messages = {}
awaiting_input = {}  # Для ожидания ввода
saved_messages = {}  # Сохраненные сообщения
dialog_messages = {}  # Для хранения ID сообщений в диалоге
last_message_text = {}  # Для хранения текста последнего сообщения
last_api_call_time = {}  # Время последнего вызова API для каждого пользователя
user_custom_notes = {}  # Пользовательские приписки к запросам

# Система лимитов запросов
user_requests = defaultdict(list)  # {user_id: [timestamps]}
user_limits = {}  # {user_id: {"requests_per_minute": int, "requests_per_hour": int, "requests_per_day": int, "cooldown": int}}
global_request_count = 0  # Общее количество запросов
error_count = 0  # Счетчик ошибок
last_error_time = None  # Время последней ошибки
error_users = set()  # Пользователи, у которых были ошибки

# Система банов и предупреждений
banned_users = set()  # Забаненные пользователи
user_warnings = defaultdict(int)  # {user_id: warnings_count}
adult_content_attempts = defaultdict(int)  # {user_id: attempts_count}

# Система отслеживания активности
user_activity = {}  # {user_id: {"last_active": timestamp, "total_messages": int, "total_time": int, "daily_stats": {}}}
daily_active_users = set()  # Активные за день пользователи
weekly_active_users = set()  # Активные за неделю пользователи
monthly_active_users = set()  # Активные за месяц пользователи

# Время запуска бота
bot_start_time = time.time()

# Константы (используем значения из bot_settings)
MAX_CHATS = bot_settings["max_chats"]
MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
MAX_WARNINGS = bot_settings["max_warnings"]
MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]

# Список ключевых слов для 18+ контента
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

def init_user_data(user_id):
    """Инициализация данных пользователя"""
    if user_id not in user_data:
        user_data[user_id] = {
            "chats": [],  # Постоянные чаты
            "temp_chat": None,  # Временный чат
            "current_chat_id": None,
            "current_chat": None,
            "chat_type": None,  # "permanent" или "temporary"
            "in_dialog": False,
            "showing_action_buttons": False,
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "total_messages": 0,
            "saved_messages_limit": MAX_SAVED_MESSAGES,  # Лимит сохраняемых сообщений
            "username": None,
            "first_seen": time.time(),
            "last_active": time.time(),
            "notes": "",  # Заметки администратора
            "total_spent_time": 0,  # Общее время использования в секундах
            "adult_attempts": 0,  # Количество попыток 18+ запросов
            "warnings": 0,  # Количество предупреждений
            "is_banned": False,  # Забанен ли пользователь
            "last_message_id": None,  # ID последнего сообщения для навигации
            "custom_note": "",  # Пользовательская приписка к запросам
            "is_owner": False,  # Является ли владельцем
        }
        dialog_messages[user_id] = []  # Список ID сообщений в текущем диалоге
        saved_messages[user_id] = []  # Сохраненные сообщения
        last_message_text[user_id] = {"user": "", "bot": ""}  # Текст последних сообщений
        last_api_call_time[user_id] = 0  # Время последнего вызова API
        user_custom_notes[user_id] = ""  # Пользовательская приписка
        
        # Инициализируем лимиты для пользователя
        if user_id not in user_limits:
            user_limits[user_id] = {
                "requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE,
                "requests_per_hour": DEFAULT_REQUESTS_PER_HOUR,
                "requests_per_day": DEFAULT_REQUESTS_PER_DAY,
                "cooldown": DEFAULT_COOLDOWN
            }
        
        # Инициализируем активность
        user_activity[user_id] = {
            "last_active": time.time(),
            "total_messages": 0,
            "total_time": 0,
            "daily_stats": {},
            "weekly_stats": {},
            "monthly_stats": {}
        }

def check_adult_content(text):
    """Проверка на наличие 18+ контента в тексте"""
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
    
    # Обновляем статистику
    user_activity[user_id]["last_active"] = now
    user_activity[user_id]["total_messages"] += 1
    
    # Дневная статистика
    if today not in user_activity[user_id]["daily_stats"]:
        user_activity[user_id]["daily_stats"][today] = 0
    user_activity[user_id]["daily_stats"][today] += 1
    
    # Недельная статистика
    if week not in user_activity[user_id]["weekly_stats"]:
        user_activity[user_id]["weekly_stats"][week] = 0
    user_activity[user_id]["weekly_stats"][week] += 1
    
    # Месячная статистика
    if month not in user_activity[user_id]["monthly_stats"]:
        user_activity[user_id]["monthly_stats"][month] = 0
    user_activity[user_id]["monthly_stats"][month] += 1
    
    # Обновляем множества активных пользователей
    daily_active_users.add(user_id)
    weekly_active_users.add(user_id)
    monthly_active_users.add(user_id)
    
    # Общее время использования
    if user_id in user_data:
        user_data[user_id]["last_active"] = now
        user_data[user_id]["total_spent_time"] = now - user_data[user_id]["first_seen"]

def check_request_limits(user_id):
    """Проверка лимитов запросов для пользователя"""
    if bot_paused:
        return False, "⏸️ Бот временно приостановлен. Причина: " + pause_reason
    
    if user_id in banned_users or (user_id in user_data and user_data[user_id].get("is_banned", False)):
        return False, "❌ Вы забанены в боте."
    
    if user_id not in user_limits:
        return True, "OK"
    
    limits = user_limits[user_id]
    now = time.time()
    
    # Очищаем старые запросы
    if user_id in user_requests:
        user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 86400]
    
    # Проверяем cooldown
    if user_requests[user_id] and now - user_requests[user_id][-1] < limits["cooldown"]:
        wait_time = int(limits["cooldown"] - (now - user_requests[user_id][-1]))
        return False, f"⏱️ Подождите {wait_time} сек"
    
    # Проверяем лимит в минуту
    minute_ago = now - 60
    minute_requests = len([t for t in user_requests[user_id] if t > minute_ago])
    if minute_requests >= limits["requests_per_minute"]:
        return False, f"⏱️ Лимит {limits['requests_per_minute']} запросов/мин"
    
    return True, "OK"

def can_call_api(user_id):
    """Проверка, можно ли вызвать API"""
    now = time.time()
    last_call = last_api_call_time.get(user_id, 0)
    if now - last_call < API_CALL_COOLDOWN:
        return False
    last_api_call_time[user_id] = now
    return True

def record_request(user_id):
    """Записать запрос пользователя"""
    user_requests[user_id].append(time.time())
    global global_request_count
    global_request_count += 1
    
    # Обновляем активность
    update_user_activity(user_id)
    
    # Обновляем время последней активности
    if user_id in user_data:
        user_data[user_id]["last_active"] = time.time()
        user_data[user_id]["total_spent_time"] = time.time() - user_data[user_id]["first_seen"]

def create_chat(user_id, name, is_temporary=False):
    """Создание нового чата"""
    if user_id not in user_data:
        init_user_data(user_id)
    
    chat_id = str(uuid.uuid4())[:8]
    
    # Получаем пользовательскую приписку
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
            return None, "Достигнут лимит чатов"
        
        user_data[user_id]["chats"].append(new_chat)
        user_data[user_id]["current_chat"] = new_chat
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "permanent"
    
    return chat_id, None

def switch_chat(user_id, chat_id):
    """Переключение на другой чат"""
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
            user_data[user_id]["model"] = chat.get("model", DEFAULT_MODEL)
            user_data[user_id]["mode"] = chat.get("mode", DEFAULT_MODE)
            return True
    return False

def delete_oldest_chat(user_id):
    """Удаление самого старого постоянного чата"""
    if user_id not in user_data:
        return False
    
    permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
    if permanent_chats:
        oldest = min(permanent_chats, key=lambda x: x["created"])
        user_data[user_id]["chats"].remove(oldest)
        return True
    return False

def save_message(user_id, message_text, sender):
    """Сохранить сообщение"""
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
    """Удалить сохраненное сообщение"""
    if user_id in saved_messages and 0 <= index < len(saved_messages[user_id]):
        saved_messages[user_id].pop(index)
        return True
    return False

def update_groq_api_key(new_api_key):
    """Обновление глобального API ключа Groq"""
    global GROQ_API_KEY
    GROQ_API_KEY = new_api_key
    return init_groq_client(new_api_key)

def ban_user(user_id, reason=""):
    """Забанить пользователя"""
    banned_users.add(user_id)
    if user_id in user_data:
        user_data[user_id]["is_banned"] = True
        user_data[user_id]["ban_reason"] = reason
        user_data[user_id]["ban_time"] = time.time()
    return True

def unban_user(user_id):
    """Разбанить пользователя"""
    if user_id in banned_users:
        banned_users.remove(user_id)
    if user_id in user_data:
        user_data[user_id]["is_banned"] = False
        if "ban_reason" in user_data[user_id]:
            del user_data[user_id]["ban_reason"]
        if "ban_time" in user_data[user_id]:
            del user_data[user_id]["ban_time"]
    return True

def warn_user(user_id, reason=""):
    """Выдать предупреждение пользователю"""
    user_warnings[user_id] += 1
    if user_id in user_data:
        user_data[user_id]["warnings"] = user_data[user_id].get("warnings", 0) + 1
        
        if user_data[user_id]["warnings"] >= MAX_WARNINGS:
            ban_user(user_id, f"Превышен лимит предупреждений")
            return True, "user_banned"
    
    return True, "warned"

def set_bot_pause(paused, reason=""):
    """Установить паузу бота"""
    global bot_paused, pause_reason
    bot_paused = paused
    pause_reason = reason
    return True

def update_bot_settings(new_settings):
    """Обновление глобальных настроек бота"""
    global bot_settings, MAX_CHATS, MAX_SAVED_MESSAGES, DEFAULT_REQUESTS_PER_MINUTE
    global DEFAULT_REQUESTS_PER_HOUR, DEFAULT_REQUESTS_PER_DAY, DEFAULT_COOLDOWN
    global MAX_WARNINGS, MAX_ADULT_ATTEMPTS, API_CALL_COOLDOWN
    
    bot_settings.update(new_settings)
    
    # Обновляем константы
    MAX_CHATS = bot_settings["max_chats"]
    MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
    DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
    DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
    DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
    DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
    MAX_WARNINGS = bot_settings["max_warnings"]
    MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
    API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]
    
    return True

async def notify_owner(context, message):
    """Отправить уведомление владельцу"""
    if OWNER_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"⚠️ **Уведомление**\n\n{message}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление: {e}")

def get_main_keyboard(user_id):
    """Главная клавиатура"""
    if user_id in user_data:
        mode_emoji = MODES[user_data[user_id]["mode"]]["emoji"]
    else:
        mode_emoji = "💬"
    
    keyboard = [
        [
            InlineKeyboardButton(f"{mode_emoji} Режим", callback_data="show_modes"),
            InlineKeyboardButton("🚀 Модель", callback_data="show_models")
        ],
        [
            InlineKeyboardButton("📋 Чаты", callback_data="show_chats"),
            InlineKeyboardButton("⚙️ Настройки", callback_data="show_settings")
        ],
        [
            InlineKeyboardButton("ℹ️ Информация", callback_data="show_info")
        ]
    ]
    
    # Кнопка связи с владельцем для всех
    keyboard.append([InlineKeyboardButton("📨 Связаться с владельцем", callback_data="contact_owner")])
    
    # Кнопка для владельца
    if user_data.get(user_id, {}).get("is_owner", False):
        keyboard.append([InlineKeyboardButton("👑 Панель владельца", callback_data="owner_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def get_dialog_navigation_keyboard(user_id):
    """Клавиатура для навигации в диалоге"""
    keyboard = [
        [InlineKeyboardButton("❤️ Сохранить", callback_data="show_save_options")],
        [InlineKeyboardButton("📋 Управление чатами", callback_data="show_chats_from_dialog")],
        [InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_save_options_keyboard():
    """Клавиатура для сохранения сообщений"""
    keyboard = [
        [KeyboardButton("👤 СОХРАНИТЬ МОЁ"), KeyboardButton("🤖 СОХРАНИТЬ БОТА")],
        [KeyboardButton("❌ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def delete_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Удаление предыдущего меню"""
    if user_id in menu_messages:
        try:
            await context.bot.delete_message(
                chat_id=user_id,
                message_id=menu_messages[user_id]
            )
        except:
            pass
        del menu_messages[user_id]

async def delete_dialog_messages(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Удаление всех сообщений в диалоге"""
    if user_id in dialog_messages:
        for message_id in dialog_messages[user_id]:
            try:
                await context.bot.delete_message(
                    chat_id=user_id,
                    message_id=message_id
                )
            except:
                pass
        dialog_messages[user_id] = []

async def post_init(application: Application):
    """После инициализации бота"""
    try:
        # Устанавливаем только одну команду
        commands = [
            BotCommand("start", "Запустить бота"),
        ]
        await application.bot.set_my_commands(commands)
        
        logger.info("Бот успешно запущен!")
        logger.info(f"Версия Python: {sys.version.split()[0]}")
        logger.info(f"Время запуска: {datetime.now()}")
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["username"] = username
        create_chat(user_id, "Основной чат", is_temporary=False)
    
    # Формируем приветственное сообщение
    current_chat_name = user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'
    welcome_text = bot_settings["welcome_message"].format(
        name=first_name,
        chat=current_chat_name
    )
    
    try:
        msg = await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = msg.message_id
        user_data[user_id]["last_message_id"] = msg.message_id
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    global error_count
    
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Сохраняем ID сообщения пользователя
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    dialog_messages[user_id].append(update.message.message_id)
    
    # Обработка кнопок сохранения
    if user_message == "👤 СОХРАНИТЬ МОЁ":
        if last_message_text.get(user_id, {}).get("user"):
            save_message(user_id, last_message_text[user_id]["user"], "user")
            await update.message.reply_text("✅ Сохранено!")
        else:
            await update.message.reply_text("❌ Нет сообщения")
        return
    
    if user_message == "🤖 СОХРАНИТЬ БОТА":
        if last_message_text.get(user_id, {}).get("bot"):
            save_message(user_id, last_message_text[user_id]["bot"], "bot")
            await update.message.reply_text("✅ Сохранено!")
        else:
            await update.message.reply_text("❌ Нет сообщения")
        return
    
    if user_message == "❌ Назад":
        await update.message.reply_text(
            "Выбери действие:",
            reply_markup=get_dialog_navigation_keyboard(user_id)
        )
        return
    
    # Проверяем ожидание ввода
    if user_id in awaiting_input:
        action_data = awaiting_input[user_id]
        
        if action_data.get("action") == "new_chat_name":
            del awaiting_input[user_id]
            chat_type = action_data.get("chat_type")
            
            if chat_type == "permanent":
                permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
                if len(permanent_chats) >= MAX_CHATS:
                    keyboard = [[InlineKeyboardButton("🗑 Удалить старый", callback_data="delete_oldest_and_create")]]
                    await update.message.reply_text(
                        "❌ Лимит чатов",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
                
                chat_id, _ = create_chat(user_id, user_message[:50], False)
                if chat_id:
                    await update.message.reply_text("✅ Чат создан!", reply_markup=get_main_keyboard(user_id))
            
            elif chat_type == "temporary":
                if user_data[user_id]["temp_chat"]:
                    awaiting_input[user_id] = {"action": "confirm_replace", "name": user_message[:50]}
                    keyboard = [[InlineKeyboardButton("✅ Да", callback_data="confirm_replace_temp")]]
                    await update.message.reply_text("Заменить?", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    create_chat(user_id, user_message[:50], True)
                    await update.message.reply_text("✅ Временный чат создан!", reply_markup=get_main_keyboard(user_id))
            return
        
        elif action_data.get("action") == "set_limit":
            del awaiting_input[user_id]
            try:
                limit = int(user_message)
                if 1 <= limit <= 100:
                    user_data[user_id]["saved_messages_limit"] = limit
                    await update.message.reply_text(f"✅ Лимит: {limit}")
                else:
                    await update.message.reply_text("❌ От 1 до 100")
            except:
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
            
            await update.message.reply_text("✅ Приписка сохранена!")
            return
        
        elif action_data.get("action") == "new_api_key" and user_data.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            new_key = user_message.strip()
            if new_key.startswith("gsk_") and len(new_key) > 30:
                if update_groq_api_key(new_key):
                    await update.message.reply_text("✅ API ключ обновлен!")
                    await notify_owner(context, "API ключ обновлен")
                else:
                    await update.message.reply_text("❌ Ошибка обновления ключа")
            else:
                await update.message.reply_text("❌ Неверный формат ключа")
            return
        
        elif action_data.get("action") == "pause_reason" and user_data.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            set_bot_pause(True, user_message)
            await update.message.reply_text(f"✅ Бот приостановлен")
            await notify_owner(context, f"Бот приостановлен")
            return
        
        elif action_data.get("action") == "contact_owner":
            del awaiting_input[user_id]
            if OWNER_ID:
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"📨 **Сообщение от пользователя**\n\nID: `{user_id}`\nUsername: @{username or 'нет'}\n\n{user_message}",
                        parse_mode='Markdown'
                    )
                    await update.message.reply_text("✅ Сообщение отправлено владельцу!")
                except:
                    await update.message.reply_text("❌ Ошибка отправки")
            else:
                await update.message.reply_text("❌ Владелец не найден")
            return
    
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
        create_chat(user_id, "Основной чат", False)
    
    if not user_data[user_id]["current_chat"]:
        create_chat(user_id, "Временный", True)
    
    # Проверка лимитов
    allowed, msg = check_request_limits(user_id)
    if not allowed:
        await update.message.reply_text(msg)
        return
    
    # Проверка 18+
    if check_adult_content(user_message):
        user_data[user_id]["adult_attempts"] = user_data[user_id].get("adult_attempts", 0) + 1
        attempts = user_data[user_id]["adult_attempts"]
        
        if attempts >= MAX_ADULT_ATTEMPTS:
            result, status = warn_user(user_id, "18+ контент")
            if status == "user_banned":
                await update.message.reply_text("❌ Вы забанены")
                return
        
        await update.message.reply_text("❌ Запрос отклонен (18+)")
        return
    
    user_data[user_id]["in_dialog"] = True
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        chat = user_data[user_id]["current_chat"]
        history = chat["messages"]
        history.append({"role": "user", "content": user_message})
        
        user_data[user_id]["total_messages"] += 1
        last_message_text[user_id]["user"] = user_message
        
        if len(history) > 51:
            history[:] = [history[0]] + history[-50:]
        
        record_request(user_id)
        
        if not groq_client:
            await update.message.reply_text("❌ Ошибка API")
            return
        
        if not can_call_api(user_id):
            await update.message.reply_text("⏱️ Слишком часто")
            return
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                model=user_data[user_id]["model"],
                messages=history,
                temperature=0.8,
                max_tokens=512
            )
        )
        
        assistant = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant})
        last_message_text[user_id]["bot"] = assistant
        
        sent = await update.message.reply_text(
            assistant,
            reply_markup=get_dialog_navigation_keyboard(user_id)
        )
        dialog_messages[user_id].append(sent.message_id)
        
        # Показываем кнопки сохранения
        save_msg = await context.bot.send_message(
            chat_id=user_id,
            text="💾 Сохранить сообщение:",
            reply_markup=get_save_options_keyboard()
        )
        dialog_messages[user_id].append(save_msg.message_id)
        user_data[user_id]["last_message_id"] = sent.message_id
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        error_count += 1
        error_users.add(user_id)
        
        if "api_key" in str(e).lower():
            await update.message.reply_text("❌ Проблема с API ключом")
        else:
            await update.message.reply_text("❌ Ошибка API")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото"""
    user_id = update.effective_user.id
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
    
    await update.message.reply_text("📸 Только текст")

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение диалога"""
    user_id = update.effective_user.id
    
    await delete_dialog_messages(user_id, context)
    
    if user_id in user_data:
        chat = user_data[user_id]["current_chat"]
        if chat and chat.get("is_temporary"):
            user_data[user_id]["temp_chat"] = None
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
        else:
            user_data[user_id]["in_dialog"] = False
    
    first_name = update.effective_user.first_name
    current_chat_name = user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'
    welcome_text = bot_settings["welcome_message"].format(
        name=first_name,
        chat=current_chat_name
    )
    
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=welcome_text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode='Markdown'
    )
    menu_messages[user_id] = msg.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        username = query.from_user.username
        first_name = query.from_user.first_name
        
        if user_id not in user_data:
            init_user_data(user_id)
            user_data[user_id]["username"] = username
            create_chat(user_id, "Основной чат", False)
        
        if query.data == "ignore":
            return
        
        # Навигация
        if query.data == "back_to_main":
            current_chat_name = user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'
            welcome_text = bot_settings["welcome_message"].format(
                name=first_name,
                chat=current_chat_name
            )
            
            await query.edit_message_text(
                welcome_text,
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
            )
            return
        
        # Возврат в диалог
        if query.data == "back_to_dialog":
            await query.edit_message_text(
                "🔄 Продолжай общение!",
                reply_markup=get_dialog_navigation_keyboard(user_id)
            )
            return
        
        # Показ опций сохранения
        if query.data == "show_save_options":
            await query.edit_message_text(
                "💾 Выбери что сохранить:",
                reply_markup=None
            )
            await context.bot.send_message(
                chat_id=user_id,
                text="Используй кнопки ниже:",
                reply_markup=get_save_options_keyboard()
            )
            return
        
        # Показ чатов из диалога
        if query.data == "show_chats_from_dialog":
            await show_chats_interface(update, context, user_id, from_dialog=True)
            return
        
        # Завершение диалога
        if query.data == "end_dialog":
            await end_dialog(update, context)
            return
        
        # Связь с владельцем
        if query.data == "contact_owner":
            awaiting_input[user_id] = {"action": "contact_owner"}
            await query.edit_message_text(
                "📨 **Напиши сообщение для владельца**\n\nОн получит его и сможет ответить.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Информация
        if query.data == "show_info":
            uptime = str(timedelta(seconds=int(time.time() - bot_start_time)))
            
            text = (
                f"ℹ️ **Информация**\n\n"
                f"⏱ Аптайм: {uptime}\n"
                f"👥 Пользователей: {len(user_data)}\n"
                f"📊 Запросов: {global_request_count}\n"
                f"🚫 Забанено: {len(banned_users)}\n"
                f"⏸️ Бот: {'приостановлен' if bot_paused else 'активен'}\n\n"
                f"📋 Все функции доступны через кнопки меню"
            )
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Настройки пользователя
        if query.data == "show_settings":
            saved_count = len(saved_messages.get(user_id, []))
            saved_limit = user_data[user_id]["saved_messages_limit"]
            custom_note = user_custom_notes.get(user_id, "Не установлена")
            
            text = (
                f"⚙️ **Настройки**\n\n"
                f"📊 **Данные:**\n"
                f"• Сохранено: {saved_count}/{saved_limit}\n"
                f"• Сообщений: {user_data[user_id].get('total_messages', 0)}\n\n"
                f"📝 **Приписка:**\n"
                f"«{custom_note}»\n\n"
                f"🔧 **Управление:**"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔢 Лимит сохранения", callback_data="set_limit")],
                [InlineKeyboardButton("📝 Установить приписку", callback_data="set_custom_note")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Установка лимита
        if query.data == "set_limit":
            awaiting_input[user_id] = {"action": "set_limit"}
            await query.edit_message_text(
                "🔢 **Лимит (1-100):**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Установка приписки
        if query.data == "set_custom_note":
            awaiting_input[user_id] = {"action": "set_custom_note"}
            await query.edit_message_text(
                "📝 **Введи приписку к запросам:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Панель владельца
        if query.data == "owner_panel" and user_data.get(user_id, {}).get("is_owner"):
            text = (
                f"👑 **Панель владельца**\n\n"
                f"📊 **Статистика:**\n"
                f"• Пользователей: {len(user_data)}\n"
                f"• Запросов: {global_request_count}\n"
                f"• Ошибок: {error_count}\n"
                f"• Забанено: {len(banned_users)}\n"
                f"• Статус: {'приостановлен' if bot_paused else 'активен'}\n\n"
                f"⚙️ **Управление:**"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔑 Сменить API ключ", callback_data="owner_change_api")],
                [InlineKeyboardButton("⏸️ Управление паузой", callback_data="owner_pause_menu")],
                [InlineKeyboardButton("🔨 Управление банами", callback_data="owner_ban_menu")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Смена API ключа
        if query.data == "owner_change_api" and user_data.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "new_api_key"}
            await query.edit_message_text(
                "🔑 **Введите новый API ключ:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Меню паузы
        if query.data == "owner_pause_menu" and user_data.get(user_id, {}).get("is_owner"):
            text = "⏸️ **Управление паузой**\n\n"
            text += f"Статус: {'приостановлен' if bot_paused else 'активен'}\n"
            if bot_paused:
                text += f"Причина: {pause_reason}\n\n"
            
            keyboard = []
            if bot_paused:
                keyboard.append([InlineKeyboardButton("▶️ Возобновить", callback_data="owner_resume_bot")])
            else:
                keyboard.append([InlineKeyboardButton("⏸️ Приостановить", callback_data="owner_pause_bot")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")])
            
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Приостановка бота
        if query.data == "owner_pause_bot" and user_data.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "pause_reason"}
            await query.edit_message_text(
                "⏸️ **Причина приостановки:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_pause_menu")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Возобновление бота
        if query.data == "owner_resume_bot" and user_data.get(user_id, {}).get("is_owner"):
            set_bot_pause(False)
            await query.edit_message_text(
                "✅ **Бот возобновил работу!**",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        # Меню банов
        if query.data == "owner_ban_menu" and user_data.get(user_id, {}).get("is_owner"):
            text = "🔨 **Управление банами**\n\n"
            
            if banned_users:
                text += "**Забаненные:**\n"
                for uid in list(banned_users)[:10]:
                    username = user_data.get(uid, {}).get("username", "?")
                    text += f"• ID: `{uid}` (@{username})\n"
            else:
                text += "Нет забаненных.\n"
            
            keyboard = [
                [InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Показ чатов
        if query.data == "show_chats":
            await show_chats_interface(update, context, user_id, from_dialog=False)
            return
        
        # Просмотр чата
        if query.data.startswith("view_chat_"):
            chat_id = query.data.replace("view_chat_", "")
            if switch_chat(user_id, chat_id):
                chat = user_data[user_id]["current_chat"]
                msgs = [m for m in chat["messages"] if m["role"] != "system"]
                
                text = f"📜 **{chat['name']}**\n\n"
                if msgs:
                    for i, msg in enumerate(msgs[-5:]):
                        emoji = "👤" if msg["role"] == "user" else "🤖"
                        text += f"{emoji} {msg['content'][:50]}\n\n"
                else:
                    text += "Нет сообщений"
                
                keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="show_chats")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Создание чата
        if query.data == "new_permanent_chat":
            perm = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary")]
            if len(perm) >= MAX_CHATS:
                keyboard = [[InlineKeyboardButton("🗑 Удалить старый", callback_data="delete_oldest_and_create")]]
                await query.edit_message_text("❌ Лимит", reply_markup=InlineKeyboardMarkup(keyboard))
                return
            
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
            await query.edit_message_text(
                "📝 **Название:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        if query.data == "new_temp_chat":
            if user_data[user_id]["temp_chat"]:
                keyboard = [[InlineKeyboardButton("✅ Да", callback_data="confirm_replace_temp")]]
                await query.edit_message_text("Заменить?", reply_markup=InlineKeyboardMarkup(keyboard))
                return
            
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "temporary"}
            await query.edit_message_text(
                "📝 **Название:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        if query.data == "delete_oldest_and_create":
            if delete_oldest_chat(user_id):
                awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
                await query.edit_message_text(
                    "✅ Удален. **Название:**",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                    ]]),
                    parse_mode='Markdown'
                )
            return
        
        if query.data == "confirm_replace_temp":
            if "name" in awaiting_input.get(user_id, {}):
                name = awaiting_input[user_id]["name"]
                del awaiting_input[user_id]
                create_chat(user_id, name, True)
                await query.edit_message_text("✅ Создан!", reply_markup=get_main_keyboard(user_id))
            return
        
        # Меню режимов
        if query.data == "show_modes":
            keyboard = []
            for mode_id, mode in MODES.items():
                mark = "✅ " if user_data[user_id]["mode"] == mode_id else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{mode['name']}", callback_data=f"mode_{mode_id}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            
            await query.edit_message_text(
                "🎭 **Режим:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        if query.data.startswith("mode_"):
            mode_id = query.data.replace("mode_", "")
            user_data[user_id]["mode"] = mode_id
            
            if user_data[user_id]["current_chat"]:
                custom_note = user_custom_notes.get(user_id, "")
                system_prompt = MODES[mode_id]["system_prompt"].format(custom_note=custom_note)
                user_data[user_id]["current_chat"]["messages"] = [{"role": "system", "content": system_prompt}]
            
            await query.edit_message_text(
                f"✅ Режим: {MODES[mode_id]['name']}",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        # Меню моделей
        if query.data == "show_models":
            keyboard = []
            for name, model_id in MODELS.items():
                mark = "✅ " if user_data[user_id]["model"] == model_id else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"model_{model_id}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            
            await query.edit_message_text(
                "🚀 **Модель:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        if query.data.startswith("model_"):
            model_id = query.data.replace("model_", "")
            user_data[user_id]["model"] = model_id
            
            if user_data[user_id]["current_chat"]:
                user_data[user_id]["current_chat"]["model"] = model_id
            
            await query.edit_message_text(
                f"✅ Модель изменена",
                reply_markup=get_main_keyboard(user_id)
            )
            return
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")

async def show_chats_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, from_dialog=False):
    """Показать интерфейс чатов"""
    keyboard = []
    
    perm_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary")]
    for chat in perm_chats:
        mark = "✅ " if user_data[user_id]["current_chat_id"] == chat["id"] else ""
        cnt = len([m for m in chat["messages"] if m["role"] != "system"])
        keyboard.append([InlineKeyboardButton(f"{mark}{chat['name']} ({cnt})", callback_data=f"view_chat_{chat['id']}")])
    
    if user_data[user_id]["temp_chat"]:
        t = user_data[user_id]["temp_chat"]
        mark = "✅ " if user_data[user_id]["current_chat_id"] == t["id"] else ""
        cnt = len([m for m in t["messages"] if m["role"] != "system"])
        keyboard.append([InlineKeyboardButton(f"{mark}⏳ {t['name']} ({cnt})", callback_data=f"view_chat_{t['id']}")])
    
    keyboard.append([
        InlineKeyboardButton("➕ Пост", callback_data="new_permanent_chat"),
        InlineKeyboardButton("⏳ Врем", callback_data="new_temp_chat")
    ])
    
    if from_dialog:
        keyboard.append([InlineKeyboardButton("🔄 В диалог", callback_data="back_to_dialog")])
    else:
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    
    text = f"📋 **Чаты**\n\nВсего: {len(perm_chats)}/{MAX_CHATS}"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

def get_model_name(model_id):
    for name, mid in MODELS.items():
        if mid == model_id:
            return name
    return model_id

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск"""
    try:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)
        
        logger.info("Запуск...")
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        time.sleep(5)
        main()

if __name__ == '__main__':
    main()
