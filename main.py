import os
import logging
import requests
import json
import asyncio
import time
import random
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.markdown import hbold, hitalic, hcode
from aiogram.exceptions import TelegramBadRequest

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация - ваши данные
TELEGRAM_TOKEN = "8569245180:AAFAkYJ56d6BPzMXIjHOjOkKX56KL5rFi_4"
OPENROUTER_API_KEY = "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"
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

# Определяем состояния FSM
class BotStates(StatesGroup):
    main_menu = State()
    settings = State()
    model_select = State()
    mode_select = State()
    lang_select = State()
    temp_set = State()
    tokens_set = State()
    chat = State()
    modes_info = State()

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Создаем клавиатуры
def get_main_keyboard():
    """Главная клавиатура под строкой ввода"""
    keyboard = [
        [KeyboardButton(text="💬 Задать вопрос"), KeyboardButton(text="🧹 Очистить историю")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="ℹ️ О боте"), KeyboardButton(text="🎭 Режимы")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_settings_keyboard():
    """Клавиатура настроек под строкой ввода"""
    keyboard = [
        [KeyboardButton(text="🤖 Сменить модель"), KeyboardButton(text="🎭 Сменить режим")],
        [KeyboardButton(text="🌡️ Температура"), KeyboardButton(text="📏 Max tokens")],
        [KeyboardButton(text="🌐 Язык"), KeyboardButton(text="◀️ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_model_keyboard():
    """Клавиатура выбора модели под строкой ввода"""
    keyboard = [
        [KeyboardButton(text="GPT-3.5 Turbo"), KeyboardButton(text="GPT-4")],
        [KeyboardButton(text="Claude 2"), KeyboardButton(text="LLaMA 2")],
        [KeyboardButton(text="Mistral 7B"), KeyboardButton(text="◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_mode_keyboard():
    """Клавиатура выбора режима под строкой ввода"""
    keyboard = [
        [KeyboardButton(text="😊 Обычный режим"), KeyboardButton(text="😈 Режим хама")],
        [KeyboardButton(text="🤬 РЕЖИМ С МАТОМ (18+)"), KeyboardButton(text="◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_language_keyboard():
    """Клавиатура выбора языка под строкой ввода"""
    keyboard = [
        [KeyboardButton(text="Русский"), KeyboardButton(text="English")],
        [KeyboardButton(text="◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_mode_name(mode):
    """Получить название режима"""
    names = {
        "normal": "😊 Обычный",
        "rude": "😈 Хам",
        "mat": "🤬 С МАТОМ"
    }
    return names.get(mode, mode)

async def safe_send_message(message: Message, text: str, reply_markup=None, parse_mode: str = None):
    """Безопасная отправка сообщения с обработкой ошибок форматирования"""
    try:
        if reply_markup:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await message.answer(text, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        logger.error(f"Ошибка отправки сообщения с форматированием: {e}")
        # Отправляем без форматирования в случае ошибки
        clean_text = re.sub(r'[*_`\[\]()]', '', text)
        if reply_markup:
            await message.answer(clean_text, reply_markup=reply_markup)
        else:
            await message.answer(clean_text)

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
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
    
    # Инициализируем историю
    if user_id not in user_conversations:
        user_conversations[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPTS[user_modes[user_id]]}
        ]
    
    # Устанавливаем состояние в меню
    await state.set_state(BotStates.main_menu)
    
    start_text = (
        f"👋 Привет, {user_name}! Я бот на основе ChatGPT.\n"
        f"Используй кнопки под строкой ввода для управления 👇\n\n"
        f"👤 Разработчик: @Dzmitry_10\n"
        f"📅 Год создания: 2026\n"
        f"🎭 Текущий режим: {get_mode_name(user_modes[user_id])}"
    )
    
    await safe_send_message(message, start_text, reply_markup=get_main_keyboard())

@dp.message(Command("clear"))
async def clear_command(message: Message, state: FSMContext):
    """Команда /clear"""
    user_id = message.from_user.id
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode]}]
    await safe_send_message(message, "🧹 История очищена!", reply_markup=get_main_keyboard())
    await state.set_state(BotStates.main_menu)

@dp.message(Command("settings"))
async def settings_command(message: Message, state: FSMContext):
    """Команда /settings"""
    await show_settings(message)
    await state.set_state(BotStates.settings)

@dp.message(Command("stats"))
async def stats_command(message: Message, state: FSMContext):
    """Команда /stats"""
    await show_stats(message)
    await state.set_state(BotStates.main_menu)

@dp.message(Command("about"))
async def about_command(message: Message, state: FSMContext):
    """Команда /about"""
    await show_about(message)
    await state.set_state(BotStates.main_menu)

@dp.message(Command("mode"))
async def mode_command(message: Message, state: FSMContext):
    """Команда /mode"""
    await show_modes(message)
    await state.set_state(BotStates.modes_info)

@dp.message(Command("mode_normal"))
async def mode_normal(message: Message, state: FSMContext):
    """Команда /mode_normal"""
    user_id = message.from_user.id
    user_modes[user_id] = "normal"
    if user_id in user_conversations:
        user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["normal"]}
    await safe_send_message(message, "✅ Обычный режим", reply_markup=get_main_keyboard())
    await state.set_state(BotStates.main_menu)

@dp.message(Command("mode_rude"))
async def mode_rude(message: Message, state: FSMContext):
    """Команда /mode_rude"""
    user_id = message.from_user.id
    user_modes[user_id] = "rude"
    if user_id in user_conversations:
        user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["rude"]}
    await safe_send_message(message, "✅ Режим хама", reply_markup=get_main_keyboard())
    await state.set_state(BotStates.main_menu)

@dp.message(Command("mode_mat"))
async def mode_mat(message: Message, state: FSMContext):
    """Команда /mode_mat"""
    user_id = message.from_user.id
    user_modes[user_id] = "mat"
    if user_id in user_conversations:
        user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["mat"]}
    await safe_send_message(message, "⚠️ РЕЖИМ С МАТОМ!", reply_markup=get_main_keyboard())
    await state.set_state(BotStates.main_menu)

async def show_settings(message: Message):
    """Показать настройки"""
    user_id = message.from_user.id
    
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
⚙️ ТЕКУЩИЕ НАСТРОЙКИ:

🎭 Режим: {get_mode_name(current_mode)}
🤖 Модель: {settings['model']}
🌡️ Температура: {settings['temperature']}
📏 Max tokens: {settings['max_tokens']}
🌐 Язык: {'Русский' if settings['language'] == 'ru' else 'English'}

Используй кнопки ниже для изменения 👇
    """
    
    await safe_send_message(message, settings_text, reply_markup=get_settings_keyboard())

async def show_stats(message: Message):
    """Показать статистику"""
    user_id = message.from_user.id
    
    if user_id in user_stats:
        stats = user_stats[user_id]
        time_now = datetime.now()
        first_seen = stats['first_seen'].strftime("%Y-%m-%d")
        days_active = (time_now - stats['first_seen']).days
        
        user_mode = user_modes.get(user_id, DEFAULT_MODE)
        
        stats_text = f"""
📊 ВАША СТАТИСТИКА:

📝 Сообщений: {stats['messages']}
📅 Первый визит: {first_seen}
📆 Дней активно: {days_active}
⏰ Последняя активность: {stats['last_active'].strftime("%H:%M:%S")}

🎭 Текущий режим: {get_mode_name(user_mode)}

📊 ГЛОБАЛЬНАЯ СТАТИСТИКА:
😊 Обычный: {mode_stats['normal']} сообщ.
😈 Хам: {mode_stats['rude']} сообщ.
🤬 С матом: {mode_stats['mat']} сообщ.
        """
        
        await safe_send_message(message, stats_text, reply_markup=get_main_keyboard())
    else:
        await safe_send_message(message, "Статистика пока отсутствует", reply_markup=get_main_keyboard())

async def show_about(message: Message):
    """Показать информацию о боте"""
    about_text = f"""
🤖 О БОТЕ

Название: ChatGPT Telegram Bot
Версия: 3.0.0 (aiogram)
Модель по умолчанию: {MODEL}
Платформа: OpenRouter.ai

ВОЗМОЖНОСТИ:
• 3 режима общения (обычный, хам, мат)
• Поддержка разных AI моделей
• История диалога
• Настройки пользователя
• Статистика использования
• Удобные кнопки под строкой ввода

👤 Разработчик: @Dzmitry_10
📅 Год создания: 2026
    """
    await safe_send_message(message, about_text, reply_markup=get_main_keyboard())

async def show_modes(message: Message):
    """Показать информацию о режимах"""
    user_id = message.from_user.id
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    
    mode_text = f"""
🎭 ИНФОРМАЦИЯ О РЕЖИМАХ

Текущий режим: {get_mode_name(current_mode)}

ДОСТУПНЫЕ РЕЖИМЫ:

😊 Обычный режим
Вежливый и дружелюбный ассистент

😈 Режим хама
Грубый и саркастичный, БЕЗ мата

🤬 РЕЖИМ С МАТОМ (18+)
⚠️ Содержит нецензурную лексику!
Максимально грубый, с матом

СТАТИСТИКА:
😊 Обычный: {mode_stats['normal']} сообщ.
😈 Хам: {mode_stats['rude']} сообщ.
🤬 С матом: {mode_stats['mat']} сообщ.

Для смены режима зайди в Настройки → Сменить режим
    """
    
    await safe_send_message(message, mode_text, reply_markup=get_main_keyboard())

@dp.message(BotStates.main_menu)
async def main_menu_handler(message: Message, state: FSMContext):
    """Обработчик главного меню"""
    user_id = message.from_user.id
    text = message.text
    
    if text == "💬 Задать вопрос":
        await state.set_state(BotStates.chat)
        await safe_send_message(message, "Отправь мне свой вопрос, и я отвечу! ✍️", reply_markup=ReplyKeyboardRemove())
    
    elif text == "🧹 Очистить историю":
        current_mode = user_modes.get(user_id, DEFAULT_MODE)
        user_conversations[user_id] = [{"role": "system", "content": SYSTEM_PROMPTS[current_mode]}]
        mode_emoji = "🤬" if current_mode == "mat" else "😈" if current_mode == "rude" else "🧹"
        await safe_send_message(message, f"{mode_emoji} История диалога очищена!", reply_markup=get_main_keyboard())
    
    elif text == "⚙️ Настройки":
        await show_settings(message)
        await state.set_state(BotStates.settings)
    
    elif text == "📊 Статистика":
        await show_stats(message)
    
    elif text == "ℹ️ О боте":
        await show_about(message)
    
    elif text == "🎭 Режимы":
        await show_modes(message)
        await state.set_state(BotStates.modes_info)

@dp.message(BotStates.settings)
async def settings_menu_handler(message: Message, state: FSMContext):
    """Обработчик меню настроек"""
    user_id = message.from_user.id
    text = message.text
    
    if text == "🤖 Сменить модель":
        await safe_send_message(message, "Выбери модель:", reply_markup=get_model_keyboard())
        await state.set_state(BotStates.model_select)
    
    elif text == "🎭 Сменить режим":
        await safe_send_message(message, "Выбери режим общения:", reply_markup=get_mode_keyboard())
        await state.set_state(BotStates.mode_select)
    
    elif text == "🌡️ Температура":
        current_temp = user_settings.get(user_id, {}).get('temperature', 0.7)
        await safe_send_message(message, 
            f"🌡️ Текущая температура: {current_temp}\n"
            f"Введи новое значение от 0 до 2\n"
            f"(чем выше, тем креативнее ответы)",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(BotStates.temp_set)
    
    elif text == "📏 Max tokens":
        current_tokens = user_settings.get(user_id, {}).get('max_tokens', 1000)
        await safe_send_message(message,
            f"📏 Текущий max tokens: {current_tokens}\n"
            f"Введи новое значение от 100 до 4000",
            reply_markup=ReplyKeyboardRemove())
        await state.set_state(BotStates.tokens_set)
    
    elif text == "🌐 Язык":
        await safe_send_message(message, "Выбери язык:", reply_markup=get_language_keyboard())
        await state.set_state(BotStates.lang_select)
    
    elif text == "◀️ Назад в меню":
        await state.set_state(BotStates.main_menu)
        await safe_send_message(message, "Главное меню:", reply_markup=get_main_keyboard())

@dp.message(BotStates.model_select)
async def model_select_handler(message: Message, state: FSMContext):
    """Обработчик выбора модели"""
    user_id = message.from_user.id
    text = message.text
    
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
        
        await safe_send_message(message, f"✅ Модель изменена на {text}\nИстория диалога очищена.", 
                               reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)
    
    elif text == "◀️ Назад":
        await safe_send_message(message, "Настройки:", reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)

@dp.message(BotStates.mode_select)
async def mode_select_handler(message: Message, state: FSMContext):
    """Обработчик выбора режима"""
    user_id = message.from_user.id
    text = message.text
    
    if text == "😊 Обычный режим":
        user_modes[user_id] = "normal"
        if user_id in user_conversations:
            user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["normal"]}
        await safe_send_message(message, "✅ Переключено в обычный режим", reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)
    
    elif text == "😈 Режим хама":
        user_modes[user_id] = "rude"
        if user_id in user_conversations:
            user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["rude"]}
        await safe_send_message(message, "✅ Переключено в режим хама", reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)
    
    elif text == "🤬 РЕЖИМ С МАТОМ (18+)":
        user_modes[user_id] = "mat"
        if user_id in user_conversations:
            user_conversations[user_id][0] = {"role": "system", "content": SYSTEM_PROMPTS["mat"]}
        await safe_send_message(message, "⚠️ ВНИМАНИЕ! РЕЖИМ С МАТОМ АКТИВИРОВАН!", 
                               reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)
    
    elif text == "◀️ Назад":
        await safe_send_message(message, "Настройки:", reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)

@dp.message(BotStates.lang_select)
async def lang_select_handler(message: Message, state: FSMContext):
    """Обработчик выбора языка"""
    user_id = message.from_user.id
    text = message.text
    
    lang_map = {
        "Русский": "ru",
        "English": "en"
    }
    
    if text in lang_map:
        if user_id not in user_settings:
            user_settings[user_id] = {}
        user_settings[user_id]["language"] = lang_map[text]
        await safe_send_message(message, f"✅ Язык изменен на {text}", reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)
    
    elif text == "◀️ Назад":
        await safe_send_message(message, "Настройки:", reply_markup=get_settings_keyboard())
        await state.set_state(BotStates.settings)

@dp.message(BotStates.temp_set)
async def temp_set_handler(message: Message, state: FSMContext):
    """Обработчик ввода температуры"""
    user_id = message.from_user.id
    text = message.text
    
    try:
        temp = float(text)
        if 0 <= temp <= 2:
            if user_id not in user_settings:
                user_settings[user_id] = {}
            user_settings[user_id]["temperature"] = temp
            await safe_send_message(message, f"✅ Температура изменена на {temp}", 
                                   reply_markup=get_settings_keyboard())
            await state.set_state(BotStates.settings)
        else:
            await safe_send_message(message, "❌ Температура должна быть от 0 до 2. Попробуй еще раз:")
    except ValueError:
        await safe_send_message(message, "❌ Пожалуйста, введите число. Попробуй еще раз:")

@dp.message(BotStates.tokens_set)
async def tokens_set_handler(message: Message, state: FSMContext):
    """Обработчик ввода max tokens"""
    user_id = message.from_user.id
    text = message.text
    
    try:
        tokens = int(text)
        if 100 <= tokens <= 4000:
            if user_id not in user_settings:
                user_settings[user_id] = {}
            user_settings[user_id]["max_tokens"] = tokens
            await safe_send_message(message, f"✅ Max tokens изменен на {tokens}", 
                                   reply_markup=get_settings_keyboard())
            await state.set_state(BotStates.settings)
        else:
            await safe_send_message(message, "❌ Max tokens должен быть от 100 до 4000. Попробуй еще раз:")
    except ValueError:
        await safe_send_message(message, "❌ Пожалуйста, введите число. Попробуй еще раз:")

@dp.message(BotStates.modes_info)
async def modes_info_handler(message: Message, state: FSMContext):
    """Обработчик информации о режимах"""
    text = message.text
    
    if text == "◀️ Назад":
        await state.set_state(BotStates.main_menu)
        await safe_send_message(message, "Главное меню:", reply_markup=get_main_keyboard())

@dp.message(BotStates.chat)
async def chat_handler(message: Message, state: FSMContext, bot: Bot):
    """Обработчик чата (вопросы к боту)"""
    user_id = message.from_user.id
    question = message.text
    
    await process_question(message, state, user_id, question)

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
        "HTTP-Referer": "https://t.me/Dzmitry_10",
        "X-Title": "Telegram ChatGPT Bot by Dzmitry_10"
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
            logger.error(f"Ошибка API: {response.status_code}")
            return None, f"Ошибка API: {response.status_code}"
            
    except Exception as e:
        logger.error(f"Исключение: {e}")
        return None, f"Ошибка: {str(e)}"

async def process_question(message: Message, state: FSMContext, user_id: int, question: str):
    """Обработка вопроса к боту"""
    
    # Обновляем статистику
    if user_id not in user_stats:
        user_stats[user_id] = {
            "messages": 0,
            "first_seen": datetime.now(),
            "last_active": datetime.now()
        }
    
    user_stats[user_id]["messages"] += 1
    user_stats[user_id]["last_active"] = datetime.now()
    
    # Получаем текущий режим
    current_mode = user_modes.get(user_id, DEFAULT_MODE)
    mode_stats[current_mode] = mode_stats.get(current_mode, 0) + 1
    
    # Проверяем пустое сообщение
    if not question.strip():
        if current_mode == "mat":
            await safe_send_message(message, "Слышь, ёбаный гений, ты че пустые сообщения шлешь? Совсем охренел? Напиши нормально, мудак!")
        elif current_mode == "rude":
            await safe_send_message(message, "Слушай, гений, ты вообще сообщение собираешься писать? Пустые сообщения - это новый вид искусства?")
        else:
            await safe_send_message(message, "Пожалуйста, отправьте непустое сообщение.")
        await state.set_state(BotStates.main_menu)
        return
    
    # Показываем, что бот печатает
    await bot.send_chat_action(message.chat.id, action="typing")
    
    try:
        # Получаем историю
        if user_id not in user_conversations:
            user_conversations[user_id] = [
                {"role": "system", "content": SYSTEM_PROMPTS[current_mode]}
            ]
        
        # Добавляем вопрос
        user_conversations[user_id].append({"role": "user", "content": question})
        
        # Ограничиваем историю
        if len(user_conversations[user_id]) > 11:
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]
        
        # Получаем ответ от OpenRouter
        bot_response, error = await ask_openrouter(user_conversations[user_id], user_id)
        
        if error:
            await safe_send_message(message, f"❌ {error}", reply_markup=get_main_keyboard())
            user_conversations[user_id].pop()
            await state.set_state(BotStates.main_menu)
            return
        
        # Добавляем ответ в историю
        user_conversations[user_id].append({"role": "assistant", "content": bot_response})
        
        # Отправляем ответ
        if len(bot_response) > 4096:
            for x in range(0, len(bot_response), 4096):
                await safe_send_message(message, bot_response[x:x+4096], reply_markup=get_main_keyboard())
        else:
            await safe_send_message(message, bot_response, reply_markup=get_main_keyboard())
        
        # Возвращаемся в меню
        await state.set_state(BotStates.main_menu)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if current_mode == "mat":
            error_message = "🤬 Пиздец, ошибка какая-то! Даже мой отборный мат не помог! Попробуй позже, мудак!"
        elif current_mode == "rude":
            error_message = "❌ Ошибка! Даже мой сарказм не помог. Попробуй позже."
        else:
            error_message = "❌ Произошла ошибка. Попробуйте позже."
        await safe_send_message(message, error_message, reply_markup=get_main_keyboard())
        await state.set_state(BotStates.main_menu)

@dp.message()
async def unknown_handler(message: Message, state: FSMContext):
    """Обработчик неизвестных сообщений"""
    current_state = await state.get_state()
    if current_state is None:
        await state.set_state(BotStates.main_menu)
        await safe_send_message(message, "Главное меню:", reply_markup=get_main_keyboard())

async def main():
    """Главная функция запуска бота"""
    
    print("🚀 Запуск бота на aiogram...")
    print(f"👤 Разработчик: @Dzmitry_10")
    print(f"📅 Год: 2026")
    print(f"🤖 Модель: {MODEL}")
    print(f"🔘 Кнопки под строкой ввода: ВКЛ")
    print(f"⚙️ Библиотека: aiogram 3.x")
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
