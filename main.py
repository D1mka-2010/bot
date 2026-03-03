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

# Токены
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"
GROQ_API_KEY = "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"

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
            '📝': '[EDIT]',
            '🔢': '[LIMIT]',
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

# Создаем клиент Groq
groq_client = Groq(api_key=GROQ_API_KEY, timeout=30.0)

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

# Время запуска бота
bot_start_time = time.time()

# Константы
MAX_CHATS = 10
MAX_SAVED_MESSAGES = 50  # Максимальное количество сохраняемых сообщений

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
        }
        dialog_messages[user_id] = []  # Список ID сообщений в текущем диалоге
        saved_messages[user_id] = []  # Сохраненные сообщения
        last_message_text[user_id] = {"user": "", "bot": ""}  # Текст последних сообщений

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

def set_saved_messages_limit(user_id, limit):
    """Установить лимит сохраненных сообщений"""
    if user_id in user_data:
        user_data[user_id]["saved_messages_limit"] = max(1, min(limit, 100))  # Ограничиваем от 1 до 100
        return True
    return False

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
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_keyboard():
    """Reply-клавиатура с кнопками действий"""
    keyboard = [
        [KeyboardButton("❤️ СОХРАНИТЬ ПОСЛЕДНЕЕ")],
        [KeyboardButton("📋 МОИ СОХРАНЕННЫЕ"), KeyboardButton("❌ ЗАВЕРШИТЬ ДИАЛОГ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_saved_messages_keyboard(user_id, page=0):
    """Клавиатура для просмотра сохраненных сообщений"""
    if user_id not in saved_messages or not saved_messages[user_id]:
        return None
    
    messages = saved_messages[user_id]
    items_per_page = 5
    start = page * items_per_page
    end = min(start + items_per_page, len(messages))
    
    keyboard = []
    
    for i in range(start, end):
        msg = messages[i]
        sender_emoji = "👤" if msg["sender"] == "user" else "🤖"
        preview = msg["text"][:30] + "..." if len(msg["text"]) > 30 else msg["text"]
        btn_text = f"{sender_emoji} {preview}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_saved_{i}")])
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"saved_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page+1}/{(len(messages)-1)//items_per_page + 1}", callback_data="ignore"))
    if end < len(messages):
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"saved_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(keyboard)

def get_end_dialog_keyboard():
    """Клавиатура с кнопкой завершения диалога"""
    keyboard = [
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
    try:
        commands = [
            BotCommand("start", "Запустить бота"),
        ]
        await application.bot.set_my_commands(commands)
        
        logger.info("Бот успешно запущен!")
        logger.info(f"Версия Python: {sys.version.split()[0]}")
        logger.info(f"Время запуска: {datetime.datetime.now()}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    user_id = update.effective_user.id
    
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        init_user_data(user_id)
        # Создаем первый чат при старте
        create_chat(user_id, "Основной чат", is_temporary=False)
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"💬 **Текущий чат:** {user_data[user_id]['current_chat']['name'] if user_data[user_id]['current_chat'] else 'Нет чата'}\n\n"
        f"Выбери действие:"
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

def get_model_name(model_id):
    for name, mid in MODELS.items():
        if mid == model_id:
            return name
    return model_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Сохраняем ID сообщения пользователя
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    dialog_messages[user_id].append(update.message.message_id)
    
    # Проверяем, не является ли сообщение командой
    if user_message == "❤️ СОХРАНИТЬ ПОСЛЕДНЕЕ":
        if last_message_text[user_id]["bot"]:
            save_message(user_id, last_message_text[user_id]["bot"], "bot")
            await update.message.reply_text("✅ Последнее сообщение бота сохранено!")
        else:
            await update.message.reply_text("❌ Нет сообщения для сохранения")
        return
    
    if user_message == "📋 МОИ СОХРАНЕННЫЕ":
        await show_saved_messages(update, context, user_id)
        return
    
    if user_message == "❌ ЗАВЕРШИТЬ ДИАЛОГ":
        await end_dialog(update, context)
        return
    
    # Проверяем, не ожидаем ли мы ввод названия чата или лимита
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
                if set_saved_messages_limit(user_id, limit):
                    await update.message.reply_text(
                        f"✅ Лимит сохраненных сообщений установлен: {limit}",
                        reply_markup=get_main_keyboard(user_id)
                    )
                else:
                    await update.message.reply_text("❌ Ошибка при установке лимита")
            except ValueError:
                await update.message.reply_text("❌ Введите число")
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
        logger.error(f"Ошибка при обработке сообщения: {e}")
        error_message = "❌ Ошибка при получении ответа. "
        
        if "timeout" in str(e).lower():
            error_message += "Превышено время ожидания."
        elif "connection" in str(e).lower():
            error_message += "Проблема с подключением."
        else:
            error_message += "Попробуйте позже."
        
        await update.message.reply_text(error_message)

async def show_saved_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Показать сохраненные сообщения"""
    if user_id not in saved_messages or not saved_messages[user_id]:
        await update.message.reply_text(
            "📋 **Сохраненные сообщения**\n\nУ вас пока нет сохраненных сообщений.",
            reply_markup=get_back_to_menu_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    keyboard = get_saved_messages_keyboard(user_id, 0)
    if keyboard:
        await update.message.reply_text(
            "📋 **Сохраненные сообщения**\n\nВыберите сообщение для просмотра:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

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
    
    # Возвращаем главное меню без сообщения о завершении
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
        
        if user_id not in user_data:
            init_user_data(user_id)
            create_chat(user_id, "Основной чат", is_temporary=False)
        
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
        
        # Показ настроек
        if query.data == "show_settings":
            mode_name = MODES[user_data[user_id]["mode"]]["name"]
            model_name = get_model_name(user_data[user_id]["model"])
            saved_count = len(saved_messages.get(user_id, []))
            saved_limit = user_data[user_id]["saved_messages_limit"]
            
            uptime_seconds = int(time.time() - bot_start_time)
            uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
            
            text = (
                f"⚙️ **Настройки**\n\n"
                f"👤 Пользователь: {query.from_user.first_name}\n\n"
                f"🎭 **Текущие настройки:**\n"
                f"• Режим: {mode_name}\n"
                f"• Модель: {model_name}\n\n"
                f"📊 **Статистика:**\n"
                f"• Сохранено сообщений: {saved_count}/{saved_limit}\n\n"
                f"🔧 **Управление:**\n"
                f"• Нажмите кнопку ниже, чтобы изменить лимит сохранения\n\n"
                f"⏱ **Аптайм:** {uptime_string}"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔢 Изменить лимит", callback_data="set_limit")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Установка лимита
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
        
        # Просмотр сохраненных сообщений
        if query.data.startswith("view_saved_"):
            index = int(query.data.replace("view_saved_", ""))
            if user_id in saved_messages and 0 <= index < len(saved_messages[user_id]):
                msg = saved_messages[user_id][index]
                sender_text = "Вы" if msg["sender"] == "user" else "Бот"
                sender_emoji = "👤" if msg["sender"] == "user" else "🤖"
                
                text = (
                    f"📋 **Сохраненное сообщение**\n\n"
                    f"Отправитель: {sender_emoji} {sender_text}\n"
                    f"Чат: {msg['chat_name']}\n"
                    f"Время: {datetime.datetime.fromtimestamp(msg['timestamp']).strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"**Текст:**\n{msg['text']}"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_saved_{index}")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="show_saved_page_0")]
                ]
                
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            return
        
        # Удаление из сохраненных
        if query.data.startswith("delete_saved_"):
            index = int(query.data.replace("delete_saved_", ""))
            if delete_saved_message(user_id, index):
                await query.answer("✅ Сообщение удалено")
                
                # Показываем обновленный список
                if user_id in saved_messages and saved_messages[user_id]:
                    keyboard = get_saved_messages_keyboard(user_id, 0)
                    if keyboard:
                        await query.edit_message_text(
                            "📋 **Сохраненные сообщения**\n\nВыберите сообщение для просмотра:",
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text(
                            "📋 **Сохраненные сообщения**\n\nУ вас пока нет сохраненных сообщений.",
                            reply_markup=get_back_to_menu_keyboard(),
                            parse_mode='Markdown'
                        )
                else:
                    await query.edit_message_text(
                        "📋 **Сохраненные сообщения**\n\nУ вас пока нет сохраненных сообщений.",
                        reply_markup=get_back_to_menu_keyboard(),
                        parse_mode='Markdown'
                    )
            return
        
        # Навигация по страницам сохраненных
        if query.data.startswith("saved_page_"):
            page = int(query.data.replace("saved_page_", ""))
            keyboard = get_saved_messages_keyboard(user_id, page)
            if keyboard:
                await query.edit_message_text(
                    "📋 **Сохраненные сообщения**\n\nВыберите сообщение для просмотра:",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            return
        
        if query.data.startswith("show_saved_page_"):
            page = int(query.data.replace("show_saved_page_", ""))
            keyboard = get_saved_messages_keyboard(user_id, page)
            if keyboard:
                await query.edit_message_text(
                    "📋 **Сохраненные сообщения**\n\nВыберите сообщение для просмотра:",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
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
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
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
