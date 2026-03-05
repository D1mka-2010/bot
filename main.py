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

# ID владельца для уведомлений (будет определено при первом обращении)
OWNER_CHAT_ID = None  # Сюда можно вписать ваш ID вручную, если знаете

# Глобальный клиент Groq (будет обновляться при смене ключа)
groq_client = None

# Флаг паузы бота
bot_paused = False
pause_reason = ""

# Глобальные настройки бота (доступны только админу)
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

# Настройка логирования с правильной кодировкой для Windows
class CustomFormatter(logging.Formatter):
    """Форматтер, который заменяет эмодзи на текстовые аналоги для консоли Windows"""
    
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        # Словарь замены эмодзи на текст
        self.emoji_map = {
            '✅': '[OK]',
            '❌': '[ERROR]',
            '🚀': '[ROCKET]',
            '🕒': '[TIME]',
            '📊': '[STATS]',
            'ℹ️': '[INFO]',
            '⚠️': '[WARN]',
            '🔸': '[GEM]',
            '🎯': '[TARGET]',
            '💬': '[CHAT]',
            '😈': '[DEVIL]',
            '🤬': '[SWEAR]',
            '👋': '[WAVE]',
            '📌': '[PIN]',
            '💡': '[IDEA]',
            '⚡': '[BOLT]',
            '📋': '[CLIPBOARD]',
            '◀️': '[BACK]',
            '🎭': '[MASKS]',
            '🤖': '[ROBOT]',
            '👤': '[USER]',
            '⏱': '[TIMER]',
            '📈': '[CHART]',
            '🐍': '[PYTHON]',
            '🔍': '[SEARCH]',
            '💾': '[SAVE]',
            '🔧': '[TOOL]',
            '📝': '[PENCIL]',
            '🎮': '[GAME]',
            '🌐': '[GLOBE]',
            '📱': '[PHONE]',
            '💻': '[PC]',
            '🔑': '[KEY]',
            '🔒': '[LOCK]',
            '🔓': '[UNLOCK]',
            '📁': '[FOLDER]',
            '📂': '[OPEN FOLDER]',
            '📄': '[FILE]',
            '📅': '[CALENDAR]',
            '⏰': '[ALARM]',
            '🌍': '[EARTH]',
            '🔥': '[FIRE]',
            '💥': '[BOOM]',
            '✨': '[SPARKLES]',
            '⭐': '[STAR]',
            '🌟': '[GLOWING STAR]',
            '💫': '[STARRY]',
            '❤️': '[LIKE]',
            '👍': '[LIKE]',
            '⚙️': '[SETTINGS]',
            '📊': '[STATS]',
            '⏱️': '[TIMER]',
            '🔢': '[LIMIT]',
            '👑': '[OWNER]',
            '📢': '[ANNOUNCE]',
            '🔨': '[BAN]',
            '🔓': '[UNBAN]',
            '📝': '[LOG]',
            '💾': '[BACKUP]',
            '🔄': '[RESTART]',
            '📈': '[STATS]',
            '🔞': '[18+]',
            '👁️': '[VIEW]',
            '📊': '[ACTIVITY]',
            '⏸️': '[PAUSE]',
            '▶️': '[RESUME]',
            '🔄': '[BACK_TO_CHAT]',
            '📝': '[NOTE]',
            '⚡': '[CUSTOM]',
        }
    
    def format(self, record):
        result = super().format(record)
        for emoji, text in self.emoji_map.items():
            result = result.replace(emoji, text)
        return result

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

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
        # Создаем новый клиент с переданным ключом
        groq_client = Groq(api_key=api_key, timeout=30.0)
        # Проверяем работоспособность ключа, сделав тестовый запрос
        test_response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        logger.info(f"Groq клиент инициализирован с новым ключом: {api_key[:10]}...")
        return True
    except Exception as e:
        logger.error(f"Ошибка инициализации Groq клиента: {e}")
        groq_client = None
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

# Информация о лимитах Groq на март 2026
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

# Константы
MAX_CHATS = bot_settings["max_chats"]
MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
MAX_WARNINGS = bot_settings["max_warnings"]
MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]

# Список ключевых слов для 18+ контента (можно расширять)
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
            "model": bot_settings["default_model"],
            "mode": bot_settings["default_mode"],
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
                "cooldown": DEFAULT_COOLDOWN,
                "is_owner": False
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
        return False, "Бот временно приостановлен. Попробуйте позже."
    
    if user_id in banned_users or (user_id in user_data and user_data[user_id].get("is_banned", False)):
        return False, "Вы забанены в боте. Обратитесь к администратору."
    
    if user_id not in user_limits:
        return True, "OK"
    
    limits = user_limits[user_id]
    now = time.time()
    
    # Очищаем старые запросы
    if user_id in user_requests:
        user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 86400]  # 24 часа
    
    # Проверяем cooldown
    if user_requests[user_id] and now - user_requests[user_id][-1] < limits["cooldown"]:
        wait_time = int(limits["cooldown"] - (now - user_requests[user_id][-1]))
        return False, f"Подождите {wait_time} сек между запросами"
    
    # Проверяем лимит в минуту
    minute_ago = now - 60
    minute_requests = len([t for t in user_requests[user_id] if t > minute_ago])
    if minute_requests >= limits["requests_per_minute"]:
        return False, f"Лимит {limits['requests_per_minute']} запросов в минуту"
    
    # Проверяем лимит в час
    hour_ago = now - 3600
    hour_requests = len([t for t in user_requests[user_id] if t > hour_ago])
    if hour_requests >= limits["requests_per_hour"]:
        return False, f"Лимит {limits['requests_per_hour']} запросов в час"
    
    # Проверяем лимит в день
    day_ago = now - 86400
    day_requests = len([t for t in user_requests[user_id] if t > day_ago])
    if day_requests >= limits["requests_per_day"]:
        return False, f"Лимит {limits['requests_per_day']} запросов в день"
    
    return True, "OK"

def can_call_api(user_id):
    """Проверка, можно ли вызвать API (для панели действий)"""
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
        if user_data[user_id]["first_seen"]:
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
        # Проверяем лимит постоянных чатов
        permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
        if len(permanent_chats) >= MAX_CHATS:
            return None, "Достигнут лимит чатов. Нужно удалить старый."
        
        user_data[user_id]["chats"].append(new_chat)
        user_data[user_id]["current_chat"] = new_chat
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "permanent"
    
    return chat_id, None

def switch_chat(user_id, chat_id):
    """Переключение на другой чат"""
    if user_id not in user_data:
        return False
    
    # Проверяем временный чат
    if user_data[user_id]["temp_chat"] and user_data[user_id]["temp_chat"]["id"] == chat_id:
        user_data[user_id]["current_chat"] = user_data[user_id]["temp_chat"]
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "temporary"
        return True
    
    # Проверяем постоянные чаты
    for chat in user_data[user_id]["chats"]:
        if chat["id"] == chat_id:
            user_data[user_id]["current_chat"] = chat
            user_data[user_id]["current_chat_id"] = chat_id
            user_data[user_id]["chat_type"] = "permanent" if not chat.get("is_temporary") else "temporary"
            
            # Обновляем настройки под чат
            user_data[user_id]["model"] = chat.get("model", bot_settings["default_model"])
            user_data[user_id]["mode"] = chat.get("mode", bot_settings["default_mode"])
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
    
    # Проверяем лимит
    if len(saved_messages[user_id]) >= user_data[user_id]["saved_messages_limit"]:
        # Удаляем самое старое сообщение
        saved_messages[user_id].pop(0)
    
    # Добавляем новое сообщение
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

def set_user_limits(user_id, limits_dict):
    """Установить лимиты для пользователя"""
    if user_id in user_limits:
        user_limits[user_id].update(limits_dict)
        return True
    return False

def update_groq_api_key(new_api_key):
    """Обновление глобального API ключа Groq"""
    global GROQ_API_KEY, groq_client
    GROQ_API_KEY = new_api_key
    
    # Полностью пересоздаем клиент с новым ключом
    try:
        # Создаем новый клиент
        new_client = Groq(api_key=new_api_key, timeout=30.0)
        
        # Проверяем работоспособность ключа
        test_response = new_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        
        # Если всё хорошо, заменяем глобальный клиент
        groq_client = new_client
        logger.info(f"API ключ успешно обновлен: {new_api_key[:10]}...")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении API ключа: {e}")
        return False

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
        if "warnings" not in user_data[user_id]:
            user_data[user_id]["warnings"] = 0
        user_data[user_id]["warnings"] += 1
        
        # Если превышен лимит предупреждений - баним
        if user_data[user_id]["warnings"] >= MAX_WARNINGS:
            ban_user(user_id, f"Превышен лимит предупреждений ({MAX_WARNINGS})")
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
    global bot_settings
    
    bot_settings.update(new_settings)
    
    # Обновляем константы
    global MAX_CHATS, MAX_SAVED_MESSAGES, DEFAULT_REQUESTS_PER_MINUTE
    global DEFAULT_REQUESTS_PER_HOUR, DEFAULT_REQUESTS_PER_DAY, DEFAULT_COOLDOWN
    global MAX_WARNINGS, MAX_ADULT_ATTEMPTS, API_CALL_COOLDOWN
    
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
    global OWNER_CHAT_ID
    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"⚠️ **Уведомление владельцу**\n\n{message}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление владельцу: {e}")

async def send_to_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить сообщение владельцу"""
    user_id = update.effective_user.id
    global OWNER_CHAT_ID
    
    # Если это первый контакт с владельцем, запоминаем его ID
    if not OWNER_CHAT_ID:
        OWNER_CHAT_ID = user_id
        logger.info(f"Владелец определен: ID {OWNER_CHAT_ID}")
        
        # Даем права владельца
        if user_id in user_limits:
            user_limits[user_id]["is_owner"] = True
        
        await update.message.reply_text(
            "✅ **Вы назначены владельцем бота!**\n\n"
            "Теперь вам доступна панель владельца в главном меню.",
            parse_mode='Markdown'
        )
        return
    
    # Если это не владелец, отправляем ему сообщение
    if user_id != OWNER_CHAT_ID:
        awaiting_input[user_id] = {"action": "message_to_owner"}
        await update.message.reply_text(
            "📝 **Напишите сообщение для владельца бота**\n\n"
            "Он получит его и сможет ответить вам.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
            ]]),
            parse_mode='Markdown'
        )
    else:
        # Если это владелец, показываем меню ответа
        await update.message.reply_text(
            "👑 **Вы владелец бота**\n\n"
            "Используйте панель владельца для управления.",
            reply_markup=get_main_keyboard(user_id)
        )

def get_main_keyboard(user_id):
    """Главная inline-клавиатура"""
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
    
    # Добавляем кнопку для владельца
    if user_limits.get(user_id, {}).get("is_owner", False):
        keyboard.append([InlineKeyboardButton("👑 Панель владельца", callback_data="owner_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def get_dialog_navigation_keyboard(user_id):
    """Клавиатура для навигации в диалоге"""
    keyboard = [
        [InlineKeyboardButton("📋 Управление чатами", callback_data="show_chats_from_dialog")],
        [InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_keyboard():
    """Reply-клавиатура с кнопками действий (появляется только при вызове API)"""
    keyboard = [
        [KeyboardButton("👤 СОХРАНИТЬ МОЁ"), KeyboardButton("🤖 СОХРАНИТЬ БОТА")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_back_to_menu_keyboard():
    """Клавиатура с кнопкой возврата в главное меню"""
    keyboard = [
        [InlineKeyboardButton("◀️ Вернуться в главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def delete_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Удаление предыдущего меню пользователя"""
    if user_id in menu_messages:
        try:
            await context.bot.delete_message(
                chat_id=user_id,
                message_id=menu_messages[user_id]
            )
        except Exception as e:
            logger.debug(f"Не удалось удалить меню: {e}")
        # Удаляем из словаря даже если не удалось удалить (сообщение могло быть уже удалено)
        if user_id in menu_messages:
            del menu_messages[user_id]

async def delete_dialog_messages(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Удаление всех сообщений в текущем диалоге"""
    if user_id in dialog_messages:
        for message_id in dialog_messages[user_id]:
            try:
                await context.bot.delete_message(
                    chat_id=user_id,
                    message_id=message_id
                )
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение {message_id}: {e}")
        dialog_messages[user_id] = []

async def post_init(application: Application):
    """Действия после инициализации бота"""
    try:
        # Устанавливаем только одну команду - /start
        commands = [
            BotCommand("start", "Запустить бота"),
        ]
        await application.bot.set_my_commands(commands)
        
        logger.info("Бот успешно запущен!")
        logger.info(f"Версия Python: {sys.version.split()[0]}")
        current_time = datetime.now()
        logger.info(f"Время запуска: {current_time}")
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
    # Всегда удаляем старое меню при старте
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["username"] = username
        # Создаем первый чат при старте
        create_chat(user_id, "Основной чат", is_temporary=False)
        
        # Если это владелец (первый запуск), отмечаем его
        global OWNER_CHAT_ID
        if not OWNER_CHAT_ID:
            OWNER_CHAT_ID = user_id
            user_limits[user_id]["is_owner"] = True
            logger.info(f"Владелец определен: ID {OWNER_CHAT_ID}")
    
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
    """Обработчик текстовых сообщений (не команд)"""
    global error_count, last_error_time, error_users, OWNER_CHAT_ID
    
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Сохраняем ID сообщения пользователя
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    dialog_messages[user_id].append(update.message.message_id)
    
    # Проверяем, не является ли сообщение командой из Reply-клавиатуры
    if user_message == "👤 СОХРАНИТЬ МОЁ":
        if last_message_text[user_id]["user"]:
            save_message(user_id, last_message_text[user_id]["user"], "user")
            await update.message.reply_text("✅ Ваше последнее сообщение сохранено!")
        else:
            await update.message.reply_text("❌ Нет вашего сообщения для сохранения")
        return
    
    if user_message == "🤖 СОХРАНИТЬ БОТА":
        if last_message_text[user_id]["bot"]:
            save_message(user_id, last_message_text[user_id]["bot"], "bot")
            await update.message.reply_text("✅ Последнее сообщение бота сохранено!")
        else:
            await update.message.reply_text("❌ Нет сообщения бота для сохранения")
        return
    
    # Проверяем, не ожидаем ли мы ввод
    if user_id in awaiting_input:
        action_data = awaiting_input[user_id]
        
        if action_data.get("action") == "new_chat_name":
            del awaiting_input[user_id]
            
            chat_type = action_data.get("chat_type")
            
            if chat_type == "permanent":
                # Проверяем лимит
                permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
                if len(permanent_chats) >= MAX_CHATS:
                    # Предлагаем удалить старый чат
                    keyboard = [
                        [InlineKeyboardButton("🗑 Удалить самый старый чат", callback_data="delete_oldest_and_create")],
                        [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                    ]
                    await update.message.reply_text(
                        f"❌ Достигнут лимит постоянных чатов ({MAX_CHATS}).\n\n"
                        f"Хотите удалить самый старый чат и создать новый?",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
                
                chat_id, error = create_chat(user_id, user_message[:50], is_temporary=False)
                if chat_id:
                    await update.message.reply_text(
                        f"✅ Постоянный чат '{user_message[:50]}' создан!",
                        reply_markup=get_main_keyboard(user_id)
                    )
                else:
                    await update.message.reply_text(f"❌ {error}")
            
            elif chat_type == "temporary":
                if user_data[user_id]["temp_chat"]:
                    # Спрашиваем, заменить ли временный чат
                    keyboard = [
                        [InlineKeyboardButton("✅ Заменить", callback_data="replace_temp_chat")],
                        [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                    ]
                    await update.message.reply_text(
                        "У вас уже есть временный чат. Заменить его?",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    awaiting_input[user_id] = {"action": "confirm_replace_temp", "name": user_message[:50]}
                else:
                    chat_id, error = create_chat(user_id, user_message[:50], is_temporary=True)
                    if chat_id:
                        await update.message.reply_text(
                            f"✅ Временный чат '{user_message[:50]}' создан!",
                            reply_markup=get_main_keyboard(user_id)
                        )
            
            return
        
        elif action_data.get("action") == "message_to_owner":
            del awaiting_input[user_id]
            if OWNER_CHAT_ID:
                try:
                    # Отправляем сообщение владельцу
                    user_info = f"От: {update.effective_user.first_name}"
                    if update.effective_user.username:
                        user_info += f" (@{update.effective_user.username})"
                    user_info += f"\nID: `{user_id}`"
                    
                    await context.bot.send_message(
                        chat_id=OWNER_CHAT_ID,
                        text=f"📨 **Сообщение от пользователя**\n\n{user_info}\n\n**Текст:**\n{user_message}",
                        parse_mode='Markdown'
                    )
                    
                    await update.message.reply_text(
                        "✅ **Сообщение отправлено владельцу!**\n\nОн ответит вам, как только сможет.",
                        reply_markup=get_main_keyboard(user_id)
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения владельцу: {e}")
                    await update.message.reply_text(
                        "❌ Не удалось отправить сообщение. Попробуйте позже.",
                        reply_markup=get_main_keyboard(user_id)
                    )
            return
        
        elif action_data.get("action") == "set_limit":
            del awaiting_input[user_id]
            try:
                limit = int(user_message)
                if 1 <= limit <= 100:
                    user_data[user_id]["saved_messages_limit"] = limit
                    await update.message.reply_text(
                        f"✅ Лимит сохраненных сообщений установлен: {limit}",
                        reply_markup=get_main_keyboard(user_id)
                    )
                else:
                    await update.message.reply_text("❌ Лимит должен быть от 1 до 100")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
            return
        
        elif action_data.get("action") == "set_custom_note":
            del awaiting_input[user_id]
            user_custom_notes[user_id] = user_message
            user_data[user_id]["custom_note"] = user_message
            
            # Обновляем system prompt в текущем чате
            if user_data[user_id]["current_chat"]:
                custom_note = user_custom_notes.get(user_id, "")
                system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
                user_data[user_id]["current_chat"]["messages"][0]["content"] = system_prompt
            
            await update.message.reply_text(
                f"✅ Ваша приписка сохранена!\n\nТеперь бот будет учитывать: {user_message}",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        elif action_data.get("action") == "set_cooldown" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                cooldown = int(user_message)
                if cooldown >= 0:
                    # Применяем ко всем пользователям
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
            await update.message.reply_text(
                f"✅ Приветственное сообщение обновлено!",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        elif action_data.get("action") == "new_api_key" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            new_key = user_message.strip()
            if new_key.startswith("gsk_") and len(new_key) > 30:
                if update_groq_api_key(new_key):
                    await update.message.reply_text(
                        "✅ **API ключ успешно обновлен!**\n\nНовый ключ активирован для всех пользователей.",
                        reply_markup=get_main_keyboard(user_id)
                    )
                    # Уведомляем владельца
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
    
    # Всегда удаляем старое меню при новом сообщении
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
        create_chat(user_id, "Основной чат", is_temporary=False)
    
    # Проверяем, есть ли активный чат
    if not user_data[user_id]["current_chat"]:
        # Если нет активного чата, создаем временный
        create_chat(user_id, "Временный чат", is_temporary=True)
    
    # Проверка на спам
    current_time = time.time()
    if user_id in user_last_message and current_time - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = current_time
    
    # Проверяем лимиты запросов
    allowed, message = check_request_limits(user_id)
    if not allowed:
        error_msg = await update.message.reply_text(f"⏱️ {message}\n\n❓ Хотите выйти из чата?", 
                                                   reply_markup=InlineKeyboardMarkup([[
                                                       InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
                                                   ]]))
        dialog_messages[user_id].append(error_msg.message_id)
        return
    
    # Проверяем на 18+ контент
    if check_adult_content(user_message):
        # Увеличиваем счетчик попыток
        user_data[user_id]["adult_attempts"] = user_data[user_id].get("adult_attempts", 0) + 1
        adult_attempts = user_data[user_id]["adult_attempts"]
        
        # Если превышен лимит попыток - выдаем предупреждение
        if adult_attempts >= MAX_ADULT_ATTEMPTS:
            result, status = warn_user(user_id, "Попытка получить 18+ контент")
            if status == "user_banned":
                await update.message.reply_text(
                    "❌ **Вы забанены за многократные попытки получить 18+ контент!**\n\n"
                    "Обратитесь к администратору для разблокировки.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📨 Связаться с владельцем", callback_data="contact_owner")
                    ]])
                )
                return
            else:
                warnings_left = MAX_WARNINGS - user_data[user_id].get("warnings", 0)
                warning_msg = await update.message.reply_text(
                    f"⚠️ **Предупреждение {user_data[user_id].get('warnings', 0)}/{MAX_WARNINGS}**\n\n"
                    f"Ваш запрос содержит потенциально неприемлемый контент.\n"
                    f"Осталось предупреждений до бана: {warnings_left}\n\n"
                    f"❓ Хотите выйти из чата?",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
                    ]])
                )
                dialog_messages[user_id].append(warning_msg.message_id)
                return
        
        # Отправляем стандартный отказ
        reject_msg = await update.message.reply_text(
            "❌ **Запрос отклонен**\n\n"
            "Бот не отвечает на запросы, содержащие 18+ контент, порнографию, насилие или другие неприемлемые темы.\n\n"
            f"Попытка {adult_attempts}/{MAX_ADULT_ATTEMPTS} (до предупреждения)\n\n"
            f"❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
            ]])
        )
        dialog_messages[user_id].append(reject_msg.message_id)
        return
    
    user_data[user_id]["in_dialog"] = True
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Проверяем, инициализирован ли groq_client
        if groq_client is None:
            error_msg = await update.message.reply_text(
                "❌ **Ошибка API**\n\n"
                "API клиент не инициализирован. Администратор уже уведомлен.\n\n"
                "❓ Хотите выйти из чата?",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
                ]]),
                parse_mode='Markdown'
            )
            dialog_messages[user_id].append(error_msg.message_id)
            return
            
        current_chat = user_data[user_id]["current_chat"]
        history = current_chat["messages"]
        history.append({"role": "user", "content": user_message})
        
        user_data[user_id]["total_messages"] = user_data[user_id].get("total_messages", 0) + 1
        
        # Сохраняем сообщение пользователя
        last_message_text[user_id]["user"] = user_message
        
        if len(history) > 51:
            history[:] = [history[0]] + history[-50:]
        
        # Записываем запрос
        record_request(user_id)
        
        # Проверяем, можно ли вызвать API
        if not can_call_api(user_id):
            cooldown_msg = await update.message.reply_text(
                "⏱️ Слишком частые запросы к API. Подождите немного.\n\n❓ Хотите выйти из чата?",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
                ]])
            )
            dialog_messages[user_id].append(cooldown_msg.message_id)
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
        
        assistant_message = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_message})
        
        # Сохраняем сообщение бота
        last_message_text[user_id]["bot"] = assistant_message
        
        # Отправляем ответ с кнопкой навигации
        sent_message = await update.message.reply_text(
            assistant_message,
            reply_markup=get_dialog_navigation_keyboard(user_id)
        )
        
        # Сохраняем ID сообщения бота
        dialog_messages[user_id].append(sent_message.message_id)
        
        # Показываем клавиатуру с действиями (только после вызова API)
        action_message = await context.bot.send_message(
            chat_id=user_id,
            text="Действия с сообщениями:",
            reply_markup=get_action_keyboard()
        )
        dialog_messages[user_id].append(action_message.message_id)
        
        # Сохраняем ID последнего сообщения для навигации
        user_data[user_id]["last_message_id"] = sent_message.message_id
            
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от пользователя {user_id}: {e}")
        
        # Увеличиваем счетчик ошибок
        error_count += 1
        last_error_time = time.time()
        error_users.add(user_id)
        
        # Отправляем уведомление владельцу
        if OWNER_CHAT_ID and len(error_users) >= 3:  # Если ошибки у 3+ пользователей
            error_message = (
                f"⚠️ **Массовая ошибка API**\n\n"
                f"• Количество ошибок: {error_count}\n"
                f"• Затронуто пользователей: {len(error_users)}\n"
                f"• Последняя ошибка: {str(e)[:100]}\n\n"
                f"Возможно, требуется обновить API ключ."
            )
            await notify_owner(context, error_message)
            error_users.clear()  # Очищаем после уведомления
        
        error_message = "❌ Ошибка при получении ответа от API. "
        
        if "timeout" in str(e).lower():
            error_message += "Превышено время ожидания."
        elif "connection" in str(e).lower():
            error_message += "Проблема с подключением."
        elif "api_key" in str(e).lower() or "authentication" in str(e).lower():
            error_message += "Проблема с API ключом. Администратор уже уведомлен."
        elif groq_client is None:
            error_message += "API клиент не инициализирован."
        else:
            error_message += "Попробуйте позже."
        
        error_msg = await update.message.reply_text(
            f"{error_message}\n\n❓ Хотите выйти из чата?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
            ]])
        )
        dialog_messages[user_id].append(error_msg.message_id)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографий"""
    user_id = update.effective_user.id
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
    
    msg = await update.message.reply_text(
        "📸 **Бот не умеет анализировать фото**\n\n"
        "Я работаю только с текстом. Отправь текстовое сообщение.\n\n"
        "❓ Хотите выйти из чата?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")
        ]]),
        parse_mode='Markdown'
    )
    
    if user_id in dialog_messages:
        dialog_messages[user_id].append(msg.message_id)

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение диалога"""
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    # Всегда удаляем старое меню
    await delete_menu(user_id, context)
    
    # Сначала удаляем все сообщения в диалоге
    await delete_dialog_messages(user_id, context)
    
    if user_id in user_data:
        current_chat = user_data[user_id]["current_chat"]
        
        # Если это временный чат - удаляем
        if current_chat and current_chat.get("is_temporary"):
            user_data[user_id]["temp_chat"] = None
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
            user_data[user_id]["showing_action_buttons"] = False
        else:
            user_data[user_id]["in_dialog"] = False
            user_data[user_id]["showing_action_buttons"] = False
    
    # Возвращаем главное меню (всегда показываем, даже если бот не работает)
    current_chat_name = user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'
    welcome_text = bot_settings["welcome_message"].format(
        name=first_name,
        chat=current_chat_name
    )
    
    # Если бот приостановлен, добавляем предупреждение
    if bot_paused:
        welcome_text = f"⏸️ **Бот временно приостановлен**\n\nПричина: {pause_reason}\n\n{welcome_text}"
    
    # Проверяем, откуда пришел вызов
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                welcome_text,
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
            )
            menu_messages[user_id] = update.callback_query.message.message_id
        except Exception as e:
            # Если не удалось отредактировать, отправляем новое сообщение
            msg = await context.bot.send_message(
                chat_id=user_id,
                text=welcome_text,
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
            )
            menu_messages[user_id] = msg.message_id
    else:
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=welcome_text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = msg.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
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
        
        if query.data == "ignore":
            return
        
        # Кнопка связи с владельцем
        if query.data == "contact_owner":
            awaiting_input[user_id] = {"action": "message_to_owner"}
            await query.edit_message_text(
                "📝 **Напишите сообщение для владельца бота**\n\n"
                "Он получит его и сможет ответить вам.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Обработка навигационных кнопок
        if query.data == "back_to_main":
            current_chat_name = user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'
            welcome_text = bot_settings["welcome_message"].format(
                name=first_name,
                chat=current_chat_name
            )
            
            # Если бот приостановлен, добавляем предупреждение
            if bot_paused:
                welcome_text = f"⏸️ **Бот временно приостановлен**\n\nПричина: {pause_reason}\n\n{welcome_text}"
            
            await query.edit_message_text(
                welcome_text,
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
            )
            menu_messages[user_id] = query.message.message_id
            return
        
        # Возврат в диалог
        if query.data == "back_to_dialog":
            last_msg_id = user_data[user_id].get("last_message_id")
            if last_msg_id:
                # Пытаемся перейти к последнему сообщению в диалоге
                await query.edit_message_text(
                    "🔄 **Возврат в диалог**\n\nПродолжай общение!",
                    reply_markup=None,
                    parse_mode='Markdown'
                )
                # Отправляем новое сообщение для продолжения диалога
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Ты вернулся в диалог. Можешь продолжать писать сообщения.",
                    reply_markup=get_dialog_navigation_keyboard(user_id)
                )
            else:
                await query.edit_message_text(
                    "❌ **Не найден активный диалог**",
                    reply_markup=get_main_keyboard(user_id)
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
        
        # Информация
        if query.data == "show_info":
            uptime_seconds = int(time.time() - bot_start_time)
            uptime_string = str(timedelta(seconds=uptime_seconds))
            
            current_time = datetime.now()
            march_2026_limits = GROQ_LIMITS["free_tier"] if current_time < datetime(2026, 4, 1) else GROQ_LIMITS["paid_tier"]
            
            # Статистика по пользователям
            total_users = len(user_data)
            active_users = sum(1 for data in user_data.values() if data.get("in_dialog", False))
            total_requests = global_request_count
            banned_count = len(banned_users)
            
            pause_status = "⏸️ **Приостановлен**" if bot_paused else "▶️ **Активен**"
            
            # Формируем информацию о доступных функциях
            features_text = ""
            if bot_settings["enable_18_plus_filter"]:
                features_text += "• 🔞 Фильтр 18+ контента\n"
            if bot_settings["enable_user_notes"]:
                features_text += "• 📝 Пользовательские приписки\n"
            if bot_settings["enable_activity_tracking"]:
                features_text += "• 📊 Отслеживание активности\n"
            
            text = (
                f"ℹ️ **Информация о боте**\n\n"
                f"📅 **Текущая дата:** {current_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏱ **Аптайм:** {uptime_string}\n"
                f"{pause_status}\n\n"
                
                f"📊 **Статистика использования:**\n"
                f"• Всего пользователей: {total_users}\n"
                f"• Активных диалогов: {active_users}\n"
                f"• Забанено: {banned_count}\n"
                f"• Всего запросов: {total_requests}\n\n"
                
                f"🚀 **Лимиты Groq API (Март 2026):**\n"
                f"• Запросов в минуту: {march_2026_limits['requests_per_minute']}\n"
                f"• Запросов в час: {march_2026_limits['requests_per_hour']}\n"
                f"• Запросов в день: {march_2026_limits['requests_per_day']}\n"
                f"• Токенов в минуту: {march_2026_limits['tokens_per_minute']}\n"
                f"• Макс. токенов/запрос: {march_2026_limits['max_tokens_per_request']}\n"
                f"• Одновременных запросов: {march_2026_limits['concurrent_requests']}\n\n"
                
                f"⚙️ **Текущие лимиты бота:**\n"
                f"• Сохраняемых сообщений: {user_data[user_id]['saved_messages_limit']}\n"
                f"• Постоянных чатов: {len([c for c in user_data[user_id]['chats'] if not c.get('is_temporary')])}/{MAX_CHATS}\n\n"
                
                f"🔧 **Доступные функции:**\n"
                f"{features_text}\n"
                f"🔞 **Политика контента:**\n"
                f"• Фильтр 18+ контента: {'активен' if bot_settings['enable_18_plus_filter'] else 'отключен'}\n"
                f"• Макс. предупреждений: {MAX_WARNINGS}\n\n"
                
                f"📨 **Связь с владельцем:**\n"
                f"Нажмите кнопку ниже, чтобы отправить сообщение"
            )
            
            keyboard = [
                [InlineKeyboardButton("📨 Написать владельцу", callback_data="contact_owner")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Настройки пользователя
        if query.data == "show_settings":
            saved_count = len(saved_messages.get(user_id, []))
            saved_limit = user_data[user_id]["saved_messages_limit"]
            warnings = user_data[user_id].get("warnings", 0)
            adult_attempts = user_data[user_id].get("adult_attempts", 0)
            custom_note = user_custom_notes.get(user_id, "Не установлена")
            
            text = (
                f"⚙️ **Настройки пользователя**\n\n"
                f"📊 **Ваши данные:**\n"
                f"• Сохранено сообщений: {saved_count}/{saved_limit}\n"
                f"• Всего сообщений: {user_data[user_id].get('total_messages', 0)}\n"
                f"• Предупреждений: {warnings}/{MAX_WARNINGS}\n"
                f"• Попыток 18+ запросов: {adult_attempts}\n\n"
                
                f"📝 **Ваша приписка к запросам:**\n"
                f"«{custom_note}»\n\n"
                
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
        
        # Установка лимита сохранения
        if query.data == "set_limit":
            awaiting_input[user_id] = {"action": "set_limit"}
            await query.edit_message_text(
                "🔢 **Введите новый лимит сохраненных сообщений** (от 1 до 100):",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Установка пользовательской приписки
        if query.data == "set_custom_note":
            awaiting_input[user_id] = {"action": "set_custom_note"}
            await query.edit_message_text(
                "📝 **Введите вашу приписку к запросам**\n\n"
                "Эта приписка будет добавляться к каждому вашему запросу. "
                "Например, вы можете попросить бота отвечать кратко, использовать определенный стиль и т.д.\n\n"
                "Введите текст:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Панель владельца
        if query.data == "owner_panel" and user_limits.get(user_id, {}).get("is_owner"):
            total_requests_today = len([t for t in sum(user_requests.values(), []) if time.time() - t < 86400])
            active_users_now = len([uid for uid, times in user_requests.items() if times and time.time() - times[-1] < 300])
            banned_count = len(banned_users)
            
            pause_status = "⏸️ **Приостановлен**" if bot_paused else "▶️ **Активен**"
            
            text = (
                f"👑 **Панель владельца**\n\n"
                
                f"📊 **Глобальная статистика:**\n"
                f"• Всего пользователей: {len(user_data)}\n"
                f"• Активных сейчас: {active_users_now}\n"
                f"• Запросов сегодня: {total_requests_today}\n"
                f"• Всего запросов: {global_request_count}\n"
                f"• Ошибок API: {error_count}\n"
                f"• Забанено пользователей: {banned_count}\n"
                f"• Статус бота: {pause_status}\n\n"
                
                f"🔞 **18+ статистика:**\n"
                f"• Всего попыток: {sum(data.get('adult_attempts', 0) for data in user_data.values())}\n"
                f"• Нарушителей: {len([uid for uid, data in user_data.items() if data.get('adult_attempts', 0) > 0])}\n\n"
                
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
        
        # Глобальные настройки
        if query.data == "owner_global_settings" and user_limits.get(user_id, {}).get("is_owner"):
            text = (
                f"⚙️ **Глобальные настройки бота**\n\n"
                f"**Текущие значения:**\n"
                f"• Макс. чатов: {bot_settings['max_chats']}\n"
                f"• Макс. сохранений: {bot_settings['max_saved_messages']}\n"
                f"• Cooldown: {bot_settings['default_cooldown']} сек\n"
                f"• Запросов/мин: {bot_settings['default_requests_per_minute']}\n"
                f"• Запросов/час: {bot_settings['default_requests_per_hour']}\n"
                f"• Запросов/день: {bot_settings['default_requests_per_day']}\n"
                f"• Макс. предупреждений: {bot_settings['max_warnings']}\n"
                f"• Попыток 18+ до предупреждения: {bot_settings['max_adult_attempts']}\n\n"
                
                f"**Состояние функций:**\n"
                f"• Фильтр 18+: {'✅ Вкл' if bot_settings['enable_18_plus_filter'] else '❌ Выкл'}\n"
                f"• Заметки пользователей: {'✅ Вкл' if bot_settings['enable_user_notes'] else '❌ Выкл'}\n"
                f"• Отслеживание активности: {'✅ Вкл' if bot_settings['enable_activity_tracking'] else '❌ Выкл'}\n\n"
                
                f"**Приветственное сообщение:**\n"
                f"{bot_settings['welcome_message'][:100]}...\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("📝 Изменить макс. чатов", callback_data="owner_set_max_chats")],
                [InlineKeyboardButton("💾 Изменить макс. сохранений", callback_data="owner_set_max_saved")],
                [InlineKeyboardButton("📢 Изменить приветствие", callback_data="owner_set_welcome")],
                [InlineKeyboardButton("🔞 Переключить фильтр 18+", callback_data="owner_toggle_18_filter")],
                [InlineKeyboardButton("📝 Переключить заметки", callback_data="owner_toggle_notes")],
                [InlineKeyboardButton("📊 Переключить активность", callback_data="owner_toggle_activity")],
                [InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Установка максимального количества чатов
        if query.data == "owner_set_max_chats" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_max_chats"}
            await query.edit_message_text(
                "📝 **Введите новое максимальное количество чатов для пользователя:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_global_settings")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Установка максимального количества сохраненных сообщений
        if query.data == "owner_set_max_saved" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_max_saved"}
            await query.edit_message_text(
                "💾 **Введите новое максимальное количество сохраненных сообщений:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_global_settings")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Установка приветственного сообщения
        if query.data == "owner_set_welcome" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_welcome_message"}
            await query.edit_message_text(
                "📢 **Введите новое приветственное сообщение**\n\n"
                "Используйте {name} для имени пользователя и {chat} для названия чата.\n\n"
                "Пример: 👋 Привет, {name}! Текущий чат: {chat}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_global_settings")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Переключение фильтра 18+
        if query.data == "owner_toggle_18_filter" and user_limits.get(user_id, {}).get("is_owner"):
            bot_settings["enable_18_plus_filter"] = not bot_settings["enable_18_plus_filter"]
            status = "включен" if bot_settings["enable_18_plus_filter"] else "отключен"
            await query.answer(f"✅ Фильтр 18+ {status}")
            
            # Обновляем сообщение
            await button_handler(update, context)  # Возвращаемся в меню глобальных настроек
            return
        
        # Переключение заметок пользователей
        if query.data == "owner_toggle_notes" and user_limits.get(user_id, {}).get("is_owner"):
            bot_settings["enable_user_notes"] = not bot_settings["enable_user_notes"]
            status = "включены" if bot_settings["enable_user_notes"] else "отключены"
            await query.answer(f"✅ Заметки пользователей {status}")
            
            # Обновляем сообщение
            await button_handler(update, context)  # Возвращаемся в меню глобальных настроек
            return
        
        # Переключение отслеживания активности
        if query.data == "owner_toggle_activity" and user_limits.get(user_id, {}).get("is_owner"):
            bot_settings["enable_activity_tracking"] = not bot_settings["enable_activity_tracking"]
            status = "включено" if bot_settings["enable_activity_tracking"] else "отключено"
            await query.answer(f"✅ Отслеживание активности {status}")
            
            # Обновляем сообщение
            await button_handler(update, context)  # Возвращаемся в меню глобальных настроек
            return
        
        # Меню паузы
        if query.data == "owner_pause_menu" and user_limits.get(user_id, {}).get("is_owner"):
            text = "⏸️ **Управление паузой бота**\n\n"
            
            if bot_paused:
                text += f"Бот **приостановлен**.\nПричина: {pause_reason}\n\n"
            else:
                text += "Бот **активен**.\n\n"
            
            keyboard = []
            if bot_paused:
                keyboard.append([InlineKeyboardButton("▶️ Возобновить работу", callback_data="owner_resume_bot")])
            else:
                keyboard.append([InlineKeyboardButton("⏸️ Приостановить бота", callback_data="owner_pause_bot")])
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Приостановка бота
        if query.data == "owner_pause_bot" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "pause_reason"}
            await query.edit_message_text(
                "⏸️ **Введите причину приостановки бота:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_pause_menu")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Возобновление бота
        if query.data == "owner_resume_bot" and user_limits.get(user_id, {}).get("is_owner"):
            set_bot_pause(False)
            await query.edit_message_text(
                "✅ **Бот возобновил работу!**",
                reply_markup=get_main_keyboard(user_id)
            )
            await notify_owner(context, "Бот возобновил работу")
            return
        
        # Меню банов
        if query.data == "owner_ban_menu" and user_limits.get(user_id, {}).get("is_owner"):
            text = "🔨 **Управление банами**\n\n"
            
            if banned_users:
                text += "**Забаненные пользователи:**\n"
                for uid in list(banned_users)[:10]:
                    username = user_data.get(uid, {}).get("username", "Неизвестно")
                    reason = user_data.get(uid, {}).get("ban_reason", "Не указана")
                    text += f"• ID: `{uid}` (@{username}) - {reason}\n"
            else:
                text += "Нет забаненных пользователей.\n"
            
            keyboard = [
                [InlineKeyboardButton("🔨 Забанить пользователя", callback_data="owner_ban_user")],
                [InlineKeyboardButton("🔓 Разбанить пользователя", callback_data="owner_unban_user")],
                [InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Забанить пользователя
        if query.data == "owner_ban_user" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "ban_user"}
            await query.edit_message_text(
                "🔨 **Введите ID пользователя для бана:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_ban_menu")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Разбанить пользователя
        if query.data == "owner_unban_user" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "unban_user"}
            await query.edit_message_text(
                "🔓 **Введите ID пользователя для разбана:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_ban_menu")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Просмотр активности
        if query.data == "owner_activity" and user_limits.get(user_id, {}).get("is_owner"):
            now = time.time()
            day_ago = now - 86400
            week_ago = now - 604800
            month_ago = now - 2592000
            
            active_day = len([uid for uid, times in user_requests.items() if times and any(t > day_ago for t in times)])
            active_week = len([uid for uid, times in user_requests.items() if times and any(t > week_ago for t in times)])
            active_month = len([uid for uid, times in user_requests.items() if times and any(t > month_ago for t in times)])
            
            text = (
                f"📊 **Активность пользователей**\n\n"
                f"**Общая статистика:**\n"
                f"• Активных за день: {active_day}\n"
                f"• Активных за неделю: {active_week}\n"
                f"• Активных за месяц: {active_month}\n\n"
                
                f"**Топ-5 нарушителей 18+:**\n"
            )
            
            adult_offenders = [(uid, data.get("adult_attempts", 0)) for uid, data in user_data.items() if data.get("adult_attempts", 0) > 0]
            for uid, attempts in sorted(adult_offenders, key=lambda x: x[1], reverse=True)[:5]:
                username = user_data.get(uid, {}).get("username", "Неизвестно")
                text += f"• ID: `{uid}` (@{username}) - {attempts} попыток\n"
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="owner_panel")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Смена API ключа (только для владельца)
        if query.data == "owner_change_api" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "new_api_key"}
            await query.edit_message_text(
                "🔑 **Введите новый API ключ Groq**\n\n"
                "Ключ должен начинаться с 'gsk_' и быть длиннее 30 символов.\n"
                "После замены ключ будет использоваться для всех пользователей.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Установка cooldown (только для владельца)
        if query.data == "owner_set_cooldown" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_cooldown"}
            await query.edit_message_text(
                "⏱️ **Введите cooldown в секундах** для всех пользователей:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Установка лимита запросов в минуту (только для владельца)
        if query.data == "owner_set_rpm" and user_limits.get(user_id, {}).get("is_owner"):
            awaiting_input[user_id] = {"action": "set_requests_per_minute"}
            await query.edit_message_text(
                "📊 **Введите лимит запросов в минуту** для всех пользователей:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="owner_panel")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Показ списка чатов
        if query.data == "show_chats":
            await show_chats_interface(update, context, user_id, from_dialog=False)
            return
        
        # Просмотр чата
        if query.data.startswith("view_chat_"):
            chat_id = query.data.replace("view_chat_", "")
            if switch_chat(user_id, chat_id):
                chat = user_data[user_id]["current_chat"]
                messages = [m for m in chat["messages"] if m["role"] != "system"]
                
                if messages:
                    text = f"📜 **История чата: {chat['name']}**\n\n"
                    for i, msg in enumerate(messages[-10:]):
                        role_emoji = "👤" if msg["role"] == "user" else "🤖"
                        text += f"**{i+1}.** {role_emoji} {msg['content'][:100]}\n\n"
                else:
                    text = f"📭 **История чата: {chat['name']}**\n\nНет сообщений."
                
                keyboard = [[InlineKeyboardButton("◀️ Назад к чатам", callback_data="show_chats")]]
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            return
        
        # Создание постоянного чата
        if query.data == "new_permanent_chat":
            permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
            if len(permanent_chats) >= MAX_CHATS:
                keyboard = [
                    [InlineKeyboardButton("🗑 Удалить самый старый", callback_data="delete_oldest_and_create")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                await query.edit_message_text(
                    f"❌ Достигнут лимит постоянных чатов ({MAX_CHATS}).\n\n"
                    f"Удалить самый старый чат и создать новый?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
            await query.edit_message_text(
                "📝 **Введите название для нового постоянного чата:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Создание временного чата
        if query.data == "new_temp_chat":
            if user_data[user_id]["temp_chat"]:
                keyboard = [
                    [InlineKeyboardButton("✅ Да, заменить", callback_data="confirm_replace_temp")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
                ]
                await query.edit_message_text(
                    "У вас уже есть временный чат. Заменить его?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "temporary"}
            await query.edit_message_text(
                "📝 **Введите название для временного чата:**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                ]]),
                parse_mode='Markdown'
            )
            return
        
        # Удаление старого чата и создание нового
        if query.data == "delete_oldest_and_create":
            if delete_oldest_chat(user_id):
                awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
                await query.edit_message_text(
                    "✅ Самый старый чат удален.\n\n📝 **Введите название для нового чата:**",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")
                    ]]),
                    parse_mode='Markdown'
                )
            return
        
        # Подтверждение замены временного чата
        if query.data == "confirm_replace_temp":
            if "name" in awaiting_input.get(user_id, {}):
                name = awaiting_input[user_id]["name"]
                del awaiting_input[user_id]
                chat_id, error = create_chat(user_id, name, is_temporary=True)
                if chat_id:
                    await query.edit_message_text(
                        f"✅ Временный чат '{name}' создан!",
                        reply_markup=get_main_keyboard(user_id)
                    )
            return
        
        # Обработка меню режимов
        if query.data == "show_modes":
            keyboard = []
            for mode_id, mode_info in MODES.items():
                mark = "✅ " if user_data[user_id]["mode"] == mode_id else ""
                keyboard.append([InlineKeyboardButton(
                    f"{mark}{mode_info['name']}",
                    callback_data=f"mode_{mode_id}"
                )])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            
            await query.edit_message_text(
                "🎭 **Выбери режим:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        elif query.data.startswith("mode_"):
            mode_id = query.data.replace("mode_", "")
            user_data[user_id]["mode"] = mode_id
            
            # Обновляем system prompt в текущем чате с учетом пользовательской приписки
            if user_data[user_id]["current_chat"]:
                custom_note = user_custom_notes.get(user_id, "")
                system_prompt = MODES[mode_id]["system_prompt"].format(custom_note=custom_note)
                user_data[user_id]["current_chat"]["messages"] = [
                    {"role": "system", "content": system_prompt}
                ]
                user_data[user_id]["current_chat"]["mode"] = mode_id
            
            await query.edit_message_text(
                f"✅ Режим изменен на {MODES[mode_id]['name']}",
                reply_markup=get_main_keyboard(user_id)
            )
            menu_messages[user_id] = query.message.message_id
            return
        
        # Обработка меню моделей
        elif query.data == "show_models":
            keyboard = []
            for name, model_id in MODELS.items():
                mark = "✅ " if user_data[user_id]["model"] == model_id else ""
                keyboard.append([InlineKeyboardButton(
                    f"{mark}{name}",
                    callback_data=f"model_{model_id}"
                )])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            
            await query.edit_message_text(
                "🚀 **Выбери модель:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        elif query.data.startswith("model_"):
            model_id = query.data.replace("model_", "")
            user_data[user_id]["model"] = model_id
            
            # Обновляем модель в текущем чате
            if user_data[user_id]["current_chat"]:
                user_data[user_id]["current_chat"]["model"] = model_id
            
            await query.edit_message_text(
                f"✅ Модель изменена на {get_model_name(model_id)}",
                reply_markup=get_main_keyboard(user_id)
            )
            menu_messages[user_id] = query.message.message_id
            return
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        try:
            # Пытаемся отправить сообщение об ошибке и вернуться в главное меню
            current_chat_name = user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'
            welcome_text = bot_settings["welcome_message"].format(
                name=first_name,
                chat=current_chat_name
            )
            
            await query.edit_message_text(
                f"❌ Произошла ошибка. Возврат в главное меню.\n\n{welcome_text}",
                reply_markup=get_main_keyboard(user_id)
            )
        except:
            pass

async def show_chats_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, from_dialog=False):
    """Показать интерфейс чатов"""
    keyboard = []
    
    # Постоянные чаты
    permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
    if permanent_chats:
        for chat in permanent_chats:
            mark = "✅ " if user_data[user_id]["current_chat_id"] == chat["id"] else ""
            msg_count = len([m for m in chat["messages"] if m["role"] != "system"])
            btn_text = f"{mark}{chat['name']} ({msg_count} сообщ.)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_chat_{chat['id']}")])
    
    # Временный чат
    if user_data[user_id]["temp_chat"]:
        temp_chat = user_data[user_id]["temp_chat"]
        mark = "✅ " if user_data[user_id]["current_chat_id"] == temp_chat["id"] else ""
        msg_count = len([m for m in temp_chat["messages"] if m["role"] != "system"])
        btn_text = f"{mark}⏳ {temp_chat['name']} ({msg_count} сообщ.)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_chat_{temp_chat['id']}")])
    
    # Кнопки создания
    action_buttons = []
    action_buttons.append(InlineKeyboardButton("➕ Постоянный", callback_data="new_permanent_chat"))
    action_buttons.append(InlineKeyboardButton("⏳ Временный", callback_data="new_temp_chat"))
    keyboard.append(action_buttons)
    
    # Кнопка возврата в диалог (если вызвано из диалога)
    if from_dialog:
        keyboard.append([InlineKeyboardButton("🔄 Вернуться в диалог", callback_data="back_to_dialog")])
    else:
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    
    text = f"📋 **Мои чаты**\n\nВсего постоянных: {len(permanent_chats)}/{MAX_CHATS}"
    
    # Проверяем, откуда пришел вызов
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
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
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка. Попробуйте позже."
            )
    except:
        pass

def main():
    """Запуск бота"""
    try:
        application = (
            ApplicationBuilder()
            .token(TELEGRAM_TOKEN)
            .post_init(post_init)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .pool_timeout(30.0)
            .build()
        )
        
        # Добавляем только обработчик команды start
        application.add_handler(CommandHandler("start", start))
        
        # Добавляем обработчик inline-кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Добавляем обработчик фотографий
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Добавляем обработчик текстовых сообщений (НЕ команд)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        application.add_error_handler(error_handler)
        
        logger.info("Бот запускается...")
        current_time = datetime.now()
        logger.info(f"Время: {current_time}")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}")
        logger.info("Перезапуск через 5 секунд...")
        time.sleep(5)
        main()

if __name__ == '__main__':
    main()
