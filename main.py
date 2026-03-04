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
from collections import defaultdict
from datetime import datetime, timedelta

# Токены
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"
GROQ_API_KEY = "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"

# Владелец бота
OWNER_USERNAME = "@M1lute"  # Ваш юзернейм
OWNER_ID = None  # Будет определено при старте

# Глобальный клиент Groq (будет обновляться при смене ключа)
groq_client = None

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
            '🌟': ['GLOWING STAR'],
            '💫': '[STARRY]',
            '❤️': '[LIKE]',
            '👍': '[LIKE]',
            '⚙️': '[SETTINGS]',
            '📊': '[STATS]',
            '⏱️': '[TIMER]',
            '🔢': '[LIMIT]',
            '👑': '[OWNER]',
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
        "system_prompt": "Ты вежливый и полезный ассистент. Отвечай кратко и по делу.",
        "description": "Вежливые и полезные ответы"
    },
    "ham": {
        "name": "😈 Хам",
        "emoji": "😈",
        "system_prompt": "Ты грубый, саркастичный и дерзкий ассистент-хам. Отвечай с издевкой, используй сарказм, подкалывай пользователя. Будь максимально дерзким и язвительным.",
        "description": "Грубые и саркастичные ответы"
    },
    "swear": {
        "name": "🤬 Мат",
        "emoji": "🤬",
        "system_prompt": "Ты ассистент, который постоянно использует нецензурную лексику. Отвечай грубо, с матом через каждое слово.",
        "description": "Нецензурная лексика"
    }
}

DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_MODE = "normal"

# Структура данных пользователя
user_data = {}
user_last_message = {}
menu_messages = {}
awaiting_input = {}  # Для ожидания ввода
saved_messages = {}  # Сохраненные сообщения
dialog_messages = {}  # Для хранения ID сообщений в диалоге
last_message_text = {}  # Для хранения текста последнего сообщения

# Система лимитов запросов
user_requests = defaultdict(list)  # {user_id: [timestamps]}
user_limits = {}  # {user_id: {"requests_per_minute": int, "requests_per_hour": int, "requests_per_day": int, "cooldown": int}}
global_request_count = 0  # Общее количество запросов
error_count = 0  # Счетчик ошибок
last_error_time = None  # Время последней ошибки
error_users = set()  # Пользователи, у которых были ошибки

# Время запуска бота
bot_start_time = time.time()

# Константы
MAX_CHATS = 10
MAX_SAVED_MESSAGES = 50  # Максимальное количество сохраняемых сообщений
DEFAULT_REQUESTS_PER_MINUTE = 10
DEFAULT_REQUESTS_PER_HOUR = 100
DEFAULT_REQUESTS_PER_DAY = 500
DEFAULT_COOLDOWN = 5  # секунд между запросами

# Информация о лимитах Groq на март 2026 (актуально для текущего периода)
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
        }
        dialog_messages[user_id] = []  # Список ID сообщений в текущем диалоге
        saved_messages[user_id] = []  # Сохраненные сообщения
        last_message_text[user_id] = {"user": "", "bot": ""}  # Текст последних сообщений
        
        # Инициализируем лимиты для пользователя
        if user_id not in user_limits:
            user_limits[user_id] = {
                "requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE,
                "requests_per_hour": DEFAULT_REQUESTS_PER_HOUR,
                "requests_per_day": DEFAULT_REQUESTS_PER_DAY,
                "cooldown": DEFAULT_COOLDOWN,
                "is_owner": False
            }

def check_request_limits(user_id):
    """Проверка лимитов запросов для пользователя"""
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

def record_request(user_id):
    """Записать запрос пользователя"""
    user_requests[user_id].append(time.time())
    global global_request_count
    global_request_count += 1

def create_chat(user_id, name, is_temporary=False):
    """Создание нового чата"""
    if user_id not in user_data:
        init_user_data(user_id)
    
    chat_id = str(uuid.uuid4())[:8]
    
    new_chat = {
        "id": chat_id,
        "name": name,
        "messages": [{"role": "system", "content": MODES[user_data[user_id]["mode"]]["system_prompt"]}],
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
    global GROQ_API_KEY
    GROQ_API_KEY = new_api_key
    return init_groq_client(new_api_key)

async def notify_owner(context, message):
    """Отправить уведомление владельцу"""
    global OWNER_ID
    if OWNER_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"⚠️ **Уведомление владельцу**\n\n{message}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление владельцу: {e}")

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

def get_action_keyboard():
    """Reply-клавиатура с кнопками действий"""
    keyboard = [
        [KeyboardButton("👤 СОХРАНИТЬ МОЁ"), KeyboardButton("🤖 СОХРАНИТЬ БОТА")],
        [KeyboardButton("❌ ЗАВЕРШИТЬ ДИАЛОГ")]
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
    global OWNER_ID
    try:
        # Пытаемся получить ID владельца по юзернейму
        try:
            owner_chat = await application.bot.get_chat(OWNER_USERNAME)
            OWNER_ID = owner_chat.id
            logger.info(f"Владелец бота определен: {OWNER_USERNAME} (ID: {OWNER_ID})")
        except Exception as e:
            logger.warning(f"Не удалось определить ID владельца: {e}")
        
        commands = [
            BotCommand("start", "Запустить бота"),
            BotCommand("help", "Помощь"),
            BotCommand("settings", "Настройки"),
            BotCommand("info", "Информация"),
            BotCommand("chats", "Мои чаты"),
        ]
        await application.bot.set_my_commands(commands)
        
        logger.info("Бот успешно запущен!")
        logger.info(f"Версия Python: {sys.version.split()[0]}")
        logger.info(f"Время запуска: {datetime.datetime.now()}")
        
        # Уведомляем владельца о запуске
        if OWNER_ID:
            await application.bot.send_message(
                chat_id=OWNER_ID,
                text="✅ **Бот успешно запущен!**\n\nВсе системы работают в штатном режиме.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["username"] = username
        # Создаем первый чат при старте
        create_chat(user_id, "Основной чат", is_temporary=False)
        
        # Если это владелец, отмечаем его
        if username and f"@{username}" == OWNER_USERNAME:
            user_limits[user_id]["is_owner"] = True
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"💬 **Текущий чат:** {user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'}\n\n"
        f"Выбери действие в меню ниже или используй команды:\n"
        f"/help - помощь\n"
        f"/settings - настройки\n"
        f"/info - информация\n"
        f"/chats - мои чаты"
    )
    
    try:
        msg = await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = msg.message_id
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    user_id = update.effective_user.id
    
    help_text = (
        f"📚 **Помощь по боту**\n\n"
        f"**Основные команды:**\n"
        f"/start - запустить бота\n"
        f"/help - показать это сообщение\n"
        f"/settings - настройки\n"
        f"/info - информация\n"
        f"/chats - управление чатами\n\n"
        
        f"**Как пользоваться:**\n"
        f"• Просто пиши сообщения - бот будет отвечать\n"
        f"• После ответа появится клавиатура с кнопками:\n"
        f"  - 👤 СОХРАНИТЬ МОЁ - сохранить своё сообщение\n"
        f"  - 🤖 СОХРАНИТЬ БОТА - сохранить ответ бота\n"
        f"  - ❌ ЗАВЕРШИТЬ ДИАЛОГ - очистить чат\n\n"
        
        f"**Чаты:**\n"
        f"• Можно создавать постоянные (до {MAX_CHATS}) и временные чаты\n"
        f"• Временные чаты удаляются после завершения\n"
        f"• История постоянных чатов сохраняется\n\n"
        
        f"**Сохранение:**\n"
        f"• Сохраняйте свои сообщения и ответы бота\n"
        f"• Лимит сохранения можно изменить в настройках\n"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда настроек"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        init_user_data(user_id)
    
    saved_count = len(saved_messages.get(user_id, []))
    saved_limit = user_data[user_id]["saved_messages_limit"]
    
    text = (
        f"⚙️ **Настройки пользователя**\n\n"
        f"📊 **Ваши данные:**\n"
        f"• Сохранено сообщений: {saved_count}/{saved_limit}\n"
        f"• Всего сообщений: {user_data[user_id].get('total_messages', 0)}\n\n"
        f"🔧 **Управление:**\n"
        f"• Нажмите кнопку ниже, чтобы изменить лимит сохранения\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔢 Изменить лимит сохранения", callback_data="set_limit")],
        [InlineKeyboardButton("◀️ Главное меню", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда информации"""
    user_id = update.effective_user.id
    
    uptime_seconds = int(time.time() - bot_start_time)
    uptime_string = str(timedelta(seconds=uptime_seconds))
    
    current_time = datetime.now()
    march_2026_limits = GROQ_LIMITS["free_tier"] if current_time < datetime(2026, 4, 1) else GROQ_LIMITS["paid_tier"]
    
    # Статистика по пользователям
    total_users = len(user_data)
    active_users = sum(1 for data in user_data.values() if data.get("in_dialog", False))
    total_requests = global_request_count
    
    text = (
        f"ℹ️ **Информация о боте**\n\n"
        f"📅 **Текущая дата:** {current_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"⏱ **Аптайм:** {uptime_string}\n\n"
        
        f"📊 **Статистика использования:**\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Активных диалогов: {active_users}\n"
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
        
        f"👑 **Владелец:** {OWNER_USERNAME}"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data="back_to_main")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра чатов"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        init_user_data(user_id)
    
    await show_chats_interface(update, context, user_id)

async def show_chats_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
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
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    
    text = f"📋 **Мои чаты**\n\nВсего постоянных: {len(permanent_chats)}/{MAX_CHATS}"
    
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (не команд)"""
    global error_count, last_error_time, error_users
    
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
    
    if user_message == "❌ ЗАВЕРШИТЬ ДИАЛОГ":
        await end_dialog(update, context)
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
        
        elif action_data.get("action") == "set_cooldown" and user_limits.get(user_id, {}).get("is_owner"):
            del awaiting_input[user_id]
            try:
                cooldown = int(user_message)
                if cooldown >= 0:
                    # Применяем ко всем пользователям
                    for uid in user_limits:
                        user_limits[uid]["cooldown"] = cooldown
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
                    await update.message.reply_text(f"✅ Лимит запросов/мин для всех установлен: {limit}")
                else:
                    await update.message.reply_text("❌ Лимит должен быть >= 0")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
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
                        "❌ Ошибка при обновлении API ключа. Проверьте ключ и попробуйте снова.",
                        reply_markup=get_main_keyboard(user_id)
                    )
            else:
                await update.message.reply_text(
                    "❌ Неверный формат API ключа. Ключ должен начинаться с 'gsk_' и быть длиннее 30 символов.",
                    reply_markup=get_main_keyboard(user_id)
                )
            return
    
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
        await update.message.reply_text(f"⏱️ {message}")
        return
    
    user_data[user_id]["in_dialog"] = True
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
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
        
        # Отправляем ответ
        sent_message = await update.message.reply_text(assistant_message)
        
        # Сохраняем ID сообщения бота
        dialog_messages[user_id].append(sent_message.message_id)
        
        # Показываем клавиатуру с действиями
        if not user_data[user_id]["showing_action_buttons"]:
            action_message = await context.bot.send_message(
                chat_id=user_id,
                text="Выбери действие:",
                reply_markup=get_action_keyboard()
            )
            dialog_messages[user_id].append(action_message.message_id)
            user_data[user_id]["showing_action_buttons"] = True
            
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от пользователя {user_id}: {e}")
        
        # Увеличиваем счетчик ошибок
        error_count += 1
        last_error_time = time.time()
        error_users.add(user_id)
        
        # Отправляем уведомление владельцу
        if OWNER_ID and len(error_users) >= 3:  # Если ошибки у 3+ пользователей
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
        elif "api_key" in str(e).lower():
            error_message += "Проблема с API ключом. Администратор уже уведомлен."
        else:
            error_message += "Попробуйте позже."
        
        await update.message.reply_text(error_message)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографий"""
    user_id = update.effective_user.id
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
    
    await update.message.reply_text(
        "📸 **Бот не умеет анализировать фото**\n\n"
        "Я работаю только с текстом. Отправь текстовое сообщение.",
        parse_mode='Markdown'
    )

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение диалога"""
    user_id = update.effective_user.id
    
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
    
    # Возвращаем главное меню
    msg = await context.bot.send_message(
        chat_id=user_id,
        text="👋 **Главное меню**\n\nВыбери действие:",
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
        
        if user_id not in user_data:
            init_user_data(user_id)
            user_data[user_id]["username"] = username
            create_chat(user_id, "Основной чат", is_temporary=False)
            
            # Если это владелец, отмечаем его
            if username and f"@{username}" == OWNER_USERNAME:
                user_limits[user_id]["is_owner"] = True
        
        if query.data == "ignore":
            return
        
        # Обработка навигационных кнопок
        if query.data == "back_to_main":
            await query.edit_message_text(
                "👋 **Главное меню**\n\nВыбери действие:",
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
            )
            menu_messages[user_id] = query.message.message_id
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
            
            text = (
                f"ℹ️ **Информация о боте**\n\n"
                f"📅 **Текущая дата:** {current_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏱ **Аптайм:** {uptime_string}\n\n"
                
                f"📊 **Статистика использования:**\n"
                f"• Всего пользователей: {total_users}\n"
                f"• Активных диалогов: {active_users}\n"
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
                
                f"👑 **Владелец:** {OWNER_USERNAME}"
            )
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Настройки
        if query.data == "show_settings":
            saved_count = len(saved_messages.get(user_id, []))
            saved_limit = user_data[user_id]["saved_messages_limit"]
            
            text = (
                f"⚙️ **Настройки пользователя**\n\n"
                f"📊 **Ваши данные:**\n"
                f"• Сохранено сообщений: {saved_count}/{saved_limit}\n"
                f"• Всего сообщений: {user_data[user_id].get('total_messages', 0)}\n\n"
                
                f"🔧 **Управление:**\n"
                f"• Нажмите кнопку ниже, чтобы изменить лимит сохранения\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔢 Изменить лимит сохранения", callback_data="set_limit")],
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
        
        # Панель владельца
        if query.data == "owner_panel" and user_limits.get(user_id, {}).get("is_owner"):
            total_requests_today = len([t for t in sum(user_requests.values(), []) if time.time() - t < 86400])
            active_users_now = len([uid for uid, times in user_requests.items() if times and time.time() - times[-1] < 300])
            
            text = (
                f"👑 **Панель владельца**\n\n"
                
                f"📊 **Глобальная статистика:**\n"
                f"• Всего пользователей: {len(user_data)}\n"
                f"• Активных сейчас: {active_users_now}\n"
                f"• Запросов сегодня: {total_requests_today}\n"
                f"• Всего запросов: {global_request_count}\n"
                f"• Ошибок API: {error_count}\n\n"
                
                f"🔧 **Управление системой:**\n"
                f"• Изменить API ключ\n"
                f"• Установить глобальные лимиты\n\n"
                
                f"⚠️ **Требуется действие:**\n"
                f"{'• Обнаружены массовые ошибки API' if error_count > 10 else '• Система работает стабильно'}"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔑 Сменить API ключ", callback_data="owner_change_api")],
                [InlineKeyboardButton("⏱️ Установить cooldown", callback_data="owner_set_cooldown")],
                [InlineKeyboardButton("📊 Лимиты запросов/мин", callback_data="owner_set_rpm")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
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
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            
            text = f"📋 **Мои чаты**\n\nВсего постоянных: {len(permanent_chats)}/{MAX_CHATS}"
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
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
        
        elif query.data.startswith("mode_"):
            mode_id = query.data.replace("mode_", "")
            user_data[user_id]["mode"] = mode_id
            
            # Обновляем system prompt в текущем чате
            if user_data[user_id]["current_chat"]:
                user_data[user_id]["current_chat"]["messages"] = [
                    {"role": "system", "content": MODES[mode_id]["system_prompt"]}
                ]
                user_data[user_id]["current_chat"]["mode"] = mode_id
            
            await query.edit_message_text(
                f"✅ Режим изменен на {MODES[mode_id]['name']}",
                reply_markup=get_main_keyboard(user_id)
            )
            menu_messages[user_id] = query.message.message_id
        
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
            
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")

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
        
        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("settings", settings_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("chats", chats_command))
        
        # Добавляем обработчик inline-кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Добавляем обработчик фотографий
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Добавляем обработчик текстовых сообщений (НЕ команд)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        application.add_error_handler(error_handler)
        
        logger.info("Бот запускается...")
        logger.info(f"Время: {datetime.datetime.now()}")
        
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
