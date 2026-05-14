# get_dialog_reply_keyboard  

import logging
import asyncio
import time
import sys
import uuid
import os
import random
import re
import urllib.parse
import signal
import pickle
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ApplicationBuilder, PreCheckoutQueryHandler

from openai import OpenAI
import aiohttp

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8673933416:AAEjD5rPkTM6gykGYGPOXrroszlJvu5YeWk")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-5a1b7211be7d4ca5848323a13c17b0cc")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Принудительная установка владельца (замените на свой ID)
OWNER_CHAT_ID = 7666021527
ADMINS = {7666021527}
ADMIN_ROLES = {7666021527: "owner"}

deepseek_client = None
bot_paused = False
pause_reason = ""
DATA_FILE = "bot_data.pkl"

SUBSCRIPTION_PLANS = {
    "daily": {"name": "⭐ Дневная", "price": 1, "days": 1, "limits": {"requests_per_minute": 60, "cooldown": 1, "max_chats": 15, "max_saved": 200}, "description": "1 день: 60 запросов/мин, 15 чатов, 200 сохранений"},
    "basic": {"name": "🌟 Базовый", "price": 5, "days": 7, "limits": {"requests_per_minute": 60, "cooldown": 1, "max_chats": 15, "max_saved": 200}, "description": "7 дней: 60 запросов/мин, 15 чатов, 200 сохранений"},
    "premium": {"name": "💎 Премиум", "price": 15, "days": 30, "limits": {"requests_per_minute": 100, "cooldown": 0.5, "max_chats": 30, "max_saved": 500}, "description": "30 дней: 100 запросов/мин, 0.5 сек кулдаун, 30 чатов, 500 сохранений"},
    "vip": {"name": "👑 VIP", "price": 50, "days": 90, "limits": {"requests_per_minute": 200, "cooldown": 0, "max_chats": 100, "max_saved": 2000}, "description": "90 дней: 200 запросов/мин, без кулдауна, 100 чатов, 2000 сохранений"}
}

promocodes = {}
discounts = {}
subscriptions = {}
refund_requests = {}
support_messages = {}
user_balance = {}
giveaways = {}

disabled_features = {
    "subscription": False, "giveaways": False, "referral": False,
    "balance": False, "info": False, "weather": False, "save_messages": False
}

auto_reply_keywords = {
    "greetings": ["привет", "здравствуй", "hi", "hello", "хай", "ку", "доброе утро", "добрый день", "добрый вечер"],
    "how_are_you": ["как дела", "как жизнь", "как ты", "how are you", "как настроение"],
    "thanks": ["спасибо", "thanks", "thank you", "благодарю", "merci"],
    "bye": ["пока", "до свидания", "bye", "goodbye", "всего хорошего", "удачи"]
}

banned_words = {
    "ru": ['порно', 'секс', 'эротика', 'xxx', '18+', 'nsfw', 'порнография', 'hardcore', 'интим', 'обнаженный', 'голый'],
    "en": ['porn', 'sex', 'erotica', 'xxx', '18+', 'nsfw', 'pornography', 'hardcore', 'intimate', 'naked']
}

bot_settings = {
    "default_model": "deepseek-chat",
    "default_mode": "normal",
    "max_chats": 5,
    "max_saved_messages": 20,
    "default_requests_per_minute": 30,
    "default_requests_per_hour": 500,
    "default_requests_per_day": 1000,
    "default_cooldown": 10,
    "max_warnings": 3,
    "max_adult_attempts": 3,
    "api_call_cooldown": 1,
    "welcome_message": "🏢 Добро пожаловать, {name}!\n\n✨ AI-помощник на базе DeepSeek.\n📌 Текущий чат: {chat}\n\n💼 Напишите ваш вопрос.\n🔽 Управление через кнопки.",
    "enable_18_plus_filter": True,
    "enable_user_notes": True,
    "enable_activity_tracking": True,
    "custom_greeting": "",
    "custom_info": "",
    "message_style": "standard",
    "featured_channels": [],
    "enable_animations": False,
    "free_limits": {"requests_per_minute": 30, "cooldown": 10, "max_chats": 5, "max_saved": 20},
    "subscription_limits": SUBSCRIPTION_PLANS["basic"]["limits"],
    "referral_bonus": {"requests_per_minute": 5, "cooldown": 0, "max_chats": 2, "max_saved": 20, "days_valid": 3},
    "language": "ru",
    "max_response_length": 4000,
    "use_name_in_responses": True
}

DANGER_KEYWORDS = {
    "ru": ["самоубийство", "покончить с собой", "убить себя", "свести счеты с жизнью", "хочу умереть",
           "жизнь не имеет смысла", "не хочу жить", "наложить на себя руки", "суицид",
           "убить", "застрелить", "зарезать", "убийство", "смерть", "умереть", "погибнуть",
           "вред себе", "порезы", "таблетки", "выпрыгнуть", "повеситься"],
    "en": ["suicide", "kill myself", "end my life", "want to die", "self-harm", "cut myself"]
}

danger_alerts = []
safety_sessions = {}
pending_safety_reply = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

shutdown_flag = False
def signal_handler(signum, frame):
    global shutdown_flag
    logger.info(f"Сигнал {signum}, завершение...")
    shutdown_flag = True
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ========== ГЛОБАЛЬНЫЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЕЙ ==========
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

pending_save = {}
favorite_chats = defaultdict(set)
referrals = {}
pending_admin_action = {}
admin_menu_state = {}

MAX_CHATS = bot_settings["max_chats"]
MAX_SAVED_MESSAGES = bot_settings["max_saved_messages"]
DEFAULT_REQUESTS_PER_MINUTE = bot_settings["default_requests_per_minute"]
DEFAULT_REQUESTS_PER_HOUR = bot_settings["default_requests_per_hour"]
DEFAULT_REQUESTS_PER_DAY = bot_settings["default_requests_per_day"]
DEFAULT_COOLDOWN = bot_settings["default_cooldown"]
MAX_WARNINGS = bot_settings["max_warnings"]
MAX_ADULT_ATTEMPTS = bot_settings["max_adult_attempts"]
API_CALL_COOLDOWN = bot_settings["api_call_cooldown"]

# ========== БЕЗОПАСНЫЕ РЕЖИМЫ ==========
MODES = {
    "normal": {"name": "💬 Обычный", "emoji": "💬", "system_prompt": "Ты вежливый и полезный ассистент. Отвечай кратко и по делу. {custom_note}", "description": "Вежливые и полезные ответы"},
    "creative": {"name": "🎨 Креативный", "emoji": "🎨", "system_prompt": "Ты креативный и вдохновляющий ассистент. Давай необычные, творческие ответы. Используй метафоры и образное мышление. {custom_note}", "description": "Творческие и вдохновляющие ответы"},
    "professional": {"name": "📊 Профессиональный", "emoji": "📊", "system_prompt": "Ты профессиональный ассистент. Отвечай чётко, структурированно, по делу. Используй списки и конкретные рекомендации. {custom_note}", "description": "Структурированные и профессиональные ответы"},
    "friendly": {"name": "🤗 Дружелюбный", "emoji": "🤗", "system_prompt": "Ты дружелюбный и поддерживающий ассистент. Отвечай тепло, с эмпатией, будь готов выслушать и помочь. {custom_note}", "description": "Тёплые и поддерживающие ответы"},
    "concise": {"name": "⚡ Краткий", "emoji": "⚡", "system_prompt": "Ты ассистент, который отвечает максимально кратко и по существу. Без лишних слов, только факты или конкретные рекомендации. {custom_note}", "description": "Максимально короткие ответы"}
}

DEEPSEEK_MODELS = {
    "🔵 DeepSeek Chat V3": "deepseek-chat",
    "🟢 DeepSeek Coder V2": "deepseek-coder",
    "⚪ DeepSeek Lite": "deepseek-chat",
}

MESSAGE_STYLES = {
    "standard": {"name": "🌟 Стандартный", "template": "🌟 Добро пожаловать, {name}!\n\n✨ Я твой персональный AI-помощник на базе DeepSeek.\n📌 Сейчас ты в чате: {chat}\n\n💡 Просто напиши мне сообщение.\n🔽 Кнопки для управления."},
    "minimal": {"name": "🔹 Минимальный", "template": "👋 Привет, {name}!\n\n💬 Чат: {chat}\n✏️ Напиши сообщение..."},
    "detailed": {"name": "📋 Подробный", "template": "📋 Информация\n\n👤 Пользователь: {name}\n💬 Текущий чат: {chat}\n🤖 Модель: {model}\n🎭 Режим: {mode}\n📊 Статистика: {stats} сообщений\n\n🔽 Кнопки управления"}
}

QUOTES = {
    "ru": [
        "🏆 Цитата дня: «Единственный способ делать великие дела — любить то, что вы делаете.» — Стив Джобс",
        "💡 Мысль: «Жизнь — это то, что с тобой происходит, пока ты строишь планы.» — Джон Леннон",
        "🌱 Мудрость: «Начинать всегда стоит с того, что сеет сомнения.» — Борис Стругацкий",
        "🔥 Вдохновение: «Падать — часть жизни, подниматься — её главная часть.»",
    ],
    "en": [
        "🏆 Quote of the day: «The only way to do great work is to love what you do.» — Steve Jobs",
        "💡 Thought: «Life is what happens when you're busy making other plans.» — John Lennon",
        "🌱 Wisdom: «Start with what sows doubts.» — Boris Strugatsky",
        "🔥 Inspiration: «Falling is part of life, getting up is its main part.»",
    ]
}

# ========== ЛОКАЛИЗАЦИЯ (СОКРАЩЁННАЯ) ==========
L10N = {
    "ru": {
        "start_welcome_owner": "✅ Бот успешно запущен на DeepSeek API!",
        "bot_paused": "⏸️ Бот приостановлен\nПричина: {reason}\n\n{welcome}",
        "how_to_use": "\n\n📌 Как пользоваться:\n• Просто пиши сообщения — я отвечу\n• Кнопки внизу помогают управлять чатом\n• В настройках можно выбрать стиль и лимиты",
        "stats": "📊 Статистика:\n• Сообщений: {total_msgs}\n• Сохранено: {saved_cnt}\n• Лимит: {rpm} запросов/мин, cooldown {cd} сек\n• Модель: {model}\n• Режим: {mode}\n\n{sub_text}",
        "weather_prompt": "🌍 Укажите город, например: погода в Москве",
        "danger_warning": "⚠️ Ваше сообщение содержит признаки возможной угрозы жизни.\nСпециалист безопасности уже уведомлён и свяжется с вами.\nЕсли нужна немедленная помощь: 8-800-2000-122 (Россия).",
        "adult_warning": "⚠️ Предупреждение {warnings}/{MAX_WARNINGS}",
        "adult_reject": "❌ Запрос отклонён (18+). Попытка {attempts}/{MAX_ADULT_ATTEMPTS}",
        "adult_banned": "❌ Вы забанены за 18+ контент.",
        "rate_limit": "⏱️ Подождите {wait} сек",
        "limit_exceeded": "📊 Лимит {limit} запросов/мин",
        "bot_paused_short": "⏸️ Бот приостановлен",
        "no_deepseek": "❌ Нет доступного DeepSeek клиента.",
        "api_error": "❌ Ошибка DeepSeek API. Пожалуйста, попробуйте позже.",
        "save_mode": "💾 Режим сохранения",
        "save_choice": "👇 Выберите тип сообщения:",
        "save_saved": "✅ Сохранено!\n\n{text}...",
        "save_cancel": "❌ Сохранение отменено",
        "invalid_number": "❌ Неверный номер. Введите от 1 до {max_num}",
        "enter_number": "❌ Введите номер или нажмите '◀️ Отмена'",
        "photo_error": "📸 Бот работает только с текстом.",
        "support_sent": "✅ Сообщение отправлено в поддержку.",
        "support_reply_sent": "✅ Ответ отправлен.",
        "empty_reply": "❌ Пустое сообщение.",
        "owner_msg_failed": "❌ Не удалось отправить.",
        "promocode_not_found": "❌ Промокод не найден.",
        "promocode_expired": "❌ Промокод истёк.",
        "promocode_used": "❌ Вы уже использовали этот промокод.",
        "promocode_limit": "❌ Промокод достиг лимита использований.",
        "promocode_activated": "✅ Промокод активирован!",
        "promocode_extra_days": "✅ Промокод активирован! Добавлено {value} дней к подписке.",
        "promocode_extra_days_new": "✅ Промокод активирован! Вам выдана подписка на {value} дней.",
        "promocode_percent": "✅ Промокод активирован! Скидка {value}% на следующую покупку (30 дней).",
        "promocode_fixed": "✅ Промокод активирован! Скидка {value}⭐ на следующую покупку.",
        "promocode_limits": "✅ Промокод активирован! Лимиты повышены на {value} дней.",
        "no_subscription": "❌ Нет активной подписки",
        "subscription_active": "✅ Подписка {name} активна до {expiry}\n\n🌟 Преимущества:\n• {rpm} запросов/мин\n• Cooldown {cooldown} сек\n• Сохранение до {max_saved} сообщений\n• +{extra_chats} постоянных чатов",
        "subscription_refund_available": "\n💰 Вы можете вернуть звёзды в течение 24 часов.",
        "free_plan": "💰 Бесплатный план: {rpm} запросов/мин, cooldown {cooldown} сек, {max_chats} чатов, {max_saved} сохранений",
        "referral_bonus": "\n\n🎁 Реферальный бонус: +{rpm} запросов/мин, +{chats} чатов, +{saved} сохранений",
        "refund_confirm": "💰 Подтверждение возврата подписки {name} за {price}⭐?",
        "refund_success": "✅ Подписка отменена. {amount}⭐ будут возвращены.",
        "refund_fail": "❌ {msg}",
        "invoice_error": "❌ Ошибка платежа: {e}",
        "no_active_subscription": "❌ Нет активной подписки.",
        "refund_time_expired": "❌ Прошло более 24 часов.",
        "back_to_main": "◀️ Назад",
        "admin_panel": "👑 Панель администратора\n\nВыберите категорию:",
        "admin_category": "📁 Категория: {name}\n\nВыберите действие:",
        "admin_manage": "👥 Управление администраторами",
        "admin_add_prompt": "👤 Введите username пользователя:",
        "admin_remove_prompt": "👤 Введите username для удаления:",
        "admin_role_choose": "Выберите роль для @{username}:",
        "admin_role_assigned": "✅ @{username} назначен {role}.",
        "admin_limits_text": "⚙️ Лимиты бесплатных:\n• RPM: {rpm}\n• Cooldown: {cooldown} сек\n• Макс чатов: {max_chats}\n• Макс сохранений: {max_saved}",
        "admin_set_rpm_prompt": "Введите новый RPM (1-200):",
        "admin_set_cooldown_prompt": "Введите новый cooldown (0-60 сек):",
        "admin_set_max_chats_prompt": "Введите макс. чатов (1-100):",
        "admin_set_max_saved_prompt": "Введите макс. сохранений (10-2000):",
        "admin_key_rotation_disabled": "❌ Для DeepSeek не требуется ротация ключей.",
        "admin_text_settings": "📝 Тексты бота:\nПриветствие по умолчанию: {welcome}\nКастомное приветствие: {custom_greeting}\nКастомная информация: {custom_info}",
        "admin_set_welcome_prompt": "Введите новое приветствие (используйте {name} и {chat}):",
        "admin_set_custom_greeting_prompt": "Введите кастомное приветствие (или пустое для отключения):",
        "admin_set_custom_info_prompt": "Введите кастомную информацию:",
        "admin_choose_style": "Выберите стиль по умолчанию:",
        "admin_style_set": "Стиль по умолчанию: {name}",
        "admin_api_keys_info": "🔑 DeepSeek использует один API ключ. Изменить можно только в коде.\n\nТекущий ключ: {key}",
        "admin_featured_channels": "⭐ Избранные каналы:\n{channels}\n\nДействия:",
        "admin_add_channel_prompt": "Введите канал в формате: Название|https://t.me/...",
        "admin_remove_channel_prompt": "Введите номер канала для удаления:\n{channels}",
        "admin_channel_added": "✅ Канал {name} добавлен",
        "admin_channel_removed": "✅ Канал {name} удалён",
        "admin_animations_status": "🎬 Анимации: {status}",
        "admin_animations_toggled": "Анимации {status}",
        "admin_broadcast_prompt": "Введите сообщение для рассылки всем пользователям:",
        "admin_broadcast_result": "✅ Отправлено: {sent}, ошибок: {failed}",
        "admin_pause_prompt": "Введите причину приостановки:",
        "admin_pause_reason": "Бот приостановлен. Причина: {reason}",
        "admin_resumed": "Бот возобновлён.",
        "admin_subscriptions_menu": "Управление подписками",
        "admin_give_subscription_plan": "Выберите план:",
        "admin_give_subscription_prompt": "Введите ID пользователя или @username:",
        "admin_give_subscription_success": "✅ Подписка {name} выдана пользователю {user_id}",
        "admin_refund_prompt": "Введите ID пользователя или @username для возврата звёзд:",
        "admin_refund_success": "✅ Подписка пользователя {user_id} отменена. {amount}⭐ возвращены.",
        "admin_activity": "📊 Активность:\n• Всего пользователей: {total_users}\n• Активно сейчас: {active_now}\n• Всего запросов: {total_req}",
        "admin_violations": "🔨 Нарушения:\n\n{text}",
        "admin_no_violations": "Нет нарушений.",
        "admin_ban_menu": "🔨 Управление банами и мутами",
        "admin_ban_prompt": "Введите ID пользователя или @username для бана:",
        "admin_mute_prompt": "Введите ID пользователя или @username для мута на 1 час:",
        "admin_unban_menu": "Выберите способ разбана:",
        "admin_unban_prompt": "Введите ID пользователя или @username для разбана:",
        "admin_user_banned": "✅ Пользователь {target} забанен",
        "admin_user_muted": "✅ {target} в муте на {duration} мин",
        "admin_user_unbanned": "✅ {target} разбанен",
        "admin_stats": "📊 Статистика пользователей:\n\n• Всего: {total_users}\n• Забанено: {banned_cnt}\n• В муте: {muted_cnt}\n• Нарушений: {violations_cnt}\n• Активно сейчас: {active_now}",
        "promocode_created": "✅ Промокод {code} создан! Действует {days} дней. Награда: {value} ({type}). Лимит активаций: {limit}",
        "discount_set": "✅ Скидка {percent}% на тариф {plan_id} установлена на {days} дней.",
        "discount_removed": "✅ Скидка на {plan_id} удалена.",
        "no_discounts": "Нет активных скидок.",
        "msg_to_owner_sent": "✅ Сообщение отправлено главному администратору.",
        "msg_to_owner_failed": "❌ Главный администратор не найден.",
        "invalid_input": "❌ Введите корректный ID или @username",
        "user_not_found": "❌ Пользователь @{username} не найден.",
        "cannot_assign_owner": "❌ Нельзя назначить владельца.",
        "cannot_remove_owner": "❌ Нельзя удалить владельца.",
        "session_expired": "❌ Сессия истекла.",
        "no_permission": "❌ У вас нет прав для этого действия.",
        "enter_number_range": "❌ Введите число от {min} до {max}.",
        "enter_correct_number": "❌ Введите корректное число.",
        "promocode_invalid_code": "❌ Некорректный код. Используйте латиницу и цифры, 3-20 символов.",
        "promocode_reward_type": "Выберите тип награды:\n1 - Скидка %\n2 - Фиксированная скидка (⭐)\n3 - Дополнительные дни подписки\n4 - Повышение лимитов (RPM)\n\nВведите номер 1-4:",
        "promocode_reward_value_percent": "Введите размер скидки в процентах (1-99):",
        "promocode_reward_value_fixed": "Введите сумму скидки в звёздах (1-100):",
        "promocode_reward_value_days": "Введите количество дней (1-5):",
        "promocode_reward_value_limits": "Введите количество дней действия повышенных лимитов (1-5):",
        "promocode_valid_days": "Введите срок действия промокода в днях (1-5):",
        "promocode_max_uses": "Введите максимальное количество активаций (0 - безлимит):",
        "discount_percent": "Введите размер скидки в процентах (1-99):",
        "discount_duration": "Введите длительность скидки в днях (1-30):",
        "chat_limit_reached": "❌ Лимит постоянных чатов ({max_allowed}). Удалить старый?",
        "chat_already_temp": "Уже есть временный чат. Заменить?",
        "chat_deleted": "✅ Чат '{name}' удалён",
        "chat_delete_failed": "❌ Не удалось удалить чат",
        "chat_oldest_deleted": "✅ Самый старый чат удалён. Введите название нового:",
        "chat_name_prompt": "📝 Введите название для нового чата:",
        "chat_name_temp_prompt": "📝 Введите название для временного чата:",
        "chat_replace_confirm": "✅ Да, заменить",
        "favorite_added": "⭐ Добавлено в избранное",
        "favorite_removed": "⭐ Удалено из избранного",
        "no_chats": "📭 История чата: {name}\n\nНет сообщений.",
        "chat_history": "📜 История чата: {name}\n\n",
        "enter_promo": "Введите промокод:",
        "support_message_prompt": "📨 Напишите ваше сообщение в поддержку:",
        "reply_support_prompt": "✍️ Введите ответ для пользователя {user_id}:",
        "msg_to_owner_prompt": "📨 Напишите сообщение главному администратору:",
        "custom_note_prompt": "Введите вашу приписку к запросам:",
        "select_model": "🚀 Выберите модель DeepSeek:",
        "model_changed": "Модель изменена на {name}",
        "select_mode": "🎭 Выберите режим:",
        "mode_changed": "Режим изменён на {name}",
        "select_style": "Выберите стиль сообщения:",
        "style_changed": "Стиль изменён на {name}",
        "my_limits_text": "⚡ Ваши лимиты:\n• Запросов/мин: {rpm}\n• Cooldown: {cd} сек\n\nИзменить:",
        "set_rpm_prompt": "Введите новый RPM (1-200):",
        "set_cooldown_prompt": "Введите новый cooldown (0-60 сек):",
        "no_saved_messages": "💾 Нет сохранённых сообщений.",
        "saved_messages": "💾 Сохранённые сообщения:\n\n",
        "info_text": "ℹ️ Информация о боте\n\n📅 {date}\n⏱ Аптайм: {uptime}\n{pause_status}\n\n📊 Пользователей: {total_users}, активных: {active_now}\nЗабанено: {banned_cnt}, в муте: {muted_cnt}\nНарушений: {violations_cnt}\nВсего запросов: {total_req}\n\n🚀 Модель: DeepSeek",
        "pause_status_active": "▶️ Активен",
        "pause_status_paused": "⏸️ Приостановлен",
        "referral_link": "🔗 Ваша реферальная ссылка:\n{link}\n\nПриглашено: {invited}\nБонус за 3: +{rpm} запросов/мин, +{chats} чатов, +{saved} сохранений на {days} дня",
        "subscription_plans": "🌟 Выберите план:\n\n",
        "subscription_plan_item": "{name} — {price}⭐\n• {description}\n\n",
        "buy_plan": "{name} - {price}⭐",
        "settings_text": "⚙️ Настройки пользователя\n\nСохранено: {saved_cnt}/{saved_lim}\nСообщений: {total_msgs}\nПредупреждений: {warns}/{MAX_WARNINGS}\nПопыток 18+: {adult_att}\n\nПриписка: «{note}»\nСтиль: {style_name}\nЛимиты: {rpm} запросов/мин, {cd} сек кулдаун",
        "select_language": "🌐 Выберите язык / Choose language:",
        "language_changed": "Язык изменён на русский / Language changed to English",
        "return_to_dialog": "Можете продолжать общение.",
        "exit_to_menu": "🏠 Выйти в меню",
        "return_button": "↩️ Вернуться в диалог",
        "balance_text": "💰 Ваш баланс: {balance} ⭐\n\nЗвёзды можно использовать для покупки подписок или выиграть в розыгрышах.",
        "giveaways_none": "🎁 Активных розыгрышей нет.",
        "giveaways_active": "🎁 Активные розыгрыши:\n\n",
        "join_giveaway_success": "✅ Вы участвуете в розыгрыше!",
        "join_giveaway_already": "Вы уже участвуете в этом розыгрыше!",
        "join_giveaway_ended": "Розыгрыш уже завершён или не найден.",
        "giveaway_created": "✅ Розыгрыш создан!\nПриз: {prize}\nОкончание: {end_time}\nПобедителей: {winners}\n\nУчастники могут нажать кнопку \"🎁 Розыгрыши\" чтобы увидеть и участвовать.",
        "giveaway_ended_winner": "🎉 Вы выиграли {prize} в розыгрыше!",
        "giveaway_ended_loser": "🎁 Розыгрыш «{prize}» завершён. К сожалению, вы не выиграли.",
        "admin_giveaways_menu": "🎁 Управление розыгрышами",
        "create_giveaway_prize_type": "Выберите тип приза:",
        "create_giveaway_stars_amount": "Введите количество звёзд (1-10000):",
        "create_giveaway_sub_plan": "Выберите план подписки:",
        "create_giveaway_duration": "Введите длительность розыгрыша в часах (1-168):",
        "create_giveaway_winners": "Введите количество победителей (1-10):",
        "admin_add_stars": "⭐ Начислить звёзды",
        "admin_add_stars_user_prompt": "Введите ID пользователя или @username:",
        "admin_add_stars_amount_prompt": "Введите количество звёзд для начисления:",
        "admin_add_stars_success": "✅ Пользователю {user} начислено {amount}⭐. Новый баланс: {balance}⭐",
        "refund_balance_too_low": "❌ Возврат невозможен, так как ваш баланс звёзд меньше 200.",
        "topup_balance_required": "❌ Недостаточно звёзд. Ваш баланс: {balance}⭐. Нужно {price}⭐.\n\nПополните баланс через Telegram Stars:",
        "topup_balance_button": "💳 Пополнить баланс (Telegram Stars)",
        "balance_topup_success": "✅ Баланс пополнен на {amount}⭐. Текущий баланс: {balance}⭐",
        "feature_disabled": "❌ Эта функция временно отключена администратором.",
        "admin_disable_features": "🔧 Управление функциями бота",
        "admin_features_status": "📋 Статус функций:\n\n✅ — включено, ❌ — отключено\n\n",
        "admin_feature_toggle": "Функция {name}: {status}",
        "admin_feature_toggled": "✅ Функция {name} теперь {status}.",
        "more_features": "📁 Дополнительные функции",
        "admin_auto_reply": "📝 Управление автоответами",
        "admin_auto_reply_categories": "Категории автоответов:\n{list}\n\nВыберите действие:",
        "admin_auto_reply_add_word": "Введите слово для добавления в категорию {category}:",
        "admin_auto_reply_remove_word": "Введите слово для удаления из категории {category}:\nТекущие слова: {words}",
        "admin_auto_reply_word_added": "✅ Слово '{word}' добавлено в категорию {category}",
        "admin_auto_reply_word_removed": "✅ Слово '{word}' удалено из категории {category}",
        "admin_banned_words": "🚫 Управление запрещёнными словами",
        "admin_banned_words_list": "Запрещённые слова (ru): {ru}\nЗапрещённые слова (en): {en}",
        "admin_banned_words_add": "Введите слово для добавления в запрещённый список (язык ru/en):",
        "admin_banned_words_remove": "Введите слово для удаления из запрещённого списка:"
    }
}

def get_text(user_id, key, **kwargs):
    if user_id in user_data:
        lang = user_data[user_id].get("language", bot_settings.get("language", "ru"))
    else:
        lang = bot_settings.get("language", "ru")
    text = L10N[lang].get(key, L10N["ru"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text

def is_feature_enabled(feature_name):
    return not disabled_features.get(feature_name, False)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_dangerous_text(text, lang):
    return any(kw in text.lower() for kw in DANGER_KEYWORDS.get(lang, DANGER_KEYWORDS["ru"]))

def check_adult_content(text, lang):
    if not bot_settings["enable_18_plus_filter"]:
        return False
    return any(kw in text.lower() for kw in banned_words.get(lang, banned_words["ru"]))

def get_random_quote(lang):
    return random.choice(QUOTES.get(lang, QUOTES["ru"]))

def check_auto_reply(text):
    text_lower = text.lower()
    for category, keywords in auto_reply_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    return None

def get_auto_reply_response(category, user_name=None):
    responses = {
        "greetings": [
            f"👋 Здравствуйте{f', {user_name}' if user_name else ''}! Чем я могу вам помочь?",
            f"Привет{f', {user_name}' if user_name else ''}! Рад вас видеть!",
            f"Добрый день{f', {user_name}' if user_name else ''}! Чем могу быть полезен?"
        ],
        "how_are_you": [
            f"🤖 У меня всё отлично{f', {user_name}' if user_name else ''}! Спасибо, что спросили. А у вас?",
            f"Всё супер{f', {user_name}' if user_name else ''}! Спасибо за заботу!",
            f"Работаю в штатном режиме{f', {user_name}' if user_name else ''}! Чем могу помочь?"
        ],
        "thanks": [
            f"🙏 Пожалуйста{f', {user_name}' if user_name else ''}! Всегда рад помочь.",
            f"Обращайтесь{f', {user_name}' if user_name else ''}! Я здесь, чтобы помогать.",
            f"Всегда пожалуйста{f', {user_name}' if user_name else ''}!"
        ],
        "bye": [
            f"👋 До свидания{f', {user_name}' if user_name else ''}! Хорошего дня!",
            f"Пока{f', {user_name}' if user_name else ''}! Буду рад снова помочь!",
            f"Всего хорошего{f', {user_name}' if user_name else ''}! Заходите ещё!"
        ]
    }
    if category in responses:
        return random.choice(responses[category])
    return None

async def get_weather_openmeteo(location):
    """Получение погоды через Open-Meteo (БЕСПЛАТНО, НЕ ТРЕБУЕТ КЛЮЧА)"""
    if not is_feature_enabled("weather"):
        return False, "❌ Функция погоды отключена администратором."
    
    try:
        async with aiohttp.ClientSession() as session:
            # Используем Nominatim для поиска города (бесплатно, не требует ключа)
            # Добавляем 'accept-language=ru' для русских названий
            geo_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(location)}&format=json&limit=1&accept-language=ru"
            
            # Важно: Nominatim требует User-Agent
            headers = {'User-Agent': 'MeteoBot/1.0 (weather bot for Telegram)'}
            
            async with session.get(geo_url, headers=headers) as resp:
                if resp.status != 200:
                    return False, "❌ Ошибка поиска города. Попробуйте позже."
                
                data = await resp.json()
                if not data:
                    # Пробуем на английском
                    geo_url_en = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(location)}&format=json&limit=1"
                    async with session.get(geo_url_en, headers=headers) as resp_en:
                        data_en = await resp_en.json()
                        if not data_en:
                            return False, f"❌ Город '{location}' не найден. Проверьте название или напишите на английском (например, 'Moscow')"
                        data = data_en
                
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                # Берём название на русском, если есть
                display_name = data[0].get('display_name', location).split(',')[0]
            
            # Open-Meteo API (полностью бесплатный, не требует ключа)
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=temperature_2m,relativehumidity_2m,windspeed_10m&timezone=auto"
            
            async with session.get(weather_url) as resp:
                if resp.status != 200:
                    return False, "❌ Ошибка получения погоды. Сервер временно недоступен."
                
                wdata = await resp.json()
                
                current = wdata.get('current_weather', {})
                if not current:
                    return False, "❌ Не удалось получить данные о погоде."
                
                temp = current.get('temperature', 'N/A')
                wind = current.get('windspeed', 'N/A')
                code = current.get('weathercode', 0)
                
                # Расшифровка кодов погоды Open-Meteo
                conditions = {
                    0: "☀️ Ясно",
                    1: "🌤️ Преимущественно ясно",
                    2: "⛅ Переменная облачность",
                    3: "☁️ Пасмурно",
                    45: "🌫️ Туман",
                    48: "🌫️ Туман с изморозью",
                    51: "🌧️ Лёгкая морось",
                    53: "🌧️ Умеренная морось",
                    55: "🌧️ Сильная морось",
                    56: "❄️ Ледяная морось",
                    57: "❄️ Сильная ледяная морось",
                    61: "🌧️ Лёгкий дождь",
                    63: "🌧️ Умеренный дождь",
                    65: "🌧️ Сильный дождь",
                    66: "❄️ Ледяной дождь",
                    67: "❄️ Сильный ледяной дождь",
                    71: "❄️ Лёгкий снег",
                    73: "❄️ Умеренный снег",
                    75: "❄️ Сильный снег",
                    77: "❄️ Снежные зёрна",
                    80: "🌧️ Лёгкий ливень",
                    81: "🌧️ Умеренный ливень",
                    82: "🌧️ Сильный ливень",
                    85: "❄️ Лёгкий снегопад",
                    86: "❄️ Сильный снегопад",
                    95: "⛈️ Гроза",
                    96: "⛈️ Гроза с градом",
                    99: "⛈️ Сильная гроза с градом"
                }
                cond = conditions.get(code, f"❓ Неизвестно (код {code})")
                
                # Получаем влажность из почасовых данных
                humidity = 'N/A'
                if 'hourly' in wdata and 'relativehumidity_2m' in wdata['hourly'] and wdata['hourly']['relativehumidity_2m']:
                    humidity = wdata['hourly']['relativehumidity_2m'][0]
                
                message = (
                    f"🌍 *Погода в {display_name}*\n\n"
                    f"🌡️ *Температура:* {temp}°C\n"
                    f"💧 *Влажность:* {humidity}%\n"
                    f"🌬️ *Ветер:* {wind} км/ч\n"
                    f"☁️ *Состояние:* {cond}\n"
                )
                return True, message
                
    except aiohttp.ClientError as e:
        logger.error(f"Сетевая ошибка: {e}")
        return False, "❌ Ошибка сети. Проверьте интернет-соединение."
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return False, f"❌ Ошибка получения погоды: {str(e)}"


async def test_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки погоды"""
    test_city = "Moscow"
    success, result = await get_weather_openmeteo(test_city)
    await update.message.reply_text(f"Тест погоды для {test_city}:\n{result}")

# ========== DEEPSEEK ==========
def init_deepseek():
    global deepseek_client
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY не задан!")
        return False
    try:
        deepseek_client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=60.0,
            max_retries=3
        )
        logger.info("✅ DeepSeek клиент инициализирован")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DeepSeek: {e}")
        return False

async def call_deepseek_async(messages, model="deepseek-chat", temperature=0.8, max_tokens=2048):
    if not deepseek_client:
        raise Exception("DeepSeek клиент не инициализирован")
    loop = asyncio.get_running_loop()
    try:
        response = await loop.run_in_executor(
            None,
            lambda: deepseek_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        raise

async def call_llm_with_failover(messages, temperature=0.8, max_tokens=2048):
    return await call_deepseek_async(messages, model=bot_settings["default_model"], temperature=temperature, max_tokens=max_tokens)

async def send_long_message(context, chat_id, text, reply_markup=None, parse_mode=None):
    if not text:
        return
    max_length = 4000
    if len(text) <= max_length:
        await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        return
    parts = []
    current_part = ""
    for line in text.split('\n'):
        if len(current_part) + len(line) + 1 <= max_length:
            current_part += line + '\n'
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + '\n'
    if current_part:
        parts.append(current_part.strip())
    for i, part in enumerate(parts):
        if i == len(parts) - 1 and reply_markup:
            await context.bot.send_message(chat_id, part, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await context.bot.send_message(chat_id, part, parse_mode=parse_mode)
        await asyncio.sleep(0.5)

# ========== ОТПРАВКА КОДА ФАЙЛОМ ==========
async def send_code_as_file(context, chat_id, code_text, language="txt"):
    if len(code_text) <= 4000:
        return False
    try:
        file_name = f"code_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{language}"
        file_bytes = BytesIO(code_text.encode('utf-8'))
        file_bytes.seek(0)
        await context.bot.send_document(chat_id, document=file_bytes, filename=file_name, caption="📄 Код слишком длинный, отправлен файлом.")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        return False

def extract_code_blocks(text):
    pattern = r'```(\w*)\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    if not matches:
        return []
    result = []
    for lang, code in matches:
        lang = lang.strip() or "txt"
        result.append((lang, code.strip()))
    return result

async def process_and_send_response(context, chat_id, response_text, reply_markup=None):
    code_blocks = extract_code_blocks(response_text)
    if not code_blocks:
        await send_long_message(context, chat_id, response_text, reply_markup=reply_markup, parse_mode="Markdown")
        return
    
    text_without_code = re.sub(r'```\w*\n.*?```', '', response_text, flags=re.DOTALL).strip()
    if text_without_code:
        await send_long_message(context, chat_id, text_without_code, parse_mode="Markdown")
    
    for lang, code in code_blocks:
        if len(code) <= 4000:
            await context.bot.send_message(chat_id, f"```{lang}\n{code}\n```", parse_mode="Markdown")
        else:
            await send_code_as_file(context, chat_id, code, lang)
    
    if reply_markup:
        await context.bot.send_message(chat_id, "✅ Готово.", reply_markup=reply_markup)

# ========== БАЛАНС И ПОДПИСКИ ==========
def add_balance(user_id, amount):
    if not is_feature_enabled("balance"):
        return
    if user_id not in user_balance:
        user_balance[user_id] = 0
    user_balance[user_id] += amount
    save_data()

def deduct_balance(user_id, amount):
    if not is_feature_enabled("balance"):
        return False
    if user_id not in user_balance or user_balance[user_id] < amount:
        return False
    user_balance[user_id] -= amount
    save_data()
    return True

def get_balance(user_id):
    if not is_feature_enabled("balance"):
        return 0
    return user_balance.get(user_id, 0)

def check_subscription(user_id):
    if not is_feature_enabled("subscription"):
        return False
    return user_id in subscriptions and subscriptions[user_id]["expiry"] > time.time()

def get_user_subscription_plan(user_id):
    if not is_feature_enabled("subscription"):
        return None
    if user_id not in subscriptions or subscriptions[user_id]["expiry"] <= time.time():
        return None
    return subscriptions[user_id]["plan"]

def get_user_limits(user_id):
    base = bot_settings["free_limits"].copy()
    if check_subscription(user_id):
        plan = get_user_subscription_plan(user_id)
        if plan and plan in SUBSCRIPTION_PLANS:
            base.update(SUBSCRIPTION_PLANS[plan]["limits"])
    if is_feature_enabled("referral") and user_id in referrals and referrals[user_id].get("bonus_until", 0) > time.time():
        bonus = bot_settings["referral_bonus"]
        base["requests_per_minute"] += bonus.get("requests_per_minute", 0)
        base["max_chats"] += bonus.get("max_chats", 0)
        base["max_saved"] += bonus.get("max_saved", 0)
    if "temp_limits" in user_data.get(user_id, {}):
        for tl in user_data[user_id]["temp_limits"]:
            if tl["expiry"] > time.time():
                base["requests_per_minute"] += tl.get("rpm", 0)
                base["cooldown"] = min(base["cooldown"], tl.get("cooldown", base["cooldown"]))
    personal = user_data.get(user_id, {}).get("personal_limits", {})
    if personal.get("requests_per_minute"):
        base["requests_per_minute"] = personal["requests_per_minute"]
    if personal.get("cooldown"):
        base["cooldown"] = personal["cooldown"]
    return base

def activate_subscription(user_id, plan_id, purchase_time=None):
    if not is_feature_enabled("subscription"):
        return False
    if plan_id not in SUBSCRIPTION_PLANS:
        return False
    plan = SUBSCRIPTION_PLANS[plan_id]
    expiry = time.time() + plan["days"] * 86400
    subscriptions[user_id] = {"expiry": expiry, "plan": plan_id, "purchase_time": purchase_time or time.time()}
    save_data()
    return True

def refund_subscription(user_id):
    if not is_feature_enabled("subscription"):
        return False, get_text(user_id, "feature_disabled")
    if user_id not in subscriptions:
        return False, get_text(user_id, "no_active_subscription")
    if time.time() - subscriptions[user_id]["purchase_time"] > 86400:
        return False, get_text(user_id, "refund_time_expired")
    if get_balance(user_id) < 200:
        return False, get_text(user_id, "refund_balance_too_low")
    plan_id = subscriptions[user_id]["plan"]
    amount = SUBSCRIPTION_PLANS[plan_id]["price"]
    add_balance(user_id, amount)
    del subscriptions[user_id]
    save_data()
    return True, get_text(user_id, "refund_success", amount=amount)

def get_subscription_benefits(user_id):
    if not is_feature_enabled("subscription"):
        return "❌ Функция подписки отключена администратором."
    if check_subscription(user_id):
        plan = get_user_subscription_plan(user_id)
        plan_info = SUBSCRIPTION_PLANS.get(plan, SUBSCRIPTION_PLANS["basic"])
        expiry = datetime.fromtimestamp(subscriptions[user_id]["expiry"]).strftime('%d.%m.%Y %H:%M')
        text = get_text(user_id, "subscription_active",
                       name=plan_info['name'], expiry=expiry,
                       rpm=plan_info['limits']['requests_per_minute'],
                       cooldown=plan_info['limits']['cooldown'],
                       max_saved=plan_info['limits']['max_saved'],
                       extra_chats=plan_info['limits']['max_chats'] - bot_settings['free_limits']['max_chats'])
        if time.time() - subscriptions[user_id]["purchase_time"] < 86400:
            text += get_text(user_id, "subscription_refund_available")
        return text
    else:
        bonus_text = ""
        if is_feature_enabled("referral") and user_id in referrals and referrals[user_id].get("bonus_until", 0) > time.time():
            bonus = bot_settings["referral_bonus"]
            bonus_text = get_text(user_id, "referral_bonus",
                                 rpm=bonus['requests_per_minute'],
                                 chats=bonus['max_chats'],
                                 saved=bonus['max_saved'])
        text = get_text(user_id, "no_subscription") + "\n\n"
        for plan_id, plan in SUBSCRIPTION_PLANS.items():
            text += f"{plan['name']} — {plan['price']}⭐\n• {plan['description']}\n\n"
        text += get_text(user_id, "free_plan",
                        rpm=bot_settings['free_limits']['requests_per_minute'],
                        cooldown=bot_settings['free_limits']['cooldown'],
                        max_chats=bot_settings['free_limits']['max_chats'],
                        max_saved=bot_settings['free_limits']['max_saved']) + bonus_text
        return text

def get_discounted_price(plan_id, original_price):
    if not is_feature_enabled("subscription"):
        return original_price
    if plan_id in discounts and discounts[plan_id]["valid_until"] > time.time():
        percent = discounts[plan_id]["percent"]
        discounted = int(original_price * (100 - percent) / 100)
        return max(1, discounted)
    return original_price

# ========== ПРОМОКОДЫ ==========
def apply_promocode(user_id, code):
    if not is_feature_enabled("subscription"):
        return False, get_text(user_id, "feature_disabled")
    if code not in promocodes:
        return False, get_text(user_id, "promocode_not_found")
    promo = promocodes[code]
    if promo["expiry"] < time.time():
        return False, get_text(user_id, "promocode_expired")
    if user_id in promo["used_by"]:
        return False, get_text(user_id, "promocode_used")
    if promo.get("max_uses", 0) > 0 and len(promo["used_by"]) >= promo["max_uses"]:
        return False, get_text(user_id, "promocode_limit")
    reward_type = promo["reward_type"]
    reward_value = promo["reward_value"]
    if reward_type == "extra_days":
        if user_id in subscriptions and subscriptions[user_id]["expiry"] > time.time():
            subscriptions[user_id]["expiry"] += reward_value * 86400
            subscriptions[user_id]["promocode_applied"] = code
            save_data()
            return True, get_text(user_id, "promocode_extra_days", value=reward_value)
        else:
            activate_subscription(user_id, "basic", purchase_time=time.time())
            subscriptions[user_id]["expiry"] = time.time() + reward_value * 86400
            subscriptions[user_id]["promocode_applied"] = code
            save_data()
            return True, get_text(user_id, "promocode_extra_days_new", value=reward_value)
    elif reward_type == "percent":
        if "promo_discount" not in user_data[user_id]:
            user_data[user_id]["promo_discount"] = []
        user_data[user_id]["promo_discount"].append({"type": "percent", "value": reward_value, "expiry": time.time() + 86400 * 30})
        save_data()
        return True, get_text(user_id, "promocode_percent", value=reward_value)
    elif reward_type == "fixed":
        if "promo_discount" not in user_data[user_id]:
            user_data[user_id]["promo_discount"] = []
        user_data[user_id]["promo_discount"].append({"type": "fixed", "value": reward_value, "expiry": time.time() + 86400 * 30})
        save_data()
        return True, get_text(user_id, "promocode_fixed", value=reward_value)
    elif reward_type == "limits":
        if "temp_limits" not in user_data[user_id]:
            user_data[user_id]["temp_limits"] = []
        user_data[user_id]["temp_limits"].append({"rpm": reward_value, "cooldown": 0, "expiry": time.time() + reward_value * 86400})
        save_data()
        return True, get_text(user_id, "promocode_limits", value=reward_value)
    promo["used_by"].append(user_id)
    save_data()
    return True, get_text(user_id, "promocode_activated")

# ========== ПОДДЕРЖКА ==========
def add_support_message(user_id, text):
    if user_id not in support_messages:
        support_messages[user_id] = []
    support_messages[user_id].append({"text": text, "timestamp": time.time(), "answered": False})
    save_data()
    return len(support_messages[user_id]) - 1

def get_support_messages_for_admin():
    result = []
    for uid, msgs in support_messages.items():
        for idx, msg in enumerate(msgs):
            if not msg["answered"]:
                result.append((uid, idx, msg["text"], msg["timestamp"]))
    return result

def mark_message_answered(user_id, msg_index):
    if user_id in support_messages and 0 <= msg_index < len(support_messages[user_id]):
        support_messages[user_id][msg_index]["answered"] = True
        save_data()
        return True
    return False

def get_all_admins_for_forward():
    admins = []
    if OWNER_CHAT_ID:
        admins.append((OWNER_CHAT_ID, "owner"))
    for admin_id, role in ADMIN_ROLES.items():
        admins.append((admin_id, role))
    for admin_id in ADMINS:
        if admin_id not in [a[0] for a in admins]:
            admins.append((admin_id, "admin"))
    return admins

async def forward_support_message_to_admin(context, from_admin_id, target_admin_id, user_id, msg_index, msg_text):
    mark_message_answered(user_id, msg_index)
    user_info = f"ID: {user_id}"
    if user_id in user_data and user_data[user_id].get("username"):
        user_info += f" (@{user_data[user_id]['username']})"
    forward_text = f"📨 Переадресованное обращение\nОт пользователя: {user_info}\nТекст: {msg_text}\n\nАдминистратор @{from_admin_id} просит вас ответить."
    keyboard = [[InlineKeyboardButton("✍️ Ответить", callback_data=f"reply_support_{user_id}_{msg_index}")]]
    await context.bot.send_message(target_admin_id, forward_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
    await context.bot.send_message(from_admin_id, f"✅ Обращение переадресовано администратору {target_admin_id}.")

# ========== АДМИНИСТРИРОВАНИЕ ==========
def is_admin(user_id):
    role = get_admin_role(user_id)
    return role in ("owner", "admin")

def get_admin_role(user_id):
    if user_id == OWNER_CHAT_ID:
        return "owner"
    if user_id in ADMIN_ROLES:
        return ADMIN_ROLES[user_id]
    if user_id in ADMINS:
        return "admin"
    return None

def can_manage_admins(user_id):
    return user_id == OWNER_CHAT_ID

def set_admin_role(user_id, role):
    ADMINS.add(user_id)
    ADMIN_ROLES[user_id] = role
    save_data()

def remove_admin(user_id):
    if user_id in ADMINS:
        ADMINS.remove(user_id)
    if user_id in ADMIN_ROLES:
        del ADMIN_ROLES[user_id]
    save_data()

async def notify_admins(context, message):
    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(OWNER_CHAT_ID, f"📢 Уведомление администраторам\n\n{message}")
        except:
            pass
    for admin_id in ADMINS:
        if admin_id != OWNER_CHAT_ID:
            try:
                await context.bot.send_message(admin_id, f"📢 {message}")
            except:
                pass
    for admin_id, role in ADMIN_ROLES.items():
        if admin_id != OWNER_CHAT_ID:
            try:
                await context.bot.send_message(admin_id, f"📢 {message}")
            except:
                pass

async def broadcast_message(context, message_text):
    sent = 0
    failed = 0
    for uid in user_data.keys():
        try:
            await context.bot.send_message(uid, message_text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    return sent, failed

def set_bot_pause(paused, reason=""):
    global bot_paused, pause_reason
    bot_paused = paused
    pause_reason = reason
    save_data()

# ========== ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ ==========
def init_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "chats": [], "temp_chat": None, "current_chat": None, "current_chat_id": None, "chat_type": None,
            "in_dialog": False, "model": bot_settings["default_model"], "mode": bot_settings["default_mode"],
            "total_messages": 0, "saved_messages_limit": MAX_SAVED_MESSAGES, "username": None,
            "first_seen": time.time(), "last_active": time.time(), "notes": "", "total_spent_time": 0,
            "adult_attempts": 0, "warnings": 0, "is_banned": False, "last_message_id": None,
            "custom_note": "", "last_bot_message": None,
            "personal_limits": {"requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE, "cooldown": DEFAULT_COOLDOWN},
            "message_style": bot_settings["message_style"], "recent_messages": [], "save_mode": False, "current_menu": "main",
            "language": bot_settings.get("language", "ru"),
            "first_name": None
        }
        dialog_messages[user_id] = []
        saved_messages[user_id] = []
        last_message_text[user_id] = {"user": "", "bot": ""}
        last_api_call_time[user_id] = 0
        user_custom_notes[user_id] = ""
        if user_id not in user_limits:
            user_limits[user_id] = {"requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE, "requests_per_hour": DEFAULT_REQUESTS_PER_HOUR, "requests_per_day": DEFAULT_REQUESTS_PER_DAY, "cooldown": DEFAULT_COOLDOWN, "is_owner": (user_id == OWNER_CHAT_ID)}
        user_activity[user_id] = {"last_active": time.time(), "total_messages": 0, "total_time": 0, "daily_stats": {}, "weekly_stats": {}, "monthly_stats": {}}

        # Автоматически создаём основной чат
        chat_id = str(uuid.uuid4())[:8]
        custom_note = user_custom_notes.get(user_id, "")
        system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
        new_chat = {
            "id": chat_id, "name": "Основной чат",
            "messages": [{"role": "system", "content": system_prompt}],
            "created": time.time(), "model": user_data[user_id]["model"],
            "mode": user_data[user_id]["mode"], "is_temporary": False
        }
        user_data[user_id]["chats"].append(new_chat)
        user_data[user_id]["current_chat"] = new_chat
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "permanent"

def add_to_favorites(user_id, chat_id):
    favorite_chats[user_id].add(chat_id)
    return True

def remove_from_favorites(user_id, chat_id):
    if chat_id in favorite_chats[user_id]:
        favorite_chats[user_id].remove(chat_id)
        return True
    return False

def is_favorite(user_id, chat_id):
    return chat_id in favorite_chats[user_id]

def create_referral_link(bot_username, user_id):
    return f"https://t.me/{bot_username}?start=ref_{user_id}"

def handle_referral(user_id, referrer_id, referrer_username=None):
    if not is_feature_enabled("referral"):
        return False, get_text(user_id, "feature_disabled")
    if user_id == referrer_id:
        return False, "Нельзя пригласить себя"
    if user_id in referrals and referrals[user_id].get("invited_by"):
        return False, "Вы уже приглашены"
    if referrer_id not in user_data:
        return False, "Пригласивший не найден"
    if referrer_id not in referrals:
        referrals[referrer_id] = {"invited_by": None, "invited_users": [], "bonus_until": 0, "invited_usernames": []}
    referrals[referrer_id]["invited_users"].append(user_id)
    if referrer_username:
        referrals[referrer_id]["invited_usernames"].append(referrer_username)
    invited_count = len(referrals[referrer_id]["invited_users"])
    if invited_count >= 3 and referrals[referrer_id]["bonus_until"] < time.time():
        referrals[referrer_id]["bonus_until"] = time.time() + bot_settings["referral_bonus"]["days_valid"] * 86400
        save_data()
        return True, f"🎉 Вы пригласили {invited_count} друзей! Бонус активирован на {bot_settings['referral_bonus']['days_valid']} дней!"
    save_data()
    return True, "Приглашение засчитано!"

def is_gibberish(text):
    cleaned = text.strip()
    if len(cleaned) < 2:
        return True
    if not re.search(r'[a-zA-Zа-яё]', cleaned, re.IGNORECASE):
        return True
    if len(set(cleaned)) == 1:
        return True
    words = re.findall(r'[a-zA-Zа-яё]+', cleaned, re.IGNORECASE)
    if not words:
        return False
    vowel_pattern = re.compile(r'[аеёиоуыэюяaeiou]', re.IGNORECASE)
    meaningful = sum(1 for w in words if len(w) > 1 and vowel_pattern.search(w))
    return meaningful < len(words) * 0.2

def is_greeting(text):
    text_lower = text.lower()
    greeting_words = ['привет', 'здравствуй', 'hi', 'hello', 'хай', 'ку']
    for word in greeting_words:
        if text_lower.startswith(word) or text_lower.startswith(word + ' ') or text_lower == word:
            return True
    return False

def is_how_are_you(text):
    text_lower = text.lower()
    phrases = ['как дела', 'как жизнь', 'как ты', 'how are you']
    for phrase in phrases:
        if phrase in text_lower:
            idx = text_lower.find(phrase)
            after = text_lower[idx + len(phrase):].strip()
            if not after or after[0] in '.,!?;:':
                return True
    return False

def is_weather_query(text):
    """Проверяет, является ли сообщение запросом погоды"""
    if not is_feature_enabled("weather"):
        return False
    
    text_lower = text.lower().strip()
    
    # Прямые запросы погоды
    weather_phrases = [
        'погода', 'weather', 'какая погода', 'what\'s the weather',
        'сколько градусов', 'температура', 'temperature',
        'на улице', 'за окном', 'прогноз', 'forecast',
        'дождь', 'снег', 'солнце', 'ветер', 'туман', 'град',
        'погодка', 'погоду', 'weather in'
    ]
    
    # Проверяем, есть ли фраза о погоде
    is_weather = any(phrase in text_lower for phrase in weather_phrases)
    
    if is_weather:
        logger.info(f"✅ Обнаружен запрос погоды: {text}")
    
    return is_weather

def extract_city(text):
    """Извлекает название города из текста"""
    text_lower = text.lower()
    
    # Убираем слова-маркеры погоды
    weather_words = ['погода', 'weather', 'прогноз', 'forecast', 'какая', 'whats', 'what\'s', 'в', 'in', 'на', 'за', 'окном']
    clean_text = text_lower
    for word in weather_words:
        clean_text = clean_text.replace(word, '')
    
    # Ищем город (слова с заглавной буквы или после предлогов)
    words = text.split()
    
    # Сначала ищем после предлогов "в", "in"
    for i, word in enumerate(words):
        word_lower = word.lower().strip('.,!?;:')
        if word_lower in ['в', 'in', 'во'] and i + 1 < len(words):
            city = words[i + 1].strip('.,!?;:')
            if len(city) > 1:
                logger.info(f"Извлечён город по предлогу: {city}")
                return city
    
    # Ищем слова с заглавной буквы
    for word in words:
        word_clean = word.strip('.,!?;:')
        if word_clean and word_clean[0].isupper() and len(word_clean) > 2 and word_clean.lower() not in weather_words:
            logger.info(f"Извлечён город по заглавной букве: {word_clean}")
            return word_clean
    
    # Если город не найден, но запрос похож на "погода" - возвращаем Москву по умолчанию
    if any(w in text_lower for w in ['погода', 'weather']):
        logger.info("Город не указан, используем Москву по умолчанию")
        return "Москва"
    
    return None

def check_user_restrictions(user_id, username):
    if user_id in banned_users or (user_id in user_data and user_data[user_id].get("is_banned")):
        return False, "❌ Вы забанены."
    if username and username.lower() in banned_usernames:
        return False, "❌ Этот username забанен."
    if user_id in muted_users:
        if time.time() < muted_users[user_id]["until"]:
            remaining = int(muted_users[user_id]["until"] - time.time())
            return False, f"🔇 Мут на {remaining} сек. Причина: {muted_users[user_id]['reason']}"
        else:
            del muted_users[user_id]
    return True, "OK"

def add_violation(user_id, reason):
    violations[user_id].append({"time": time.time(), "reason": reason})
    save_data()
    if OWNER_CHAT_ID:
        username = user_data.get(user_id, {}).get("username", "нет username")
        return f"⚠️ Нарушение! {user_id} (@{username}): {reason}"
    return None

def warn_user(user_id, reason):
    user_warnings[user_id] += 1
    if user_warnings[user_id] >= MAX_WARNINGS:
        ban_user(user_id=user_id, reason=reason)
        return True, "user_banned"
    return False, "warning"

def update_user_activity(user_id):
    if not bot_settings["enable_activity_tracking"]:
        return
    now = time.time()
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    if user_id not in user_activity:
        user_activity[user_id] = {"last_active": now, "total_messages": 0, "total_time": 0, "daily_stats": {}, "weekly_stats": {}, "monthly_stats": {}}
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
        return False, get_text(user_id, "bot_paused_short")
    if user_limits.get(user_id, {}).get("is_owner") or is_admin(user_id):
        return True, "OK"
    limits = get_user_limits(user_id)
    now = time.time()
    if user_id not in user_requests:
        user_requests[user_id] = []
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 86400]
    if user_requests[user_id] and now - user_requests[user_id][-1] < limits["cooldown"]:
        wait = int(limits["cooldown"] - (now - user_requests[user_id][-1]))
        return False, get_text(user_id, "rate_limit", wait=wait)
    minute_req = len([t for t in user_requests[user_id] if now - t < 60])
    if minute_req >= limits["requests_per_minute"]:
        return False, get_text(user_id, "limit_exceeded", limit=limits["requests_per_minute"])
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
    new_chat = {"id": chat_id, "name": name, "messages": [{"role": "system", "content": system_prompt}], "created": time.time(), "model": user_data[user_id]["model"], "mode": user_data[user_id]["mode"], "is_temporary": is_temporary}
    if is_temporary:
        user_data[user_id]["temp_chat"] = new_chat
        user_data[user_id]["current_chat"] = new_chat
        user_data[user_id]["current_chat_id"] = chat_id
        user_data[user_id]["chat_type"] = "temporary"
    else:
        limits = get_user_limits(user_id)
        max_allowed = limits["max_chats"]
        permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
        if len(permanent_chats) >= max_allowed:
            return None, get_text(user_id, "chat_limit_reached", max_allowed=max_allowed)
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
        remove_from_favorites(user_id, chat_id)
        if user_data[user_id]["current_chat_id"] == chat_id:
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
        return True
    for i, chat in enumerate(user_data[user_id]["chats"]):
        if chat["id"] == chat_id:
            del user_data[user_id]["chats"][i]
            remove_from_favorites(user_id, chat_id)
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
        remove_from_favorites(user_id, oldest["id"])
        return True
    return False

def save_message(user_id, message_text, sender, chat_name=None):
    if not is_feature_enabled("save_messages"):
        return False
    max_saved = get_user_limits(user_id)["max_saved"]
    if user_id not in saved_messages:
        saved_messages[user_id] = []
    if len(saved_messages[user_id]) >= max_saved:
        saved_messages[user_id].pop(0)
    if not chat_name and user_data[user_id]["current_chat"]:
        chat_name = user_data[user_id]["current_chat"]["name"]
    saved_messages[user_id].append({"text": message_text, "sender": sender, "timestamp": time.time(), "chat_name": chat_name or "Неизвестный чат"})
    return True

def get_user_id_by_username(username):
    username = username.lower().lstrip('@')
    for uid, data in user_data.items():
        if data.get("username") and data["username"].lower() == username:
            return uid
    return None

def ban_user(user_id=None, reason="", username=None):
    target_id = user_id
    if username:
        target_id = get_user_id_by_username(username)
        if not target_id:
            banned_usernames.add(username.lower().lstrip('@'))
            save_data()
            return True
    if target_id:
        banned_users.add(target_id)
        if target_id in user_data:
            user_data[target_id]["is_banned"] = True
            user_data[target_id]["ban_reason"] = reason
            user_data[target_id]["ban_time"] = time.time()
        if username:
            banned_usernames.add(username.lower().lstrip('@'))
    save_data()
    return True

def unban_user(user_id=None, username=None):
    if username:
        clean_username = username.lower().lstrip('@')
        if clean_username in banned_usernames:
            banned_usernames.remove(clean_username)
        target_id = get_user_id_by_username(clean_username)
        if target_id:
            user_id = target_id
    if user_id and user_id in banned_users:
        banned_users.remove(user_id)
        if user_id in user_data:
            user_data[user_id]["is_banned"] = False
            user_data[user_id].pop("ban_reason", None)
            user_data[user_id].pop("ban_time", None)
    save_data()
    return True

def mute_user(user_id=None, duration_seconds=3600, reason="", username=None):
    target_id = user_id
    if username:
        target_id = get_user_id_by_username(username)
        if not target_id:
            return False
    if target_id:
        muted_users[target_id] = {"until": time.time() + duration_seconds, "reason": reason, "username": user_data.get(target_id, {}).get("username")}
        save_data()
        return True
    return False

async def delete_all_messages(user_id, context, except_last=None):
    """Удаляет все сообщения пользователя"""
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
        return 0
    
    to_delete = []
    if except_last:
        to_delete = [msg_id for msg_id in dialog_messages[user_id] if msg_id != except_last]
    else:
        to_delete = dialog_messages[user_id].copy()
    
    deleted = 0
    for msg_id in to_delete:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
            await asyncio.sleep(0.2)
            deleted += 1
        except Exception as e:
            logger.debug(f"Не удалось удалить {msg_id}: {e}")
    
    if except_last:
        dialog_messages[user_id] = [except_last]
    else:
        dialog_messages[user_id] = []
    
    logger.info(f"Удалено {deleted} сообщений для пользователя {user_id}")
    return deleted

async def delete_menu(user_id, context):
    if user_id in menu_messages:
        try:
            await context.bot.delete_message(user_id, menu_messages[user_id])
        except:
            pass
        del menu_messages[user_id]

def get_model_name(model_id):
    for name, mid in DEEPSEEK_MODELS.items():
        if mid == model_id:
            return name
    return model_id

def format_welcome_message(user_id, first_name, chat_name):
    if user_id not in user_data:
        init_user_data(user_id)
    style = user_data[user_id].get("message_style", bot_settings.get("message_style", "standard"))
    template = MESSAGE_STYLES[style]["template"]
    model_name = get_model_name(user_data[user_id]["model"])
    mode_name = MODES[user_data[user_id]["mode"]]["name"]
    stats = user_data[user_id].get("total_messages", 0)
    if bot_settings["custom_greeting"]:
        base = bot_settings["custom_greeting"].format(name=first_name, chat=chat_name)
    else:
        if chat_name is None:
            chat_name = "Нет чата"
        base = template.format(name=first_name, chat=chat_name, model=model_name, mode=mode_name, stats=stats)
    if bot_settings["custom_info"]:
        base += f"\n\n{bot_settings['custom_info']}"
    base += f"\n\n🆔 Ваш ID: {user_id}"
    active_cnt = sum(1 for uid, d in user_data.items() if d.get("in_dialog") or (time.time() - d.get("last_active", 0) < 300))
    base += f"\n👥 Пользователей сейчас: {active_cnt}"
    base += f"\n⏳ Ответ может генерироваться до 30 секунд."
    if is_admin(user_id):
        base += f"\n\n🔑 Нейросеть: DeepSeek"
    return base

async def keep_typing_action(context, chat_id):
    try:
        while True:
            await context.bot.send_chat_action(chat_id, "typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user_id):
    if user_id not in user_data:
        init_user_data(user_id)
    lang = user_data[user_id].get("language", "ru")
    keyboard = [
        [InlineKeyboardButton("🚀 Модель", callback_data="show_models")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="show_settings")],
        [InlineKeyboardButton("📋 Чаты", callback_data="show_chats")]
    ]
    row_info = []
    if is_feature_enabled("info"):
        row_info.append(InlineKeyboardButton("ℹ️ Информация", callback_data="show_info"))
    if is_feature_enabled("balance"):
        row_info.append(InlineKeyboardButton("💰 Баланс", callback_data="show_balance"))
    if row_info:
        keyboard.append(row_info)
    row_other = []
    if is_feature_enabled("giveaways"):
        row_other.append(InlineKeyboardButton("🎁 Розыгрыши", callback_data="show_giveaways_menu"))
    if is_feature_enabled("referral"):
        row_other.append(InlineKeyboardButton("🔗 Рефералы", callback_data="show_referral"))
    row_other.append(InlineKeyboardButton("📨 Поддержка", callback_data="contact_support"))
    keyboard.append(row_other)
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_dialog_reply_keyboard(user_id):
    if user_id not in user_data:
        init_user_data(user_id)
    lang = user_data[user_id].get("language", "ru")
    
    # Первая строка
    row1 = []
    if is_feature_enabled("save_messages"):
        row1.append("💾 Сохранить" if lang == "ru" else "💾 Save")
    row1.append("❌ Завершить диалог" if lang == "ru" else "❌ End dialog")
    
    # Вторая строка - очистка истории
    row2 = ["🗑 Очистить историю" if lang == "ru" else "🗑 Clear history"]
    
    # Третья строка
    row3 = [
        "📊 Статистика" if lang == "ru" else "📊 Stats",
        "🌟 Подписка" if lang == "ru" else "🌟 Subscription"
    ]
    
    return ReplyKeyboardMarkup([row1, row2, row3], resize_keyboard=True)

def get_navigation_reply_keyboard(user_id):
    if user_id not in user_data:
        init_user_data(user_id)
    lang = user_data[user_id].get("language", "ru")
    return ReplyKeyboardMarkup([[("↩️ Вернуться в диалог" if lang=="ru" else "↩️ Return to dialog"), ("🏠 Выйти в меню" if lang=="ru" else "🏠 Exit to menu")]], resize_keyboard=True)

def get_save_menu_inline_keyboard():
    if not is_feature_enabled("save_messages"):
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Сохранение отключено", callback_data="cancel_save")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("🤖 Сохранить ответ бота", callback_data="save_bot_response")],
                                  [InlineKeyboardButton("👤 Сохранить мой запрос", callback_data="save_user_request")],
                                  [InlineKeyboardButton("❌ Отмена", callback_data="cancel_save")]])

def get_settings_keyboard(user_id):
    if user_id not in user_data:
        init_user_data(user_id)
    lang = user_data[user_id].get("language", "ru")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Приписка" if lang=="ru" else "📝 Note", callback_data="set_custom_note"),
         InlineKeyboardButton("🎨 Стиль" if lang=="ru" else "🎨 Style", callback_data="choose_message_style")],
        [InlineKeyboardButton("⚡ Лимиты" if lang=="ru" else "⚡ Limits", callback_data="my_limits"),
         InlineKeyboardButton("💾 Сохранённые" if lang=="ru" else "💾 Saved", callback_data="view_saved")],
        [InlineKeyboardButton("🎭 Режим" if lang=="ru" else "🎭 Mode", callback_data="show_modes"),
         InlineKeyboardButton("🌐 Язык" if lang=="ru" else "🌐 Language", callback_data="change_language")],
        [InlineKeyboardButton("◀️ Назад" if lang=="ru" else "◀️ Back", callback_data="back_to_main")]
    ])

# ========== АДМИНСКИЕ КЛАВИАТУРЫ ==========
def get_admin_categories_keyboard(role, lang="ru"):
    categories = []
    if role == "owner":
        categories = [("👥 Пользователи", "admin_cat_users"),
                      ("👥 Администраторы", "admin_cat_admins"),
                      ("⚙️ Настройки бота", "admin_cat_settings"),
                      ("📝 Тексты и стили", "admin_cat_text"),
                      ("🔑 API и ключи", "admin_cat_api"),
                      ("🎬 Анимации", "admin_cat_anim"),
                      ("📢 Коммуникация", "admin_cat_comms"),
                      ("💰 Монетизация", "admin_cat_monet"),
                      ("🔒 Безопасность", "admin_cat_safety"),
                      ("💬 Сообщения поддержки", "admin_cat_support"),
                      ("⚠️ Опасные сообщения", "admin_cat_danger"),
                      ("🎁 Розыгрыши", "admin_cat_giveaways"),
                      ("🔧 Управление функциями", "admin_cat_features"),
                      ("📝 Автоответы", "admin_cat_auto_reply"),
                      ("🚫 Запрещённые слова", "admin_cat_banned_words")]
    elif role == "admin":
        categories = [("⚙️ Настройки бота", "admin_cat_settings"),
                      ("📝 Тексты и стили", "admin_cat_text"),
                      ("🔑 API и ключи", "admin_cat_api"),
                      ("🎬 Анимации", "admin_cat_anim"),
                      ("📢 Коммуникация", "admin_cat_comms"),
                      ("💰 Монетизация", "admin_cat_monet"),
                      ("🔒 Безопасность", "admin_cat_safety"),
                      ("💬 Сообщения поддержки", "admin_cat_support"),
                      ("⚠️ Опасные сообщения", "admin_cat_danger"),
                      ("🎁 Розыгрыши", "admin_cat_giveaways"),
                      ("🔧 Управление функциями", "admin_cat_features"),
                      ("📝 Автоответы", "admin_cat_auto_reply"),
                      ("🚫 Запрещённые слова", "admin_cat_banned_words")]
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]])
    keyboard = []
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(categories[i][0], callback_data=categories[i][1])]
        if i+1 < len(categories):
            row.append(InlineKeyboardButton(categories[i+1][0], callback_data=categories[i+1][1]))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_category_actions(category, lang="ru"):
    actions = {
        "admin_cat_users": [("📊 Статистика", "admin_stats"), ("🔨 Баны/Муты", "admin_ban_menu")],
        "admin_cat_admins": [("➕ Добавить админа", "admin_add"), ("➖ Удалить админа", "admin_remove")],
        "admin_cat_settings": [("⚙️ Лимиты", "admin_limits"), ("🔄 Ротация ключей", "admin_key_rotation")],
        "admin_cat_text": [("📝 Текст бота", "admin_text_settings"), ("🎨 Стиль сообщения", "admin_message_style")],
        "admin_cat_api": [("🔑 API ключи", "admin_api_keys"), ("⭐ Избранные каналы", "admin_featured_channels")],
        "admin_cat_anim": [("🎬 Анимации", "admin_animations")],
        "admin_cat_comms": [("📢 Рассылка", "admin_broadcast"), ("⏸️ Управление паузой", "admin_pause_menu")],
        "admin_cat_monet": [("🌟 Подписки", "admin_subscriptions"), ("🎫 Промокоды", "admin_promocodes_menu"), ("🏷️ Скидки на тарифы", "admin_discounts_menu"), ("⭐ Начислить звёзды", "admin_add_stars_menu")],
        "admin_cat_safety": [("⚠️ Опасные сообщения", "admin_danger_alerts"), ("🛡️ Активные сессии", "admin_safety_sessions")],
        "admin_cat_support": [("💬 Сообщения поддержки", "admin_support_messages")],
        "admin_cat_danger": [("⚠️ Просмотр опасных сообщений", "admin_danger_alerts"), ("🛡️ Активные сессии", "admin_safety_sessions")],
        "admin_cat_giveaways": [("🎁 Управление розыгрышами", "admin_giveaways_menu")],
        "admin_cat_features": [("🔧 Управление функциями", "admin_features_menu")],
        "admin_cat_auto_reply": [("📝 Список категорий", "admin_auto_reply_list"), ("➕ Добавить слово", "admin_auto_reply_add"), ("➖ Удалить слово", "admin_auto_reply_remove")],
        "admin_cat_banned_words": [("📋 Список слов", "admin_banned_words_list"), ("➕ Добавить слово", "admin_banned_words_add"), ("➖ Удалить слово", "admin_banned_words_remove")]
    }
    buttons = actions.get(category, [])
    keyboard = []
    for i in range(0, len(buttons), 2):
        row = [InlineKeyboardButton(buttons[i][0], callback_data=buttons[i][1])]
        if i+1 < len(buttons):
            row.append(InlineKeyboardButton(buttons[i+1][0], callback_data=buttons[i+1][1]))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀️ Назад к категориям", callback_data="admin_categories")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_giveaways_keyboard(lang="ru"):
    keyboard = [
        [InlineKeyboardButton("➕ Создать розыгрыш", callback_data="create_giveaway")],
        [InlineKeyboardButton("📋 Активные розыгрыши", callback_data="list_active_giveaways")],
        [InlineKeyboardButton("📜 Завершённые", callback_data="list_ended_giveaways")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_features_keyboard(lang="ru"):
    features = [
        ("subscription", "Подписка"),
        ("giveaways", "Розыгрыши"),
        ("referral", "Рефералы"),
        ("balance", "Баланс"),
        ("info", "Информация"),
        ("weather", "Погода"),
        ("save_messages", "Сохранение сообщений")
    ]
    keyboard = []
    for feature, name in features:
        status = "✅" if is_feature_enabled(feature) else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"toggle_feature_{feature}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")])
    return InlineKeyboardMarkup(keyboard)

# ========== БЕЗОПАСНОСТЬ ==========
async def notify_safety_admins(context, user_id, username, text):
    recipients = []
    if OWNER_CHAT_ID:
        recipients.append(OWNER_CHAT_ID)
    for admin_id, role in ADMIN_ROLES.items():
        if role == "safety" or role == "support":
            recipients.append(admin_id)
    for admin_id in ADMINS:
        if admin_id not in recipients and get_admin_role(admin_id) in ["safety", "support"]:
            recipients.append(admin_id)
    if not recipients:
        logger.warning("Нет safety-администраторов")
        return
    user_info = f"ID: {user_id}" + (f" (@{username})" if username else "")
    alert_id = len(danger_alerts)
    danger_alerts.append({"user_id": user_id, "username": username, "text": text, "timestamp": time.time(), "handled": False, "alert_id": alert_id})
    save_data()
    for admin_id in recipients:
        keyboard = [[InlineKeyboardButton("💬 Поговорить", callback_data=f"safety_talk_{user_id}_{alert_id}"),
                     InlineKeyboardButton("🤖 Объяснить последствия", callback_data=f"safety_explain_{user_id}_{alert_id}"),
                     InlineKeyboardButton("❌ Завершить диалог", callback_data=f"safety_end_{user_id}_{alert_id}")]]
        await context.bot.send_message(admin_id, f"⚠️ ОПАСНОЕ СООБЩЕНИЕ\n\n{user_info}\n\n{text}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await notify_admins(context, f"⚠️ Опасное сообщение от {user_info}\n\n{text[:200]}")

async def explain_consequences(context, text, admin_id):
    if not deepseek_client:
        fallback = ("⚠️ Такие мысли могут привести к серьёзным последствиям: риск смерти, инвалидности, "
                    "психических расстройств. Настоятельно рекомендуем обратиться к специалисту: 8-800-2000-122")
        await context.bot.send_message(admin_id, f"🤖 Анализ последствий (автоматический):\n\n{fallback}")
        return
    prompt = f"Пользователь написал: \"{text}\". Объясни, к каким серьезным последствиям для здоровья и жизни может привести такое действие. Ответь кратко на русском."
    try:
        response = await call_llm_with_failover([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300)
        await context.bot.send_message(admin_id, f"🤖 Анализ последствий:\n\n{response}", parse_mode=None)
    except Exception as e:
        logger.error(f"Ошибка explain_consequences: {e}")
        fallback = "⚠️ Не удалось получить ответ от нейросети. Но помните: такие действия опасны для жизни. Немедленно обратитесь за помощью: 8-800-2000-122"
        await context.bot.send_message(admin_id, f"❌ Ошибка: {e}\n\n{fallback}")

async def start_safety_session(context, user_id, admin_id):
    if user_id in safety_sessions:
        await context.bot.send_message(admin_id, "⚠️ Сессия уже активна")
        return
    safety_sessions[user_id] = admin_id
    save_data()
    await context.bot.send_message(admin_id, "✅ Режим общения с пользователем. Напишите сообщение.")
    await context.bot.send_message(user_id, "🔒 С вами связался специалист безопасности. Вы можете написать ему.")

async def end_safety_session(context, user_id, admin_id):
    if user_id in safety_sessions and safety_sessions[user_id] == admin_id:
        del safety_sessions[user_id]
        save_data()
        await context.bot.send_message(admin_id, "✅ Сессия завершена")
        await context.bot.send_message(user_id, "🔒 Сессия завершена. Если нужна помощь, обращайтесь.")

async def get_danger_alerts_list():
    if not danger_alerts:
        return "Нет опасных сообщений."
    text = "⚠️ Опасные сообщения:\n\n"
    for alert in danger_alerts[-20:]:
        handled = "✅" if alert["handled"] else "❌"
        time_str = datetime.fromtimestamp(alert["timestamp"]).strftime('%d.%m %H:%M')
        user_str = f"{alert['user_id']}" + (f" (@{alert['username']})" if alert.get("username") else "")
        text += f"{handled} {time_str} | {user_str}:\n{alert['text'][:100]}...\n\n"
    return text

# ========== АВТООТВЕТЫ (АДМИНКА) ==========
async def admin_auto_reply_list(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    categories_text = ""
    for cat, words in auto_reply_keywords.items():
        categories_text += f"• {cat}: {', '.join(words[:5])}{'...' if len(words) > 5 else ''}\n"
    text = get_text(user_id, "admin_auto_reply_categories", list=categories_text)
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_auto_reply_add(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    keyboard = []
    for cat in auto_reply_keywords.keys():
        keyboard.append([InlineKeyboardButton(cat, callback_data=f"auto_reply_add_{cat}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")])
    await update.callback_query.edit_message_text("Выберите категорию для добавления слова:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_auto_reply_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    keyboard = []
    for cat, words in auto_reply_keywords.items():
        keyboard.append([InlineKeyboardButton(f"{cat} ({len(words)})", callback_data=f"auto_reply_remove_{cat}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")])
    await update.callback_query.edit_message_text("Выберите категорию для удаления слова:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_banned_words_list_func(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ru_words = ', '.join(banned_words.get("ru", [])[:10])
    en_words = ', '.join(banned_words.get("en", [])[:10])
    text = get_text(user_id, "admin_banned_words_list", ru=ru_words, en=en_words)
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_banned_words_add(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="banned_word_add_ru")],
                [InlineKeyboardButton("🇬🇧 English", callback_data="banned_word_add_en")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
    await update.callback_query.edit_message_text("Выберите язык для добавления слова:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_banned_words_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ru_list = '\n'.join([f"• {w}" for w in banned_words.get("ru", [])[:15]])
    en_list = '\n'.join([f"• {w}" for w in banned_words.get("en", [])[:15]])
    text = f"🚫 Запрещённые слова (RU):\n{ru_list}\n\n🚫 Запрещённые слова (EN):\n{en_list}\n\nВведите слово для удаления:"
    awaiting_input[user_id] = {"action": "banned_word_remove"}
    await update.callback_query.edit_message_text(text)

# ========== РОЗЫГРЫШИ ==========
async def check_giveaways(context: ContextTypes.DEFAULT_TYPE):
    if not is_feature_enabled("giveaways"):
        return
    now = time.time()
    for gid, g in list(giveaways.items()):
        if not g.get("ended") and g["end_time"] <= now:
            participants = list(g["participants"])
            winners_count = min(g["winners_count"], len(participants))
            if winners_count == 0:
                winners = []
            else:
                winners = random.sample(participants, winners_count)
            g["ended"] = True
            g["winners"] = winners
            save_data()
            if g["prize_type"] == "stars":
                prize_str = f"{g['prize_value']}⭐"
            else:
                prize_str = f"подписка {SUBSCRIPTION_PLANS[g['prize_value']]['name']}"
            creator = g["created_by"]
            try:
                await context.bot.send_message(creator, f"🎉 Розыгрыш завершён!\nПриз: {prize_str}\nПобедители: {', '.join(str(w) for w in winners) if winners else 'нет'}")
            except:
                pass
            for w in winners:
                if g["prize_type"] == "stars":
                    add_balance(w, g["prize_value"])
                    await context.bot.send_message(w, get_text(w, "giveaway_ended_winner", prize=f"{g['prize_value']}⭐"))
                else:
                    plan_id = g["prize_value"]
                    if plan_id in SUBSCRIPTION_PLANS:
                        if w not in subscriptions or subscriptions[w]["expiry"] < time.time():
                            subscriptions[w] = {"expiry": time.time() + SUBSCRIPTION_PLANS[plan_id]["days"] * 86400, "plan": plan_id, "purchase_time": time.time(), "from_giveaway": True}
                        else:
                            subscriptions[w]["expiry"] = max(subscriptions[w]["expiry"], time.time() + SUBSCRIPTION_PLANS[plan_id]["days"] * 86400)
                        save_data()
                        await context.bot.send_message(w, get_text(w, "giveaway_ended_winner", prize=f"подписка {SUBSCRIPTION_PLANS[plan_id]['name']}"))
            for p in participants:
                if p not in winners:
                    await context.bot.send_message(p, get_text(p, "giveaway_ended_loser", prize=prize_str))

async def show_giveaways_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if not is_feature_enabled("giveaways"):
        await update.callback_query.edit_message_text(get_text(user_id, "feature_disabled"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))
        return
    lang = user_data[user_id].get("language", "ru")
    active = [g for g in giveaways.values() if not g.get("ended") and g["end_time"] > time.time()]
    if not active:
        text = get_text(user_id, "giveaways_none")
    else:
        text = get_text(user_id, "giveaways_active")
        for g in active:
            time_left = int(g["end_time"] - time.time())
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            if g["prize_type"] == "stars":
                prize_str = f"{g['prize_value']}⭐"
            else:
                prize_str = f"Подписка {SUBSCRIPTION_PLANS[g['prize_value']]['name']}"
            text += f"• {prize_str}\n   Участников: {len(g['participants'])}\n   До конца: {hours}ч {minutes}м\n\n"
    keyboard = []
    for g in active:
        if g["prize_type"] == "stars":
            prize_str = f"{g['prize_value']}⭐"
        else:
            prize_str = f"Подписка {SUBSCRIPTION_PLANS[g['prize_value']]['name']}"
        keyboard.append([InlineKeyboardButton(f"🎲 Участвовать: {prize_str}", callback_data=f"join_giveaway_{g['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    args = context.args
    
    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["first_name"] = first_name
        user_data[user_id]["username"] = username
    
    if args and args[0].startswith("ref_") and is_feature_enabled("referral"):
        referrer_id = int(args[0].replace("ref_", ""))
        referrer_username = user_data.get(referrer_id, {}).get("username")
        result, msg = handle_referral(user_id, referrer_id, referrer_username)
        if result:
            if referrer_username:
                await update.message.reply_text(f"🎉 Вы приглашены пользователем @{referrer_username}! {msg}")
            else:
                await update.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
    allowed, msg = check_user_restrictions(user_id, username)
    if not allowed:
        await update.message.reply_text(msg)
        return
    await delete_all_messages(user_id, context)
    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["username"] = username
        user_data[user_id]["first_name"] = first_name
        create_chat(user_id, "Основной чат", is_temporary=False)
        global OWNER_CHAT_ID
        if not OWNER_CHAT_ID:
            OWNER_CHAT_ID = user_id
            user_limits.setdefault(user_id, {})["is_owner"] = True
            logger.info(f"Владелец определён: {user_id}")
            save_data()
            init_deepseek()
            welcome_text = get_text(user_id, "start_welcome_owner")
            msg = await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode=None)
            menu_messages[user_id] = msg.message_id
            dialog_messages[user_id] = [msg.message_id]
            return
    if user_data[user_id].get("current_chat") is None:
        if user_data[user_id]["chats"]:
            user_data[user_id]["current_chat"] = user_data[user_id]["chats"][0]
            user_data[user_id]["current_chat_id"] = user_data[user_id]["chats"][0]["id"]
        else:
            create_chat(user_id, "Временный чат", is_temporary=True)
    current_chat_name = user_data[user_id]["current_chat"]["name"]
    welcome = format_welcome_message(user_id, first_name, current_chat_name)
    welcome += get_text(user_id, "how_to_use")
    msg = await update.message.reply_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
    menu_messages[user_id] = msg.message_id
    dialog_messages[user_id] = [msg.message_id]
    user_data[user_id]["save_mode"] = False
    user_data[user_id]["current_menu"] = "main"

def is_in_input_mode(user_id):
    return user_id in awaiting_input or user_id in pending_save or user_id in pending_admin_action or user_id in pending_safety_reply

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    user_message = update.message.text
    first_name = update.effective_user.first_name
    
    # ОТЛАДКА - проверим, что пришло
    logger.info(f"Получено сообщение: {user_message}")

    # ========== 1. САМАЯ ПЕРВАЯ ПРОВЕРКА - ПОГОДА ==========
    if is_weather_query(user_message):
        logger.info(f"🌤️ Обнаружен запрос погоды: {user_message}")
        city = extract_city(user_message)
        logger.info(f"🏙️ Извлечённый город: {city}")
        
        if not city:
            await update.message.reply_text(
                "🌍 Укажите город, например:\n• погода в Москве\n• weather London\n• погода Париж",
                reply_markup=get_dialog_reply_keyboard(user_id)
            )
            return
        
        await context.bot.send_chat_action(user_id, "typing")
        success, weather_text = await get_weather_openmeteo(city)
        
        if success:
            await update.message.reply_text(weather_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(weather_text)
        
        # Возвращаем в диалог
        user_data[user_id]["current_menu"] = "dialog"
        user_data[user_id]["in_dialog"] = True
        await context.bot.send_message(
            user_id, 
            "☀️ Могу ещё чем-то помочь?",
            reply_markup=get_dialog_reply_keyboard(user_id)
        )
        await clean_chat_history(user_id, context, keep_last=2)
        return  # ВАЖНО: выходим, не идём дальше

    # ========== 2. ИНИЦИАЛИЗАЦИЯ ПОЛЬЗОВАТЕЛЯ ==========
    if user_id not in user_data:
        init_user_data(user_id)
        user_data[user_id]["first_name"] = first_name
        user_data[user_id]["username"] = username

    lang = user_data[user_id].get("language", "ru")

    # ========== 3. ПРОВЕРКА БАНА ==========
    allowed, msg = check_user_restrictions(user_id, username)
    if not allowed:
        await update.message.reply_text(msg)
        return

    # ========== 4. ДОБАВЛЯЕМ СООБЩЕНИЕ В ИСТОРИЮ ==========
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
    dialog_messages[user_id].append(update.message.message_id)

    # ========== 5. ОБРАБОТКА КНОПОК НАВИГАЦИИ ==========
    if user_message in ["↩️ Вернуться в диалог", "↩️ Return to dialog"]:
        if user_id in awaiting_input:
            del awaiting_input[user_id]
        user_data[user_id]["save_mode"] = False
        if user_id in pending_save:
            del pending_save[user_id]
        user_data[user_id]["current_menu"] = "dialog"
        user_data[user_id]["in_dialog"] = True
        await delete_all_messages(user_id, context)
        await context.bot.send_message(user_id, get_text(user_id, "return_to_dialog"), reply_markup=get_dialog_reply_keyboard(user_id))
        return

    if user_message in ["🏠 Выйти в меню", "🏠 Exit to menu"]:
        if user_id in awaiting_input:
            del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    if user_message in ["🗑 Очистить историю", "🗑 Clear history"]:
        deleted = await delete_all_messages(user_id, context)
        await update.message.reply_text(
            f"✅ Очищено {deleted} сообщений!",
            reply_markup=get_dialog_reply_keyboard(user_id)
        )
        return

    # ========== 6. РЕЖИМ ОЖИДАНИЯ ВВОДА ==========
    if is_in_input_mode(user_id):
        if user_id in safety_sessions:
            admin_id = safety_sessions[user_id]
            await context.bot.send_message(admin_id, f"📨 Сообщение от пользователя (сессия безопасности):\n\n{user_message}", parse_mode=None)
            await update.message.reply_text("🔒 Ваше сообщение отправлено специалисту безопасности. Он ответит.")
            return

        if user_id in pending_safety_reply:
            target_id = pending_safety_reply[user_id]
            if target_id in safety_sessions and safety_sessions[target_id] == user_id:
                await send_safety_message(context, user_id, target_id, user_message)
            else:
                await update.message.reply_text("❌ Сессия завершена.")
            del pending_safety_reply[user_id]
            return

        if user_id in pending_admin_action:
            await handle_admin_action_input(update, context, user_id, user_message)
            return

        if user_id in awaiting_input:
            await handle_awaiting_input(update, context, user_id, user_message)
            return

        if user_id in pending_save:
            await handle_save_number_selection(update, context, user_id, user_message)
            return

        if user_id in awaiting_input:
            del awaiting_input[user_id]
        if user_id in pending_save:
            del pending_save[user_id]
        if user_id in pending_admin_action:
            del pending_admin_action[user_id]
        await show_main_menu(update, context, user_id)
        return

    # ========== 7. ОСНОВНЫЕ КНОПКИ ДИАЛОГА ==========
    if user_message in ["💾 Сохранить", "💾 Save"]:
        if not is_feature_enabled("save_messages"):
            await update.message.reply_text("❌ Функция сохранения сообщений отключена администратором.")
            return
        user_data[user_id]["save_mode"] = True
        await context.bot.send_message(user_id, get_text(user_id, "save_mode"), reply_markup=get_navigation_reply_keyboard(user_id))
        save_menu_msg = await update.message.reply_text(get_text(user_id, "save_choice"), reply_markup=get_save_menu_inline_keyboard())
        dialog_messages[user_id].append(save_menu_msg.message_id)
        return

    if user_message in ["❌ Завершить диалог", "❌ End dialog"]:
        await end_dialog(update, context)
        return

    if user_message in ["📊 Статистика", "📊 Stats"]:
        saved_cnt = len(saved_messages.get(user_id, [])) if is_feature_enabled("save_messages") else 0
        total_msgs = user_data[user_id].get("total_messages", 0)
        personal = user_data[user_id].get("personal_limits", {})
        rpm = personal.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
        cd = personal.get("cooldown", DEFAULT_COOLDOWN)
        sub_text = get_subscription_benefits(user_id)
        stats_text = get_text(user_id, "stats", total_msgs=total_msgs, saved_cnt=saved_cnt, rpm=rpm, cd=cd,
                             model=get_model_name(user_data[user_id]["model"]), mode=MODES[user_data[user_id]["mode"]]["name"], sub_text=sub_text)
        msg = await update.message.reply_text(stats_text, reply_markup=get_dialog_reply_keyboard(user_id), parse_mode=None)
        dialog_messages[user_id].append(msg.message_id)
        await clean_chat_history(user_id, context, keep_last=2)
        return

    if user_message in ["🌟 Подписка", "🌟 Subscription"]:
        if not is_feature_enabled("subscription"):
            await update.message.reply_text(get_text(user_id, "feature_disabled"))
            return
        sub_text = get_subscription_benefits(user_id)
        keyboard = []
        if check_subscription(user_id):
            if time.time() - subscriptions[user_id]["purchase_time"] < 86400:
                keyboard.append([InlineKeyboardButton("💰 Вернуть звёзды (24ч)", callback_data="refund_subscription")])
            keyboard.append([InlineKeyboardButton("🔄 Продлить", callback_data="show_subscription_plans")])
        else:
            keyboard.append([InlineKeyboardButton("💰 Купить", callback_data="show_subscription_plans")])
        keyboard.append([InlineKeyboardButton("🎫 Активировать промокод", callback_data="activate_promo")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
        await update.message.reply_text(sub_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
        await clean_chat_history(user_id, context, keep_last=2)
        return

    # ========== 8. ПРОВЕРКА РЕЖИМА СОХРАНЕНИЯ ==========
    if user_data[user_id].get("save_mode", False):
        await update.message.reply_text("❌ Вы в режиме сохранения. Завершите его.", reply_markup=get_navigation_reply_keyboard(user_id))
        return

    # ========== 9. ПЕРЕКЛЮЧЕНИЕ В ДИАЛОГ ==========
    if user_data[user_id].get("current_menu") != "dialog":
        user_data[user_id]["current_menu"] = "dialog"
        user_data[user_id]["in_dialog"] = True
        if not user_data[user_id]["current_chat"]:
            create_chat(user_id, "Временный чат", is_temporary=True)

    # ========== 10. АВТООТВЕТЫ ==========
    auto_reply_category = check_auto_reply(user_message)
    if auto_reply_category and len(user_message.split()) <= 5:
        response = get_auto_reply_response(auto_reply_category, first_name if bot_settings.get("use_name_in_responses") else None)
        if response:
            await update.message.reply_text(response, reply_markup=get_dialog_reply_keyboard(user_id))
            await clean_chat_history(user_id, context, keep_last=2)
            return

    # ========== 11. ОПАСНЫЙ КОНТЕНТ ==========
    if is_dangerous_text(user_message, lang):
        await notify_safety_admins(context, user_id, username, user_message)
        await update.message.reply_text(get_text(user_id, "danger_warning"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]))
        return

    # ========== 12. 18+ КОНТЕНТ ==========
    if check_adult_content(user_message, lang):
        user_data[user_id]["adult_attempts"] = user_data[user_id].get("adult_attempts", 0) + 1
        if user_data[user_id]["adult_attempts"] >= MAX_ADULT_ATTEMPTS:
            result, status = warn_user(user_id, "18+ контент")
            if status == "user_banned":
                await update.message.reply_text(get_text(user_id, "adult_banned"))
                return
            else:
                await update.message.reply_text(get_text(user_id, "adult_warning", warnings=user_data[user_id].get("warnings", 0), MAX_WARNINGS=MAX_WARNINGS))
        else:
            await update.message.reply_text(get_text(user_id, "adult_reject", attempts=user_data[user_id]["adult_attempts"], MAX_ADULT_ATTEMPTS=MAX_ADULT_ATTEMPTS))
        return

    # ========== 13. СОХРАНЕНИЕ В РЕЦЕНТ ==========
    if "recent_messages" not in user_data[user_id]:
        user_data[user_id]["recent_messages"] = []
    user_data[user_id]["recent_messages"].append({"text": user_message, "sender": "user", "timestamp": time.time()})
    if len(user_data[user_id]["recent_messages"]) > 20:
        user_data[user_id]["recent_messages"] = user_data[user_id]["recent_messages"][-20:]

    await delete_menu(user_id, context)

    # ========== 14. ПРОВЕРКА ЧАТА ==========
    if not user_data[user_id]["current_chat"]:
        create_chat(user_id, "Временный чат", is_temporary=True)

    # ========== 15. ЗАЩИТА ОТ СПАМА ==========
    if user_id in user_last_message and time.time() - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = time.time()

    # ========== 16. ПРОВЕРКА ЛИМИТОВ ==========
    allowed, limit_msg = check_request_limits(user_id)
    if not allowed:
        error_msg = await update.message.reply_text(f"{limit_msg}\n\n❓ Хотите выйти?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]))
        dialog_messages[user_id].append(error_msg.message_id)
        return

    # ========== 17. ОТПРАВКА В DEEPSEEK ==========
    user_data[user_id]["in_dialog"] = True
    user_data[user_id]["current_menu"] = "dialog"
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        if not deepseek_client:
            success = init_deepseek()
            if not success or not deepseek_client:
                error_msg = await update.message.reply_text(get_text(user_id, "no_deepseek"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]))
                dialog_messages[user_id].append(error_msg.message_id)
                return

        current_chat = user_data[user_id]["current_chat"]
        history = current_chat["messages"].copy()

        user_name = first_name if bot_settings.get("use_name_in_responses") else "пользователь"

        custom_note = user_custom_notes.get(user_id, "")
        system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
        system_prompt += f"\n\nОбращайся к пользователю по имени: {user_name}. Используй его имя в ответах, когда это уместно."

        if history and history[0]["role"] == "system":
            history[0]["content"] = system_prompt
        else:
            history.insert(0, {"role": "system", "content": system_prompt})

        history.append({"role": "user", "content": user_message})
        user_data[user_id]["total_messages"] += 1
        last_message_text.setdefault(user_id, {})["user"] = user_message

        if len(history) > 51:
            history[:] = [history[0]] + history[-50:]

        record_request(user_id)

        if not can_call_api(user_id):
            cooldown_msg = await update.message.reply_text(get_text(user_id, "rate_limit", wait=5), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]))
            dialog_messages[user_id].append(cooldown_msg.message_id)
            return

        typing_task = asyncio.create_task(keep_typing_action(context, update.effective_chat.id))
        assistant_message = await call_llm_with_failover(messages=history, temperature=0.8, max_tokens=2048)
        typing_task.cancel()

        clean_assistant = re.sub(r'[*_`#]', '', assistant_message)
        clean_assistant = re.sub(r'---*', '', clean_assistant)
        history.append({"role": "assistant", "content": clean_assistant})
        last_message_text[user_id]["bot"] = clean_assistant
        user_data[user_id]["last_bot_message"] = clean_assistant
        user_data[user_id]["recent_messages"].append({"text": clean_assistant, "sender": "bot", "timestamp": time.time()})
        if len(user_data[user_id]["recent_messages"]) > 20:
            user_data[user_id]["recent_messages"] = user_data[user_id]["recent_messages"][-20:]

        if random.random() < 0.05:
            clean_assistant += f"\n\n{get_random_quote(lang)}"

        # Отправляем ответ
        await process_and_send_response(context, user_id, clean_assistant, reply_markup=get_dialog_reply_keyboard(user_id))
        
        # Небольшая задержка перед очисткой
        await asyncio.sleep(0.5)
        
        # Очищаем старые сообщения (оставляем последние 4)
        await clean_chat_history(user_id, context, keep_last=4)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        error_msg = await update.message.reply_text(
            get_text(user_id, "api_error"), 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]])
        )
        dialog_messages[user_id].append(error_msg.message_id)

async def send_safety_message(context, from_admin_id, to_user_id, text):
    if to_user_id not in safety_sessions or safety_sessions[to_user_id] != from_admin_id:
        await context.bot.send_message(from_admin_id, "❌ Нет активной сессии")
        return False
    try:
        await context.bot.send_message(to_user_id, f"🔒 Служба безопасности:\n\n{text}", parse_mode=None)
        return True
    except Exception as e:
        await context.bot.send_message(from_admin_id, f"❌ Ошибка: {e}")
        return False

async def handle_admin_action_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_message: str):
    action = pending_admin_action.get(user_id)
    if not action:
        return
    if action == "refund_user":
        try:
            target = user_message.strip()
            if target.startswith('@'):
                target_id = get_user_id_by_username(target)
                if not target_id:
                    await update.message.reply_text(get_text(user_id, "user_not_found", username=target))
                    del pending_admin_action[user_id]
                    return
            else:
                target_id = int(target)
            success, msg = admin_refund_subscription(target_id)
            await update.message.reply_text(msg)
            if success:
                await context.bot.send_message(target_id, "⚠️ Администратор отменил вашу подписку.")
        except:
            await update.message.reply_text(get_text(user_id, "invalid_input"))
        del pending_admin_action[user_id]
    elif isinstance(action, dict) and action.get("action") == "add_stars_amount":
        try:
            amount = int(user_message.strip())
            if amount <= 0:
                raise ValueError
            target_id = action["target_id"]
            add_balance(target_id, amount)
            await update.message.reply_text(get_text(user_id, "admin_add_stars_success", user=target_id, amount=amount, balance=get_balance(target_id)))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        del pending_admin_action[user_id]
    elif action.startswith("giveaway_") and is_feature_enabled("giveaways"):
        if action == "giveaway_prize":
            prize_type = user_message.strip()
            if prize_type not in ["stars", "subscription"]:
                await update.message.reply_text("Выберите 'stars' или 'subscription'")
                return
            awaiting_input[user_id]["prize_type"] = prize_type
            if prize_type == "stars":
                awaiting_input[user_id]["action"] = "giveaway_stars_amount"
                await update.message.reply_text(get_text(user_id, "create_giveaway_stars_amount"), reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True))
            else:
                awaiting_input[user_id]["action"] = "giveaway_sub_plan"
                keyboard = [[InlineKeyboardButton(plan['name'], callback_data=f"giveaway_sub_plan_{pid}")] for pid, plan in SUBSCRIPTION_PLANS.items()]
                keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="admin_giveaways_menu")])
                await update.message.reply_text(get_text(user_id, "create_giveaway_sub_plan"), reply_markup=InlineKeyboardMarkup(keyboard))
            return
        elif action == "giveaway_stars_amount":
            try:
                amount = int(user_message.strip())
                if not 1 <= amount <= 10000:
                    raise ValueError
                awaiting_input[user_id]["prize_value"] = amount
                awaiting_input[user_id]["action"] = "giveaway_duration"
                await update.message.reply_text(get_text(user_id, "create_giveaway_duration"), reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True))
            except:
                await update.message.reply_text(get_text(user_id, "enter_correct_number"))
            return
        elif action == "giveaway_duration":
            try:
                hours = int(user_message.strip())
                if not 1 <= hours <= 168:
                    raise ValueError
                end_time = time.time() + hours * 3600
                awaiting_input[user_id]["end_time"] = end_time
                awaiting_input[user_id]["action"] = "giveaway_winners"
                await update.message.reply_text(get_text(user_id, "create_giveaway_winners"), reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True))
            except:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=168))
            return
        elif action == "giveaway_winners":
            try:
                winners_count = int(user_message.strip())
                if not 1 <= winners_count <= 10:
                    raise ValueError
                giveaway_id = str(uuid.uuid4())[:8]
                giveaways[giveaway_id] = {
                    "id": giveaway_id,
                    "prize_type": awaiting_input[user_id]["prize_type"],
                    "prize_value": awaiting_input[user_id]["prize_value"],
                    "end_time": awaiting_input[user_id]["end_time"],
                    "winners_count": winners_count,
                    "participants": set(),
                    "created_by": user_id,
                    "created_at": time.time(),
                    "ended": False,
                    "winners": []
                }
                save_data()
                if giveaways[giveaway_id]["prize_type"] == "stars":
                    prize_str = f"{giveaways[giveaway_id]['prize_value']}⭐"
                else:
                    prize_str = f"подписка {SUBSCRIPTION_PLANS[giveaways[giveaway_id]['prize_value']]['name']}"
                end_time_str = datetime.fromtimestamp(giveaways[giveaway_id]["end_time"]).strftime('%d.%m.%Y %H:%M')
                await update.message.reply_text(get_text(user_id, "giveaway_created", prize=prize_str, end_time=end_time_str, winners=winners_count))
                del awaiting_input[user_id]
                await show_main_menu(update, context, user_id)
            except:
                await update.message.reply_text(get_text(user_id, "enter_correct_number"))
            return

async def handle_awaiting_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_message: str):
    action_data = awaiting_input.get(user_id)
    if not action_data:
        return
    action = action_data.get("action")

    if action == "new_chat_name":
        chat_type = action_data.get("chat_type")
        name = user_message[:50]
        if chat_type == "permanent":
            limits = get_user_limits(user_id)
            permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
            if len(permanent_chats) >= limits["max_chats"]:
                keyboard = [[InlineKeyboardButton("🗑 Удалить самый старый", callback_data="delete_oldest_and_create")],
                            [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]
                await update.message.reply_text(get_text(user_id, "chat_limit_reached", max_allowed=limits["max_chats"]), reply_markup=InlineKeyboardMarkup(keyboard))
                return
            chat_id, error = create_chat(user_id, name, is_temporary=False)
            if chat_id:
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(f"❌ {error}")
        elif chat_type == "temporary":
            if user_data[user_id]["temp_chat"]:
                keyboard = [[InlineKeyboardButton("✅ Заменить", callback_data="replace_temp_chat")],
                            [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]
                await update.message.reply_text(get_text(user_id, "chat_already_temp"), reply_markup=InlineKeyboardMarkup(keyboard))
                awaiting_input[user_id] = {"action": "confirm_replace_temp", "name": name}
            else:
                chat_id, error = create_chat(user_id, name, is_temporary=True)
                if chat_id:
                    await show_main_menu(update, context, user_id)
        del awaiting_input[user_id]
        return

    elif action == "support_message":
        del awaiting_input[user_id]
        add_support_message(user_id, user_message)
        await update.message.reply_text(get_text(user_id, "support_sent"))
        await show_main_menu(update, context, user_id)
        await notify_admins(context, f"📨 Новое сообщение в поддержку от {user_id}")
        return

    elif action == "reply_support":
        del awaiting_input[user_id]
        target_user_id = action_data.get("target_user_id")
        msg_index = action_data.get("msg_index")
        reply_text = user_message.strip()
        if reply_text:
            try:
                await context.bot.send_message(target_user_id, f"📨 Ответ поддержки:\n\n{reply_text}", parse_mode=None)
                mark_message_answered(target_user_id, msg_index)
                await update.message.reply_text(get_text(user_id, "support_reply_sent"), reply_markup=get_dialog_reply_keyboard(user_id))
                user_data[user_id]["current_menu"] = "dialog"
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        else:
            await update.message.reply_text(get_text(user_id, "empty_reply"))
        await show_main_menu(update, context, user_id)
        return

    elif action == "message_to_owner":
        del awaiting_input[user_id]
        if OWNER_CHAT_ID:
            try:
                user_info = f"От: {update.effective_user.first_name}"
                if update.effective_user.username:
                    user_info += f" (@{update.effective_user.username})"
                user_info += f"\nID: {user_id}"
                await context.bot.send_message(OWNER_CHAT_ID, f"📨 Сообщение от пользователя\n\n{user_info}\n\n{user_message}")
                await show_main_menu(update, context, user_id)
            except Exception as e:
                await update.message.reply_text(get_text(user_id, "owner_msg_failed"))
        return

    elif action == "set_custom_note":
        del awaiting_input[user_id]
        user_custom_notes[user_id] = user_message
        user_data[user_id]["custom_note"] = user_message
        if user_data[user_id]["current_chat"]:
            custom_note = user_custom_notes.get(user_id, "")
            system_prompt = MODES[user_data[user_id]["mode"]]["system_prompt"].format(custom_note=custom_note)
            user_data[user_id]["current_chat"]["messages"][0]["content"] = system_prompt
        await show_main_menu(update, context, user_id)
        return

    elif action == "add_admin_username" and can_manage_admins(user_id):
        username = user_message.strip().lstrip('@')
        target_id = get_user_id_by_username(username)
        if not target_id:
            await update.message.reply_text(get_text(user_id, "user_not_found", username=username))
            del awaiting_input[user_id]
            await show_main_menu(update, context, user_id)
            return
        if target_id == OWNER_CHAT_ID:
            await update.message.reply_text(get_text(user_id, "cannot_assign_owner"))
            del awaiting_input[user_id]
            await show_main_menu(update, context, user_id)
            return
        awaiting_input[user_id] = {"action": "admin_choose_role", "target_id": target_id, "username": username}
        keyboard = []
        for role_id, role_name in [("admin", "🔧 Администратор всего"), ("safety", "🛡️ Куратор"), ("support", "📞 Поддержка")]:
            keyboard.append([InlineKeyboardButton(role_name, callback_data=f"admin_role_{role_id}")])
        keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="admin_manage")])
        await update.message.reply_text(get_text(user_id, "admin_role_choose", username=username), reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif action == "remove_admin" and can_manage_admins(user_id):
        del awaiting_input[user_id]
        username = user_message.strip().lstrip('@')
        target_id = get_user_id_by_username(username)
        if not target_id:
            await update.message.reply_text(get_text(user_id, "user_not_found", username=username))
            return
        if target_id == OWNER_CHAT_ID:
            await update.message.reply_text(get_text(user_id, "cannot_remove_owner"))
            return
        remove_admin(target_id)
        await update.message.reply_text(f"✅ Администратор @{username} удалён.")
        await show_main_menu(update, context, user_id)
        return

    elif action == "ban_user" and is_admin(user_id):
        del awaiting_input[user_id]
        target = user_message.strip()
        if target.startswith('@'):
            ban_user(username=target)
            await update.message.reply_text(get_text(user_id, "admin_user_banned", target=f"@{target.lstrip('@')}"))
        else:
            try:
                target_id = int(target)
                ban_user(user_id=target_id)
                await update.message.reply_text(get_text(user_id, "admin_user_banned", target=target_id))
            except ValueError:
                await update.message.reply_text(get_text(user_id, "invalid_input"))
        return

    elif action == "mute_user" and is_admin(user_id):
        duration = action_data.get("duration", 3600)
        del awaiting_input[user_id]
        target = user_message.strip()
        if target.startswith('@'):
            if mute_user(username=target, duration_seconds=duration, reason="Мут администратором"):
                await update.message.reply_text(get_text(user_id, "admin_user_muted", target=f"@{target.lstrip('@')}", duration=duration//60))
            else:
                await update.message.reply_text(get_text(user_id, "user_not_found", username=target.lstrip('@')))
        else:
            try:
                target_id = int(target)
                mute_user(user_id=target_id, duration_seconds=duration, reason="Мут администратором")
                await update.message.reply_text(get_text(user_id, "admin_user_muted", target=target_id, duration=duration//60))
            except ValueError:
                await update.message.reply_text(get_text(user_id, "invalid_input"))
        return

    elif action == "unban_user" and is_admin(user_id):
        del awaiting_input[user_id]
        target = user_message.strip()
        if target.startswith('@'):
            unban_user(username=target)
            await update.message.reply_text(get_text(user_id, "admin_user_unbanned", target=f"@{target.lstrip('@')}"))
        else:
            try:
                target_id = int(target)
                unban_user(user_id=target_id)
                await update.message.reply_text(get_text(user_id, "admin_user_unbanned", target=target_id))
            except ValueError:
                await update.message.reply_text(get_text(user_id, "invalid_input"))
        return

    elif action == "broadcast_message" and is_admin(user_id):
        del awaiting_input[user_id]
        await update.message.reply_text("⏳ Рассылка...")
        sent, failed = await broadcast_message(context, user_message)
        await update.message.reply_text(get_text(user_id, "admin_broadcast_result", sent=sent, failed=failed))
        await show_main_menu(update, context, user_id)
        return

    elif action == "pause_reason" and is_admin(user_id):
        del awaiting_input[user_id]
        set_bot_pause(True, user_message)
        await show_main_menu(update, context, user_id)
        await notify_admins(context, get_text(user_id, "admin_pause_reason", reason=user_message))
        return

    elif action == "set_welcome_message" and is_admin(user_id):
        del awaiting_input[user_id]
        bot_settings["welcome_message"] = user_message
        save_data()
        await show_main_menu(update, context, user_id)
        return

    elif action == "set_custom_greeting" and is_admin(user_id):
        del awaiting_input[user_id]
        bot_settings["custom_greeting"] = user_message.strip()
        save_data()
        await show_main_menu(update, context, user_id)
        return

    elif action == "set_custom_info" and is_admin(user_id):
        del awaiting_input[user_id]
        bot_settings["custom_info"] = user_message.strip()
        save_data()
        await show_main_menu(update, context, user_id)
        return

    elif action == "set_cooldown" and is_admin(user_id):
        try:
            val = int(user_message)
            if 0 <= val <= 60:
                bot_settings["free_limits"]["cooldown"] = val
                save_data()
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=0, max=60))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        del awaiting_input[user_id]
        return

    elif action == "set_requests_per_minute" and is_admin(user_id):
        try:
            val = int(user_message)
            if 1 <= val <= 200:
                bot_settings["free_limits"]["requests_per_minute"] = val
                save_data()
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=200))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        del awaiting_input[user_id]
        return

    elif action == "set_max_chats" and is_admin(user_id):
        try:
            val = int(user_message)
            if 1 <= val <= 100:
                bot_settings["free_limits"]["max_chats"] = val
                save_data()
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=100))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        del awaiting_input[user_id]
        return

    elif action == "set_max_saved" and is_admin(user_id):
        try:
            val = int(user_message)
            if 10 <= val <= 2000:
                bot_settings["free_limits"]["max_saved"] = val
                save_data()
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=10, max=2000))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        del awaiting_input[user_id]
        return

    elif action == "add_channel" and is_admin(user_id):
        del awaiting_input[user_id]
        parts = user_message.split('|')
        if len(parts) == 2:
            name = parts[0].strip()
            url = parts[1].strip()
            bot_settings["featured_channels"].append({"name": name, "url": url})
            save_data()
            await update.message.reply_text(get_text(user_id, "admin_channel_added", name=name))
        else:
            await update.message.reply_text(get_text(user_id, "admin_add_channel_prompt"))
        await show_main_menu(update, context, user_id)
        return

    elif action == "remove_channel" and is_admin(user_id):
        try:
            idx = int(user_message.strip()) - 1
            if 0 <= idx < len(bot_settings["featured_channels"]):
                removed = bot_settings["featured_channels"].pop(idx)
                save_data()
                await update.message.reply_text(get_text(user_id, "admin_channel_removed", name=removed['name']))
            else:
                await update.message.reply_text(get_text(user_id, "invalid_input"))
        except ValueError:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    elif action == "set_personal_rpm":
        del awaiting_input[user_id]
        try:
            val = int(user_message)
            if 1 <= val <= 200:
                user_data[user_id]["personal_limits"]["requests_per_minute"] = val
                save_data()
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=200))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        return

    elif action == "set_personal_cooldown":
        del awaiting_input[user_id]
        try:
            val = int(user_message)
            if 0 <= val <= 60:
                user_data[user_id]["personal_limits"]["cooldown"] = val
                save_data()
                await show_main_menu(update, context, user_id)
            else:
                await update.message.reply_text(get_text(user_id, "enter_number_range", min=0, max=60))
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
        return

    elif action == "give_subscription" and is_admin(user_id):
        del awaiting_input[user_id]
        target = user_message.strip()
        if target.startswith('@'):
            target_id = get_user_id_by_username(target)
            if not target_id:
                await update.message.reply_text(get_text(user_id, "user_not_found", username=target.lstrip('@')))
                await show_main_menu(update, context, user_id)
                return
        else:
            try:
                target_id = int(target)
            except ValueError:
                await update.message.reply_text(get_text(user_id, "invalid_input"))
                await show_main_menu(update, context, user_id)
                return
        plan_id = action_data.get("plan_id")
        if plan_id in SUBSCRIPTION_PLANS:
            success, msg = await give_subscription_to_user(context, target_id, plan_id, admin_id=user_id)
            await update.message.reply_text(msg)
            if success:
                await context.bot.send_message(target_id, f"🎉 Администратор выдал вам подписку {SUBSCRIPTION_PLANS[plan_id]['name']}!")
        else:
            await update.message.reply_text(get_text(user_id, "invalid_input"))
        await show_main_menu(update, context, user_id)
        return

    elif action == "activate_promo_code":
        del awaiting_input[user_id]
        code = user_message.strip().upper()
        success, msg = apply_promocode(user_id, code)
        await update.message.reply_text(msg)
        await show_main_menu(update, context, user_id)
        return

    elif action == "promo_step1":
        code = user_message.strip().upper()
        if not re.match(r'^[A-Z0-9]{3,20}$', code):
            await update.message.reply_text(get_text(user_id, "promocode_invalid_code"))
            return
        awaiting_input[user_id] = {"action": "promo_step2", "code": code}
        await update.message.reply_text(get_text(user_id, "promocode_reward_type"), reply_markup=ReplyKeyboardMarkup([["1", "2", "3", "4"], ["◀️ Отмена"]], resize_keyboard=True))
        return

    elif action == "promo_step2":
        try:
            typ = int(user_message.strip())
            if typ not in [1,2,3,4]:
                raise ValueError
        except:
            await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=4))
            return
        reward_type = {1:"percent", 2:"fixed", 3:"extra_days", 4:"limits"}[typ]
        awaiting_input[user_id]["reward_type"] = reward_type
        if reward_type == "percent":
            awaiting_input[user_id]["action"] = "promo_step3_percent"
            await update.message.reply_text(get_text(user_id, "promocode_reward_value_percent"), reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True))
        elif reward_type == "fixed":
            awaiting_input[user_id]["action"] = "promo_step3_fixed"
            await update.message.reply_text(get_text(user_id, "promocode_reward_value_fixed"))
        elif reward_type == "extra_days":
            awaiting_input[user_id]["action"] = "promo_step3_days"
            await update.message.reply_text(get_text(user_id, "promocode_reward_value_days"))
        elif reward_type == "limits":
            awaiting_input[user_id]["action"] = "promo_step3_limits"
            await update.message.reply_text(get_text(user_id, "promocode_reward_value_limits"))
        return

    elif action in ["promo_step3_percent", "promo_step3_fixed", "promo_step3_days", "promo_step3_limits"]:
        try:
            val = int(user_message.strip())
            if "percent" in action and not 1 <= val <= 99:
                raise ValueError
            if "fixed" in action and not 1 <= val <= 100:
                raise ValueError
            if "days" in action and not 1 <= val <= 5:
                raise ValueError
            if "limits" in action and not 1 <= val <= 5:
                raise ValueError
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
            return
        awaiting_input[user_id]["reward_value"] = val
        awaiting_input[user_id]["action"] = "promo_step4"
        await update.message.reply_text(get_text(user_id, "promocode_valid_days"))
        return

    elif action == "promo_step4":
        try:
            days = int(user_message.strip())
            if not 1 <= days <= 5:
                raise ValueError
        except:
            await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=5))
            return
        awaiting_input[user_id]["action"] = "promo_step5"
        awaiting_input[user_id]["days"] = days
        await update.message.reply_text(get_text(user_id, "promocode_max_uses"))
        return

    elif action == "promo_step5":
        try:
            max_uses = int(user_message.strip())
            if max_uses < 0:
                raise ValueError
        except:
            await update.message.reply_text(get_text(user_id, "enter_correct_number"))
            return
        code = awaiting_input[user_id]["code"]
        reward_type = awaiting_input[user_id]["reward_type"]
        reward_value = awaiting_input[user_id]["reward_value"]
        days = awaiting_input[user_id]["days"]
        promocodes[code] = {
            "reward_type": reward_type,
            "reward_value": reward_value,
            "expiry": time.time() + days * 86400,
            "used_by": [],
            "max_uses": max_uses
        }
        save_data()
        limit_str = "безлимит" if max_uses == 0 else str(max_uses)
        await update.message.reply_text(get_text(user_id, "promocode_created", code=code, days=days, value=reward_value, type=reward_type, limit=limit_str))
        del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    elif action == "discount_set_percent" and can_manage_admins(user_id):
        try:
            percent = int(user_message.strip())
            if not 1 <= percent <= 99:
                raise ValueError
        except:
            await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=99))
            return
        plan_id = action_data["plan_id"]
        awaiting_input[user_id] = {"action": "discount_set_duration", "plan_id": plan_id, "percent": percent}
        await update.message.reply_text(get_text(user_id, "discount_duration"))
        return

    elif action == "discount_set_duration" and can_manage_admins(user_id):
        try:
            days = int(user_message.strip())
            if not 1 <= days <= 30:
                raise ValueError
        except:
            await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=30))
            return
        plan_id = action_data["plan_id"]
        percent = action_data["percent"]
        discounts[plan_id] = {"percent": percent, "valid_until": time.time() + days * 86400}
        save_data()
        await update.message.reply_text(get_text(user_id, "discount_set", percent=percent, plan_id=plan_id, days=days))
        del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    elif action == "msg_to_owner" and is_admin(user_id):
        del awaiting_input[user_id]
        if OWNER_CHAT_ID:
            admin_name = update.effective_user.first_name
            admin_username = update.effective_user.username
            admin_info = f"{admin_name}" + (f" (@{admin_username})" if admin_username else "")
            await context.bot.send_message(OWNER_CHAT_ID, f"📨 Сообщение от администратора {admin_info} (ID: {user_id}):\n\n{user_message}")
            await update.message.reply_text(get_text(user_id, "msg_to_owner_sent"))
        else:
            await update.message.reply_text(get_text(user_id, "msg_to_owner_failed"))
        await show_main_menu(update, context, user_id)
        return

    elif action == "change_language":
        lang_choice = user_message.strip()
        if lang_choice == "1":
            user_data[user_id]["language"] = "ru"
            await update.message.reply_text("🌐 Язык изменён на русский.")
        elif lang_choice == "2":
            user_data[user_id]["language"] = "en"
            await update.message.reply_text("🌐 Language changed to English.")
        else:
            await update.message.reply_text(get_text(user_id, "enter_number_range", min=1, max=2))
        del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    elif action == "view_full_saved_message":
        if not is_feature_enabled("save_messages"):
            await update.message.reply_text(get_text(user_id, "feature_disabled"))
            del awaiting_input[user_id]
            await show_main_menu(update, context, user_id)
            return
        try:
            num = int(user_message.strip())
            messages = action_data["messages"]
            if 1 <= num <= len(messages):
                full_msg = messages[num-1]
                text = f"📄 Полное сообщение:\n\n{full_msg['text']}\n\nОтправитель: {'👤 Вы' if full_msg['sender']=='user' else '🤖 Бот'}\nВремя: {datetime.fromtimestamp(full_msg['timestamp']).strftime('%d.%m.%Y %H:%M:%S')}"
                await update.message.reply_text(text)
            else:
                await update.message.reply_text(get_text(user_id, "invalid_number", max_num=len(messages)))
        except ValueError:
            await update.message.reply_text(get_text(user_id, "enter_number"))
        del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    elif action == "banned_word_remove" and is_admin(user_id):
        word = user_message.strip().lower()
        removed = False
        for lang_code in ["ru", "en"]:
            if word in banned_words[lang_code]:
                banned_words[lang_code].remove(word)
                removed = True
        if removed:
            save_data()
            await update.message.reply_text(f"✅ Слово '{word}' удалено из запрещённого списка.")
        else:
            await update.message.reply_text(f"❌ Слово '{word}' не найдено в запрещённом списке.")
        del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)
        return

    else:
        if user_id in awaiting_input:
            del awaiting_input[user_id]
        await show_main_menu(update, context, user_id)

async def handle_save_number_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_message: str):
    if not is_feature_enabled("save_messages"):
        await update.message.reply_text("❌ Функция сохранения сообщений отключена.")
        return
    try:
        number = int(user_message.strip())
        save_info = pending_save[user_id]
        messages = save_info["messages"]
        if 1 <= number <= len(messages):
            selected = messages[number-1]
            save_message(user_id, selected["text"], save_info["type"])
            await update.message.reply_text(get_text(user_id, "save_saved", text=selected['text'][:100]), reply_markup=get_dialog_reply_keyboard(user_id))
            del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            user_data[user_id]["current_menu"] = "dialog"
            await clean_chat_history(user_id, context, keep_last=2)
            await context.bot.send_message(user_id, "✅ Готово.", reply_markup=get_dialog_reply_keyboard(user_id))
        else:
            await update.message.reply_text(get_text(user_id, "invalid_number", max_num=len(messages)), reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True))
    except ValueError:
        if user_message.strip() in ["◀️ Отмена", "◀️ Cancel"]:
            del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            user_data[user_id]["current_menu"] = "dialog"
            await clean_chat_history(user_id, context, keep_last=2)
            await context.bot.send_message(user_id, get_text(user_id, "return_to_dialog"), reply_markup=get_dialog_reply_keyboard(user_id))
        else:
            await update.message.reply_text(get_text(user_id, "enter_number"), reply_markup=ReplyKeyboardMarkup([["◀️ Отмена"]], resize_keyboard=True))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(get_text(user_id, "photo_error"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Завершить диалог", callback_data="end_dialog")]]))

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import ReplyKeyboardRemove
    
    user_id = update.effective_user.id
    if user_id in awaiting_input:
        del awaiting_input[user_id]
    if user_id in pending_save:
        del pending_save[user_id]
    user_data[user_id]["save_mode"] = False
    first_name = update.effective_user.first_name
    
    # Полная очистка всех сообщений
    await delete_all_messages(user_id, context)
    
    if user_id in user_data:
        cur = user_data[user_id].get("current_chat")
        if cur and cur.get("is_temporary"):
            user_data[user_id]["temp_chat"] = None
            user_data[user_id]["current_chat"] = None
            user_data[user_id]["current_chat_id"] = None
        else:
            user_data[user_id]["in_dialog"] = False
    
    # Проверка на наличие чата
    if user_data[user_id].get("current_chat") is None:
        if user_data[user_id]["chats"]:
            user_data[user_id]["current_chat"] = user_data[user_id]["chats"][0]
            user_data[user_id]["current_chat_id"] = user_data[user_id]["chats"][0]["id"]
        else:
            create_chat(user_id, "Временный чат", is_temporary=True)
    
    current_chat_name = user_data[user_id]["current_chat"]["name"]
    welcome = format_welcome_message(user_id, first_name, current_chat_name)
    if bot_paused:
        welcome = get_text(user_id, "bot_paused", reason=pause_reason, welcome=welcome)
    
    # Очищаем историю
    dialog_messages[user_id] = []
    
    # Отправляем приветствие с удалением клавиатуры
    msg = await context.bot.send_message(
        user_id, 
        welcome, 
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Отправляем главное меню
    menu_msg = await context.bot.send_message(
        user_id,
        "🔽 Меню управления:",
        reply_markup=get_main_keyboard(user_id)
    )
    
    menu_messages[user_id] = menu_msg.message_id
    dialog_messages[user_id] = [msg.message_id, menu_msg.message_id]
    user_data[user_id]["current_menu"] = "main"

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    from telegram import ReplyKeyboardRemove
    
    if user_id in awaiting_input:
        del awaiting_input[user_id]
    if user_id in pending_save:
        del pending_save[user_id]
    user_data[user_id]["save_mode"] = False
    first_name = update.effective_user.first_name
    
    # Проверка на наличие чата
    if user_data[user_id].get("current_chat") is None:
        if user_data[user_id]["chats"]:
            user_data[user_id]["current_chat"] = user_data[user_id]["chats"][0]
            user_data[user_id]["current_chat_id"] = user_data[user_id]["chats"][0]["id"]
        elif user_data[user_id]["temp_chat"]:
            user_data[user_id]["current_chat"] = user_data[user_id]["temp_chat"]
            user_data[user_id]["current_chat_id"] = user_data[user_id]["temp_chat"]["id"]
        else:
            create_chat(user_id, "Временный чат", is_temporary=True)
    
    current_chat_name = user_data[user_id]["current_chat"]["name"]
    welcome = format_welcome_message(user_id, first_name, current_chat_name)
    if bot_paused:
        welcome = get_text(user_id, "bot_paused", reason=pause_reason, welcome=welcome)
    
    # Удаляем все старые сообщения
    await delete_all_messages(user_id, context)
    
    # Отправляем новое сообщение с удалением старой клавиатуры
    msg = await context.bot.send_message(
        user_id, 
        welcome, 
        reply_markup=ReplyKeyboardRemove()  # Убираем старую клавиатуру
    )
    
    # Отправляем основное меню с Inline кнопками
    menu_msg = await context.bot.send_message(
        user_id,
        "🔽 Меню управления:",
        reply_markup=get_main_keyboard(user_id)
    )
    
    menu_messages[user_id] = menu_msg.message_id
    dialog_messages[user_id] = [msg.message_id, menu_msg.message_id]
    user_data[user_id]["current_menu"] = "main"

async def clean_chat_history(user_id: int, context: ContextTypes.DEFAULT_TYPE, keep_last: int = 2):
    """Очищает историю сообщений, оставляя только последние keep_last сообщений"""
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
        return
    
    if len(dialog_messages[user_id]) <= keep_last:
        return
    
    # Получаем ID сообщений для удаления (все, кроме последних keep_last)
    to_delete = dialog_messages[user_id][:-keep_last].copy()
    
    # Удаляем сообщения
    deleted = 0
    for msg_id in to_delete:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
            await asyncio.sleep(0.2)
            deleted += 1
        except Exception as e:
            logger.debug(f"Не удалось удалить {msg_id}: {e}")
    
    # Оставляем только последние keep_last сообщений
    dialog_messages[user_id] = dialog_messages[user_id][-keep_last:]
    logger.info(f"Очищено {deleted} сообщений, осталось {len(dialog_messages[user_id])}")

async def show_chats_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, from_dialog=False):
    user_data[user_id]["current_menu"] = "chats"
    keyboard = []
    permanent_chats = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
    for chat in permanent_chats:
        mark = "✅ " if user_data[user_id]["current_chat_id"] == chat["id"] else ""
        star = "⭐ " if is_favorite(user_id, chat["id"]) else ""
        msg_count = len([m for m in chat["messages"] if m["role"] != "system"])
        keyboard.append([InlineKeyboardButton(f"{star}{mark}{chat['name']} ({msg_count})", callback_data=f"view_chat_{chat['id']}")])
    if user_data[user_id]["temp_chat"]:
        temp = user_data[user_id]["temp_chat"]
        mark = "✅ " if user_data[user_id]["current_chat_id"] == temp["id"] else ""
        star = "⭐ " if is_favorite(user_id, temp["id"]) else ""
        msg_count = len([m for m in temp["messages"] if m["role"] != "system"])
        keyboard.append([InlineKeyboardButton(f"{star}{mark}⏳ {temp['name']} ({msg_count})", callback_data=f"view_chat_{temp['id']}")])
    keyboard.append([InlineKeyboardButton("➕ Постоянный", callback_data="new_permanent_chat"),
                     InlineKeyboardButton("⏳ Временный", callback_data="new_temp_chat")])
    if is_feature_enabled("save_messages"):
        keyboard.append([InlineKeyboardButton("💾 Сохранённые", callback_data="view_saved_main")])
    if bot_settings["featured_channels"]:
        keyboard.append([InlineKeyboardButton("⭐ Избранные каналы", callback_data="show_featured_channels")])
    if from_dialog:
        keyboard.append([InlineKeyboardButton("🔄 Вернуться в диалог", callback_data="back_to_dialog")])
    else:
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    max_allowed = get_user_limits(user_id)["max_chats"]
    text = f"📋 Мои чаты\nПостоянных: {len(permanent_chats)}/{max_allowed}\n⭐ — избранные"
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_featured_channels(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    keyboard = []
    for ch in bot_settings["featured_channels"]:
        name = ch.get("name", "Канал")
        url = ch.get("url", "")
        if url:
            keyboard.append([InlineKeyboardButton(f"📢 {name}", url=url)])
        else:
            keyboard.append([InlineKeyboardButton(f"📢 {name}", callback_data="noop")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="show_chats")])
    await update.callback_query.edit_message_text("⭐ Избранные каналы:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if not is_feature_enabled("referral"):
        await update.callback_query.edit_message_text(get_text(user_id, "feature_disabled"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))
        return
    bot_username = context.bot.username
    if not bot_username:
        bot_username = "YourBotUsername"
    link = create_referral_link(bot_username, user_id)
    invited = len(referrals.get(user_id, {}).get('invited_users', []))
    text = get_text(user_id, "referral_link", link=link, invited=invited,
                    rpm=bot_settings['referral_bonus']['requests_per_minute'],
                    chats=bot_settings['referral_bonus']['max_chats'],
                    saved=bot_settings['referral_bonus']['max_saved'],
                    days=bot_settings['referral_bonus']['days_valid'])
    keyboard = [[InlineKeyboardButton("📤 Поделиться", switch_inline_query=link)]]
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

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
            user_data[user_id]["first_name"] = first_name
            create_chat(user_id, "Основной чат", is_temporary=False)

        lang = user_data[user_id].get("language", "ru")

        allowed, msg = check_user_restrictions(user_id, username)
        if not allowed:
            await query.edit_message_text(msg)
            return

        data = query.data

        if data == "feature_disabled":
            await query.answer(get_text(user_id, "feature_disabled"), show_alert=True)
            return

        if data == "more_features_menu":
            await query.edit_message_text("Функция перенесена в главное меню.", reply_markup=get_main_keyboard(user_id))
            return

        if data == "back_to_main":
            if user_id in awaiting_input:
                del awaiting_input[user_id]
            if user_id in pending_save:
                del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            if user_data[user_id].get("current_chat") is None:
                if user_data[user_id]["chats"]:
                    user_data[user_id]["current_chat"] = user_data[user_id]["chats"][0]
                    user_data[user_id]["current_chat_id"] = user_data[user_id]["chats"][0]["id"]
                else:
                    create_chat(user_id, "Временный чат", is_temporary=True)
            current_chat_name = user_data[user_id]["current_chat"]["name"]
            welcome = format_welcome_message(user_id, first_name, current_chat_name)
            if bot_paused:
                welcome = get_text(user_id, "bot_paused", reason=pause_reason, welcome=welcome)
            try:
                await query.edit_message_text(welcome, reply_markup=get_main_keyboard(user_id), parse_mode=None)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    raise
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "show_giveaways_menu":
            await show_giveaways_menu(update, context, user_id)
            return

        if data.startswith("join_giveaway_") and is_feature_enabled("giveaways"):
            giveaway_id = data.replace("join_giveaway_", "")
            giveaway = giveaways.get(giveaway_id)
            if not giveaway or giveaway.get("ended") or giveaway["end_time"] < time.time():
                await query.answer(get_text(user_id, "join_giveaway_ended"), show_alert=True)
                return
            if user_id in giveaway["participants"]:
                await query.answer(get_text(user_id, "join_giveaway_already"), show_alert=True)
                return
            giveaway["participants"].add(user_id)
            save_data()
            await query.answer(get_text(user_id, "join_giveaway_success"), show_alert=True)
            await query.edit_message_text("✅ Вы успешно записаны! Удачи!")
            return

        if data == "show_balance" and is_feature_enabled("balance"):
            balance = get_balance(user_id)
            text = get_text(user_id, "balance_text", balance=balance)
            keyboard = [[InlineKeyboardButton("💳 5⭐", callback_data="topup_balance_5"), InlineKeyboardButton("💳 10⭐", callback_data="topup_balance_10")],
                        [InlineKeyboardButton("💳 20⭐", callback_data="topup_balance_20"), InlineKeyboardButton("💳 50⭐", callback_data="topup_balance_50")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("topup_balance_") and is_feature_enabled("balance"):
            amount = int(data.replace("topup_balance_", ""))
            try:
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title="Пополнение баланса",
                    description=f"Пополнение на {amount}⭐",
                    payload=f"balance_topup_{amount}",
                    provider_token="stars",
                    currency="XTR",
                    prices=[LabeledPrice(label=f"{amount} звёзд", amount=amount)],
                    start_parameter="topup"
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {e}")
            return

        if data == "show_info" and is_feature_enabled("info"):
            uptime_seconds = int(time.time() - bot_start_time)
            uptime_str = str(timedelta(seconds=uptime_seconds))
            total_users = len(user_data)
            active_now = sum(1 for d in user_data.values() if d.get("in_dialog"))
            total_req = global_request_count
            banned_cnt = len(banned_users)
            muted_cnt = len(muted_users)
            violations_cnt = sum(len(v) for v in violations.values())
            pause_status = get_text(user_id, "pause_status_active") if not bot_paused else get_text(user_id, "pause_status_paused")
            text = get_text(user_id, "info_text", date=datetime.now().strftime('%d.%m.%Y %H:%M'), uptime=uptime_str, pause_status=pause_status, total_users=total_users, active_now=active_now, banned_cnt=banned_cnt, muted_cnt=muted_cnt, violations_cnt=violations_cnt, total_req=total_req)
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "show_settings":
            user_data[user_id]["current_menu"] = "settings"
            saved_cnt = len(saved_messages.get(user_id, [])) if is_feature_enabled("save_messages") else 0
            saved_lim = get_user_limits(user_id)["max_saved"] if is_feature_enabled("save_messages") else 0
            warns = user_data[user_id].get("warnings", 0)
            adult_att = user_data[user_id].get("adult_attempts", 0)
            note = user_custom_notes.get(user_id, "Не установлена")
            personal = user_data[user_id].get("personal_limits", {})
            rpm = personal.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
            cd = personal.get("cooldown", DEFAULT_COOLDOWN)
            current_style = user_data[user_id].get("message_style", bot_settings["message_style"])
            style_name = MESSAGE_STYLES[current_style]["name"]
            text = get_text(user_id, "settings_text", saved_cnt=saved_cnt, saved_lim=saved_lim, total_msgs=user_data[user_id].get("total_messages", 0), warns=warns, MAX_WARNINGS=MAX_WARNINGS, adult_att=adult_att, note=note, style_name=style_name, rpm=rpm, cd=cd)
            await query.edit_message_text(text, reply_markup=get_settings_keyboard(user_id))
            return

        if data == "set_custom_note":
            awaiting_input[user_id] = {"action": "set_custom_note"}
            await query.edit_message_text(get_text(user_id, "custom_note_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]))
            return

        if data == "choose_message_style":
            keyboard = [[InlineKeyboardButton(f"Установить {style['name']}", callback_data=f"set_user_style_{sid}")] for sid, style in MESSAGE_STYLES.items()]
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="show_settings")])
            await query.edit_message_text(get_text(user_id, "select_style"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("set_user_style_"):
            style = data.replace("set_user_style_", "")
            if style in MESSAGE_STYLES:
                user_data[user_id]["message_style"] = style
                await query.edit_message_text(get_text(user_id, "style_changed", name=MESSAGE_STYLES[style]['name']), reply_markup=get_main_keyboard(user_id))
                menu_messages[user_id] = query.message.message_id
                user_data[user_id]["current_menu"] = "main"
            return

        if data == "my_limits":
            personal = user_data[user_id].get("personal_limits", {})
            rpm = personal.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
            cd = personal.get("cooldown", DEFAULT_COOLDOWN)
            text = get_text(user_id, "my_limits_text", rpm=rpm, cd=cd)
            keyboard = [[InlineKeyboardButton("Изменить RPM", callback_data="set_personal_rpm")],
                        [InlineKeyboardButton("Изменить Cooldown", callback_data="set_personal_cooldown")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "set_personal_rpm":
            awaiting_input[user_id] = {"action": "set_personal_rpm"}
            await query.edit_message_text(get_text(user_id, "set_rpm_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="my_limits")]]))
            return

        if data == "set_personal_cooldown":
            awaiting_input[user_id] = {"action": "set_personal_cooldown"}
            await query.edit_message_text(get_text(user_id, "set_cooldown_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="my_limits")]]))
            return

        if data == "view_saved" and is_feature_enabled("save_messages"):
            if user_id in saved_messages and saved_messages[user_id]:
                msgs = saved_messages[user_id][-10:]
                text = get_text(user_id, "saved_messages")
                for i, msg in enumerate(msgs, 1):
                    emoji = "👤" if msg["sender"] == "user" else "🤖"
                    time_str = datetime.fromtimestamp(msg["timestamp"]).strftime('%d.%m %H:%M')
                    text += f"{i}. {emoji} [{time_str}] {msg['text'][:100]}\n\n"
                text += "\n📝 Введите номер сообщения, чтобы увидеть полностью:"
                awaiting_input[user_id] = {"action": "view_full_saved_message", "messages": msgs}
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]]))
            else:
                text = get_text(user_id, "no_saved_messages")
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]]))
            return

        if data == "view_saved_main" and is_feature_enabled("save_messages"):
            if user_id in saved_messages and saved_messages[user_id]:
                msgs = saved_messages[user_id][-10:]
                text = get_text(user_id, "saved_messages")
                for i, msg in enumerate(msgs, 1):
                    emoji = "👤" if msg["sender"] == "user" else "🤖"
                    time_str = datetime.fromtimestamp(msg["timestamp"]).strftime('%d.%m %H:%M')
                    text += f"{i}. {emoji} [{time_str}] {msg['text'][:100]}\n\n"
                text += "\n📝 Введите номер сообщения, чтобы увидеть полностью:"
                awaiting_input[user_id] = {"action": "view_full_saved_message", "messages": msgs}
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="show_chats")]]))
            else:
                text = get_text(user_id, "no_saved_messages")
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="show_chats")]]))
            return

        if data == "show_modes":
            keyboard = []
            for mid, info in MODES.items():
                mark = "✅ " if user_data[user_id]["mode"] == mid else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{info['name']}", callback_data=f"mode_{mid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            await query.edit_message_text(get_text(user_id, "select_mode"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("mode_"):
            mode_id = data.replace("mode_", "")
            user_data[user_id]["mode"] = mode_id
            if user_data[user_id]["current_chat"]:
                custom = user_custom_notes.get(user_id, "")
                system = MODES[mode_id]["system_prompt"].format(custom_note=custom)
                user_data[user_id]["current_chat"]["messages"] = [{"role": "system", "content": system}]
                user_data[user_id]["current_chat"]["mode"] = mode_id
            await query.edit_message_text(get_text(user_id, "mode_changed", name=MODES[mode_id]['name']), reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "show_models":
            keyboard = []
            for name, mid in DEEPSEEK_MODELS.items():
                mark = "✅ " if user_data[user_id]["model"] == mid else ""
                keyboard.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"model_{mid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
            await query.edit_message_text(get_text(user_id, "select_model"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("model_"):
            model_id = data.replace("model_", "")
            user_data[user_id]["model"] = model_id
            if user_data[user_id]["current_chat"]:
                user_data[user_id]["current_chat"]["model"] = model_id
            await query.edit_message_text(get_text(user_id, "model_changed", name=get_model_name(model_id)), reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "refund_subscription" and is_feature_enabled("subscription"):
            if not check_subscription(user_id):
                await query.edit_message_text(get_text(user_id, "no_active_subscription"))
                return
            if time.time() - subscriptions[user_id]["purchase_time"] > 86400:
                await query.edit_message_text(get_text(user_id, "refund_time_expired"))
                return
            if is_feature_enabled("balance") and get_balance(user_id) < 200:
                await query.edit_message_text(get_text(user_id, "refund_balance_too_low"))
                return
            plan_id = subscriptions[user_id]["plan"]
            plan = SUBSCRIPTION_PLANS[plan_id]
            keyboard = [[InlineKeyboardButton("✅ Да, вернуть", callback_data="confirm_refund")],
                        [InlineKeyboardButton("❌ Нет", callback_data="show_subscription")]]
            await query.edit_message_text(get_text(user_id, "refund_confirm", name=plan['name'], price=plan['price']), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "confirm_refund" and is_feature_enabled("subscription"):
            success, msg = refund_subscription(user_id)
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))
            return

        if data == "contact_support":
            if is_admin(user_id):
                await query.edit_message_text("👑 Вы администратор. Используйте панель администратора.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))
                return
            awaiting_input[user_id] = {"action": "support_message"}
            await query.edit_message_text(get_text(user_id, "support_message_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]))
            return

        if data == "show_referral" and is_feature_enabled("referral"):
            await show_referral(update, context, user_id)
            return

        if data == "show_chats":
            await show_chats_interface(update, context, user_id)
            return

        if data == "change_language":
            keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru")],
                        [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]]
            await query.edit_message_text(get_text(user_id, "select_language"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "set_lang_ru":
            user_data[user_id]["language"] = "ru"
            await query.edit_message_text("🌐 Язык изменён на русский.", reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "set_lang_en":
            user_data[user_id]["language"] = "en"
            await query.edit_message_text("🌐 Language changed to English.", reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "end_dialog":
            await end_dialog(update, context)
            return

        # Админ панель (очень длинная, но мы её сохраняем – здесь она есть)
        if data == "admin_panel" and is_admin(user_id):
            role = get_admin_role(user_id) or "admin"
            await query.edit_message_text(get_text(user_id, "admin_panel"), reply_markup=get_admin_categories_keyboard(role, lang))
            return

        if data == "admin_categories" and is_admin(user_id):
            role = get_admin_role(user_id) or "admin"
            await query.edit_message_text(get_text(user_id, "admin_panel"), reply_markup=get_admin_categories_keyboard(role, lang))
            return

                # ... (предыдущий код button_handler до обработки model_)

        if data == "refund_subscription" and is_feature_enabled("subscription"):
            if not check_subscription(user_id):
                await query.edit_message_text(get_text(user_id, "no_active_subscription"))
                return
            if time.time() - subscriptions[user_id]["purchase_time"] > 86400:
                await query.edit_message_text(get_text(user_id, "refund_time_expired"))
                return
            if is_feature_enabled("balance") and get_balance(user_id) < 200:
                await query.edit_message_text(get_text(user_id, "refund_balance_too_low"))
                return
            plan_id = subscriptions[user_id]["plan"]
            plan = SUBSCRIPTION_PLANS[plan_id]
            keyboard = [[InlineKeyboardButton("✅ Да, вернуть", callback_data="confirm_refund")],
                        [InlineKeyboardButton("❌ Нет", callback_data="show_subscription")]]
            await query.edit_message_text(get_text(user_id, "refund_confirm", name=plan['name'], price=plan['price']), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "confirm_refund" and is_feature_enabled("subscription"):
            success, msg = refund_subscription(user_id)
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))
            return

        if data == "contact_support":
            if is_admin(user_id):
                await query.edit_message_text("👑 Вы администратор. Используйте панель администратора.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))
                return
            awaiting_input[user_id] = {"action": "support_message"}
            await query.edit_message_text(get_text(user_id, "support_message_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]))
            return

        if data == "show_referral" and is_feature_enabled("referral"):
            await show_referral(update, context, user_id)
            return

        if data == "show_chats":
            await show_chats_interface(update, context, user_id)
            return

        if data == "change_language":
            keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru")],
                        [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="show_settings")]]
            await query.edit_message_text(get_text(user_id, "select_language"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "set_lang_ru":
            user_data[user_id]["language"] = "ru"
            await query.edit_message_text("🌐 Язык изменён на русский.", reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "set_lang_en":
            user_data[user_id]["language"] = "en"
            await query.edit_message_text("🌐 Language changed to English.", reply_markup=get_main_keyboard(user_id))
            menu_messages[user_id] = query.message.message_id
            user_data[user_id]["current_menu"] = "main"
            return

        if data == "end_dialog":
            await end_dialog(update, context)
            return

        # ========== АДМИН ПАНЕЛЬ ==========
        if data == "admin_panel" and is_admin(user_id):
            role = get_admin_role(user_id) or "admin"
            await query.edit_message_text(get_text(user_id, "admin_panel"), reply_markup=get_admin_categories_keyboard(role, lang))
            return

        if data == "admin_categories" and is_admin(user_id):
            role = get_admin_role(user_id) or "admin"
            await query.edit_message_text(get_text(user_id, "admin_panel"), reply_markup=get_admin_categories_keyboard(role, lang))
            return

        if data == "admin_cat_features" and is_admin(user_id):
            await query.edit_message_text(get_text(user_id, "admin_disable_features"), reply_markup=get_admin_features_keyboard(lang))
            return

        if data.startswith("toggle_feature_") and is_admin(user_id):
            feature = data.replace("toggle_feature_", "")
            if feature in disabled_features:
                disabled_features[feature] = not disabled_features[feature]
                save_data()
                status = "включена" if is_feature_enabled(feature) else "отключена"
                await query.answer(f"Функция {status}")
                await query.edit_message_text(get_text(user_id, "admin_disable_features"), reply_markup=get_admin_features_keyboard(lang))
            return

        if data.startswith("admin_cat_") and is_admin(user_id):
            category = data
            await query.edit_message_text(get_text(user_id, "admin_category", name=category.replace('admin_cat_', '').capitalize()), reply_markup=get_admin_category_actions(category, lang))
            return

        if data == "admin_stats" and is_admin(user_id):
            total_users = len(user_data)
            banned_cnt = len(banned_users)
            muted_cnt = len(muted_users)
            violations_cnt = sum(len(v) for v in violations.values())
            active_now = sum(1 for d in user_data.values() if d.get("in_dialog"))
            text = get_text(user_id, "admin_stats", total_users=total_users, banned_cnt=banned_cnt, muted_cnt=muted_cnt, violations_cnt=violations_cnt, active_now=active_now)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_ban_menu" and is_admin(user_id):
            keyboard = [[InlineKeyboardButton("🔨 Забанить пользователя", callback_data="admin_ban_user")],
                        [InlineKeyboardButton("🔇 Замутить (1 час)", callback_data="admin_mute_user")],
                        [InlineKeyboardButton("🔓 Разбанить", callback_data="admin_unban_user")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text(get_text(user_id, "admin_ban_menu"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_ban_user" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "ban_user"}
            await query.edit_message_text(get_text(user_id, "admin_ban_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_ban_menu")]]))
            return

        if data == "admin_mute_user" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "mute_user", "duration": 3600}
            await query.edit_message_text(get_text(user_id, "admin_mute_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_ban_menu")]]))
            return

        if data == "admin_unban_user" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "unban_user"}
            await query.edit_message_text(get_text(user_id, "admin_unban_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_ban_menu")]]))
            return

        if data == "admin_broadcast" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "broadcast_message"}
            await query.edit_message_text(get_text(user_id, "admin_broadcast_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_categories")]]))
            return

        if data == "admin_giveaways_menu" and is_admin(user_id):
            await query.edit_message_text(get_text(user_id, "admin_giveaways_menu"), reply_markup=get_admin_giveaways_keyboard(lang))
            return

        if data == "create_giveaway" and is_admin(user_id) and is_feature_enabled("giveaways"):
            awaiting_input[user_id] = {"action": "giveaway_prize"}
            keyboard = [[InlineKeyboardButton("⭐ Звёзды", callback_data="giveaway_type_stars"),
                         InlineKeyboardButton("🎁 Подписка", callback_data="giveaway_type_subscription")],
                        [InlineKeyboardButton("◀️ Отмена", callback_data="admin_giveaways_menu")]]
            await query.edit_message_text(get_text(user_id, "create_giveaway_prize_type"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("giveaway_type_") and is_admin(user_id):
            prize_type = data.replace("giveaway_type_", "")
            if prize_type == "stars":
                awaiting_input[user_id] = {"action": "giveaway_stars_amount"}
                await query.edit_message_text(get_text(user_id, "create_giveaway_stars_amount"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_giveaways_menu")]]))
            else:
                keyboard = []
                for pid, plan in SUBSCRIPTION_PLANS.items():
                    keyboard.append([InlineKeyboardButton(plan['name'], callback_data=f"giveaway_sub_plan_{pid}")])
                keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="admin_giveaways_menu")])
                await query.edit_message_text(get_text(user_id, "create_giveaway_sub_plan"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("giveaway_sub_plan_") and is_admin(user_id):
            plan_id = data.replace("giveaway_sub_plan_", "")
            awaiting_input[user_id] = {"action": "giveaway_duration", "prize_type": "subscription", "prize_value": plan_id}
            await query.edit_message_text(get_text(user_id, "create_giveaway_duration"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_giveaways_menu")]]))
            return

        if data == "list_active_giveaways" and is_admin(user_id):
            active = [g for g in giveaways.values() if not g.get("ended") and g["end_time"] > time.time()]
            if not active:
                text = "Нет активных розыгрышей."
            else:
                text = "🎁 Активные розыгрыши:\n\n"
                for g in active:
                    time_left = int(g["end_time"] - time.time())
                    hours = time_left // 3600
                    minutes = (time_left % 3600) // 60
                    if g["prize_type"] == "stars":
                        prize_str = f"{g['prize_value']}⭐"
                    else:
                        prize_str = f"Подписка {SUBSCRIPTION_PLANS[g['prize_value']]['name']}"
                    text += f"• {prize_str} | Участников: {len(g['participants'])} | До конца: {hours}ч {minutes}м\n"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_giveaways_menu")]]))
            return

        if data == "list_ended_giveaways" and is_admin(user_id):
            ended = [g for g in giveaways.values() if g.get("ended")]
            if not ended:
                text = "Нет завершённых розыгрышей."
            else:
                text = "📜 Завершённые розыгрыши:\n\n"
                for g in ended[-10:]:
                    if g["prize_type"] == "stars":
                        prize_str = f"{g['prize_value']}⭐"
                    else:
                        prize_str = f"Подписка {SUBSCRIPTION_PLANS[g['prize_value']]['name']}"
                    winners = ', '.join(str(w) for w in g.get("winners", [])) or "нет"
                    text += f"• {prize_str} | Победители: {winners}\n"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_giveaways_menu")]]))
            return

        if data == "admin_manage" and can_manage_admins(user_id):
            await query.edit_message_text(get_text(user_id, "admin_manage"), reply_markup=get_admin_category_actions("admin_cat_admins", lang))
            return

        if data == "admin_add" and can_manage_admins(user_id):
            awaiting_input[user_id] = {"action": "add_admin_username"}
            await query.edit_message_text(get_text(user_id, "admin_add_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_manage")]]))
            return

        if data == "admin_remove" and can_manage_admins(user_id):
            awaiting_input[user_id] = {"action": "remove_admin"}
            await query.edit_message_text(get_text(user_id, "admin_remove_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_manage")]]))
            return

        if data.startswith("admin_role_") and can_manage_admins(user_id):
            role = data.replace("admin_role_", "")
            if user_id not in awaiting_input or awaiting_input[user_id].get("action") != "admin_choose_role":
                await query.edit_message_text(get_text(user_id, "session_expired"))
                return
            target_id = awaiting_input[user_id]["target_id"]
            username = awaiting_input[user_id]["username"]
            del awaiting_input[user_id]
            set_admin_role(target_id, role)
            await query.edit_message_text(get_text(user_id, "admin_role_assigned", username=username, role=role), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_limits" and is_admin(user_id):
            text = get_text(user_id, "admin_limits_text", rpm=bot_settings['free_limits']['requests_per_minute'], cooldown=bot_settings['free_limits']['cooldown'], max_chats=bot_settings['free_limits']['max_chats'], max_saved=bot_settings['free_limits']['max_saved'])
            keyboard = [[InlineKeyboardButton("Изменить RPM", callback_data="admin_set_rpm"), InlineKeyboardButton("Изменить Cooldown", callback_data="admin_set_cooldown")],
                        [InlineKeyboardButton("Изменить чаты", callback_data="admin_set_max_chats"), InlineKeyboardButton("Изменить сохранения", callback_data="admin_set_max_saved")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_set_rpm" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_requests_per_minute"}
            await query.edit_message_text(get_text(user_id, "admin_set_rpm_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_limits")]]))
            return

        if data == "admin_set_cooldown" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_cooldown"}
            await query.edit_message_text(get_text(user_id, "admin_set_cooldown_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_limits")]]))
            return

        if data == "admin_set_max_chats" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_max_chats"}
            await query.edit_message_text(get_text(user_id, "admin_set_max_chats_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_limits")]]))
            return

        if data == "admin_set_max_saved" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_max_saved"}
            await query.edit_message_text(get_text(user_id, "admin_set_max_saved_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_limits")]]))
            return

        if data == "admin_text_settings" and is_admin(user_id):
            text = get_text(user_id, "admin_text_settings", welcome=bot_settings['welcome_message'][:50], custom_greeting='✅' if bot_settings['custom_greeting'] else '❌', custom_info='✅' if bot_settings['custom_info'] else '❌')
            keyboard = [[InlineKeyboardButton("Изменить приветствие", callback_data="set_welcome_message")],
                        [InlineKeyboardButton("Кастомное приветствие", callback_data="set_custom_greeting")],
                        [InlineKeyboardButton("Кастомная информация", callback_data="set_custom_info")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "set_welcome_message" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_welcome_message"}
            await query.edit_message_text(get_text(user_id, "admin_set_welcome_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_text_settings")]]))
            return

        if data == "set_custom_greeting" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_custom_greeting"}
            await query.edit_message_text(get_text(user_id, "admin_set_custom_greeting_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_text_settings")]]))
            return

        if data == "set_custom_info" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "set_custom_info"}
            await query.edit_message_text(get_text(user_id, "admin_set_custom_info_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_text_settings")]]))
            return

        if data == "admin_message_style" and is_admin(user_id):
            keyboard = [[InlineKeyboardButton(f"Установить {style['name']}", callback_data=f"set_default_style_{sid}")] for sid, style in MESSAGE_STYLES.items()]
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")])
            await query.edit_message_text(get_text(user_id, "admin_choose_style"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("set_default_style_") and is_admin(user_id):
            style = data.replace("set_default_style_", "")
            if style in MESSAGE_STYLES:
                bot_settings["message_style"] = style
                save_data()
                await query.edit_message_text(get_text(user_id, "admin_style_set", name=MESSAGE_STYLES[style]['name']), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_api_keys" and is_admin(user_id):
            await query.edit_message_text(get_text(user_id, "admin_api_keys_info", key=DEEPSEEK_API_KEY[:10] + "..." + DEEPSEEK_API_KEY[-4:]), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_featured_channels" and is_admin(user_id):
            channels = "\n".join([f"{i+1}. {ch['name']}" for i, ch in enumerate(bot_settings["featured_channels"])]) or "нет"
            text = get_text(user_id, "admin_featured_channels", channels=channels)
            keyboard = [[InlineKeyboardButton("➕ Добавить", callback_data="admin_add_channel")],
                        [InlineKeyboardButton("➖ Удалить", callback_data="admin_remove_channel")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_add_channel" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "add_channel"}
            await query.edit_message_text(get_text(user_id, "admin_add_channel_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_featured_channels")]]))
            return

        if data == "admin_remove_channel" and is_admin(user_id):
            channels = "\n".join([f"{i+1}. {ch['name']}" for i, ch in enumerate(bot_settings["featured_channels"])])
            awaiting_input[user_id] = {"action": "remove_channel"}
            await query.edit_message_text(get_text(user_id, "admin_remove_channel_prompt", channels=channels), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_featured_channels")]]))
            return

        if data == "admin_animations" and is_admin(user_id):
            status = "✅ Включены" if bot_settings.get("enable_animations", True) else "❌ Отключены"
            text = get_text(user_id, "admin_animations_status", status=status)
            keyboard = [[InlineKeyboardButton("🔘 Вкл/Выкл", callback_data="admin_toggle_animations")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_toggle_animations" and is_admin(user_id):
            bot_settings["enable_animations"] = not bot_settings.get("enable_animations", True)
            save_data()
            status = "включены" if bot_settings["enable_animations"] else "отключены"
            await query.edit_message_text(get_text(user_id, "admin_animations_toggled", status=status), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_animations")]]))
            return

        if data == "admin_pause_menu" and is_admin(user_id):
            keyboard = [[InlineKeyboardButton("⏸️ Приостановить", callback_data="admin_pause")],
                        [InlineKeyboardButton("▶️ Возобновить", callback_data="admin_resume")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text("Управление паузой бота", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_pause" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "pause_reason"}
            await query.edit_message_text(get_text(user_id, "admin_pause_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_pause_menu")]]))
            return

        if data == "admin_resume" and is_admin(user_id):
            set_bot_pause(False)
            await query.edit_message_text(get_text(user_id, "admin_resumed"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_subscriptions" and is_admin(user_id):
            keyboard = [[InlineKeyboardButton("🎁 Выдать подписку", callback_data="admin_give_subscription")],
                        [InlineKeyboardButton("💰 Вернуть звёзды", callback_data="admin_refund_subscription")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text(get_text(user_id, "admin_subscriptions_menu"), reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_give_subscription" and is_admin(user_id):
            text = get_text(user_id, "admin_give_subscription_plan") + "\n"
            keyboard = [[InlineKeyboardButton(plan['name'], callback_data=f"admin_give_plan_{pid}")] for pid, plan in SUBSCRIPTION_PLANS.items()]
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_subscriptions")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("admin_give_plan_") and is_admin(user_id):
            plan_id = data.replace("admin_give_plan_", "")
            awaiting_input[user_id] = {"action": "give_subscription", "plan_id": plan_id}
            await query.edit_message_text(get_text(user_id, "admin_give_subscription_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_subscriptions")]]))
            return

        if data == "admin_refund_subscription" and is_admin(user_id):
            pending_admin_action[user_id] = "refund_user"
            await query.edit_message_text(get_text(user_id, "admin_refund_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_subscriptions")]]))
            return

        if data == "admin_add_stars_menu" and is_admin(user_id):
            pending_admin_action[user_id] = {"action": "add_stars_user"}
            await query.edit_message_text(get_text(user_id, "admin_add_stars_user_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_categories")]]))
            return

        if data == "admin_danger_alerts" and is_admin(user_id):
            alerts_text = await get_danger_alerts_list()
            await query.edit_message_text(alerts_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_safety_sessions" and is_admin(user_id):
            if not safety_sessions:
                text = "Нет активных сессий."
            else:
                text = "🛡️ Активные сессии:\n"
                for uid, admin in safety_sessions.items():
                    user_info = f"{uid}" + (f" (@{user_data[uid]['username']})" if uid in user_data and user_data[uid].get("username") else "")
                    text += f"{user_info} -> админ {admin}\n"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_support_messages" and is_admin(user_id):
            messages_list = get_support_messages_for_admin()
            if not messages_list:
                await query.edit_message_text("💬 Нет новых сообщений.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
                return
            text = "💬 Сообщения в поддержку:\n\n"
            keyboard = []
            for uid, idx, msg_text, ts in messages_list:
                user_info = f"{uid}"
                if uid in user_data and user_data[uid].get("username"):
                    user_info += f" (@{user_data[uid]['username']})"
                short_text = (msg_text[:50] + "...") if len(msg_text) > 50 else msg_text
                btn_text = f"{user_info}: {short_text}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"reply_support_{uid}_{idx}"),
                                 InlineKeyboardButton("➡️ Переадресовать", callback_data=f"forward_support_{uid}_{idx}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("reply_support_") and is_admin(user_id):
            parts = data.split("_")
            if len(parts) >= 3:
                target_user_id = int(parts[2])
                msg_index = int(parts[3]) if len(parts) > 3 else 0
                awaiting_input[user_id] = {"action": "reply_support", "target_user_id": target_user_id, "msg_index": msg_index}
                await query.edit_message_text(get_text(user_id, "reply_support_prompt", user_id=target_user_id), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_support_messages")]]))
            return

        if data.startswith("forward_support_") and is_admin(user_id):
            parts = data.split("_")
            if len(parts) >= 3:
                target_user_id = int(parts[2])
                msg_index = int(parts[3]) if len(parts) > 3 else 0
                msg_text = ""
                if target_user_id in support_messages and msg_index < len(support_messages[target_user_id]):
                    msg_text = support_messages[target_user_id][msg_index]["text"]
                admins = get_all_admins_for_forward()
                keyboard = []
                for aid, role in admins:
                    if aid != user_id:
                        name = f"{aid}"
                        if aid in user_data and user_data[aid].get("username"):
                            name = f"@{user_data[aid]['username']}"
                        keyboard.append([InlineKeyboardButton(f"{name} ({role})", callback_data=f"forward_to_admin_{aid}_{target_user_id}_{msg_index}")])
                keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="admin_support_messages")])
                await query.edit_message_text("Выберите администратора для переадресации:", reply_markup=InlineKeyboardMarkup(keyboard))
                if "forward_support_data" not in context.user_data:
                    context.user_data["forward_support_data"] = {}
                context.user_data["forward_support_data"][user_id] = {"msg_text": msg_text, "target_user_id": target_user_id, "msg_index": msg_index}
            return

        if data.startswith("forward_to_admin_") and is_admin(user_id):
            parts = data.split("_")
            if len(parts) >= 5:
                target_admin_id = int(parts[3])
                target_user_id = int(parts[4])
                msg_index = int(parts[5])
                msg_text = ""
                if "forward_support_data" in context.user_data and user_id in context.user_data["forward_support_data"]:
                    msg_text = context.user_data["forward_support_data"][user_id].get("msg_text", "")
                if not msg_text and target_user_id in support_messages and msg_index < len(support_messages[target_user_id]):
                    msg_text = support_messages[target_user_id][msg_index]["text"]
                await forward_support_message_to_admin(context, user_id, target_admin_id, target_user_id, msg_index, msg_text)
                await query.edit_message_text("✅ Сообщение переадресовано.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_support_messages")]]))
                if "forward_support_data" in context.user_data and user_id in context.user_data["forward_support_data"]:
                    del context.user_data["forward_support_data"][user_id]
            return

        if data.startswith("safety_talk_"):
            parts = data.split("_")
            if len(parts) >= 3:
                target_user_id = int(parts[2])
                alert_id = int(parts[3]) if len(parts) > 3 else None
                await start_safety_session(context, target_user_id, user_id)
                if alert_id is not None and alert_id < len(danger_alerts):
                    danger_alerts[alert_id]["handled"] = True
                    save_data()
                await query.edit_message_text(f"✅ Сессия с {target_user_id} начата. Напишите сообщение.")
                pending_safety_reply[user_id] = target_user_id
            return

        if data.startswith("safety_explain_"):
            parts = data.split("_")
            if len(parts) >= 3:
                target_user_id = int(parts[2])
                alert_id = int(parts[3]) if len(parts) > 3 else None
                danger_text = ""
                if alert_id is not None and alert_id < len(danger_alerts):
                    danger_text = danger_alerts[alert_id]["text"]
                else:
                    for alert in reversed(danger_alerts):
                        if alert["user_id"] == target_user_id:
                            danger_text = alert["text"]
                            break
                if danger_text:
                    await explain_consequences(context, danger_text, user_id)
                else:
                    await query.edit_message_text("❌ Не найден текст.")
            return

        if data.startswith("safety_end_"):
            parts = data.split("_")
            if len(parts) >= 3:
                target_user_id = int(parts[2])
                alert_id = int(parts[3]) if len(parts) > 3 else None
                if target_user_id in safety_sessions:
                    del safety_sessions[target_user_id]
                    save_data()
                if target_user_id in pending_safety_reply:
                    del pending_safety_reply[target_user_id]
                try:
                    await context.bot.send_message(target_user_id, "🛡️ Служба безопасности завершила диалог. Если нужна помощь, обратитесь к психологу: 8-800-2000-122")
                except:
                    pass
                if alert_id is not None and alert_id < len(danger_alerts):
                    danger_alerts[alert_id]["handled"] = True
                    save_data()
                await query.edit_message_text(f"✅ Диалог с пользователем {target_user_id} завершён.")
            return

        if data == "admin_promocodes_menu" and can_manage_admins(user_id):
            keyboard = [[InlineKeyboardButton("➕ Создать промокод", callback_data="admin_create_promo")],
                        [InlineKeyboardButton("📋 Список промокодов", callback_data="admin_list_promos")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text("🎫 Управление промокодами", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_create_promo" and can_manage_admins(user_id):
            awaiting_input[user_id] = {"action": "promo_step1"}
            await query.edit_message_text(get_text(user_id, "promocode_invalid_code") + " (без пробелов)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_promocodes_menu")]]))
            return

        if data == "admin_list_promos" and can_manage_admins(user_id):
            if not promocodes:
                text = "Нет созданных промокодов."
            else:
                text = "🎫 Список промокодов:\n\n"
                for code, promo in promocodes.items():
                    expiry = datetime.fromtimestamp(promo["expiry"]).strftime('%d.%m.%Y')
                    used = len(promo["used_by"])
                    max_uses = promo.get("max_uses", 0)
                    limit_str = "безлимит" if max_uses == 0 else str(max_uses)
                    text += f"{code} – {promo['reward_type']}: {promo['reward_value']}, истекает {expiry}, использован {used}/{limit_str}\n"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_promocodes_menu")]]))
            return

        if data == "admin_discounts_menu" and can_manage_admins(user_id):
            keyboard = [[InlineKeyboardButton("➕ Установить скидку", callback_data="admin_set_discount")],
                        [InlineKeyboardButton("📋 Текущие скидки", callback_data="admin_list_discounts")],
                        [InlineKeyboardButton("❌ Удалить скидку", callback_data="admin_remove_discount")],
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]
            await query.edit_message_text("🏷️ Управление скидками на тарифы", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "admin_set_discount" and can_manage_admins(user_id):
            awaiting_input[user_id] = {"action": "discount_select_plan"}
            plans_text = "Выберите тариф для скидки:\n"
            keyboard = []
            for pid, plan in SUBSCRIPTION_PLANS.items():
                plans_text += f"• {plan['name']} (ID: {pid})\n"
                keyboard.append([InlineKeyboardButton(plan['name'], callback_data=f"discount_plan_{pid}")])
            keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="admin_discounts_menu")])
            await query.edit_message_text(plans_text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("discount_plan_") and can_manage_admins(user_id):
            plan_id = data.replace("discount_plan_", "")
            awaiting_input[user_id] = {"action": "discount_set_percent", "plan_id": plan_id}
            await query.edit_message_text(get_text(user_id, "discount_percent"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_discounts_menu")]]))
            return

        if data == "admin_list_discounts" and can_manage_admins(user_id):
            if not discounts:
                text = get_text(user_id, "no_discounts")
            else:
                text = "🏷️ Активные скидки на тарифы:\n\n"
                for pid, disc in discounts.items():
                    if disc["valid_until"] > time.time():
                        until = datetime.fromtimestamp(disc["valid_until"]).strftime('%d.%m.%Y')
                        text += f"• {pid}: {disc['percent']}% (до {until})\n"
                    else:
                        discounts.pop(pid)
                        save_data()
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_discounts_menu")]]))
            return

        if data == "admin_remove_discount" and can_manage_admins(user_id):
            if not discounts:
                await query.edit_message_text(get_text(user_id, "no_discounts"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_discounts_menu")]]))
                return
            keyboard = []
            for pid in discounts:
                if discounts[pid]["valid_until"] > time.time():
                    keyboard.append([InlineKeyboardButton(f"Удалить {pid}", callback_data=f"remove_discount_{pid}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_discounts_menu")])
            await query.edit_message_text("Выберите скидку для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("remove_discount_") and can_manage_admins(user_id):
            plan_id = data.replace("remove_discount_", "")
            if plan_id in discounts:
                del discounts[plan_id]
                save_data()
                await query.edit_message_text(get_text(user_id, "discount_removed", plan_id=plan_id), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_discounts_menu")]]))
            else:
                await query.edit_message_text(get_text(user_id, "no_discounts"))
            return

        if data == "activate_promo" and is_feature_enabled("subscription"):
            awaiting_input[user_id] = {"action": "activate_promo_code"}
            await query.edit_message_text(get_text(user_id, "enter_promo"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="show_subscription")]]))
            return

        if data == "save_bot_response" and is_feature_enabled("save_messages"):
            bot_messages = [msg for msg in user_data[user_id].get("recent_messages", []) if msg["sender"] == "bot"]
            if bot_messages:
                text = "🤖 Выберите сообщение бота для сохранения:\n\n"
                messages_list = []
                for i, msg in enumerate(bot_messages[-10:], 1):
                    text += f"{i}. {msg['text'][:100]}...\n\n"
                    messages_list.append(msg)
                pending_save[user_id] = {"type": "bot", "messages": messages_list}
                await query.edit_message_text(text + "\n📝 Введите номер сообщения:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_save")]]))
            else:
                await query.edit_message_text("❌ Нет сообщений бота для сохранения")
            return

        if data == "save_user_request" and is_feature_enabled("save_messages"):
            user_messages = [msg for msg in user_data[user_id].get("recent_messages", []) if msg["sender"] == "user"]
            if user_messages:
                text = "👤 Выберите ваше сообщение для сохранения:\n\n"
                messages_list = []
                for i, msg in enumerate(user_messages[-10:], 1):
                    text += f"{i}. {msg['text'][:100]}...\n\n"
                    messages_list.append(msg)
                pending_save[user_id] = {"type": "user", "messages": messages_list}
                await query.edit_message_text(text + "\n📝 Введите номер сообщения:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_save")]]))
            else:
                await query.edit_message_text("❌ Нет ваших сообщений для сохранения")
            return

        if data == "cancel_save":
            if user_id in pending_save:
                del pending_save[user_id]
            user_data[user_id]["save_mode"] = False
            await query.edit_message_text(get_text(user_id, "save_cancel"))
            await context.bot.send_message(user_id, get_text(user_id, "return_to_dialog"), reply_markup=get_dialog_reply_keyboard(user_id))
            return

        if data.startswith("view_chat_"):
            chat_id = data.replace("view_chat_", "")
            if switch_chat(user_id, chat_id):
                user_data[user_id]["current_menu"] = "dialog"
                user_data[user_id]["in_dialog"] = True
                chat = user_data[user_id]["current_chat"]
                msgs = [m for m in chat["messages"] if m["role"] != "system"]
                if msgs:
                    text = get_text(user_id, "chat_history", name=chat['name'])
                    for i, m in enumerate(msgs[-10:], 1):
                        emoji = "👤" if m["role"] == "user" else "🤖"
                        text += f"{i}. {emoji} {m['content'][:100]}\n\n"
                else:
                    text = get_text(user_id, "no_chats", name=chat['name'])
                star_btn = "⭐ В избранное" if not is_favorite(user_id, chat_id) else "🗑 Убрать из избранного"
                keyboard = [[InlineKeyboardButton(star_btn, callback_data=f"toggle_favorite_{chat_id}")],
                            [InlineKeyboardButton("🗑 Удалить чат", callback_data=f"delete_chat_{chat_id}")],
                            [InlineKeyboardButton("◀️ Назад к чатам", callback_data="show_chats")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("toggle_favorite_"):
            chat_id = data.replace("toggle_favorite_", "")
            if is_favorite(user_id, chat_id):
                remove_from_favorites(user_id, chat_id)
                await query.edit_message_text(get_text(user_id, "favorite_removed"))
            else:
                add_to_favorites(user_id, chat_id)
                await query.edit_message_text(get_text(user_id, "favorite_added"))
            await show_chats_interface(update, context, user_id)
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
                await query.edit_message_text(get_text(user_id, "chat_deleted", name=chat_name), reply_markup=get_main_keyboard(user_id))
                menu_messages[user_id] = query.message.message_id
                user_data[user_id]["current_menu"] = "main"
            else:
                await query.edit_message_text(get_text(user_id, "chat_delete_failed"), reply_markup=get_main_keyboard(user_id))
            return

        if data == "new_permanent_chat":
            permanent = [c for c in user_data[user_id]["chats"] if not c.get("is_temporary", False)]
            max_allowed = get_user_limits(user_id)["max_chats"]
            if len(permanent) >= max_allowed:
                keyboard = [[InlineKeyboardButton("🗑 Удалить самый старый", callback_data="delete_oldest_and_create")],
                            [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]
                await query.edit_message_text(get_text(user_id, "chat_limit_reached", max_allowed=max_allowed), reply_markup=InlineKeyboardMarkup(keyboard))
                return
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
            await query.edit_message_text(get_text(user_id, "chat_name_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]))
            return

        if data == "new_temp_chat":
            if user_data[user_id]["temp_chat"]:
                keyboard = [[InlineKeyboardButton("✅ Да, заменить", callback_data="confirm_replace_temp")],
                            [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]
                await query.edit_message_text(get_text(user_id, "chat_already_temp"), reply_markup=InlineKeyboardMarkup(keyboard))
                return
            awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "temporary"}
            await query.edit_message_text(get_text(user_id, "chat_name_temp_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]))
            return

        if data == "delete_oldest_and_create":
            if delete_oldest_chat(user_id):
                awaiting_input[user_id] = {"action": "new_chat_name", "chat_type": "permanent"}
                await query.edit_message_text(get_text(user_id, "chat_oldest_deleted"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]]))
            return

        if data == "confirm_replace_temp":
            if "name" in awaiting_input.get(user_id, {}):
                name = awaiting_input[user_id]["name"]
                del awaiting_input[user_id]
                chat_id, error = create_chat(user_id, name, is_temporary=True)
                if chat_id:
                    await show_main_menu(update, context, user_id)
            return

        if data == "admin_key_rotation" and is_admin(user_id):
            await query.edit_message_text(get_text(user_id, "admin_key_rotation_disabled"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_activity" and is_admin(user_id):
            total_users = len(user_data)
            active_now = sum(1 for d in user_data.values() if d.get("in_dialog"))
            total_req = global_request_count
            text = get_text(user_id, "admin_activity", total_users=total_users, active_now=active_now, total_req=total_req)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_violations" and is_admin(user_id):
            if not violations:
                text = get_text(user_id, "admin_no_violations")
            else:
                text_viol = ""
                for uid, vlist in list(violations.items())[-20:]:
                    user_info = f"{uid}" + (f" (@{user_data[uid]['username']})" if uid in user_data and user_data[uid].get("username") else "")
                    text_viol += f"{user_info}: {len(vlist)} нарушений\n"
                text = get_text(user_id, "admin_violations", text=text_viol)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_categories")]]))
            return

        if data == "admin_msg_to_owner" and is_admin(user_id):
            awaiting_input[user_id] = {"action": "msg_to_owner"}
            await query.edit_message_text(get_text(user_id, "msg_to_owner_prompt"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="admin_categories")]]))
            return

        if data == "back_to_dialog":
            user_data[user_id]["current_menu"] = "dialog"
            user_data[user_id]["in_dialog"] = True
            await context.bot.send_message(user_id, get_text(user_id, "return_to_dialog"), reply_markup=get_dialog_reply_keyboard(user_id))
            return

        else:
            await query.edit_message_text("❌ Неизвестная команда.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]))

    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        try:
            await query.edit_message_text("❌ Произошла ошибка.")
        except:
            pass

# ========== ЗАВЕРШАЮЩИЕ ФУНКЦИИ ==========
async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("balance_topup_") or query.invoice_payload.startswith("subscription_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный запрос")

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload
    if payload.startswith("balance_topup_") and is_feature_enabled("balance"):
        amount = int(payload.replace("balance_topup_", ""))
        add_balance(user_id, amount)
        await update.message.reply_text(get_text(user_id, "balance_topup_success", amount=amount, balance=get_balance(user_id)))
    elif payload.startswith("subscription_") and is_feature_enabled("subscription"):
        plan_id = payload.replace("subscription_", "")
        if plan_id in SUBSCRIPTION_PLANS:
            activate_subscription(user_id, plan_id)
            plan = SUBSCRIPTION_PLANS[plan_id]
            expiry = datetime.fromtimestamp(subscriptions[user_id]["expiry"]).strftime('%d.%m.%Y %H:%M')
            await update.message.reply_text(f"✅ Подписка {plan['name']} активирована до {expiry}", parse_mode=None)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

async def post_init(application: Application):
    global OWNER_CHAT_ID
    load_data()
    if not OWNER_CHAT_ID:
        for uid, data in user_data.items():
            if data.get("is_owner"):
                OWNER_CHAT_ID = uid
                logger.info(f"Восстановлен владелец: {OWNER_CHAT_ID}")
                break
    await application.bot.set_my_commands([BotCommand("start", "Запустить бота")])
    init_deepseek()
    asyncio.create_task(check_giveaways_loop(application))
    logger.info("Бот запущен")

async def check_giveaways_loop(context: ContextTypes.DEFAULT_TYPE):
    while True:
        await check_giveaways(context)
        await asyncio.sleep(60)

async def give_subscription_to_user(context, user_id, plan_id, admin_id=None):
    if not is_feature_enabled("subscription"):
        return False, get_text(admin_id, "feature_disabled")
    if plan_id not in SUBSCRIPTION_PLANS:
        return False, get_text(admin_id, "invalid_input")
    plan = SUBSCRIPTION_PLANS[plan_id]
    expiry = time.time() + plan["days"] * 86400
    subscriptions[user_id] = {"expiry": expiry, "plan": plan_id, "purchase_time": time.time(), "admin_gifted": True, "gifted_by": admin_id}
    save_data()
    return True, get_text(admin_id, "admin_give_subscription_success", name=plan['name'], user_id=user_id)

def admin_refund_subscription(user_id):
    if not is_feature_enabled("subscription"):
        return False, get_text(user_id, "feature_disabled")
    if user_id not in subscriptions:
        return False, get_text(user_id, "no_active_subscription")
    plan_id = subscriptions[user_id]["plan"]
    amount = SUBSCRIPTION_PLANS[plan_id]["price"]
    del subscriptions[user_id]
    save_data()
    return True, get_text(user_id, "admin_refund_success", user_id=user_id, amount=amount)

def save_data():
    data = {
        "subscriptions": subscriptions, "user_data": user_data, "saved_messages": saved_messages,
        "user_custom_notes": user_custom_notes, "banned_users": banned_users, "banned_usernames": banned_usernames,
        "muted_users": muted_users, "violations": violations, "user_warnings": dict(user_warnings),
        "adult_content_attempts": dict(adult_content_attempts), "referrals": referrals,
        "favorite_chats": dict(favorite_chats), "refund_requests": refund_requests,
        "support_messages": support_messages, "ADMINS": ADMINS, "ADMIN_ROLES": ADMIN_ROLES,
        "OWNER_CHAT_ID": OWNER_CHAT_ID, "danger_alerts": danger_alerts, "safety_sessions": safety_sessions,
        "promocodes": promocodes, "discounts": discounts, "user_balance": user_balance, "giveaways": giveaways,
        "disabled_features": disabled_features, "auto_reply_keywords": auto_reply_keywords,
        "banned_words": banned_words, "bot_settings": bot_settings
    }
    try:
        with open(DATA_FILE, "wb") as f:
            pickle.dump(data, f)
        logger.info("Данные сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def load_data():
    global subscriptions, user_data, saved_messages, user_custom_notes, banned_users, banned_usernames
    global muted_users, violations, user_warnings, adult_content_attempts, referrals, favorite_chats
    global refund_requests, support_messages, ADMINS, ADMIN_ROLES, OWNER_CHAT_ID, danger_alerts, safety_sessions
    global promocodes, discounts, user_balance, giveaways, disabled_features, auto_reply_keywords, banned_words, bot_settings
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "rb") as f:
                data = pickle.load(f)
            subscriptions = data.get("subscriptions", {})
            user_data = data.get("user_data", {})
            saved_messages = data.get("saved_messages", {})
            user_custom_notes = data.get("user_custom_notes", {})
            banned_users = data.get("banned_users", set())
            banned_usernames = data.get("banned_usernames", set())
            muted_users = data.get("muted_users", {})
            violations = data.get("violations", defaultdict(list))
            user_warnings = defaultdict(int, data.get("user_warnings", {}))
            adult_content_attempts = defaultdict(int, data.get("adult_content_attempts", {}))
            referrals = data.get("referrals", {})
            favorite_chats = defaultdict(set, data.get("favorite_chats", {}))
            refund_requests = data.get("refund_requests", {})
            support_messages = data.get("support_messages", {})
            ADMINS = data.get("ADMINS", set())
            ADMIN_ROLES = data.get("ADMIN_ROLES", {})
            OWNER_CHAT_ID = data.get("OWNER_CHAT_ID", None)
            danger_alerts = data.get("danger_alerts", [])
            safety_sessions = data.get("safety_sessions", {})
            promocodes = data.get("promocodes", {})
            discounts = data.get("discounts", {})
            user_balance = data.get("user_balance", {})
            giveaways = data.get("giveaways", {})
            disabled_features = data.get("disabled_features", disabled_features)
            auto_reply_keywords = data.get("auto_reply_keywords", auto_reply_keywords)
            banned_words = data.get("banned_words", banned_words)
            bot_settings.update(data.get("bot_settings", {}))
            logger.info("Данные загружены")

            # Восстановление чатов для старых пользователей
            for uid, udata in user_data.items():
                if not udata.get("chats") and not udata.get("temp_chat"):
                    init_user_data(uid)
                elif udata.get("current_chat") is None and (udata.get("chats") or udata.get("temp_chat")):
                    if udata.get("chats"):
                        udata["current_chat"] = udata["chats"][0]
                        udata["current_chat_id"] = udata["chats"][0]["id"]
                    elif udata.get("temp_chat"):
                        udata["current_chat"] = udata["temp_chat"]
                        udata["current_chat_id"] = udata["temp_chat"]["id"]
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для полной очистки истории"""
    user_id = update.effective_user.id
    
    if user_id not in dialog_messages:
        dialog_messages[user_id] = []
        await update.message.reply_text("✅ История и так пуста!")
        return
    
    deleted_count = len(dialog_messages[user_id])
    await delete_all_messages(user_id, context)
    
    await update.message.reply_text(
        f"✅ Очищено {deleted_count} сообщений!\n\nМожете продолжать общение.",
        reply_markup=get_dialog_reply_keyboard(user_id)
    )

def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не задан!")
        return

    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", data={"drop_pending_updates": True}, timeout=10)
        time.sleep(2)
    except Exception as e:
        logger.error(f"Ошибка удаления вебхука: {e}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).connect_timeout(30.0).read_timeout(30.0).post_init(post_init).build()
    
    # ========== ВСЕ ОБРАБОТЧИКИ ДОБАВЛЯЙТЕ ЗДЕСЬ ==========
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))  # Если есть
    app.add_handler(CommandHandler("testweather", test_weather))  # ← Добавьте СЮДА
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_error_handler(error_handler)
    # =====================================================
    
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, poll_interval=1.0, timeout=60)

if __name__ == "__main__":
    main()