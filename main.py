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
        }
    
    def format(self, record):
        # Сначала форматируем как обычно
        result = super().format(record)
        # Заменяем эмодзи на текстовые аналоги
        for emoji, text in self.emoji_map.items():
            result = result.replace(emoji, text)
        return result

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем обработчик для файла (UTF-8)
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Создаем обработчик для консоли с заменой эмодзи
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Перенаправляем stderr и stdout для корректной обработки Unicode
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# НЕ используем прокси
if USE_PROXY:
    try:
        socks.set_default_proxy(PROXY_TYPE, PROXY_HOST, PROXY_PORT)
        socket.socket = socks.socksocket
        logger.info("Прокси настроен")
    except Exception as e:
        logger.error(f"Ошибка настройки прокси: {e}")
        logger.info("Работаем без прокси")

# Создаем клиент Groq с таймаутами
groq_client = Groq(
    api_key=GROQ_API_KEY,
    timeout=30.0
)

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

user_data = {}
user_last_message = {}
menu_messages = {}

# Время запуска бота для отслеживания аптайма
bot_start_time = time.time()

def get_main_keyboard(user_id):
    """Главная inline-клавиатура в сообщении"""
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
            InlineKeyboardButton("📋 История", callback_data="show_history"),
            InlineKeyboardButton("ℹ️ Инфо", callback_data="settings")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_end_dialog_keyboard():
    """Клавиатура с кнопкой завершения диалога"""
    keyboard = [
        [KeyboardButton("❌ ЗАВЕРШИТЬ ДИАЛОГ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

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

async def post_init(application: Application):
    """Действия после инициализации бота"""
    try:
        # Устанавливаем команды бота
        commands = [
            BotCommand("start", "Запустить бота"),
            BotCommand("ping", "Проверить скорость"),
            BotCommand("status", "Статус бота"),
        ]
        await application.bot.set_my_commands(commands)
        
        logger.info("Бот успешно запущен!")
        logger.info(f"Версия Python: {sys.version.split()[0]}")
        logger.info(f"Время запуска: {datetime.datetime.now()}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота - НЕ УДАЛЯЕТ сообщение с командой"""
    user_id = update.effective_user.id
    
    # НЕ удаляем сообщение с командой /start
    # Просто удаляем предыдущее меню если было
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        user_data[user_id] = {
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
            "in_dialog": False,
            "showing_end_button": False
        }
    
    # Получаем аптайм бота
    uptime_seconds = int(time.time() - bot_start_time)
    uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"📌 **Сейчас:** {MODES[user_data[user_id]['mode']]['name']} | {get_model_name(user_data[user_id]['model'])}\n\n"
        f"💡 **Как пользоваться:**\n"
        f"• Пиши сообщения - я буду отвечать\n"
        f"• Кнопка ЗАВЕРШИТЬ ДИАЛОГ появляется после первого сообщения\n"
        f"• Используй /ping для проверки скорости ответа\n"
        f"• Используй /status для информации о боте"
    )
    
    try:
        # Отправляем приветственное сообщение
        msg = await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = msg.message_id
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра статуса бота"""
    try:
        # Получаем аптайм бота
        uptime_seconds = int(time.time() - bot_start_time)
        uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
        
        # Получаем информацию о пользователе
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        
        # Статистика
        total_users = len(user_data)
        active_users = sum(1 for data in user_data.values() if data.get("in_dialog", False))
        
        # Информация о системе
        python_version = sys.version.split()[0]
        
        status_text = (
            f"🤖 **Статус бота**\n\n"
            f"⏱ **Аптайм:** {uptime_string}\n"
            f"📊 **Версия:** 2.0\n"
            f"🐍 **Python:** {python_version}\n\n"
            f"📈 **Статистика:**\n"
            f"• Всего пользователей: {total_users}\n"
            f"• Активных диалогов: {active_users}\n\n"
            f"👤 **Ваш профиль:**\n"
            f"• ID: `{user_id}`\n"
            f"• Имя: {user_name}"
        )
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка в status: {e}")
        await update.message.reply_text("❌ Ошибка при получении статуса")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для проверки скорости ответа бота"""
    user_id = update.effective_user.id
    start_time = time.time()
    
    # Отправляем сообщение о начале проверки
    status_msg = await update.message.reply_text("🔄 Проверка скорости...")
    
    try:
        # Проверяем задержку Telegram API
        telegram_ping = time.time() - start_time
        
        # Проверяем скорость ответа Groq API
        groq_start = time.time()
        
        # Используем простой синхронный вызов в отдельном потоке
        loop = asyncio.get_event_loop()
        test_response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[{"role": "user", "content": "Ответь одним словом: привет"}],
                temperature=0.1,
                max_tokens=10
            )
        )
        
        groq_time = time.time() - groq_start
        total_time = time.time() - start_time
        
        # Получаем информацию о модели
        current_model = user_data.get(user_id, {}).get("model", DEFAULT_MODEL)
        model_name = get_model_name(current_model)
        
        # Форматируем время
        result_text = (
            f"📊 **Результаты проверки скорости:**\n\n"
            f"⏱ **Общее время:** `{total_time:.2f} сек`\n"
            f"📨 **Telegram API:** `{telegram_ping:.2f} сек`\n"
            f"🤖 **Groq API:** `{groq_time:.2f} сек`\n\n"
            f"📌 **Текущая модель:** {model_name}\n"
            f"🕒 **Время проверки:** {datetime.datetime.now().strftime('%H:%M:%S')}\n\n"
            f"**Тестовый ответ:**\n{test_response.choices[0].message.content}"
        )
        
        await status_msg.edit_text(result_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в ping: {e}")
        total_time = time.time() - start_time
        error_text = (
            f"❌ **Ошибка при проверке скорости**\n\n"
            f"⏱ **Общее время до ошибки:** `{total_time:.2f} сек`\n"
            f"⚠️ **Ошибка:** {str(e)[:100]}\n\n"
            f"💡 Возможно, проблема с сетью"
        )
        try:
            await status_msg.edit_text(error_text, parse_mode='Markdown')
        except:
            await update.message.reply_text(error_text, parse_mode='Markdown')

def get_model_name(model_id):
    for name, mid in MODELS.items():
        if mid == model_id:
            return name
    return model_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Проверяем, не является ли сообщение командой завершения
    if user_message == "❌ ЗАВЕРШИТЬ ДИАЛОГ":
        await end_dialog(update, context)
        return
    
    # Удаляем предыдущее меню если оно было
    await delete_menu(user_id, context)
    
    # Проверка на спам
    current_time = time.time()
    if user_id in user_last_message and current_time - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = current_time
    
    # Инициализация данных пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
            "in_dialog": True,
            "showing_end_button": False
        }
    else:
        user_data[user_id]["in_dialog"] = True
    
    # Отправляем индикатор печатания
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        history = user_data[user_id]["history"]
        history.append({"role": "user", "content": user_message})
        
        if len(history) > 11:
            history[:] = [history[0]] + history[-10:]
        
        # Используем отдельный поток для запроса к Groq
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
        
        # Отправляем ответ
        await update.message.reply_text(assistant_message)
        
        # Показываем кнопку завершения если еще не показывали
        if not user_data[user_id]["showing_end_button"]:
            menu_text = (
                f"⚡ **Меню диалога**\n\n"
                f"Продолжай общение или нажми кнопку ниже, чтобы завершить диалог."
            )
            msg = await context.bot.send_message(
                chat_id=user_id,
                text=menu_text,
                reply_markup=get_end_dialog_keyboard(),
                parse_mode='Markdown'
            )
            user_data[user_id]["showing_end_button"] = True
            
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        error_message = "❌ Ошибка при получении ответа. "
        
        if "timeout" in str(e).lower():
            error_message += "Превышено время ожидания. Попробуйте позже."
        elif "connection" in str(e).lower():
            error_message += "Проблема с подключением к API."
        else:
            error_message += f"Попробуйте позже."
        
        await update.message.reply_text(error_message)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографий"""
    user_id = update.effective_user.id
    await delete_menu(user_id, context)
    
    await update.message.reply_text(
        "📸 **Бот не умеет анализировать фото**\n\n"
        "Я работаю только с текстом. Отправь текстовое сообщение.",
        parse_mode='Markdown'
    )

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение диалога"""
    user_id = update.effective_user.id
    
    if user_id in user_data:
        current_mode = user_data[user_id]["mode"]
        user_data[user_id]["history"] = [{"role": "system", "content": MODES[current_mode]["system_prompt"]}]
        user_data[user_id]["in_dialog"] = False
        user_data[user_id]["showing_end_button"] = False
    
    # Убираем клавиатуру
    try:
        await update.message.reply_text(
            "✅ Диалог завершен",
            reply_markup=ReplyKeyboardRemove()
        )
    except:
        pass
    
    # Возвращаем главное меню
    uptime_seconds = int(time.time() - bot_start_time)
    uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
    
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=(
            f"✅ **Диалог завершен!**\n\n"
            f"История очищена.\n"
            f"Текущие настройки:\n"
            f"• Режим: {MODES[user_data[user_id]['mode']]['name']}\n"
            f"• Модель: {get_model_name(user_data[user_id]['model'])}\n\n"
            f"⏱ **Аптайм:** {uptime_string}"
        ),
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
        
        if query.data == "ignore":
            await query.message.delete()
            if user_id in menu_messages:
                del menu_messages[user_id]
            return
        
        if user_id not in user_data:
            user_data[user_id] = {
                "model": DEFAULT_MODEL,
                "mode": DEFAULT_MODE,
                "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
                "in_dialog": False,
                "showing_end_button": False
            }
        
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
            user_data[user_id]["history"] = [{"role": "system", "content": MODES[mode_id]["system_prompt"]}]
            
            await query.edit_message_text(
                f"✅ Режим изменен на {MODES[mode_id]['name']}",
                reply_markup=get_main_keyboard(user_id)
            )
            menu_messages[user_id] = query.message.message_id
        
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
            
            await query.edit_message_text(
                f"✅ Модель изменена",
                reply_markup=get_main_keyboard(user_id)
            )
            menu_messages[user_id] = query.message.message_id
        
        elif query.data == "show_history":
            history = user_data[user_id]["history"]
            user_msgs = [msg for msg in history if msg["role"] == "user"]
            
            if user_msgs:
                text = f"📋 **История**\n\nВсего сообщений: {len(user_msgs)}\n\nПоследние:\n"
                for msg in history[-6:]:
                    if msg["role"] == "user":
                        text += f"👤 {msg['content'][:50]}...\n"
                    elif msg["role"] == "assistant":
                        text += f"🤖 {msg['content'][:50]}...\n"
            else:
                text = "📋 История пуста"
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        elif query.data == "settings":
            mode_name = MODES[user_data[user_id]["mode"]]["name"]
            model_name = get_model_name(user_data[user_id]["model"])
            history_len = len([msg for msg in user_data[user_id]["history"] if msg["role"] == "user"])
            
            uptime_seconds = int(time.time() - bot_start_time)
            uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
            
            text = (
                f"ℹ️ **Информация**\n\n"
                f"👤 Пользователь: {query.from_user.first_name}\n"
                f"🎭 Режим: {mode_name}\n"
                f"🚀 Модель: {model_name}\n"
                f"💬 Сообщений: {history_len}\n\n"
                f"⏱ **Аптайм:** {uptime_string}\n\n"
                f"📌 **Режимы:**\n"
                f"• 💬 Обычный - вежливые ответы\n"
                f"• 😈 Хам - грубые и саркастичные\n"
                f"• 🤬 Мат - с нецензурной лексикой"
            )
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        elif query.data == "back_to_main":
            await query.edit_message_text(
                f"⚡ **Главное меню**\n\n"
                f"{MODES[user_data[user_id]['mode']]['name']} | {get_model_name(user_data[user_id]['model'])}",
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
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
        # Создаем приложение
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
        application.add_handler(CommandHandler("ping", ping_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Добавляем глобальный обработчик ошибок
        application.add_error_handler(error_handler)
        
        logger.info("Бот запускается...")
        logger.info(f"Время: {datetime.datetime.now()}")
        
        # Запускаем бота
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
