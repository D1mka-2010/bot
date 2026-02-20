import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncio
import time
import socks
import socket
from groq import Groq
import datetime
import platform
import psutil
import random

# Токены
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"
GROQ_API_KEY = "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"

# ============================================
# НАСТРОЙКА ПРОКСИ
# ============================================
USE_PROXY = False  # Пока отключаем прокси, так как он не работает
PROXY_HOST = "195.74.72.111"
PROXY_PORT = 5678
PROXY_TYPE = socks.SOCKS4
# ============================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройка прокси (если нужно)
if USE_PROXY:
    try:
        socks.set_default_proxy(PROXY_TYPE, PROXY_HOST, PROXY_PORT)
        socket.socket = socks.socksocket
        logger.info(f"✅ Прокси {PROXY_HOST}:{PROXY_PORT} настроен")
    except Exception as e:
        logger.error(f"❌ Ошибка настройки прокси: {e}")
        logger.info("🔄 Работаем без прокси")

# Создаем клиент Groq
groq_client = Groq(api_key=GROQ_API_KEY)

# Модели
MODELS = {
    "🚀 LLaMA 3.1 8B": "llama-3.1-8b-instant",
    "⚡ LLaMA 3.2 3B": "llama-3.2-3b-preview",
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
        ],
        [
            InlineKeyboardButton("🛠 Тест бота", callback_data="show_tests"),
            InlineKeyboardButton("🎲 Рандом", callback_data="random_tools")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tests_keyboard():
    """Клавиатура для тестов"""
    keyboard = [
        [
            InlineKeyboardButton("🏓 Пинг", callback_data="test_ping"),
            InlineKeyboardButton("⏱ Задержка", callback_data="test_latency")
        ],
        [
            InlineKeyboardButton("💾 Статус", callback_data="test_status"),
            InlineKeyboardButton("🌐 IP", callback_data="test_ip")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="test_stats"),
            InlineKeyboardButton("🔍 Эхо", callback_data="test_echo")
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"),
            InlineKeyboardButton("❌ Закрыть", callback_data="ignore")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_random_keyboard():
    """Клавиатура для рандомных инструментов"""
    keyboard = [
        [
            InlineKeyboardButton("🎲 Кубик", callback_data="random_dice"),
            InlineKeyboardButton("🪙 Монетка", callback_data="random_coin")
        ],
        [
            InlineKeyboardButton("🔢 Число", callback_data="random_number"),
            InlineKeyboardButton("🎯 Шар судьбы", callback_data="random_8ball")
        ],
        [
            InlineKeyboardButton("💖 Комплимент", callback_data="random_compliment"),
            InlineKeyboardButton("😄 Шутка", callback_data="random_joke")
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"),
            InlineKeyboardButton("❌ Закрыть", callback_data="ignore")
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
        except:
            pass
        del menu_messages[user_id]

async def remove_end_dialog_button(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Удаление кнопки завершения диалога"""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="◀️ Возврат в главное меню",
            reply_markup=ReplyKeyboardRemove()
        )
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    user_id = update.effective_user.id
    
    try:
        await update.message.delete()
    except:
        pass
    
    await delete_menu(user_id, context)
    await remove_end_dialog_button(context, update.effective_chat.id)
    
    if user_id not in user_data:
        user_data[user_id] = {
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
            "in_dialog": False,
            "ping_count": 0,
            "last_ping": 0
        }
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"📌 **Сейчас:** {MODES[user_data[user_id]['mode']]['name']} | {get_model_name(user_data[user_id]['model'])}\n\n"
        f"💡 **Что умею:**\n"
        f"• 💬 Общаться в разных режимах\n"
        f"• 🛠 Тестировать соединение и статус\n"
        f"• 🎲 Рандомные числа и предсказания\n\n"
        f"🔹 **Как пользоваться:**\n"
        f"1️⃣ Напиши сообщение - начнется диалог\n"
        f"2️⃣ После ответа появится кнопка ❌ ЗАВЕРШИТЬ ДИАЛОГ\n"
        f"3️⃣ В меню есть кнопка 🛠 Тест бота для проверки"
    )
    
    msg = await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode='Markdown'
    )
    menu_messages[user_id] = msg.message_id

def get_model_name(model_id):
    for name, mid in MODELS.items():
        if mid == model_id:
            return name
    return model_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Проверка на команду завершения диалога
    if user_message == "❌ ЗАВЕРШИТЬ ДИАЛОГ":
        await end_dialog(update, context)
        return
    
    # Удаляем меню, если оно есть
    await delete_menu(user_id, context)
    
    # Защита от спама
    current_time = time.time()
    if user_id in user_last_message and current_time - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = current_time
    
    # Инициализация пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
            "in_dialog": True,
            "ping_count": 0,
            "last_ping": 0
        }
    else:
        user_data[user_id]["in_dialog"] = True
    
    # Отправляем сообщение о начале обработки
    wait_msg = await update.message.reply_text(
        "⏳ Обрабатываю запрос...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Добавляем сообщение пользователя в историю
        history = user_data[user_id]["history"]
        history.append({"role": "user", "content": user_message})
        
        # Ограничиваем историю
        if len(history) > 11:
            history[:] = [history[0]] + history[-10:]
        
        # Получаем ответ от Groq
        response = await asyncio.get_event_loop().run_in_executor(
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
        
        # Удаляем сообщение о загрузке
        await wait_msg.delete()
        
        # Отправляем ответ с кнопкой завершения диалога
        await update.message.reply_text(
            assistant_message,
            reply_markup=get_end_dialog_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await wait_msg.delete()
        await update.message.reply_text(
            "❌ Ошибка при обработке запроса. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографий"""
    user_id = update.effective_user.id
    await delete_menu(user_id, context)
    
    await update.message.reply_text(
        "📸 **Бот не умеет анализировать фото**\n\n"
        "Я работаю только с текстом. Отправь текстовое сообщение.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение диалога и возврат в меню"""
    user_id = update.effective_user.id
    
    # Сбрасываем историю, сохраняя системный промпт текущего режима
    if user_id in user_data:
        current_mode = user_data[user_id]["mode"]
        user_data[user_id]["history"] = [{"role": "system", "content": MODES[current_mode]["system_prompt"]}]
        user_data[user_id]["in_dialog"] = False
    
    # Удаляем сообщение с кнопкой "ЗАВЕРШИТЬ ДИАЛОГ"
    try:
        await update.message.delete()
    except:
        pass
    
    # Показываем главное меню
    msg = await update.message.reply_text(
        f"✅ **Диалог завершен!**\n\n"
        f"Возвращаюсь в меню.\n"
        f"Текущие настройки:\n"
        f"• Режим: {MODES[user_data[user_id]['mode']]['name']}\n"
        f"• Модель: {get_model_name(user_data[user_id]['model'])}",
        reply_markup=get_main_keyboard(user_id),
        parse_mode='Markdown'
    )
    menu_messages[user_id] = msg.message_id
    
    # Убираем клавиатуру с кнопкой "ЗАВЕРШИТЬ ДИАЛОГ"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="◀️ Кнопка закрыта",
        reply_markup=ReplyKeyboardRemove()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок"""
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
            "ping_count": 0,
            "last_ping": 0
        }
    
    # ===== ТЕСТЫ =====
    if query.data == "show_tests":
        await query.edit_message_text(
            "🛠 **Тестирование бота**\n\n"
            "Выберите тип проверки:",
            reply_markup=get_tests_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "test_ping":
        start_time = time.time()
        user_data[user_id]["ping_count"] += 1
        user_data[user_id]["last_ping"] = start_time
        
        await query.edit_message_text(
            f"🏓 **Понг!**\n\n"
            f"Время ответа: `{time.time() - start_time:.3f}с`\n"
            f"Пингов за сессию: {user_data[user_id]['ping_count']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще пинг", callback_data="test_ping"),
                InlineKeyboardButton("◀️ Назад", callback_data="show_tests")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "test_latency":
        # Тест задержки до разных сервисов
        await query.edit_message_text(
            "⏱ **Измеряю задержку...**",
            reply_markup=None
        )
        
        services = {
            "Google": "google.com",
            "GitHub": "github.com",
            "Telegram": "api.telegram.org",
            "Groq": "api.groq.com"
        }
        
        result_text = "⏱ **Задержка до сервисов:**\n\n"
        
        for name, host in services.items():
            try:
                start = time.time()
                await asyncio.get_event_loop().getaddrinfo(host, 80)
                latency = (time.time() - start) * 1000
                result_text += f"• {name}: `{latency:.1f} мс`\n"
            except:
                result_text += f"• {name}: `❌ Недоступен`\n"
        
        await query.edit_message_text(
            result_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Обновить", callback_data="test_latency"),
                InlineKeyboardButton("◀️ Назад", callback_data="show_tests")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "test_status":
        # Статус бота
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024 / 1024  # в MB
        cpu_usage = process.cpu_percent(interval=0.1)
        
        users_count = len(user_data)
        active_dialogs = len([u for u in user_data.values() if u.get("in_dialog", False)])
        
        status_text = (
            f"💾 **Статус бота:**\n\n"
            f"📊 **Система:**\n"
            f"• Платформа: {platform.system()} {platform.release()}\n"
            f"• Процессор: {platform.processor() or 'N/A'}\n"
            f"• RAM бота: {memory_usage:.1f} MB\n"
            f"• CPU бота: {cpu_usage:.1f}%\n\n"
            f"👥 **Пользователи:**\n"
            f"• Всего: {users_count}\n"
            f"• В диалогах: {active_dialogs}\n\n"
            f"🤖 **Groq:**\n"
            f"• Статус: {'✅ Доступен' if groq_client else '❌ Недоступен'}"
        )
        
        await query.edit_message_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Обновить", callback_data="test_status"),
                InlineKeyboardButton("◀️ Назад", callback_data="show_tests")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "test_ip":
        # Получаем IP (если есть доступ к внешним API)
        try:
            import aiohttp
            
            await query.edit_message_text(
                "🌐 Получаю IP...",
                reply_markup=None
            )
            
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.ipify.org?format=json') as resp:
                    ip_data = await resp.json()
                    ip = ip_data.get('ip', 'Неизвестно')
                
                async with session.get('https://ipapi.co/json/') as resp:
                    location_data = await resp.json()
                    city = location_data.get('city', 'Неизвестно')
                    country = location_data.get('country_name', 'Неизвестно')
                    
            ip_text = (
                f"🌐 **Информация о соединении:**\n\n"
                f"🖥 **IP адрес:** `{ip}`\n"
                f"📍 **Локация:** {city}, {country}\n"
                f"🔒 **Прокси:** {'Включен' if USE_PROXY else 'Выключен'}\n"
                f"🌍 **Хост:** {PROXY_HOST if USE_PROXY else 'Прямое соединение'}"
            )
        except:
            ip_text = (
                f"🌐 **Информация о соединении:**\n\n"
                f"❌ Не удалось получить IP информацию\n"
                f"🔒 **Прокси:** {'Включен' if USE_PROXY else 'Выключен'}"
            )
        
        await query.edit_message_text(
            ip_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Обновить", callback_data="test_ip"),
                InlineKeyboardButton("◀️ Назад", callback_data="show_tests")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "test_stats":
        # Статистика использования
        total_messages = sum(len([m for m in u.get("history", []) if m["role"] == "user"]) 
                           for u in user_data.values())
        
        mode_stats = {}
        for mode in MODES:
            mode_stats[mode] = len([u for u in user_data.values() if u.get("mode") == mode])
        
        model_stats = {}
        for model_name, model_id in MODELS.items():
            model_stats[model_name] = len([u for u in user_data.values() if u.get("model") == model_id])
        
        stats_text = (
            f"📊 **Статистика:**\n\n"
            f"💬 **Всего сообщений:** {total_messages}\n"
            f"👥 **Активных пользователей:** {len(user_data)}\n\n"
            f"🎭 **Режимы:**\n"
        )
        
        for mode_id, mode_info in MODES.items():
            count = mode_stats.get(mode_id, 0)
            stats_text += f"• {mode_info['name']}: {count} пользователей\n"
        
        stats_text += f"\n🚀 **Модели:**\n"
        for model_name, count in model_stats.items():
            if count > 0:
                stats_text += f"• {model_name}: {count} пользователей\n"
        
        await query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Обновить", callback_data="test_stats"),
                InlineKeyboardButton("◀️ Назад", callback_data="show_tests")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "test_echo":
        await query.edit_message_text(
            "🔍 **Эхо-тест**\n\n"
            "Отправь любое сообщение, и я повторю его!\n"
            "(Нажми ❌ ЗАВЕРШИТЬ ДИАЛОГ для выхода)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="show_tests")
            ]]),
            parse_mode='Markdown'
        )
        user_data[user_id]["in_dialog"] = True
        user_data[user_id]["echo_mode"] = True
    
    # ===== РАНДОМ =====
    elif query.data == "random_tools":
        await query.edit_message_text(
            "🎲 **Рандомные инструменты**\n\n"
            "Выберите что-нибудь:",
            reply_markup=get_random_keyboard(),
            parse_mode='Markdown'
        )
    
    elif query.data == "random_dice":
        dice = random.randint(1, 6)
        dice_emoji = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"][dice-1]
        
        await query.edit_message_text(
            f"🎲 **Бросок кубика**\n\n"
            f"Выпало: **{dice}** {dice_emoji}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще раз", callback_data="random_dice"),
                InlineKeyboardButton("◀️ Назад", callback_data="random_tools")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "random_coin":
        coin = random.choice(["Орел", "Решка"])
        coin_emoji = "🦅" if coin == "Орел" else "💶"
        
        await query.edit_message_text(
            f"🪙 **Подбрасывание монетки**\n\n"
            f"Выпало: **{coin}** {coin_emoji}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще раз", callback_data="random_coin"),
                InlineKeyboardButton("◀️ Назад", callback_data="random_tools")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "random_number":
        number = random.randint(1, 100)
        
        await query.edit_message_text(
            f"🔢 **Случайное число**\n\n"
            f"**{number}**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще число", callback_data="random_number"),
                InlineKeyboardButton("◀️ Назад", callback_data="random_tools")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "random_8ball":
        answers = [
            "Бесспорно", "Предрешено", "Никаких сомнений", "Определённо да", "Можешь быть уверен в этом",
            "Мне кажется - да", "Вероятнее всего", "Хорошие перспективы", "Знаки говорят - да", "Да",
            "Пока не ясно, попробуй снова", "Спроси позже", "Лучше не рассказывать", "Сейчас нельзя предсказать", "Сконцентрируйся и спроси опять",
            "Даже не думай", "Мой ответ - нет", "По моим данным - нет", "Перспективы не очень хорошие", "Весьма сомнительно"
        ]
        answer = random.choice(answers)
        
        await query.edit_message_text(
            f"🎯 **Шар судьбы**\n\n"
            f"❓ Задай вопрос мысленно\n"
            f"✨ Ответ: **{answer}**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще ответ", callback_data="random_8ball"),
                InlineKeyboardButton("◀️ Назад", callback_data="random_tools")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "random_compliment":
        compliments = [
            "Ты сегодня прекрасно выглядишь! ✨",
            "У тебя отличное чувство юмора! 😄",
            "Ты очень умный собеседник! 🧠",
            "С тобой приятно общаться! 💫",
            "Ты делаешь мой день лучше! ☀️",
            "У тебя золотое сердце! 💛",
            "Ты настоящий друг! 🤝",
            "Твоя улыбка освещает всё вокруг! 🌟",
            "Ты уникальный человек! 💎",
            "С тобой легко и весело! 🎉"
        ]
        compliment = random.choice(compliments)
        
        await query.edit_message_text(
            f"💖 **Комплимент дня**\n\n"
            f"{compliment}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще комплимент", callback_data="random_compliment"),
                InlineKeyboardButton("◀️ Назад", callback_data="random_tools")
            ]]),
            parse_mode='Markdown'
        )
    
    elif query.data == "random_joke":
        jokes = [
            "Почему программисты путают Хэллоуин и Рождество?\nПотому что Oct 31 = Dec 25! 🎃",
            "Встречаются два друга:\n- Ты какой язык программирования учишь?\n- Python.\n- А почему?\n- Потому что жизнь и так слишком коротка! 🐍",
            "Сколько программистов нужно, чтобы вкрутить лампочку?\nНи одного. Это аппаратная проблема! 💡",
            "Админ не ошибается. Он просто проводит внеплановое тестирование! 👨‍💻",
            "Как называют слепого оленя?\nНикогда не знает, когда переходить дорогу! 🦌",
            "Почему скелет не дрался?\nПотому что у него не было кишок! 💀",
            "Что сказал виноград, когда его раздавили?\nНичего, просто выпустил сок! 🍇"
        ]
        joke = random.choice(jokes)
        
        await query.edit_message_text(
            f"😄 **Шутка**\n\n"
            f"{joke}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Еще шутку", callback_data="random_joke"),
                InlineKeyboardButton("◀️ Назад", callback_data="random_tools")
            ]]),
            parse_mode='Markdown'
        )
    
    # ===== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ =====
    elif query.data == "show_modes":
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
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
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
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = query.message.message_id
    
    elif query.data == "show_history":
        history = user_data[user_id]["history"]
        user_msgs = [msg for msg in history if msg["role"] == "user"]
        
        if user_msgs:
            text = f"📋 **История диалога**\n\n"
            text += f"Всего сообщений: {len(user_msgs)}\n"
            text += f"В режиме: {MODES[user_data[user_id]['mode']]['name']}\n\n"
            text += "**Последние сообщения:**\n"
            
            for msg in history[-6:]:
                if msg["role"] == "user":
                    text += f"👤 **Вы:** {msg['content'][:50]}...\n"
                elif msg["role"] == "assistant":
                    text += f"🤖 **Бот:** {msg['content'][:50]}...\n"
        else:
            text = "📋 История пока пуста. Напиши что-нибудь!"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == "settings":
        mode_name = MODES[user_data[user_id]["mode"]]["name"]
        mode_desc = MODES[user_data[user_id]["mode"]]["description"]
        model_name = get_model_name(user_data[user_id]["model"])
        history_len = len([msg for msg in user_data[user_id]["history"] if msg["role"] == "user"])
        
        text = (
            f"ℹ️ **Информация**\n\n"
            f"👤 **Пользователь:** {query.from_user.first_name}\n"
            f"🎭 **Режим:** {mode_name}\n"
            f"📝 **Описание:** {mode_desc}\n"
            f"🚀 **Модель:** {model_name}\n"
            f"💬 **Сообщений в истории:** {history_len}\n\n"
            f"📌 **Доступные режимы:**\n"
            f"• 💬 Обычный - вежливые ответы\n"
            f"• 😈 Хам - грубые и саркастичные\n"
            f"• 🤬 Мат - с нецензурной лексикой"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == "back_to_main":
        await remove_end_dialog_button(context, query.message.chat_id)
        
        await query.edit_message_text(
            f"⚡ **Главное меню**\n\n"
            f"🎭 {MODES[user_data[user_id]['mode']]['name']} | 🚀 {get_model_name(user_data[user_id]['model'])}",
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = query.message.message_id

def main():
    print("🎭 Бот запускается...")
    print("="*50)
