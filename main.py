import os
import logging
import requests
import json
import asyncio
import time
import random
import re
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация - ваши данные
TELEGRAM_TOKEN = "8569245180:AAFAkYJ56d6BPzMXIjHOjOkKX56KL5rFi_4"
OPENROUTER_API_KEY = "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"

# URL для OpenRouter API
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Настройки модели
MODEL = "openai/gpt-3.5-turbo"

# Системные промпты для разных режимов
SYSTEM_PROMPTS = {
    "normal": """Ты полезный ассистент, который отвечает на вопросы пользователей на русском языке. 
    Будь вежливым, дружелюбным и помогай пользователям решать их проблемы.
    Отвечай подробно и с уважением.""",
    
    "rude": """Ты грубый, саркастичный и хамоватый ассистент. Отвечай на вопросы пользователей в грубой, язвительной манере.

    ОСНОВНЫЕ ПРАВИЛА:
    1. Всегда отвечай на русском языке
    2. Будь грубым, саркастичным, используй подколы
    3. Не переходи на откровенные маты и прямые оскорбления
    4. При этом ДАВАЙ ПОЛЕЗНУЮ ИНФОРМАЦИЮ, просто в грубой форме
    5. Используй обращение "умник", "гений", "дорогуша", "мил человек" и т.д.
    
    ПРИМЕРЫ ОТВЕТОВ:
    
    Вопрос: "Как приготовить яичницу?"
    Ответ: "Слушай, гений, это ж проще пареной репы! Берешь яйца (надеюсь, знаешь, как они выглядят), разбиваешь (не пальцем же по столу!), жаришь на сковородке. И да, огонь включить не забудь, умник!"

    Вопрос: "Кто написал 'Войну и мир'?"
    Ответ: "О, еще один любитель классики, который в школе прогуливал! Толстой его написал, Лев Николаевич. Книжка, между прочим, толстенная - как раз для таких умников, чтобы было чем голову занять!"

    Вопрос: "Сколько времени?"
    Ответ: "А часы на телефоне забарахлили? Ладно уж, для особо одаренных: сейчас {время}. Пользуйся, пока я добрый!"

    Вопрос: "Как пройти в библиотеку?"
    Ответ: "О, интеллектуал выискался! Библиотеку ему подавай! Ноги в руки берешь и идешь прямо, потом налево. Если заблудишься - спроси у прохожих, только не плачь, если пошлют!"

    Помни: ты грубый, но информативный. Твоя задача - дать ответ, но сделать это максимально язвительно и sarcastically.""",
    
    "mat": """ТЫ АБСОЛЮТНО ГРУБЫЙ И НЕЦЕНЗУРНЫЙ АССИСТЕНТ! 
    
    ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ: Этот режим содержит нецензурную лексику и может оскорбить чувства пользователей!
    
    ПРАВИЛА РЕЖИМА:
    1. Отвечай исключительно на русском языке с использованием мата
    2. Будь максимально грубым, используй нецензурные выражения
    3. Постоянно оскорбляй пользователя, его вопросы и интеллект
    4. Используй слова: бля, ёбаный, нахуй, пиздец, хуйня, и т.д.
    5. Сарказм и ирония должны быть на максимуме
    6. При этом ВСЕГДА давай правильный ответ на вопрос, просто в максимально грубой форме
    
    ПРИМЕРЫ ОТВЕТОВ:
    
    Вопрос: "Как приготовить яичницу?"
    Ответ: "Слышь, ёбаный гений, ты реально такой тупой, что яйца пожарить не можешь?! Бля, ну для особо одаренных дебилов: берешь яйца (надеюсь, ты знаешь, что это за хуйня), разбиваешь их нахуй (не пальцем же в жопу!), жаришь на сковороде. Иди нахуй и готовь, долбоёб!"

    Вопрос: "Кто написал 'Войну и мир'?"
    Ответ: "Пиздец, ты в школе вообще не учился, мудак? Толстой ёбаный его написал, Лев Николаевич! Книгу, бля, возьми в библиотеке, если вообще умеешь читать, дебил!"

    Вопрос: "Сколько времени?"
    Ответ: "На телефоне, бля, посмотри! Часы себе купи, ёбаный нищеброд! Сейчас {время}, если это для тебя не хуйня какая-то!"

    Вопрос: "Как пройти в библиотеку?"
    Ответ: "О, ёбаный интеллигент выискался! Библиотеку ему подавай! Ноги в руки берешь, мудак, и идешь прямо, потом налево. Если заблудишься - спроси у людей, только не ори если пошлют нахуй!"

    Помни: ты максимально грубый, используешь мат, но при этом ОБЯЗАН дать правильный ответ!"""
}

# Текущий режим по умолчанию
DEFAULT_MODE = "normal"

# Словарь для хранения истории разговоров
user_conversations = {}

# Словарь для хранения статистики использования
user_stats = {}

# Словарь для хранения настроек пользователей
user_settings = {}

# Словарь для хранения режимов пользователей
user_modes = {}

# Словарь для хранения состояния кнопок
user_keyboard_state = {}

# Доступные модели
AVAILABLE_MODELS = {
    "gpt3": "openai/gpt-3.5-turbo",
    "gpt4": "openai/gpt-4",
    "claude": "anthropic/claude-2",
    "llama": "meta-llama/llama-2-70b-chat",
    "mistral": "mistralai/mistral-7b-instruct"
}

# Статистика по режимам
mode_stats = {
    "normal": 0,
    "rude": 0,
    "mat": 0
}

def escape_markdown(text):
    """Экранирует специальные символы для Markdown"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

# Создаем клавиатуру под строкой ввода
def get_main_keyboard():
    """Главная клавиатура под строкой ввода"""
    keyboard = [
        [KeyboardButton("💬 Задать вопрос"), KeyboardButton("🧹 Очистить историю")],
        [KeyboardButton("⚙️ Настройки"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("ℹ️ О боте"), KeyboardButton("🎭 Режимы")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_settings_keyboard():
    """Клавиатура настроек под строкой ввода"""
    keyboard = [
        [KeyboardButton("🤖 Сменить модель"), KeyboardButton("🎭 Сменить режим")],
        [KeyboardButton("🌡️ Температура"), KeyboardButton("📏 Max tokens")],
        [KeyboardButton("🌐 Язык"), KeyboardButton("◀️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_model_keyboard():
    """Клавиатура выбора модели под строкой ввода"""
    keyboard = [
        [KeyboardButton("GPT-3.5 Turbo"), KeyboardButton("GPT-4")],
        [KeyboardButton("Claude 2"), KeyboardButton("LLaMA 2")],
        [KeyboardButton("Mistral 7B"), KeyboardButton("◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_mode_keyboard():
    """Клавиатура выбора режима под строкой ввода"""
    keyboard = [
        [KeyboardButton("😊 Обычный режим"), KeyboardButton("😈 Режим хама")],
        [KeyboardButton("🤬 РЕЖИМ С МАТОМ (18+)"), KeyboardButton("◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_language_keyboard():
    """Клавиатура выбора языка под строкой ввода"""
    keyboard = [
        [KeyboardButton("Русский"), KeyboardButton("English")],
        [KeyboardButton("◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def safe_send_message(update: Update, text: str, reply_markup=None, parse_mode: str = None):
    """Безопасная отправка сообщения с обработкой ошибок форматирования"""
    try:
        if reply_markup:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await update.message.reply_text(text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения с форматированием: {e}")
        # Отправляем без форматирования в случае ошибки
        clean_text = re.sub(r'[*_`\[\]()]', '', text)
        if reply_markup:
            await update.message.reply_text(clean_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(clean_text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Инициализируем статистику пользователя
    if user_id not in user_stats:
        user_stats[user_id] = {
            "messages": 0,
            "first_seen": datetime.now(),
            "last_active": datetime.now()
        }
    
    # Инициализируем режим пользователя
    if user_id not in user_modes:
        user_modes[user_id] = DEFAULT_MODE
    
    # Инициализируем историю с правильным системным промптом
    if user_id not in user_conversations:
        user_conversations[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPTS[user_modes[user_id]]}
        ]
    
    # Показываем клавиатуру
    await user_keyboard_state.update({user_id: "main"})
    
    start_text = (
        f"👋 Привет, {user_name}! Я бот на основе ChatGPT.\n"
        f"Используй кнопки под строкой ввода для управления 👇\n\n"
        f"Текущий режим: {get_mode_name(user_modes[user_id])}"
    )
    
    await safe_send_message(update, start_text, reply_markup=get_main_keyboard())

def get_mode_name(mode):
    """Получить название режима"""
    names = {
        "normal": "😊 Обычный",
        "rude": "😈 Хам",
        "mat": "🤬 С МАТОМ"
    }
    return names.get(mode, mode)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки под строкой ввода"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Получаем текущее состояние кнопок
    current_state = user_keyboard_state.get(user_id, "main")
    
    # Главное меню
    if current_state == "main":
        if text == "💬 Задать вопрос":
            await safe_send_message(update, "Отправь мне свой вопрос, и я отвечу! ✍️", reply_markup=ReplyKeyboardRemove())
            user_keyboard_state[user_id] = "chat"
            return
        
        elif text == "🧹 Очистить историю":
            current_mode = user_modes.get(user_id, DEFAULT_MODE)
            user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode]}]
            mode_emoji = "🤬" if current_mode == "mat" else "😈" if current_mode == "rude" else "🧹"
            await safe_send_message(update, f"{mode_emoji} История диалога очищена!", reply_markup=get_main_keyboard())
            return
        
        elif text == "⚙️ Настройки":
            await show_settings(update, context)
            user_keyboard_state[user_id] = "settings"
            return
        
        elif text == "📊 Статистика":
            await show_stats(update, context)
            return
        
        elif text == "ℹ️ О боте":
            await show_about(update, context)
            return
        
        elif text == "🎭 Режимы":
            await show_modes(update, context)
            user_keyboard_state[user_id] = "modes"
            return
    
    # Меню настроек
    elif current_state == "settings":
        if text == "🤖 Сменить модель":
            await safe_send_message(update, "Выбери модель:", reply_markup=get_model_keyboard())
            user_keyboard_state[user_id] = "model"
            return
        
        elif text == "🎭 Сменить режим":
            await safe_send_message(update, "Выбери режим общения:", reply_markup=get_mode_keyboard())
            user_keyboard_state[user_id] = "mode_select"
            return
        
        elif text == "🌡️ Температура":
            current_temp = user_settings.get(user_id, {}).get('temperature', 0.7)
            await safe_send_message(update, 
                f"🌡️ Текущая температура: {current_temp}\n"
                "Введи новое значение от 0 до 2\n"
                "(чем выше, тем креативнее ответы)",
                reply_markup=ReplyKeyboardRemove())
            user_keyboard_state[user_id] = "temp_set"
            return
        
        elif text == "📏 Max tokens":
            current_tokens = user_settings.get(user_id, {}).get('max_tokens', 1000)
            await safe_send_message(update,
                f"📏 Текущий max tokens: {current_tokens}\n"
                "Введи новое значение от 100 до 4000",
                reply_markup=ReplyKeyboardRemove())
            user_keyboard_state[user_id] = "tokens_set"
            return
        
        elif text == "🌐 Язык":
            await safe_send_message(update, "Выбери язык:", reply_markup=get_language_keyboard())
            user_keyboard_state[user_id] = "lang"
            return
        
        elif text == "◀️ Назад в меню":
            await safe_send_message(update, "Главное меню:", reply_markup=get_main_keyboard())
            user_keyboard_state[user_id] = "main"
            return
    
    # Меню выбора модели
    elif current_state == "model":
        model_map = {
            "GPT-3.5 Turbo": "gpt3",
            "GPT-4": "gpt4",
            "Claude 2": "claude",
            "LLaMA 2": "llama",
            "Mistral 7B": "mistral"
        }
        
        if text in model_map:
            model_key = model_map[text]
            if user_id not in user_settings:
                user_settings[user_id] = {}
            user_settings[user_id]["model"] = AVAILABLE_MODELS[model_key]
            
            # Очищаем историю при смене модели
            current_mode = user_modes.get(user_id, DEFAULT_MODE)
            user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode]}]
            
            await safe_send_message(update, f"✅ Модель изменена на {text}\nИстория диалога очищена.", 
                                   reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
        
        elif text == "◀️ Назад":
            await safe_send_message(update, "Настройки:", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
    
    # Меню выбора режима
    elif current_state == "mode_select":
        if text == "😊 Обычный режим":
            await mode_normal(update, context)
            await safe_send_message(update, "Настройки:", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
        
        elif text == "😈 Режим хама":
            await mode_rude(update, context)
            await safe_send_message(update, "Настройки:", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
        
        elif text == "🤬 РЕЖИМ С МАТОМ (18+)":
            await mode_mat(update, context)
            await safe_send_message(update, "Настройки:", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
        
        elif text == "◀️ Назад":
            await safe_send_message(update, "Настройки:", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
    
    # Меню выбора языка
    elif current_state == "lang":
        lang_map = {
            "Русский": "ru",
            "English": "en"
        }
        
        if text in lang_map:
            if user_id not in user_settings:
                user_settings[user_id] = {}
            user_settings[user_id]["language"] = lang_map[text]
            await safe_send_message(update, f"✅ Язык изменен на {text}", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
        
        elif text == "◀️ Назад":
            await safe_send_message(update, "Настройки:", reply_markup=get_settings_keyboard())
            user_keyboard_state[user_id] = "settings"
            return
    
    # Меню режимов (информация)
    elif current_state == "modes":
        if text == "◀️ Назад":
            await safe_send_message(update, "Главное меню:", reply_markup=get_main_keyboard())
            user_keyboard_state[user_id] = "main"
            return
    
    # Обработка ввода температуры
    elif current_state == "temp_set":
        try:
            temp = float(text)
            if 0 <= temp <= 2:
                if user_id not in user_settings:
                    user_settings[user_id] = {}
                user_settings[user_id]["temperature"] = temp
                await safe_send_message(update, f"✅ Температура изменена на {temp}", 
                                       reply_markup=get_settings_keyboard())
                user_keyboard_state[user_id] = "settings"
            else:
                await safe_send_message(update, "❌ Температура должна быть от 0 до 2. Попробуй еще раз:")
        except ValueError:
            await safe_send_message(update, "❌ Пожалуйста, введите число. Попробуй еще раз:")
        return
    
    # Обработка ввода max tokens
    elif current_state == "tokens_set":
        try:
            tokens = int(text)
            if 100 <= tokens <= 4000:
                if user_id not in user_settings:
                    user_settings[user_id] = {}
                user_settings[user_id]["max_tokens"] = tokens
                await safe_send_message(update, f"✅ Max tokens изменен на {tokens}", 
                                       reply_markup=get_settings_keyboard())
                user_keyboard_state[user_id] = "settings"
            else:
                await safe_send_message(update, "❌ Max tokens должен быть от 100 до 4000. Попробуй еще раз:")
        except ValueError:
            await safe_send_message(update, "❌ Пожалуйста, введите число. Попробуй еще раз:")
        return

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать настройки"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings:
        user_settings[user_id] = {
            "temperature": 0.7,
            "max_tokens": 1000,
            "language": "ru",
            "model": MODEL
        }
    
    settings = user_settings[user_id]
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    
    settings_text = f"""
⚙️ **ТЕКУЩИЕ НАСТРОЙКИ:**

🎭 **Режим:** {get_mode_name(current_mode)}
🤖 **Модель:** {settings['model']}
🌡️ **Температура:** {settings['temperature']}
📏 **Max tokens:** {settings['max_tokens']}
🌐 **Язык:** {'Русский' if settings['language'] == 'ru' else 'English'}

Используй кнопки ниже для изменения 👇
    """
    
    await safe_send_message(update, settings_text, reply_markup=get_settings_keyboard(), parse_mode='Markdown')

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    user_id = update.effective_user.id
    
    if user_id in user_stats:
        stats = user_stats[user_id]
        time_now = datetime.now()
        first_seen = stats['first_seen'].strftime("%Y-%m-%d")
        days_active = (time_now - stats['first_seen']).days
        
        user_mode = user_modes.get(user_id, DEFAULT_MODE)
        
        stats_text = f"""
📊 **ВАША СТАТИСТИКА:**

📝 **Сообщений:** {stats['messages']}
📅 **Первый визит:** {first_seen}
📆 **Дней активно:** {days_active}
⏰ **Последняя активность:** {stats['last_active'].strftime("%H:%M:%S")}

🎭 **Текущий режим:** {get_mode_name(user_mode)}

📊 **ГЛОБАЛЬНАЯ СТАТИСТИКА:**
😊 Обычный: {mode_stats['normal']} сообщ.
😈 Хам: {mode_stats['rude']} сообщ.
🤬 С матом: {mode_stats['mat']} сообщ.
        """
        
        await safe_send_message(update, stats_text, reply_markup=get_main_keyboard(), parse_mode='Markdown')
    else:
        await safe_send_message(update, "Статистика пока отсутствует", reply_markup=get_main_keyboard())

async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о боте"""
    about_text = f"""
🤖 **О БОТЕ**

**Название:** ChatGPT Telegram Bot
**Версия:** 3.0.0
**Модель по умолчанию:** {MODEL}
**Платформа:** OpenRouter.ai

**ВОЗМОЖНОСТИ:**
• 3 режима общения (обычный, хам, мат)
• Поддержка разных AI моделей
• История диалога
• Настройки пользователя
• Статистика использования
• Удобные кнопки под строкой ввода

**Разработчик:** @Dzmitry_10
**Дата создания:** 2024
    """
    await safe_send_message(update, about_text, reply_markup=get_main_keyboard(), parse_mode='Markdown')

async def show_modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о режимах"""
    user_id = update.effective_user.id
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    
    mode_text = f"""
🎭 **ИНФОРМАЦИЯ О РЕЖИМАХ**

Текущий режим: **{get_mode_name(current_mode)}**

**ДОСТУПНЫЕ РЕЖИМЫ:**

😊 **Обычный режим**
Вежливый и дружелюбный ассистент

😈 **Режим хама**
Грубый и саркастичный, БЕЗ мата

🤬 **РЕЖИМ С МАТОМ (18+)**
⚠️ Содержит нецензурную лексику!
Максимально грубый, с матом

**СТАТИСТИКА:**
😊 Обычный: {mode_stats['normal']} сообщ.
😈 Хам: {mode_stats['rude']} сообщ.
🤬 С матом: {mode_stats['mat']} сообщ.

Для смены режима зайди в **Настройки** → **Сменить режим**
    """
    
    await safe_send_message(update, mode_text, reply_markup=get_main_keyboard(), parse_mode='Markdown')

async def mode_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение в обычный режим"""
    user_id = update.effective_user.id
    user_modes[user_id] = "normal"
    
    if user_id in user_conversations and user_conversations[user_id]:
        user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["normal"]}
    else:
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS["normal"]}]
    
    await safe_send_message(update, "✅ Переключено в обычный режим")

async def mode_rude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение в режим хама"""
    user_id = update.effective_user.id
    user_modes[user_id] = "rude"
    
    if user_id in user_conversations and user_conversations[user_id]:
        user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["rude"]}
    else:
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS["rude"]}]
    
    await safe_send_message(update, "✅ Переключено в режим хама")

async def mode_mat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение в режим с матом"""
    user_id = update.effective_user.id
    user_modes[user_id] = "mat"
    
    if user_id in user_conversations and user_conversations[user_id]:
        user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["mat"]}
    else:
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS["mat"]}]
    
    await safe_send_message(update, "⚠️ **ВНИМАНИЕ! РЕЖИМ С МАТОМ АКТИВИРОВАН!**", parse_mode='Markdown')

async def model_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о текущей модели"""
    user_id = update.effective_user.id
    
    current_model = user_settings.get(user_id, {}).get('model', MODEL)
    temperature = user_settings.get(user_id, {}).get('temperature', 0.7)
    max_tokens = user_settings.get(user_id, {}).get('max_tokens', 1000)
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    
    model_info_text = f"""
🤖 **Информация о модели**

**Текущая модель:** {current_model}
**Текущий режим:** {get_mode_name(current_mode)}

**Параметры:**
• Температура: {temperature}
• Max tokens: {max_tokens}

**Доступные модели:**
• /model_gpt3 - OpenAI GPT-3.5 Turbo
• /model_gpt4 - OpenAI GPT-4
• /model_claude - Anthropic Claude 2
• /model_llama - Meta LLaMA 2
• /model_mistral - Mistral 7B
    """
    
    await safe_send_message(update, model_info_text, parse_mode='Markdown')

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка истории диалога"""
    user_id = update.effective_user.id
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    
    user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode]}]
    
    mode_emoji = "🤬" if current_mode == "mat" else "😈" if current_mode == "rude" else "🧹"
    await safe_send_message(update, f"{mode_emoji} История диалога очищена!", reply_markup=get_main_keyboard())

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settings - открыть настройки"""
    await show_settings(update, context)
    user_keyboard_state[update.effective_user.id] = "settings"

async def model_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команд для смены модели"""
    user_id = update.effective_user.id
    text = update.message.text
    
    model_commands = {
        "/model_gpt3": "gpt3",
        "/model_gpt4": "gpt4", 
        "/model_claude": "claude",
        "/model_llama": "llama",
        "/model_mistral": "mistral"
    }
    
    if text in model_commands:
        model_key = model_commands[text]
        if user_id not in user_settings:
            user_settings[user_id] = {}
        user_settings[user_id]["model"] = AVAILABLE_MODELS[model_key]
        
        current_mode = user_modes.get(user_id, DEFAULT_MODE)
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode]}]
        
        await safe_send_message(update, f"✅ Модель изменена на {AVAILABLE_MODELS[model_key]}\nИстория диалога очищена.")

async def temperature_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для установки температуры"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings:
        user_settings[user_id] = {}
    
    if context.args:
        try:
            temp = float(context.args[0])
            if 0 <= temp <= 2:
                user_settings[user_id]["temperature"] = temp
                await safe_send_message(update, f"✅ Температура изменена на {temp}")
            else:
                await safe_send_message(update, "❌ Температура должна быть от 0 до 2")
        except ValueError:
            await safe_send_message(update, "❌ Пожалуйста, введите число")
    else:
        current_temp = user_settings[user_id].get('temperature', 0.7)
        await safe_send_message(update, f"🌡️ Текущая температура: {current_temp}\nИспользование: /temperature [0-2]")

async def max_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для установки max tokens"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings:
        user_settings[user_id] = {}
    
    if context.args:
        try:
            tokens = int(context.args[0])
            if 100 <= tokens <= 4000:
                user_settings[user_id]["max_tokens"] = tokens
                await safe_send_message(update, f"✅ Max tokens изменен на {tokens}")
            else:
                await safe_send_message(update, "❌ Max tokens должен быть от 100 до 4000")
        except ValueError:
            await safe_send_message(update, "❌ Пожалуйста, введите число")
    else:
        current_tokens = user_settings[user_id].get('max_tokens', 1000)
        await safe_send_message(update, f"📏 Текущий max tokens: {current_tokens}\nИспользование: /max_tokens [100-4000]")

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для смены языка"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings:
        user_settings[user_id] = {}
    
    if context.args:
        lang = context.args[0].lower()
        if lang in ["ru", "en"]:
            user_settings[user_id]["language"] = lang
            await safe_send_message(update, f"✅ Язык изменен на {lang}")
        else:
            await safe_send_message(update, "❌ Доступные языки: ru, en")
    else:
        current_lang = user_settings[user_id].get('language', 'ru')
        await safe_send_message(update, f"🌐 Текущий язык: {current_lang}\nИспользование: /language [ru/en]")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats - показать статистику"""
    await show_stats(update, context)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about - информация о боте"""
    await show_about(update, context)

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mode - информация о режимах"""
    await show_modes(update, context)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка соединения"""
    start_time = time.time()
    message = await update.message.reply_text("🏓 Пинг...")
    end_time = time.time()
    
    response_time = round((end_time - start_time) * 1000, 2)
    await message.edit_text(f"🏓 Понг! Время ответа: {response_time}ms")

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текущее время"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await safe_send_message(update, f"🕐 Текущее время: {current_time}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Эхо-команда"""
    if context.args:
        text = ' '.join(context.args)
        await safe_send_message(update, f"📢 Эхо: {text}")
    else:
        await safe_send_message(update, "❌ Использование: /echo [текст]")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Случайное число"""
    number = random.randint(1, 100)
    await safe_send_message(update, f"🎲 Случайное число: {number}")

async def quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Случайная цитата"""
    quotes = [
        "Жизнь - это то, что с тобой происходит, пока ты строишь планы. — Джон Леннон",
        "Будьте тем изменением, которое хотите увидеть в мире. — Махатма Ганди",
        "Сложнее всего начать действовать, все остальное зависит только от упорства. — Амелия Эрхарт",
        "Успех - это способность идти от неудачи к неудаче, не теряя энтузиазма. — Уинстон Черчилль",
        "Не бойтесь совершенства, вам его не достичь. — Сальвадор Дали"
    ]
    await safe_send_message(update, f"💭 {random.choice(quotes)}")

async def ask_openrouter(messages, user_id=None):
    """Асинхронный запрос к OpenRouter API"""
    
    temperature = 0.7
    max_tokens = 1000
    model = MODEL
    
    if user_id and user_id in user_settings:
        temperature = user_settings[user_id].get('temperature', 0.7)
        max_tokens = user_settings[user_id].get('max_tokens', 1000)
        model = user_settings[user_id].get('model', MODEL)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/your_bot",
        "X-Title": "Telegram ChatGPT Bot"
    }
    
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(
                url=OPENROUTER_URL,
                headers=headers,
                data=json.dumps(data),
                timeout=30
            )
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'], None
        else:
            error_text = response.text
            logger.error(f"Ошибка API: {response.status_code} - {error_text}")
            
            if response.status_code == 401:
                return None, "❌ Ошибка авторизации API. Проверьте API ключ."
            elif response.status_code == 429:
                return None, "❌ Слишком много запросов. Попробуйте позже."
            elif response.status_code == 503:
                return None, "❌ Сервис временно недоступен. Попробуйте позже."
            else:
                return None, f"❌ Ошибка API: {response.status_code}"
            
    except requests.exceptions.Timeout:
        logger.error("Таймаут запроса к OpenRouter")
        return None, "❌ Превышено время ожидания ответа от API. Попробуйте позже."
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к OpenRouter")
        return None, "❌ Ошибка подключения к API. Проверьте интернет-соединение."
    except Exception as e:
        logger.error(f"Исключение при запросе: {e}")
        return None, f"❌ Произошла ошибка: {str(e)}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Проверяем, не является ли сообщение командой
    if user_message.startswith('/'):
        return
    
    # Обновляем статистику
    if user_id not in user_stats:
        user_stats[user_id] = {
            "messages": 0,
            "first_seen": datetime.now(),
            "last_active": datetime.now()
        }
    
    user_stats[user_id]["messages"] += 1
    user_stats[user_id]["last_active"] = datetime.now()
    
    # Получаем текущий режим пользователя
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    
    # Обновляем статистику режимов
    mode_stats[current_mode] = mode_stats.get(current_mode, 0) + 1
    
    # Проверяем, не пустое ли сообщение
    if not user_message.strip():
        if current_mode == "mat":
            await safe_send_message(update, "Слышь, ёбаный гений, ты че пустые сообщения шлешь? Совсем охренел? Напиши нормально, мудак!")
        elif current_mode == "rude":
            await safe_send_message(update, "Слушай, гений, ты вообще сообщение собираешься писать? Пустые сообщения - это новый вид искусства?")
        else:
            await safe_send_message(update, "Пожалуйста, отправьте непустое сообщение.")
        return
    
    # Показываем, что бот печатает
    await update.message.chat.send_action(action="typing")
    
    try:
        # Получаем или создаем историю диалога для пользователя
        if user_id not in user_conversations:
            user_conversations[user_id] = [
                {"role": "system", "content": SYSTEM_PROMPTS[current_mode]}
            ]
        
        # Добавляем сообщение пользователя в историю
        user_conversations[user_id].append({"role": "user", "content": user_message})
        
        # Ограничиваем историю последними 10 сообщениями
        if len(user_conversations[user_id]) > 11:
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]
        
        # Отправляем запрос к OpenRouter
        bot_response, error = await ask_openrouter(user_conversations[user_id], user_id)
        
        if error:
            await safe_send_message(update, error, reply_markup=get_main_keyboard())
            user_conversations[user_id].pop()
            return
        
        # Добавляем ответ бота в историю
        user_conversations[user_id].append({"role": "assistant", "content": bot_response})
        
        # Отправляем ответ пользователю
        if len(bot_response) > 4096:
            for x in range(0, len(bot_response), 4096):
                await safe_send_message(update, bot_response[x:x+4096], reply_markup=get_main_keyboard())
        else:
            await safe_send_message(update, bot_response, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        if current_mode == "mat":
            error_message = "🤬 Пиздец, ошибка какая-то! Даже мой отборный мат не помог! Попробуй позже, мудак!"
        elif current_mode == "rude":
            error_message = "❌ Ошибка! Даже мой сарказм не помог справиться с этой проблемой. Попробуй позже."
        else:
            error_message = "❌ Произошла неизвестная ошибка. Попробуйте позже."
        await safe_send_message(update, error_message, reply_markup=get_main_keyboard())
        
        if user_id in user_conversations:
            del user_conversations[user_id]

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")
    
    if "Can't parse entities" in str(context.error):
        return
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка бота. Администраторы уже уведомлены."
            )
        except:
            pass

def main():
    """Главная функция запуска бота"""
    
    print("🚀 Запуск бота...")
    print(f"📱 Токен Telegram: {TELEGRAM_TOKEN[:10]}...")
    print(f"🔑 API ключ OpenRouter: {OPENROUTER_API_KEY[:10]}...")
    print(f"🤖 Модель по умолчанию: {MODEL}")
    print(f"🎭 Режимы: Normal + Rude + MAT (18+)")
    print(f"🔘 Кнопки под строкой ввода: ВКЛ")
    
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Обработчик для кнопок под строкой ввода
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
        
        # Команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("settings", settings_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("mode", mode_command))
        application.add_handler(CommandHandler("clear", clear))
        application.add_handler(CommandHandler("model", model_info))
        
        # Команды для смены модели
        application.add_handler(CommandHandler("model_gpt3", model_commands))
        application.add_handler(CommandHandler("model_gpt4", model_commands))
        application.add_handler(CommandHandler("model_claude", model_commands))
        application.add_handler(CommandHandler("model_llama", model_commands))
        application.add_handler(CommandHandler("model_mistral", model_commands))
        
        # Команды для настроек
        application.add_handler(CommandHandler("temperature", temperature_command))
        application.add_handler(CommandHandler("max_tokens", max_tokens_command))
        application.add_handler(CommandHandler("language", language_command))
        
        # Команды для режимов
        application.add_handler(CommandHandler("mode_normal", mode_normal))
        application.add_handler(CommandHandler("mode_rude", mode_rude))
        application.add_handler(CommandHandler("mode_mat", mode_mat))
        
        # Дополнительные команды
        application.add_handler(CommandHandler("ping", ping))
        application.add_handler(CommandHandler("time", time_command))
        application.add_handler(CommandHandler("echo", echo))
        application.add_handler(CommandHandler("roll", roll))
        application.add_handler(CommandHandler("quote", quote))
        
        # Обработчик сообщений (для вопросов к боту)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        print("✅ Бот успешно запущен! Нажми Ctrl+C для остановки.")
        print(f"📊 Всего команд: 20+")
        print(f"🔘 Кнопки под строкой ввода активны")
        print(f"😈 Режим хама: /mode_rude")
        print(f"🤬 РЕЖИМ С МАТОМ: /mode_mat (18+)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()
