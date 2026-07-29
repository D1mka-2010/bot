import telebot
from telebot import types
import json
import os
import time
import datetime
import threading
import requests
import asyncio
import random
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
import signal
import sys
import logging
import traceback
from flask import Flask, jsonify

# Отключаем лишние логи
logging.getLogger('telethon').setLevel(logging.WARNING)

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8817363723:AAGJQG38Pyd7caE9f4LWrpBwy-A44O5kDK0")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-5e32f44e18f04897a8a4b1f94b52f482")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

API_ID = int(os.environ.get("API_ID", 28432904))
API_HASH = os.environ.get("API_HASH", "2150e2107b519bd98d2a2a9057510373")

ADMIN_IDS = os.environ.get("ADMIN_IDS", "7666021527")
ADMIN_LIST = [int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip()]

SUPPORT_IDS = os.environ.get("SUPPORT_IDS", "")
SUPPORT_LIST = [int(x.strip()) for x in SUPPORT_IDS.split(",") if x.strip()]

CONFIG_FILE = "dcheck_data.json"
SESSIONS_DIR = "sessions"

if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# ===================== ИНИЦИАЛИЗАЦИЯ ID БОТА =====================
try:
    BOT_ID = bot.get_me().id
    print(f"✅ ID бота: {BOT_ID}")
except Exception as e:
    print(f"⚠️ Не удалось получить ID бота: {e}")
    BOT_ID = None

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ===================== БАЗА ДАННЫХ =====================
def load_data():
    if not os.path.exists(CONFIG_FILE):
        default_data = {
            "users": {},
            "deleted_messages": {},
            "muted_chats": [],
            "ai_chats": [],
            "ai_profiles": {},
            "user_sessions": {},
            "user_settings": {},
            "clean_chats": [],
            "command_blacklist": [],
            "tos_versions": {},
            "show_deleted_notifications": True,
            "typing_speed": {},
            "user_stats": {},
            "support_list": [],
            "bot_status": "online",
            "topics": {},
            "respected_users": {},
            "active_topics_chats": {}
        }
        save_data(default_data)
        return default_data
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user(user_id):
    data = load_data()
    return data["users"].get(str(user_id))

def save_user(user_id, user_data):
    data = load_data()
    data["users"][str(user_id)] = user_data
    save_data(data)

def get_user_settings(user_id):
    data = load_data()
    return data.get("user_settings", {}).get(str(user_id), {})

def save_user_settings(user_id, settings):
    data = load_data()
    if "user_settings" not in data:
        data["user_settings"] = {}
    data["user_settings"][str(user_id)] = settings
    save_data(data)

def get_auth_method(user_id):
    settings = get_user_settings(user_id)
    return settings.get("auth_method", 1)

def set_auth_method(user_id, method):
    settings = get_user_settings(user_id)
    settings["auth_method"] = method
    save_user_settings(user_id, settings)

def get_user_session_data(user_id):
    data = load_data()
    session_data = data.get("user_sessions", {}).get(str(user_id))
    if session_data is None:
        return None
    if isinstance(session_data, str):
        session_data = {"session": session_data, "api_id": 0, "api_hash": ""}
        data["user_sessions"][str(user_id)] = session_data
        save_data(data)
    return session_data

def save_user_session(user_id, session_string, api_id, api_hash):
    data = load_data()
    data["user_sessions"][str(user_id)] = {
        "session": session_string,
        "api_id": api_id,
        "api_hash": api_hash
    }
    save_data(data)

def get_session_file(user_id):
    return os.path.join(SESSIONS_DIR, f"user_{user_id}.session")

def session_file_exists(user_id):
    return os.path.exists(get_session_file(user_id))

def delete_session_file(user_id):
    try:
        if session_file_exists(user_id):
            os.remove(get_session_file(user_id))
            return True
    except:
        pass
    return False

def add_deleted_message(user_id, sender_id, sender_name, text, msg_id=None):
    data = load_data()
    uid = str(user_id)
    sid = str(sender_id)
    if "deleted_messages" not in data:
        data["deleted_messages"] = {}
    if uid not in data["deleted_messages"]:
        data["deleted_messages"][uid] = {}
    if sid not in data["deleted_messages"][uid]:
        data["deleted_messages"][uid][sid] = {"name": sender_name, "msgs": []}
    if isinstance(data["deleted_messages"][uid][sid], list):
        data["deleted_messages"][uid][sid] = {"name": sender_name, "msgs": []}
    data["deleted_messages"][uid][sid]["name"] = sender_name
    for msg in data["deleted_messages"][uid][sid]["msgs"]:
        if msg.get("msg_id") == msg_id:
            return
    data["deleted_messages"][uid][sid]["msgs"].append({
        "time": datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y"),
        "text": text[:500],
        "msg_id": msg_id
    })
    if len(data["deleted_messages"][uid][sid]["msgs"]) > 200:
        data["deleted_messages"][uid][sid]["msgs"] = data["deleted_messages"][uid][sid]["msgs"][-200:]
    save_data(data)

def is_admin(user_id):
    if 0 in ADMIN_LIST:
        return True
    return user_id in ADMIN_LIST

def is_support(user_id):
    if 0 in SUPPORT_LIST:
        return True
    return user_id in SUPPORT_LIST or is_admin(user_id)

def is_authorized(user_id):
    user = get_user(user_id)
    if not user:
        return False
    method = get_auth_method(user_id)
    if method == 1:
        session_data = get_user_session_data(user_id)
        if not session_data:
            return False
    elif method == 7:
        if not session_file_exists(user_id):
            return False
    return user.get("logged_in", False)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
last_bot_messages = {}
message_cache = {}
MAX_CACHE_SIZE = 1000
active_clients = {}
user_tasks = {}

BOT_START_TIME = datetime.datetime.now()

def get_bot_uptime():
    delta = datetime.datetime.now() - BOT_START_TIME
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    seconds = delta.seconds % 60
    if days > 0:
        return f"{days}д {hours}ч {minutes}м {seconds}с"
    else:
        return f"{hours}ч {minutes}м {seconds}с"

def delete_old_bot_message(chat_id):
    if chat_id in last_bot_messages:
        try:
            bot.delete_message(chat_id, last_bot_messages[chat_id])
        except:
            pass
        last_bot_messages.pop(chat_id, None)

def send_new_message(chat_id, text, reply_markup=None):
    delete_old_bot_message(chat_id)
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')
    last_bot_messages[chat_id] = msg.message_id
    return msg

def is_command_blocked(chat_id):
    data = load_data()
    return str(chat_id) in data.get("command_blacklist", [])

def get_typing_speed(user_id):
    data = load_data()
    return data.get("typing_speed", {}).get(str(user_id), 2)

def set_typing_speed(user_id, speed):
    data = load_data()
    if "typing_speed" not in data:
        data["typing_speed"] = {}
    data["typing_speed"][str(user_id)] = speed
    save_data(data)

def increment_user_stats(user_id):
    data = load_data()
    if "user_stats" not in data:
        data["user_stats"] = {}
    if str(user_id) not in data["user_stats"]:
        data["user_stats"][str(user_id)] = {
            "messages": 0,
            "first_use": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_use": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    data["user_stats"][str(user_id)]["messages"] += 1
    data["user_stats"][str(user_id)]["last_use"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_data(data)

def get_total_users():
    data = load_data()
    return len(data.get("user_stats", {}))

def get_api_info_text():
    return (
        "🔑 <b>ЧТО ТАКОЕ API ID И API HASH?</b>\n\n"
        "Это уникальные ключи, которые позволяют боту подключаться к вашему аккаунту Telegram.\n\n"
        "📌 <b>ГДЕ ИХ ВЗЯТЬ?</b>\n\n"
        "1️⃣ Перейдите на сайт: <a href='https://my.telegram.org'>my.telegram.org</a>\n"
        "2️⃣ Войдите в свой аккаунт Telegram\n"
        "3️⃣ В меню выберите <b>API Development Tools</b>\n"
        "4️⃣ Создайте новое приложение (Create application)\n"
        "5️⃣ Заполните поля (можно любое название)\n"
        "6️⃣ Скопируйте <b>api_id</b> и <b>api_hash</b>\n\n"
        "⚠️ <b>ВАЖНО:</b>\n"
        "• Эти данные НИКОМУ не передавайте\n"
        "• Они нужны только для подключения бота\n"
        "• Хранятся в зашифрованном виде\n\n"
        "ℹ️ <b>Способ 7 (файлы сессий):</b>\n"
        "• Использует общие API данные из настроек бота\n"
        "• Не требует ввода API при каждом входе"
    )

# ===================== ФУНКЦИИ ДЛЯ ТЕМ И УВАЖИТЕЛЬНЫХ ОБРАЩЕНИЙ =====================
def get_user_topics(user_id):
    data = load_data()
    return data.get("topics", {}).get(str(user_id), {})

def save_user_topic(user_id, topic_name, examples, response):
    data = load_data()
    if "topics" not in data:
        data["topics"] = {}
    if str(user_id) not in data["topics"]:
        data["topics"][str(user_id)] = {}
    data["topics"][str(user_id)][topic_name] = {
        "examples": examples,
        "response": response
    }
    save_data(data)

def delete_user_topic(user_id, topic_name):
    data = load_data()
    if str(user_id) in data.get("topics", {}):
        if topic_name in data["topics"][str(user_id)]:
            del data["topics"][str(user_id)][topic_name]
            save_data(data)
            return True
    return False

def get_respected_users(user_id):
    data = load_data()
    return data.get("respected_users", {}).get(str(user_id), [])

def add_respected_user(user_id, username):
    data = load_data()
    if "respected_users" not in data:
        data["respected_users"] = {}
    if str(user_id) not in data["respected_users"]:
        data["respected_users"][str(user_id)] = []
    if username not in data["respected_users"][str(user_id)]:
        data["respected_users"][str(user_id)].append(username)
        save_data(data)
        return True
    return False

def remove_respected_user(user_id, username):
    data = load_data()
    if str(user_id) in data.get("respected_users", {}):
        if username in data["respected_users"][str(user_id)]:
            data["respected_users"][str(user_id)].remove(username)
            save_data(data)
            return True
    return False

# ===================== DEEPSEEK AI (ОБНОВЛЁННАЯ: РОЛЬ + УВАЖИТЕЛЬНЫЕ ОБРАЩЕНИЯ) =====================
def call_deepseek_ai(user_message, user_id, chat_id, history=None, sender_username=None):
    user = get_user(user_id)
    if not user:
        return None
    profile = user.get("ai_profile", {})
    context = "\n".join(history[-15:]) if history else "Нет истории сообщений."
    ai_name = profile.get('name', 'пользователь')
    ai_style = profile.get('style', 'дружелюбный')
    ai_phrases = profile.get('phrases', '')
    ai_role = profile.get('role', '')
    phrase_instruction = ""
    if ai_phrases and random.random() < 0.15:
        phrase_instruction = f"Твои любимые фразы (используй их редко и только к месту): {ai_phrases}."
    else:
        phrase_instruction = "Не используй шаблонные фразы, отвечай естественно."

    respected_users = get_respected_users(user_id)
    respectful_instruction = ""
    if sender_username and sender_username in respected_users:
        respectful_instruction = f"Обращайся к собеседнику на 'Вы' и используйте его имя или username {sender_username}."
    elif ai_role:
        respectful_instruction = f"Ты - {ai_role}. Отвечай соответственно своей роли."

    system_prompt = (
        f"Ты живой человек по имени {ai_name}. Твой стиль общения: {ai_style}. "
        f"НИКОГДА не говори, что ты ИИ, нейросеть, ассистент или языковая модель. "
        f"Отвечай как обычный пользователь Telegram. "
        f"{phrase_instruction}\n"
        f"{respectful_instruction}\n\n"
        f"Контекст:\n{context}\n\n"
        f"Ответь на последнее сообщение. "
        f"Обязательно используй Markdown форматирование Telegram (звездочки **жирный**, обратные кавычки `код`)."
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
        "max_tokens": 60,
        "temperature": 0.8
    }
    try:
        resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ AI ошибка: {e}")
    return None

# ===================== АВТОРИЗАЦИЯ =====================
code_input_data = {}
auth_data = {}
auth_in_progress = {}
pending_phone = {}

def get_code_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=5)
    row1 = [types.InlineKeyboardButton(str(i), callback_data=f"code_{i}") for i in range(1, 6)]
    markup.row(*row1)
    row2 = [types.InlineKeyboardButton(str(i), callback_data=f"code_{i}") for i in range(6, 10)] + [types.InlineKeyboardButton("0", callback_data="code_0")]
    markup.row(*row2)
    markup.row(
        types.InlineKeyboardButton("🔙 Удалить", callback_data="code_backspace"),
        types.InlineKeyboardButton("✅ Отправить", callback_data="code_done")
    )
    return markup

def update_code_display(chat_id, user_id):
    code = code_input_data.get(user_id, {}).get("code", "")
    display_text = "🔐 <b>Введите код из Telegram:</b>\n\n"
    if code:
        displayed = []
        for i in range(5):
            if i < len(code):
                displayed.append(code[i])
            else:
                displayed.append("_")
        display_text += " ".join(displayed)
        display_text += f"\n\nВведено: {len(code)}/5 цифр"
    else:
        display_text += "_ _ _ _ _\n\n0/5 цифр введено"
    markup = get_code_keyboard()
    if chat_id in last_bot_messages:
        try:
            bot.edit_message_text(display_text, chat_id, last_bot_messages[chat_id], reply_markup=markup, parse_mode='HTML')
            return
        except:
            pass
    msg = bot.send_message(chat_id, display_text, reply_markup=markup, parse_mode='HTML')
    last_bot_messages[chat_id] = msg.message_id

def start_auth_process(message):
    user_id = message.chat.id
    if auth_in_progress.get(user_id):
        bot.send_message(user_id, "⚠️ Процесс авторизации уже запущен. Введите код или отмените.")
        return
    auth_in_progress[user_id] = True
    method = get_auth_method(user_id)
    if method == 1:
        start_auth_method_1(message)
    else:
        start_auth_method_7(message)

# ===================== НОВАЯ АВТОРИЗАЦИЯ СПОСОБ 1 (С ВЫБОРОМ ДЛЯ АДМИНА) =====================
def start_auth_method_1(message):
    user_id = message.chat.id
    auth_data[user_id] = {"step": "instruction"}

    if is_admin(user_id):
        text = (
            "👑 <b>Вы администратор!</b>\n\n"
            "Вы можете использовать API-данные бота (встроенные) или ввести свои.\n\n"
            f"📌 Данные бота:\n"
            f"• API_ID: <code>{API_ID}</code>\n"
            f"• API_HASH: <code>{API_HASH[:10]}...</code>\n\n"
            "Что делаем?"
        )
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("✅ Использовать данные бота", callback_data="admin_use_bot_api"),
            types.InlineKeyboardButton("✏️ Ввести свои", callback_data="admin_enter_own_api")
        )
        markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="auth_back_to_menu"))
        send_new_message(user_id, text, reply_markup=markup)
        return

    text = (
        "🔐 <b>АВТОРИЗАЦИЯ (Способ 1)</b>\n\n"
        "Для входа в аккаунт нужны ключи API.\n\n"
        "📌 <b>Как получить:</b>\n"
        "1️⃣ Перейдите на <a href='https://my.telegram.org'>my.telegram.org</a>\n"
        "2️⃣ Войдите в аккаунт\n"
        "3️⃣ Выберите <b>API Development Tools</b>\n"
        "4️⃣ Создайте приложение\n"
        "5️⃣ Скопируйте <b>api_id</b> и <b>api_hash</b>\n\n"
        "⚠️ <b>ВАЖНО:</b>\n"
        "• Никому не передавайте эти данные\n"
        "• Они нужны только для подключения бота\n\n"
        "➡️ Нажмите <b>ПРОДОЛЖИТЬ</b>, чтобы ввести данные:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ ПРОДОЛЖИТЬ", callback_data="auth_continue_step1"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="auth_back_to_menu")
    )
    send_new_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_use_bot_api")
def admin_use_bot_api(call):
    user_id = call.message.chat.id
    auth_data[user_id]["api_id"] = API_ID
    auth_data[user_id]["api_hash"] = API_HASH
    auth_data[user_id]["step"] = "phone"
    delete_old_bot_message(user_id)
    text = (
        "📱 <b>Введите номер телефона</b>\n\n"
        "Формат: <code>+375291234567</code>\n"
        "Укажите код страны без пробелов."
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"),
        types.InlineKeyboardButton("🆘 Помощь", callback_data="auth_help")
    )
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_phone_method_1)

@bot.callback_query_handler(func=lambda call: call.data == "admin_enter_own_api")
def admin_enter_own_api(call):
    user_id = call.message.chat.id
    delete_old_bot_message(user_id)
    auth_data[user_id]["step"] = "api_id"
    text = (
        "🔐 <b>Введите ваш API_ID</b>\n\n"
        "Это цифры, которые вы скопировали на my.telegram.org\n"
        "Пример: <code>12345678</code>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔙 Инструкция", callback_data="auth_back_to_instruction"),
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
    )
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_api_id)

@bot.callback_query_handler(func=lambda call: call.data == "auth_continue_step1")
def auth_continue_step1(call):
    user_id = call.message.chat.id
    auth_data[user_id] = {"step": "api_id"}
    text = (
        "🔐 <b>АВТОРИЗАЦИЯ (Способ 1)</b>\n\n"
        "➡️ <b>Шаг 1 из 3:</b> Введите ваш API_ID\n\n"
        "📌 Это цифры, которые вы скопировали на my.telegram.org\n"
        "Пример: <code>12345678</code>\n\n"
        "Напишите в ответном сообщении только цифры:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔙 Инструкция", callback_data="auth_back_to_instruction"),
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
    )
    delete_old_bot_message(user_id)
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_api_id)

@bot.callback_query_handler(func=lambda call: call.data == "auth_back_to_instruction")
def auth_back_to_instruction(call):
    user_id = call.message.chat.id
    start_auth_method_1(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "auth_back_to_menu")
def auth_back_to_menu(call):
    user_id = call.message.chat.id
    if user_id in auth_data:
        del auth_data[user_id]
    if user_id in code_input_data:
        del code_input_data[user_id]
    if user_id in auth_in_progress:
        del auth_in_progress[user_id]
    if user_id in pending_phone:
        del pending_phone[user_id]
    delete_old_bot_message(user_id)
    show_main_menu(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_auth")
def cancel_auth(call):
    user_id = call.message.chat.id
    if user_id in auth_data:
        del auth_data[user_id]
    if user_id in code_input_data:
        del code_input_data[user_id]
    if user_id in auth_in_progress:
        del auth_in_progress[user_id]
    if user_id in pending_phone:
        del pending_phone[user_id]
    delete_old_bot_message(user_id)
    send_new_message(user_id, "❌ <b>Вход отменен</b>\n\nВы можете попробовать снова позже.")
    show_main_menu(call.message)

def process_api_id(message):
    user_id = message.chat.id
    try:
        api_id = int(message.text.strip())
        auth_data[user_id]["api_id"] = api_id
        auth_data[user_id]["step"] = "api_hash"
        text = (
            "🔐 <b>АВТОРИЗАЦИЯ (Способ 1)</b>\n\n"
            "✅ API_ID принят!\n\n"
            "➡️ <b>Шаг 2 из 3:</b> Введите ваш API_HASH\n\n"
            "📌 Это длинная строка из букв и цифр\n"
            "Пример: <code>abcdef1234567890</code>\n\n"
            "Напишите в ответном сообщении:"
        )
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("🔙 Шаг 1", callback_data="auth_back_to_api_id"),
            types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
        )
        delete_old_bot_message(user_id)
        msg = send_new_message(user_id, text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_api_hash)
    except ValueError:
        text = "❌ <b>Ошибка!</b>\n\nAPI_ID должен состоять только из цифр.\n\nПопробуйте снова:"
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("🔙 Инструкция", callback_data="auth_back_to_instruction"),
            types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
        )
        delete_old_bot_message(user_id)
        msg = send_new_message(user_id, text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_api_id)

@bot.callback_query_handler(func=lambda call: call.data == "auth_back_to_api_id")
def auth_back_to_api_id(call):
    user_id = call.message.chat.id
    auth_data[user_id]["step"] = "api_id"
    text = (
        "🔐 <b>АВТОРИЗАЦИЯ (Способ 1)</b>\n\n"
        "➡️ <b>Шаг 1 из 3:</b> Введите ваш API_ID\n\n"
        "📌 Это цифры, которые вы скопировали на my.telegram.org\n"
        "Пример: <code>12345678</code>\n\n"
        "Напишите в ответном сообщении только цифры:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔙 Инструкция", callback_data="auth_back_to_instruction"),
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
    )
    delete_old_bot_message(user_id)
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_api_id)

def process_api_hash(message):
    user_id = message.chat.id
    api_hash = message.text.strip()
    auth_data[user_id]["api_hash"] = api_hash
    auth_data[user_id]["step"] = "phone"
    text = (
        "📱 <b>АВТОРИЗАЦИЯ (Способ 1)</b>\n\n"
        "✅ API_HASH принят!\n\n"
        "➡️ <b>Шаг 3 из 3:</b> Введите номер телефона\n\n"
        "📌 Формат: <code>+375291234567</code>\n"
        "• Укажите код страны\n"
        "• Без пробелов и лишних символов\n\n"
        "Напишите в ответном сообщении:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔙 Шаг 2", callback_data="auth_back_to_api_hash"),
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
    )
    delete_old_bot_message(user_id)
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_phone_method_1)

@bot.callback_query_handler(func=lambda call: call.data == "auth_back_to_api_hash")
def auth_back_to_api_hash(call):
    user_id = call.message.chat.id
    auth_data[user_id]["step"] = "api_hash"
    text = (
        "🔐 <b>АВТОРИЗАЦИЯ (Способ 1)</b>\n\n"
        "➡️ <b>Шаг 2 из 3:</b> Введите ваш API_HASH\n\n"
        "📌 Это длинная строка из букв и цифр\n"
        "Пример: <code>abcdef1234567890</code>\n\n"
        "Напишите в ответном сообщении:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔙 Шаг 1", callback_data="auth_back_to_api_id"),
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
    )
    delete_old_bot_message(user_id)
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_api_hash)

# ===== НОВАЯ ВЕРСИЯ process_phone_method_1 с подтверждением номера =====
def process_phone_method_1(message):
    user_id = message.chat.id
    phone = message.text.strip()

    if not phone.startswith("+"):
        delete_old_bot_message(user_id)
        text = "❌ <b>Ошибка!</b>\n\nНомер должен начинаться с +.\n\n📌 Пример: <code>+375291234567</code>\n\nПопробуйте снова:"
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("🔙 Назад", callback_data="auth_back_to_api_hash"),
            types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth")
        )
        msg = send_new_message(user_id, text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_phone_method_1)
        return

    auth_data[user_id]["phone"] = phone
    pending_phone[user_id] = phone
    delete_old_bot_message(user_id)

    text = (
        "📱 <b>Проверьте номер</b>\n\n"
        f"Введённый номер: <code>{phone}</code>\n\n"
        "Всё верно? Нажмите «Продолжить», чтобы получить код из Telegram."
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Продолжить", callback_data="confirm_phone_step1"),
        types.InlineKeyboardButton("✏️ Изменить номер", callback_data="edit_phone_step1"),
        types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_auth")
    )
    send_new_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_phone_step1")
def confirm_phone_step1(call):
    user_id = call.message.chat.id
    if user_id not in pending_phone:
        bot.answer_callback_query(call.id, "⚠️ Номер не найден. Начните заново.", show_alert=True)
        return
    phone = pending_phone[user_id]
    auth_data[user_id]["phone"] = phone

    try:
        async def send_code():
            client = TelegramClient(
                StringSession(),
                auth_data[user_id]["api_id"],
                auth_data[user_id]["api_hash"]
            )
            await client.connect()
            result = await client.send_code_request(phone)
            session = client.session.save()
            await client.disconnect()
            return result.phone_code_hash, session
        phone_code_hash, session_string = asyncio.run(send_code())
        auth_data[user_id]["phone_code_hash"] = phone_code_hash
        auth_data[user_id]["session_string"] = session_string
        code_input_data[user_id] = {"code": ""}
        delete_old_bot_message(user_id)
        update_code_display(call.message.chat.id, user_id)
        if user_id in pending_phone:
            del pending_phone[user_id]
    except Exception as e:
        error_msg = str(e)
        if "A wait of" in error_msg:
            match = re.search(r'(\d+)', error_msg)
            if match:
                seconds = int(match.group(1))
                delete_old_bot_message(user_id)
                text = f"⚠️ <b>Telegram временно блокирует запросы.</b>\n\nНужно подождать {seconds // 3600} ч {(seconds % 3600) // 60} мин.\n\nПопробуйте позже или отмените вход."
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"))
                send_new_message(user_id, text, reply_markup=markup)
                return
        delete_old_bot_message(user_id)
        text = f"❌ <b>Ошибка:</b> <code>{e}</code>\n\nПопробуйте позже или отмените вход."
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"))
        markup.row(types.InlineKeyboardButton("🆘 Помощь", callback_data="auth_help"))
        send_new_message(user_id, text, reply_markup=markup)
        print(f"❌ Ошибка отправки кода: {e}")
        print(traceback.format_exc())

@bot.callback_query_handler(func=lambda call: call.data == "edit_phone_step1")
def edit_phone_step1(call):
    user_id = call.message.chat.id
    delete_old_bot_message(user_id)
    text = "📱 Введите номер заново (формат: <code>+375291234567</code>):"
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"))
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_phone_method_1)

@bot.callback_query_handler(func=lambda call: call.data == "auth_help")
def auth_help(call):
    user_id = call.message.chat.id
    text = (
        "🆘 <b>ПОМОЩЬ ПО АВТОРИЗАЦИИ</b>\n\n"
        "❓ <b>Что такое API_ID и API_HASH?</b>\n"
        "Это уникальные ключи, которые Telegram выдает для подключения к API.\n\n"
        "📌 <b>Как получить:</b>\n"
        "1. Зайдите на <a href='https://my.telegram.org'>my.telegram.org</a>\n"
        "2. Войдите в аккаунт\n"
        "3. Нажмите «API Development Tools»\n"
        "4. Создайте приложение\n"
        "5. Скопируйте цифры (api_id) и длинную строку (api_hash)\n\n"
        "ℹ️ Если у вас возникли проблемы:\n"
        "• Проверьте, что вы вошли в правильный аккаунт\n"
        "• Убедитесь, что вводите цифры без пробелов\n"
        "• Попробуйте обновить страницу и создать новое приложение"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="auth_back_to_instruction"))
    markup.row(types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"))
    send_new_message(user_id, text, reply_markup=markup)

# ===================== АВТОРИЗАЦИЯ СПОСОБ 7 (ФАЙЛЫ СЕССИЙ) =====================
def start_auth_method_7(message):
    user_id = message.chat.id
    if session_file_exists(user_id):
        send_new_message(user_id, "✅ <b>Сессия уже существует!</b>\n\nЮзербот подключается...")
        start_userbot(user_id)
        return
    auth_data[user_id] = {}
    text = (
        "🔐 <b>АВТОРИЗАЦИЯ (Способ 7)</b>\n\n"
        "📱 Введите номер телефона в формате:\n"
        "<code>+375291234567</code>\n\n"
        "📌 Укажите код страны без пробелов"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"),
        types.InlineKeyboardButton("🆘 Помощь", callback_data="auth_help")
    )
    msg = send_new_message(user_id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_phone_method_7)

def process_phone_method_7(message):
    user_id = message.chat.id
    phone = message.text.strip()
    if not phone.startswith("+"):
        delete_old_bot_message(user_id)
        text = "❌ <b>Ошибка!</b>\n\nНомер должен начинаться с +.\n\n📌 Пример: <code>+375291234567</code>\n\nПопробуйте снова:"
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"),
            types.InlineKeyboardButton("🆘 Помощь", callback_data="auth_help")
        )
        msg = send_new_message(user_id, text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_phone_method_7)
        return
    auth_data[user_id]["phone"] = phone
    try:
        async def send_code():
            client = TelegramClient(
                get_session_file(user_id),
                API_ID,
                API_HASH
            )
            await client.connect()
            result = await client.send_code_request(phone)
            await client.disconnect()
            return result.phone_code_hash
        phone_code_hash = asyncio.run(send_code())
        auth_data[user_id]["phone_code_hash"] = phone_code_hash
        code_input_data[user_id] = {"code": ""}
        update_code_display(message.chat.id, user_id)
    except Exception as e:
        error_msg = str(e)
        if "A wait of" in error_msg:
            match = re.search(r'(\d+)', error_msg)
            if match:
                seconds = int(match.group(1))
                delete_old_bot_message(user_id)
                text = f"⚠️ <b>Telegram временно блокирует запросы.</b>\n\nНужно подождать {seconds // 3600} ч {(seconds % 3600) // 60} мин.\n\nПопробуйте позже или отмените вход."
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"))
                send_new_message(user_id, text, reply_markup=markup)
                return
        delete_old_bot_message(user_id)
        text = f"❌ <b>Ошибка:</b> <code>{e}</code>\n\nПопробуйте позже или отмените вход."
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("❌ Отменить вход", callback_data="cancel_auth"))
        markup.row(types.InlineKeyboardButton("🆘 Помощь", callback_data="auth_help"))
        send_new_message(user_id, text, reply_markup=markup)
        print(f"❌ Ошибка в process_phone_method_7: {e}")
        print(traceback.format_exc())

# ===================== ОБРАБОТЧИК ВВОДА КОДА (ОБЩИЙ) =====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("code_"))
def handle_code_input(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if user_id not in code_input_data:
        code_input_data[user_id] = {"code": ""}
    action = call.data.replace("code_", "")
    if action == "backspace":
        if len(code_input_data[user_id]["code"]) > 0:
            code_input_data[user_id]["code"] = code_input_data[user_id]["code"][:-1]
            update_code_display(chat_id, user_id)
        try:
            bot.answer_callback_query(call.id)
        except:
            pass
        return
    if action == "done":
        code = code_input_data[user_id]["code"]
        if len(code) < 4:
            bot.answer_callback_query(call.id, "❌ Код должен содержать минимум 4 цифры!", show_alert=True)
            return
        method = get_auth_method(user_id)
        if method == 1:
            process_code_submit_method_1(call.message, code, user_id)
        else:
            process_code_submit_method_7(call.message, code, user_id)
        try:
            bot.answer_callback_query(call.id)
        except:
            pass
        return
    if len(code_input_data[user_id]["code"]) < 5:
        code_input_data[user_id]["code"] += action
        update_code_display(chat_id, user_id)
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

def process_code_submit_method_1(message, code, user_id):
    if user_id not in auth_data:
        delete_old_bot_message(user_id)
        send_new_message(user_id, "⚠️ Сессия не найдена. Начни заново.")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        return
    try:
        async def sign_in():
            client = TelegramClient(
                StringSession(auth_data[user_id]["session_string"]),
                auth_data[user_id]["api_id"],
                auth_data[user_id]["api_hash"]
            )
            await client.connect()
            await client.sign_in(
                phone=auth_data[user_id]["phone"],
                code=code,
                phone_code_hash=auth_data[user_id]["phone_code_hash"]
            )
            new_sess = client.session.save()
            await client.disconnect()
            return new_sess, client
        new_session_string, client = asyncio.run(sign_in())
        save_user_session(
            user_id,
            new_session_string,
            auth_data[user_id]["api_id"],
            auth_data[user_id]["api_hash"]
        )
        user_data = get_user(user_id) or {}
        user_data.update({"logged_in": True, "phone": auth_data[user_id]["phone"]})
        try:
            me = client.loop.run_until_complete(client.get_me())
            if me and me.username:
                user_data["username"] = me.username
        except:
            pass
        save_user(user_id, user_data)
        delete_old_bot_message(message.chat.id)
        if user_id in code_input_data:
            del code_input_data[user_id]
        if user_id in auth_data:
            del auth_data[user_id]
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        if user_id in pending_phone:
            del pending_phone[user_id]
        stop_userbot(user_id)
        send_new_message(message.chat.id, "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА!</b> 🎉\n\nЮзербот подключается...")
        show_main_menu(message)
        start_userbot(user_id)
    except Exception as e:
        if "password" in str(e).lower():
            delete_old_bot_message(user_id)
            msg = send_new_message(user_id, "🔐 Введите облачный пароль:")
            bot.register_next_step_handler(msg, process_password_method_1)
        else:
            delete_old_bot_message(user_id)
            send_new_message(user_id, f"❌ Ошибка: {e}")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]

def process_password_method_1(message):
    user_id = message.chat.id
    if user_id not in auth_data:
        delete_old_bot_message(user_id)
        send_new_message(user_id, "⚠️ Сессия не найдена. Начни заново.")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        return
    try:
        async def sign_in_password():
            client = TelegramClient(
                StringSession(auth_data[user_id]["session_string"]),
                auth_data[user_id]["api_id"],
                auth_data[user_id]["api_hash"]
            )
            await client.connect()
            await client.sign_in(password=message.text.strip())
            new_sess = client.session.save()
            await client.disconnect()
            return new_sess, client
        new_session_string, client = asyncio.run(sign_in_password())
        save_user_session(
            user_id,
            new_session_string,
            auth_data[user_id]["api_id"],
            auth_data[user_id]["api_hash"]
        )
        user_data = get_user(user_id) or {}
        user_data.update({"logged_in": True})
        try:
            me = client.loop.run_until_complete(client.get_me())
            if me and me.username:
                user_data["username"] = me.username
        except:
            pass
        save_user(user_id, user_data)
        delete_old_bot_message(message.chat.id)
        if user_id in code_input_data:
            del code_input_data[user_id]
        if user_id in auth_data:
            del auth_data[user_id]
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        if user_id in pending_phone:
            del pending_phone[user_id]
        stop_userbot(user_id)
        send_new_message(message.chat.id, "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА!</b> 🎉\n\nЮзербот подключается...")
        show_main_menu(message)
        start_userbot(user_id)
    except Exception as e:
        delete_old_bot_message(user_id)
        send_new_message(user_id, f"❌ Неверный пароль: {e}")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]

def process_code_submit_method_7(message, code, user_id):
    if user_id not in auth_data:
        delete_old_bot_message(user_id)
        send_new_message(user_id, "⚠️ Сессия не найдена. Начни заново.")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        return
    try:
        async def sign_in():
            client = TelegramClient(
                get_session_file(user_id),
                API_ID,
                API_HASH
            )
            await client.connect()
            await client.sign_in(
                phone=auth_data[user_id]["phone"],
                code=code,
                phone_code_hash=auth_data[user_id]["phone_code_hash"]
            )
            await client.disconnect()
            return client
        client = asyncio.run(sign_in())
        user_data = get_user(user_id) or {}
        user_data.update({"logged_in": True, "phone": auth_data[user_id]["phone"]})
        try:
            me = client.loop.run_until_complete(client.get_me())
            if me and me.username:
                user_data["username"] = me.username
        except:
            pass
        save_user(user_id, user_data)
        delete_old_bot_message(message.chat.id)
        if user_id in code_input_data:
            del code_input_data[user_id]
        if user_id in auth_data:
            del auth_data[user_id]
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        if user_id in pending_phone:
            del pending_phone[user_id]
        stop_userbot(user_id)
        send_new_message(message.chat.id, "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА!</b> 🎉\n\nЮзербот подключается...")
        show_main_menu(message)
        start_userbot(user_id)
    except Exception as e:
        if "password" in str(e).lower():
            delete_old_bot_message(user_id)
            msg = send_new_message(user_id, "🔐 Введите облачный пароль:")
            bot.register_next_step_handler(msg, process_password_method_7)
        else:
            delete_old_bot_message(user_id)
            send_new_message(user_id, f"❌ Ошибка: {e}")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]

def process_password_method_7(message):
    user_id = message.chat.id
    if user_id not in auth_data:
        delete_old_bot_message(user_id)
        send_new_message(user_id, "⚠️ Сессия не найдена. Начни заново.")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        return
    try:
        async def sign_in_password():
            client = TelegramClient(
                get_session_file(user_id),
                API_ID,
                API_HASH
            )
            await client.connect()
            await client.sign_in(password=message.text.strip())
            await client.disconnect()
            return client
        client = asyncio.run(sign_in_password())
        user_data = get_user(user_id) or {}
        user_data.update({"logged_in": True})
        try:
            me = client.loop.run_until_complete(client.get_me())
            if me and me.username:
                user_data["username"] = me.username
        except:
            pass
        save_user(user_id, user_data)
        delete_old_bot_message(message.chat.id)
        if user_id in code_input_data:
            del code_input_data[user_id]
        if user_id in auth_data:
            del auth_data[user_id]
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]
        if user_id in pending_phone:
            del pending_phone[user_id]
        stop_userbot(user_id)
        send_new_message(message.chat.id, "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА!</b> 🎉\n\nЮзербот подключается...")
        show_main_menu(message)
        start_userbot(user_id)
    except Exception as e:
        delete_old_bot_message(user_id)
        send_new_message(user_id, f"❌ Неверный пароль: {e}")
        if user_id in auth_in_progress:
            del auth_in_progress[user_id]

# ===================== КОМАНДЫ ПЕРЕКЛЮЧЕНИЯ =====================
@bot.message_handler(commands=["use7"])
def use7_command(message):
    user_id = message.chat.id
    set_auth_method(user_id, 7)
    text = (
        "🔄 <b>Переключено на способ 7</b>\n\n"
        "Теперь используется авторизация через файлы сессий.\n"
        "При входе нужно будет ввести только номер телефона и код.\n\n"
        "📌 Чтобы выйти и войти заново, нажмите:\n"
        "⚙️ Настройки → 🔐 Авторизация → Войти в аккаунт"
    )
    send_new_message(user_id, text)

@bot.message_handler(commands=["use1"])
def use1_command(message):
    user_id = message.chat.id
    set_auth_method(user_id, 1)
    text = (
        "🔄 <b>Переключено на способ 1</b>\n\n"
        "Теперь используется авторизация через ввод API_ID и API_HASH.\n"
        "При входе нужно будет ввести API_ID, API_HASH, номер телефона и код.\n\n"
        "📌 Чтобы выйти и войти заново, нажмите:\n"
        "⚙️ Настройки → 🔐 Авторизация → Войти в аккаунт"
    )
    send_new_message(user_id, text)

# ===================== ВЫХОД ИЗ АККАУНТА =====================
@bot.callback_query_handler(func=lambda call: call.data == "logout")
def logout_handler(call):
    user_id = call.message.chat.id
    data = load_data()
    if str(user_id) in data.get("user_sessions", {}):
        del data["user_sessions"][str(user_id)]
    delete_session_file(user_id)
    if str(user_id) in data["users"]:
        data["users"][str(user_id)]["logged_in"] = False
        if "phone" in data["users"][str(user_id)]:
            del data["users"][str(user_id)]["phone"]
    save_data(data)
    stop_userbot(user_id)
    send_new_message(user_id, "🚪 <b>Вы успешно вышли из аккаунта.</b>\nЮзербот остановлен.")
    show_main_menu(call.message)

# ===================== НАСТРОЙКА ИИ (С РОЛЬЮ) =====================
@bot.callback_query_handler(func=lambda call: call.data == "setup_ai")
def setup_ai_start(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    msg = send_new_message(call.message.chat.id, "🤖 <b>НАСТРОЙКА ИИ</b>\n\nШаг 1: Как называть твоего ИИ-двойника?")
    bot.register_next_step_handler(msg, process_ai_name)

def process_ai_name(message):
    user_id = message.chat.id
    if not is_authorized(user_id):
        return
    user_data = get_user(user_id) or {}
    if "ai_profile" not in user_data:
        user_data["ai_profile"] = {}
    user_data["ai_profile"]["name"] = message.text.strip()
    save_user(user_id, user_data)
    msg = send_new_message(user_id, "Шаг 2: В каком стиле он должен общаться?")
    bot.register_next_step_handler(msg, process_ai_style)

def process_ai_style(message):
    user_id = message.chat.id
    if not is_authorized(user_id):
        return
    user_data = get_user(user_id) or {}
    if "ai_profile" not in user_data:
        user_data["ai_profile"] = {}
    user_data["ai_profile"]["style"] = message.text.strip()
    save_user(user_id, user_data)
    msg = send_new_message(user_id, "Шаг 3: Напиши любимые фразы через запятую (можно пропустить):")
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_phrases"))
    bot.register_next_step_handler(msg, process_ai_phrases, markup)

def process_ai_phrases(message, markup=None):
    user_id = message.chat.id
    if not is_authorized(user_id):
        return
    user_data = get_user(user_id) or {}
    if "ai_profile" not in user_data:
        user_data["ai_profile"] = {}
    user_data["ai_profile"]["phrases"] = message.text.strip() if message.text != "/skip" else ""
    save_user(user_id, user_data)
    msg = send_new_message(user_id, "Шаг 4: Укажите вашу роль (например, 'воспитатель', 'учитель') или пропустите:")
    markup = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_role"))
    bot.register_next_step_handler(msg, process_ai_role)

def process_ai_role(message):
    user_id = message.chat.id
    if not is_authorized(user_id):
        return
    user_data = get_user(user_id) or {}
    if "ai_profile" not in user_data:
        user_data["ai_profile"] = {}
    user_data["ai_profile"]["role"] = message.text.strip() if message.text != "/skip" else ""
    save_user(user_id, user_data)
    send_new_message(user_id, "✅ <b>Профиль ИИ успешно сохранён!</b>")
    show_main_menu(message)

@bot.callback_query_handler(func=lambda call: call.data == "skip_phrases")
def skip_phrases(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    user_data = get_user(user_id) or {}
    if "ai_profile" not in user_data:
        user_data["ai_profile"] = {}
    user_data["ai_profile"]["phrases"] = ""
    save_user(user_id, user_data)
    delete_old_bot_message(user_id)
    msg = send_new_message(user_id, "Шаг 4: Укажите вашу роль (например, 'воспитатель', 'учитель') или пропустите:")
    markup = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_role"))
    bot.register_next_step_handler(msg, process_ai_role)

@bot.callback_query_handler(func=lambda call: call.data == "skip_role")
def skip_role(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    user_data = get_user(user_id) or {}
    if "ai_profile" not in user_data:
        user_data["ai_profile"] = {}
    user_data["ai_profile"]["role"] = ""
    save_user(user_id, user_data)
    delete_old_bot_message(user_id)
    send_new_message(user_id, "✅ <b>Профиль ИИ успешно сохранён!</b>")
    show_main_menu(call.message)

# ===================== НОВЫЕ ОБРАБОТЧИКИ: ТЕМЫ И УВАЖИТЕЛЬНЫЕ ОБРАЩЕНИЯ =====================
# ---- Меню тем ----
@bot.callback_query_handler(func=lambda call: call.data == "topics_menu")
def topics_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("➕ Добавить тему", callback_data="add_topic"))
    markup.row(types.InlineKeyboardButton("📋 Список тем", callback_data="list_topics"))
    markup.row(types.InlineKeyboardButton("🗑️ Удалить тему", callback_data="delete_topic"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, "📋 <b>Управление темами</b>\n\nЗдесь вы можете создавать темы для автоматического ответа на определённые сообщения в чатах.", reply_markup=markup)

topic_creation_data = {}

@bot.callback_query_handler(func=lambda call: call.data == "add_topic")
def add_topic_start(call):
    user_id = call.message.chat.id
    topic_creation_data[user_id] = {"examples": []}
    msg = send_new_message(user_id, "📝 <b>Введите название темы</b> (например, 'Приветствие'):")
    bot.register_next_step_handler(msg, process_topic_name)

def process_topic_name(message):
    user_id = message.chat.id
    topic_name = message.text.strip()
    if not topic_name:
        send_new_message(user_id, "❌ Название не может быть пустым. Попробуйте снова.")
        add_topic_start(message)
        return
    topic_creation_data[user_id]["name"] = topic_name
    msg = send_new_message(user_id, f"📝 <b>Введите пример сообщения</b> (или отправьте /done, чтобы закончить):")
    bot.register_next_step_handler(msg, process_topic_example)

def process_topic_example(message):
    user_id = message.chat.id
    if message.text == "/done":
        if len(topic_creation_data[user_id]["examples"]) == 0:
            send_new_message(user_id, "❌ Нужно добавить хотя бы один пример.")
            msg = send_new_message(user_id, "📝 Введите пример сообщения (или /done):")
            bot.register_next_step_handler(msg, process_topic_example)
            return
        msg = send_new_message(user_id, "💬 <b>Введите ответ бота</b> (что отправлять при совпадении):")
        bot.register_next_step_handler(msg, process_topic_response)
        return
    if message.text:
        topic_creation_data[user_id]["examples"].append(message.text)
        send_new_message(user_id, f"✅ Пример добавлен. Всего: {len(topic_creation_data[user_id]['examples'])}\n\nОтправьте ещё пример или /done для завершения.")
        msg = send_new_message(user_id, "📝 Введите пример сообщения (или /done):")
        bot.register_next_step_handler(msg, process_topic_example)
    else:
        send_new_message(user_id, "❌ Отправьте текстовое сообщение.")
        msg = send_new_message(user_id, "📝 Введите пример сообщения (или /done):")
        bot.register_next_step_handler(msg, process_topic_example)

def process_topic_response(message):
    user_id = message.chat.id
    response = message.text.strip()
    if not response:
        send_new_message(user_id, "❌ Ответ не может быть пустым. Попробуйте снова:")
        msg = send_new_message(user_id, "💬 Введите ответ бота:")
        bot.register_next_step_handler(msg, process_topic_response)
        return
    topic_name = topic_creation_data[user_id]["name"]
    examples = topic_creation_data[user_id]["examples"]
    save_user_topic(user_id, topic_name, examples, response)
    del topic_creation_data[user_id]
    send_new_message(user_id, f"✅ <b>Тема '{topic_name}' успешно создана!</b>\n\nПримеры: {len(examples)}\nОтвет: {response}")
    topics_menu(message)

@bot.callback_query_handler(func=lambda call: call.data == "list_topics")
def list_topics(call):
    user_id = call.message.chat.id
    topics = get_user_topics(user_id)
    if not topics:
        send_new_message(user_id, "📭 У вас пока нет тем.")
        topics_menu(call)
        return
    text = "📋 <b>Ваши темы:</b>\n\n"
    for name, data in topics.items():
        text += f"🔹 <b>{name}</b>\n"
        text += f"   Примеров: {len(data['examples'])}\n"
        text += f"   Ответ: {data['response'][:50]}...\n\n"
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="topics_menu"))
    send_new_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "delete_topic")
def delete_topic_menu(call):
    user_id = call.message.chat.id
    topics = get_user_topics(user_id)
    if not topics:
        send_new_message(user_id, "📭 Нет тем для удаления.")
        topics_menu(call)
        return
    markup = types.InlineKeyboardMarkup()
    for name in topics.keys():
        markup.row(types.InlineKeyboardButton(f"🗑️ {name}", callback_data=f"delete_topic_{name}"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="topics_menu"))
    send_new_message(user_id, "Выберите тему для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_topic_"))
def delete_topic_confirm(call):
    user_id = call.message.chat.id
    topic_name = call.data.split("_", 2)[2]
    if delete_user_topic(user_id, topic_name):
        bot.answer_callback_query(call.id, f"✅ Тема '{topic_name}' удалена", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка удаления", show_alert=True)
    delete_topic_menu(call)

# ---- Меню уважительных обращений ----
@bot.callback_query_handler(func=lambda call: call.data == "respect_menu")
def respect_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_respect"))
    markup.row(types.InlineKeyboardButton("📋 Список", callback_data="list_respect"))
    markup.row(types.InlineKeyboardButton("➖ Удалить", callback_data="remove_respect"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, "🙏 <b>Уважительные обращения</b>\n\nЗдесь вы можете указать пользователей, к которым бот должен обращаться на 'Вы' (например, воспитатели, учителя).", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_respect")
def add_respect_start(call):
    user_id = call.message.chat.id
    msg = send_new_message(user_id, "📝 Введите @username пользователя (например, @ivan):")
    bot.register_next_step_handler(msg, process_add_respect)

def process_add_respect(message):
    user_id = message.chat.id
    username = message.text.strip()
    if not username.startswith("@"):
        username = "@" + username
    if add_respected_user(user_id, username):
        send_new_message(user_id, f"✅ {username} добавлен в список уважительных обращений.")
    else:
        send_new_message(user_id, f"ℹ️ {username} уже в списке.")
    respect_menu(message)

@bot.callback_query_handler(func=lambda call: call.data == "list_respect")
def list_respect(call):
    user_id = call.message.chat.id
    users = get_respected_users(user_id)
    if not users:
        send_new_message(user_id, "📭 Список пуст.")
        respect_menu(call)
        return
    text = "📋 <b>Список уважительных обращений:</b>\n\n" + "\n".join([f"• {u}" for u in users])
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="respect_menu"))
    send_new_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "remove_respect")
def remove_respect_menu(call):
    user_id = call.message.chat.id
    users = get_respected_users(user_id)
    if not users:
        send_new_message(user_id, "📭 Нет пользователей для удаления.")
        respect_menu(call)
        return
    markup = types.InlineKeyboardMarkup()
    for u in users:
        markup.row(types.InlineKeyboardButton(f"❌ {u}", callback_data=f"remove_respect_{u}"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="respect_menu"))
    send_new_message(user_id, "Выберите пользователя для удаления из списка:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_respect_"))
def remove_respect_confirm(call):
    user_id = call.message.chat.id
    username = call.data.split("_", 2)[2]
    if remove_respected_user(user_id, username):
        bot.answer_callback_query(call.id, f"✅ {username} удалён", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка удаления", show_alert=True)
    remove_respect_menu(call)

# ===================== ПРОСМОТР ЧАТОВ =====================
@bot.callback_query_handler(func=lambda call: call.data == "view_ai_chats")
def view_ai_chats(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    data = load_data()
    ai_chats = data.get("ai_chats", [])
    text = "🤖 <b>Активные чаты с ИИ:</b>\n\n" + ("\n".join([f"• ID: <code>{cid}</code>" for cid in ai_chats]) if ai_chats else "Нет активных чатов.")
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(call.message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "view_muted_chats")
def view_muted_chats(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    data = load_data()
    muted_chats = data.get("muted_chats", [])
    text = "🔇 <b>Замученные чаты:</b>\n\n" + ("\n".join([f"• ID: <code>{cid}</code>" for cid in muted_chats]) if muted_chats else "Нет замученных чатов.")
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(call.message.chat.id, text, reply_markup=markup)

# ===================== ИНСТРУКЦИЯ ПО РАБОТЕ С ЮЗЕРАМИ =====================
@bot.callback_query_handler(func=lambda call: call.data == "user_commands")
def user_commands_handler(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    text = (
        "👤 <b>РАБОТА С ПОЛЬЗОВАТЕЛЯМИ</b>\n\n"
        "Используйте команды с @username для работы с конкретными пользователями:\n\n"
        "🔹 <code>/mute @username</code> - замутить чат с пользователем\n"
        "🔹 <code>/unmute @username</code> - размутить чат\n"
        "🔹 <code>/ai @username</code> - включить ИИ в чате\n"
        "🔹 <code>/ai_off @username</code> - выключить ИИ\n\n"
        "📌 <b>Пример:</b> <code>/mute @ivan</code>\n\n"
        "⚠️ Команды работают только в личных чатах с ботом, чтобы другие не видели ваши действия."
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(call.message.chat.id, text, reply_markup=markup)

# ===================== СТАТИСТИКА =====================
@bot.callback_query_handler(func=lambda call: call.data == "user_stats")
def user_stats_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    data = load_data()
    user_stats = data.get("user_stats", {})
    total_users = len(user_stats)
    typing_speed = get_typing_speed(user_id)
    user_stat = user_stats.get(str(user_id), {})
    user_messages = user_stat.get("messages", 0)
    user_first_use = user_stat.get("first_use", "Неизвестно")
    user_last_use = user_stat.get("last_use", "Неизвестно")
    text = (
        "📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>Общая статистика:</b>\n"
        f"• Всего пользователей: <b>{total_users}</b>\n"
        f"• Активных чатов ИИ: <b>{len(data.get('ai_chats', []))}</b>\n"
        f"• Замученных чатов: <b>{len(data.get('muted_chats', []))}</b>\n"
        f"• Сообщений в корзине: <b>{sum(len(v) for v in data.get('deleted_messages', {}).values())}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>Ваша статистика:</b>\n"
        f"• Отправлено сообщений: <b>{user_messages}</b>\n"
        f"• Скорость печати: <b>{typing_speed} символов/сек</b>\n"
        f"• Первое использование: <code>{user_first_use}</code>\n"
        f"• Последнее использование: <code>{user_last_use}</code>\n"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_stats"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "refresh_stats")
def refresh_stats(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    user_stats_menu(call)

# ===================== НАСТРОЙКА СКОРОСТИ ПЕЧАТИ =====================
@bot.callback_query_handler(func=lambda call: call.data == "typing_speed")
def typing_speed_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    current_speed = get_typing_speed(user_id)
    text = (
        "⌨️ <b>НАСТРОЙКА СКОРОСТИ ПЕЧАТИ</b>\n\n"
        f"Текущая скорость: <b>{current_speed} символов/сек</b>\n\n"
        "Бот будет печатать ответы ИИ с этой скоростью.\n"
        "Чем больше скорость, тем быстрее появится ответ.\n\n"
        "📌 <b>Пример:</b>\n"
        "Ответ ИИ: 'Привет! Как дела?' (17 символов)\n"
        f"Скорость: {current_speed} символов/сек\n"
        f"Время печати: {17 / current_speed:.1f} секунд\n\n"
        "⚠️ Рекомендуемые значения: 2-10 символов/сек"
    )
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = [
        types.InlineKeyboardButton("1", callback_data="speed_1"),
        types.InlineKeyboardButton("2", callback_data="speed_2"),
        types.InlineKeyboardButton("3", callback_data="speed_3"),
        types.InlineKeyboardButton("4", callback_data="speed_4"),
        types.InlineKeyboardButton("5", callback_data="speed_5"),
        types.InlineKeyboardButton("7", callback_data="speed_7"),
        types.InlineKeyboardButton("10", callback_data="speed_10"),
        types.InlineKeyboardButton("15", callback_data="speed_15"),
        types.InlineKeyboardButton("20", callback_data="speed_20")
    ]
    markup.add(*buttons)
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("speed_"))
def set_typing_speed_handler(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    speed = int(call.data.split("_")[1])
    set_typing_speed(user_id, speed)
    bot.answer_callback_query(call.id, f"✅ Скорость установлена: {speed} символов/сек", show_alert=True)
    typing_speed_menu(call)

# ===================== ГЛАВНОЕ МЕНЮ =====================
@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.chat.id
    increment_user_stats(user_id)
    user_data = get_user(user_id) or {}
    if not user_data.get("tos_accepted"):
        show_tos(message)
        return
    show_main_menu(message)

def show_main_menu(message):
    uid = message.chat.id
    user_data = get_user(uid) or {}
    is_logged_in = user_data.get("logged_in", False)
    total_users = get_total_users()
    is_admin_user = is_admin(uid)
    is_support_user = is_support(uid)
    markup = types.InlineKeyboardMarkup()
    if not is_logged_in:
        markup.row(types.InlineKeyboardButton("🔐 Войти в аккаунт", callback_data="login_action"))
    if is_logged_in:
        markup.row(types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu"))
        markup.row(types.InlineKeyboardButton("🤖 Управление ИИ", callback_data="ai_menu"))
        markup.row(types.InlineKeyboardButton("🔇 Управление чатами", callback_data="chats_menu"))
        markup.row(types.InlineKeyboardButton("🗑️ Корзина", callback_data="view_trash"))
        markup.row(types.InlineKeyboardButton("📊 Статистика", callback_data="user_stats"))
        markup.row(types.InlineKeyboardButton("📋 Темы", callback_data="topics_menu"))
        markup.row(types.InlineKeyboardButton("🙏 Уважительные обращения", callback_data="respect_menu"))
        markup.row(types.InlineKeyboardButton("🚪 Выйти", callback_data="logout"))
    if is_support_user or is_admin_user:
        markup.row(types.InlineKeyboardButton("🔄 Статус бота", callback_data="bot_status"))
    if is_admin_user:
        markup.row(types.InlineKeyboardButton("👑 Панель администратора", callback_data="admin_panel"))
    markup.row(types.InlineKeyboardButton("🆘 Поддержка", callback_data="support_command"))
    markup.row(types.InlineKeyboardButton("📜 Соглашение", callback_data="view_current_tos"))
    if is_logged_in:
        text = (
            "🏠 <b>d.Check Панель Управления</b>\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"✅ Аккаунт: <b>активен</b>\n\n"
            "Выберите раздел для управления:"
        )
    else:
        text = (
            "🏠 <b>d.Check Панель Управления</b>\n\n"
            f"👥 Пользователей: {total_users}\n"
            "❌ Аккаунт: <b>не активен</b>\n\n"
            "Для работы войдите в аккаунт Telegram.\n"
            "Нажмите кнопку 'Войти в аккаунт' ниже."
        )
    text += "\n\n━━━━━━━━━━━━━━━━━━\n"
    text += f"⏰ {datetime.datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
    send_new_message(uid, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "login_action")
def login_action_handler(call):
    start_auth_process(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main" or call.data == "support_command")
def back_to_main_handler(call):
    if call.data == "support_command":
        support_command(call.message)
    else:
        show_main_menu(call.message)

# ===================== МЕНЮ НАСТРОЕК =====================
@bot.callback_query_handler(func=lambda call: call.data == "settings_menu")
def settings_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    text = (
        "⚙️ <b>НАСТРОЙКИ</b>\n\n"
        "Управляйте параметрами бота:\n\n"
        "🔐 Настройки авторизации\n"
        "🔔 Уведомления об удалении\n"
        "⌨️ Скорость печати ИИ\n"
        "⚙️ Управление командами"
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔐 Авторизация", callback_data="auth_settings"))
    markup.row(types.InlineKeyboardButton("🔔 Уведомления", callback_data="toggle_notifications"))
    markup.row(types.InlineKeyboardButton("⌨️ Скорость печати", callback_data="typing_speed"))
    markup.row(types.InlineKeyboardButton("⚙️ Команды", callback_data="toggle_commands"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, text, reply_markup=markup)

# ===================== МЕНЮ ИИ =====================
@bot.callback_query_handler(func=lambda call: call.data == "ai_menu")
def ai_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    data = load_data()
    ai_chats = data.get("ai_chats", [])
    text = (
        "🤖 <b>УПРАВЛЕНИЕ ИИ</b>\n\n"
        f"Активных чатов с ИИ: <b>{len(ai_chats)}</b>\n\n"
        "Настройте профиль ИИ или посмотрите активные чаты."
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("⚙️ Настроить профиль", callback_data="setup_ai"))
    markup.row(types.InlineKeyboardButton("🤖 Активные чаты", callback_data="view_ai_chats"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, text, reply_markup=markup)

# ===================== МЕНЮ ЧАТОВ =====================
@bot.callback_query_handler(func=lambda call: call.data == "chats_menu")
def chats_menu(call):
    user_id = call.message.chat.id
    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "⚠️ Сначала войдите в аккаунт!", show_alert=True)
        return
    data = load_data()
    muted_chats = data.get("muted_chats", [])
    text = (
        "🔇 <b>УПРАВЛЕНИЕ ЧАТАМИ</b>\n\n"
        f"Замученных чатов: <b>{len(muted_chats)}</b>\n\n"
        "Управляйте мутом и автоматической очисткой."
    )
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔇 Замученные чаты", callback_data="view_muted_chats"))
    markup.row(types.InlineKeyboardButton("🧹 Автоочистка", callback_data="clean_chats_menu"))
    markup.row(types.InlineKeyboardButton("👤 Работа с юзерами", callback_data="user_commands"))
    markup.row(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    send_new_message(user_id, text, reply_markup=markup)

# ===================== ОБРАБОТЧИКИ КОМАНД С @USERNAME (ОСТАВЛЯЕМ ТОЛЬКО ДЛЯ ИНТЕРФЕЙСА) =====================
@bot.message_handler(commands=["mute", "unmute", "ai", "ai_off"])
def handle_user_commands(message):
    # Этот обработчик остаётся только для информации, реальная работа через юзербота
    user_id = message.chat.id
    if not is_authorized(user_id):
        bot.send_message(user_id, "⚠️ Сначала войдите в аккаунт через кнопку 'Войти в аккаунт'", parse_mode='HTML')
        return
    if is_command_blocked(message.chat.id):
        return
    if message.chat.type != "private":
        bot.send_message(user_id, "⚠️ Команды с @username работают только в личных сообщениях с ботом!\n\nДля работы в группах используйте юзербота (он уже активен, если вы вошли в аккаунт).", parse_mode='HTML')
        return
    command = message.text.split()[0] if message.text else ""
    args = message.text.replace(command, "").strip() if message.text else ""
    if not args:
        bot.send_message(user_id, f"⚠️ Используйте: <code>{command} @username</code>", parse_mode='HTML')
        return
    # Если юзербот не активен, можно выполнить через временное подключение (как было раньше)
    # Но сейчас мы рекомендуем использовать юзербота в группах.

# ===================== УПРАВЛЕНИЕ ЮЗЕРБОТАМИ =====================
def start_userbot(user_id):
    method = get_auth_method(user_id)
    if method == 1:
        session_data = get_user_session_data(user_id)
        if not session_data:
            return
        start_userbot_method_1(user_id, session_data)
    else:
        if not session_file_exists(user_id):
            return
        start_userbot_method_7(user_id)

def start_userbot_method_1(user_id, session_data):
    user_data = get_user(user_id) or {}
    if not user_data.get("logged_in", False):
        return
    stop_userbot(user_id)
    task = loop.create_task(run_userbot_method_1(user_id, session_data))
    user_tasks[user_id] = task

def start_userbot_method_7(user_id):
    user_data = get_user(user_id) or {}
    if not user_data.get("logged_in", False):
        return
    stop_userbot(user_id)
    task = loop.create_task(run_userbot_method_7(user_id))
    user_tasks[user_id] = task

# ========== ИСПРАВЛЕННАЯ ФУНКЦИЯ ОСТАНОВКИ ==========
def stop_userbot(user_id):
    if user_id in active_clients:
        try:
            client = active_clients[user_id]
            if client and client.is_connected():
                # Безопасное отключение через asyncio
                asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
            # Удаляем из словаря после попытки отключения
            del active_clients[user_id]
        except Exception as e:
            print(f"❌ Ошибка остановки юзербота {user_id}: {e}")
    if user_id in user_tasks:
        user_tasks[user_id].cancel()
        del user_tasks[user_id]

async def run_userbot_method_1(user_id, session_data):
    global BOT_ID
    if BOT_ID is None:
        try:
            BOT_ID = bot.get_me().id
        except:
            BOT_ID = 0
    client = TelegramClient(
        StringSession(session_data["session"]),
        session_data["api_id"],
        session_data["api_hash"]
    )
    active_clients[user_id] = client
    try:
        await run_userbot_handlers(user_id, client)
    except Exception as e:
        print(f"❌ [{user_id}] Ошибка юзербота: {e}")
    finally:
        if user_id in active_clients:
            del active_clients[user_id]
        print(f"🔄 [{user_id}] Юзербот отключен")

async def run_userbot_method_7(user_id):
    global BOT_ID
    if BOT_ID is None:
        try:
            BOT_ID = bot.get_me().id
        except:
            BOT_ID = 0
    client = TelegramClient(
        get_session_file(user_id),
        API_ID,
        API_HASH
    )
    active_clients[user_id] = client
    try:
        await run_userbot_handlers(user_id, client)
    except Exception as e:
        print(f"❌ [{user_id}] Ошибка юзербота: {e}")
    finally:
        if user_id in active_clients:
            del active_clients[user_id]
        print(f"🔄 [{user_id}] Юзербот отключен")

# ===================== ИСПРАВЛЕННЫЙ ОБРАБОТЧИК (с игнорированием ЛС и правильным кешированием) =====================
async def run_userbot_handlers(user_id, client):
    global BOT_ID
    if BOT_ID is None:
        try:
            BOT_ID = bot.get_me().id
        except:
            BOT_ID = 0

    me = await client.get_me()
    my_id = me.id

    try:
        # ========== НОВОЕ: ОБРАБОТКА ИСХОДЯЩИХ КОМАНД (УДАЛЯЮТСЯ ВЕЗДЕ) ==========
        @client.on(events.NewMessage(outgoing=True))
        async def handle_outgoing_commands(event):
            if not event.text or not event.text.startswith('/'):
                return
            if event.chat_id == user_id or event.chat_id == BOT_ID:
                return
            if is_command_blocked(event.chat_id):
                return

            command = event.text.split()[0].lower()
            chat_id = event.chat_id

            # Удаляем команду сразу
            await event.delete()

            data = load_data()

            if command == '/mute':
                if chat_id not in data["muted_chats"]:
                    data["muted_chats"].append(chat_id)
                    save_data(data)
                    await client.send_message(user_id, f"🔇 Чат {chat_id} замучен.")
                else:
                    await client.send_message(user_id, f"ℹ️ Чат {chat_id} уже замучен.")
            elif command == '/unmute':
                if chat_id in data["muted_chats"]:
                    data["muted_chats"].remove(chat_id)
                    save_data(data)
                    await client.send_message(user_id, f"🔊 Чат {chat_id} размучен.")
                else:
                    await client.send_message(user_id, f"ℹ️ Чат {chat_id} не был замучен.")
            elif command == '/ai':
                if chat_id not in data["ai_chats"]:
                    data["ai_chats"].append(chat_id)
                    save_data(data)
                    await client.send_message(user_id, f"🤖 ИИ включен в чате {chat_id}.")
                else:
                    await client.send_message(user_id, f"ℹ️ ИИ уже включен в чате {chat_id}.")
            elif command == '/ai_off':
                if chat_id in data["ai_chats"]:
                    data["ai_chats"].remove(chat_id)
                    save_data(data)
                    await client.send_message(user_id, f"🛑 ИИ выключен в чате {chat_id}.")
                else:
                    await client.send_message(user_id, f"ℹ️ ИИ не был включен в чате {chat_id}.")
            elif command == '/check':
                if str(chat_id) in data.get("active_topics_chats", {}):
                    del data["active_topics_chats"][str(chat_id)]
                    save_data(data)
                    await client.send_message(user_id, f"⏹ Отслеживание тем выключено в чате {chat_id}.")
                else:
                    if "active_topics_chats" not in data:
                        data["active_topics_chats"] = {}
                    data["active_topics_chats"][str(chat_id)] = True
                    save_data(data)
                    await client.send_message(user_id, f"▶️ Отслеживание тем включено в чате {chat_id}.")

        # ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ==========
        @client.on(events.NewMessage(pattern=r'/mute', outgoing=True))
        async def mute_handler(event):
            if event.chat_id == user_id or (BOT_ID is not None and event.chat_id == BOT_ID):
                return
            if is_command_blocked(event.chat_id):
                return
            data = load_data()
            chat_id = event.chat_id
            if chat_id not in data["muted_chats"]:
                data["muted_chats"].append(chat_id)
                save_data(data)
            await event.delete()
            print(f"🔇 [{user_id}] MUTE для чата: {chat_id}")

        @client.on(events.NewMessage(pattern=r'/unmute', outgoing=True))
        async def unmute_handler(event):
            if event.chat_id == user_id or (BOT_ID is not None and event.chat_id == BOT_ID):
                return
            if is_command_blocked(event.chat_id):
                return
            data = load_data()
            chat_id = event.chat_id
            if chat_id in data["muted_chats"]:
                data["muted_chats"].remove(chat_id)
                save_data(data)
            await event.delete()
            print(f"🔊 [{user_id}] MUTE выключен для чата: {chat_id}")

        @client.on(events.NewMessage(pattern=r'/ai$', outgoing=True))
        async def ai_on_handler(event):
            if event.chat_id == user_id or (BOT_ID is not None and event.chat_id == BOT_ID):
                return
            if is_command_blocked(event.chat_id):
                return
            data = load_data()
            chat_id = event.chat_id
            if chat_id not in data["ai_chats"]:
                data["ai_chats"].append(chat_id)
                save_data(data)
            await event.delete()
            print(f"🤖 [{user_id}] ИИ ВКЛЮЧЕН: {chat_id}")

        @client.on(events.NewMessage(pattern=r'/ai_off', outgoing=True))
        async def ai_off_handler(event):
            if event.chat_id == user_id or (BOT_ID is not None and event.chat_id == BOT_ID):
                return
            if is_command_blocked(event.chat_id):
                return
            data = load_data()
            chat_id = event.chat_id
            if chat_id in data["ai_chats"]:
                data["ai_chats"].remove(chat_id)
                save_data(data)
            await event.delete()
            print(f"🛑 [{user_id}] ИИ ВЫКЛЮЧЕН: {chat_id}")

        @client.on(events.NewMessage())
        async def message_handler(event):
            # Игнорируем исходящие от бота и в чате с самим собой
            if event.sender_id == BOT_ID or (BOT_ID is not None and event.chat_id == BOT_ID):
                return
            if event.chat_id == user_id:
                return
            # Игнорируем личные сообщения (чтобы не мешать)
            if event.is_private:
                return
            # Кешируем все сообщения (только из групп)
            if event.message:
                try:
                    sender = await event.get_sender()
                    sender_name = getattr(sender, 'first_name', "Неизвестный") or "Неизвестный"
                except:
                    sender_name = "Неизвестный"
                message_cache[event.id] = {
                    'text': event.text or "[Медиа/Стикер]",
                    'chat_id': event.chat_id,
                    'sender_id': event.sender_id,
                    'sender_name': sender_name
                }
                if len(message_cache) > MAX_CACHE_SIZE:
                    message_cache.pop(next(iter(message_cache)))

                # Обрабатываем входящие сообщения (не исходящие) для мута и ИИ
                if not event.out:
                    data = load_data()
                    chat_id = event.chat_id
                    if chat_id in data.get("muted_chats", []):
                        try:
                            await event.delete()
                        except:
                            pass
                        return
                    if chat_id in data.get("ai_chats", []) and event.text:
                        try:
                            await event.client.send_read_acknowledge(chat_id)
                        except Exception as e:
                            print(f"Ошибка прочтения: {e}")
                        typing_speed = get_typing_speed(user_id)
                        history = []
                        try:
                            async for msg in event.client.iter_messages(chat_id, limit=15):
                                if msg.text:
                                    history.append(f"{'Я' if msg.out else 'Собеседник'}: {msg.text}")
                        except:
                            pass
                        # Передаём username отправителя для уважительного обращения
                        sender_username = event.sender.username if event.sender else None
                        reply = call_deepseek_ai(event.text, user_id, chat_id, history, sender_username)
                        if reply:
                            chars_count = len(reply)
                            typing_time = max(min(chars_count / typing_speed, 15.0), 2.0)
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            try:
                                async with event.client.action(chat_id, 'typing'):
                                    await asyncio.sleep(typing_time)
                                await event.reply(reply, parse_mode='md')
                            except:
                                pass

        @client.on(events.MessageDeleted())
        async def deleted_handler(event):
            if event.chat_id == user_id or (BOT_ID is not None and event.chat_id == BOT_ID):
                return
            # Игнорируем удаления в личных чатах
            if event.is_private:
                return
            for msg_id in event.deleted_ids:
                if msg_id in message_cache:
                    msg_data = message_cache[msg_id]
                    add_deleted_message(
                        user_id,
                        msg_data['sender_id'],
                        msg_data['sender_name'],
                        msg_data['text'],
                        msg_id
                    )
                    data = load_data()
                    if data.get("show_deleted_notifications", True):
                        try:
                            notification_text = (
                                "🗑 <b>УДАЛЕНО СООБЩЕНИЕ</b>\n"
                                f"👤 От: <code>{msg_data['sender_name']}</code>\n\n"
                                f"📝 {msg_data['text']}"
                            )
                            def send_and_delete_notify():
                                try:
                                    msg = bot.send_message(user_id, notification_text, parse_mode='HTML')
                                    time.sleep(10)
                                    bot.delete_message(user_id, msg.message_id)
                                except:
                                    pass
                            threading.Thread(target=send_and_delete_notify, daemon=True).start()
                        except Exception as e:
                            print(f"❌ Ошибка уведомления: {e}")
                    del message_cache[msg_id]

        await client.start()
        print(f"✅ [{user_id}] Юзербот успешно работает!")
        await client.run_until_disconnected()
    except Exception as e:
        print(f"❌ [{user_id}] Ошибка юзербота: {e}")
        raise

async def auto_start_userbots():
    while True:
        try:
            data = load_data()
            sessions = data.get("user_sessions", {})
            for user_id_str, session_data in sessions.items():
                user_id = int(user_id_str)
                if user_id not in active_clients:
                    user_data = get_user(user_id) or {}
                    if user_data.get("logged_in"):
                        print(f"🚀 Автозапуск юзербота для пользователя {user_id}")
                        start_userbot(user_id)
            if os.path.exists(SESSIONS_DIR):
                for file in os.listdir(SESSIONS_DIR):
                    if file.endswith(".session"):
                        try:
                            user_id = int(file.replace("user_", "").replace(".session", ""))
                            if user_id not in active_clients:
                                user_data = get_user(user_id) or {}
                                if user_data.get("logged_in"):
                                    print(f"🚀 Автозапуск юзербота для пользователя {user_id} (способ 7)")
                                    start_userbot(user_id)
                        except:
                            pass
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ Ошибка в auto_start_userbots: {e}")
            await asyncio.sleep(10)

def run_telebot():
    try:
        print("🚀 Запуск Telegram бота...")
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")

def signal_handler(sig, frame):
    print("\n🛑 Получен сигнал остановки...")
    for user_id in list(active_clients.keys()):
        stop_userbot(user_id)
    loop.stop()
    sys.exit(0)

# ===================== ВЕБ-СЕРВЕР ДЛЯ RENDER =====================
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "d.Check", "users": get_total_users(), "active_userbots": len(active_clients)})

@app.route('/ping')
def ping():
    return "pong", 200

# ===================== ЗАПУСК =====================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ d.Check ЗАПУЩЕН")
    if 0 in ADMIN_LIST:
        print("⚠️ ВНИМАНИЕ: ADMIN_ID не установлен! Любой может войти в бота.")
    else:
        print(f"🔒 Безопасность включена. Владельцы: {ADMIN_LIST}")
    if SUPPORT_LIST:
        print(f"🆘 Поддержка: {SUPPORT_LIST}")
    print("=" * 50)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot_thread = threading.Thread(target=run_telebot, daemon=True)
    bot_thread.start()

    try:
        loop.run_until_complete(auto_start_userbots())
    except KeyboardInterrupt:
        print("🛑 Остановка скрипта...")
    finally:
        for user_id in list(active_clients.keys()):
            stop_userbot(user_id)
        loop.stop()
        print("✅ Бот остановлен")

    # Запускаем Flask для Render (health checks)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
