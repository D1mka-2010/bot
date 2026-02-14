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
    user_conversations[user_id] = [{"role": 
