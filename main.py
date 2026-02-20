import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncio
import time
import socks
import socket
from groq import Groq
import random

# Токены
TELEGRAM_TOKEN = "8569245180:AAFAkYJ56d6BPzMXIjHOjOkKX56KL5rFi_4"
GROQ_API_KEY = "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"

# ============================================
# НАСТРОЙКА ПРОКСИ - СПИСОК ПРОКСИ
# ============================================
USE_PROXY = True  # Включить прокси

# Список прокси для автоматической смены при ошибках
PROXY_LIST = [
    {"host": "195.74.72.111", "port": 5678, "type": socks.SOCKS4},
    {"host": "213.219.215.233", "port": 1080, "type": socks.SOCKS5},
    {"host": "45.67.89.10", "port": 1080, "type": socks.SOCKS5},  # Добавь свои рабочие прокси
]

current_proxy_index = 0
# ============================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_proxy(proxy_index=None):
    """Настройка прокси с возможностью выбора"""
    global current_proxy_index
    
    if not USE_PROXY:
        return True
    
    if proxy_index is not None:
        current_proxy_index = proxy_index
    
    try:
        proxy = PROXY_LIST[current_proxy_index]
        socks.set_default_proxy(proxy["type"], proxy["host"], proxy["port"])
        socket.socket = socks.socksocket
        
        # Тестируем соединение
        test_socket = socks.socksocket()
        test_socket.set_proxy(proxy["type"], proxy["host"], proxy["port"])
        test_socket.settimeout(5)
        test_socket.connect(('api.telegram.org', 443))
        test_socket.close()
        
        logger.info(f"✅ Прокси {proxy['host']}:{proxy['port']} работает")
        return True
    except Exception as e:
        logger.error(f"❌ Прокси {proxy['host']}:{proxy['port']} не работает: {e}")
        return False

def rotate_proxy():
    """Смена прокси при ошибке"""
    global current_proxy_index
    current_proxy_index = (current_proxy_index + 1) % len(PROXY_LIST)
    logger.info(f"🔄 Переключаюсь на прокси {PROXY_LIST[current_proxy_index]['host']}")
    return setup_proxy(current_proxy_index)

# Пробуем настроить первый прокси
if USE_PROXY:
    if not setup_proxy(0):
        logger.warning("⚠️ Первый прокси не работает, пробую следующие...")
        for i in range(1, len(PROXY_LIST)):
            if setup_proxy(i):
                break
        else:
            logger.error("❌ Ни один прокси не работает. Отключаю прокси.")
            USE_PROXY = False

# Создаем клиент Groq
groq_client = Groq(api_key=GROQ_API_KEY)

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
user_chat_ids = set()  # Для отслеживания активных чатов

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
    """Клавиатура с кнопкой завершения"""
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    user_id = update.effective_user.id
    user_chat_ids.add(user_id)  # Добавляем в активные чаты
    
    try:
        await update.message.delete()
    except:
        pass
    
    await delete_menu(user_id, context)
    
    if user_id not in user_data:
        user_data[user_id] = {
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
            "in_dialog": False
        }
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"📌 **Сейчас:** {MODES[user_data[user_id]['mode']]['name']} | {get_model_name(user_data[user_id]['model'])}\n\n"
        f"💡 **Как пользоваться:**\n"
        f"• Пиши сообщения\n"
        f"• После ответа появится кнопка ЗАВЕРШИТЬ ДИАЛОГ\n"
        f"• Нажми её - вернёшься в меню"
    )
    
    try:
        msg = await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = msg.message_id
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        # Пробуем переподключиться
        if USE_PROXY:
            rotate_proxy()

def get_model_name(model_id):
    for name, mid in MODELS.items():
        if mid == model_id:
            return name
    return model_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    
    try:
        user_message = update.message.text
        
        if user_message == "❌ ЗАВЕРШИТЬ ДИАЛОГ":
            await end_dialog(update, context)
            return
        
        await delete_menu(user_id, context)
        
        current_time = time.time()
        if user_id in user_last_message and current_time - user_last_message[user_id] < 1:
            return
        user_last_message[user_id] = current_time
        
        if user_id not in user_data:
            user_data[user_id] = {
                "model": DEFAULT_MODEL,
                "mode": DEFAULT_MODE,
                "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
                "in_dialog": True
            }
        else:
            user_data[user_id]["in_dialog"] = True
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            history = user_data[user_id]["history"]
            history.append({"role": "user", "content": user_message})
            
            if len(history) > 11:
                history[:] = [history[0]] + history[-10:]
            
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
            
            await update.message.reply_text(
                assistant_message,
                reply_markup=get_end_dialog_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text(
                "❌ Ошибка. Попробуйте позже.",
                reply_markup=ReplyKeyboardRemove()
            )
            
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        # Пробуем переподключиться
        if USE_PROXY:
            rotate_proxy()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    # Если ошибка связана с прокси
    if USE_PROXY and "proxy" in str(context.error).lower():
        logger.info("🔄 Проблема с прокси, переключаюсь...")
        rotate_proxy()
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Произошла ошибка. Бот переподключается..."
        )
    except:
        pass

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
    """Завершение диалога"""
    user_id = update.effective_user.id
    
    if user_id in user_data:
        current_mode = user_data[user_id]["mode"]
        user_data[user_id]["history"] = [{"role": "system", "content": MODES[current_mode]["system_prompt"]}]
        user_data[user_id]["in_dialog"] = False
    
    try:
        await update.message.delete()
    except:
        pass
    
    try:
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
    except Exception as e:
        logger.error(f"Ошибка при завершении: {e}")

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
                "in_dialog": False
            }
        
        # Обработка кнопок (как в предыдущей версии)
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
                f"✅ Режим: {MODES[mode_id]['name']}",
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
            
            text = (
                f"ℹ️ **Информация**\n\n"
                f"👤 Пользователь: {query.from_user.first_name}\n"
                f"🎭 Режим: {mode_name}\n"
                f"🚀 Модель: {model_name}\n"
                f"💬 Сообщений: {history_len}\n\n"
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

def main():
    print("🎭 Бот запускается с защитой от вылетов...")
    print("="*50)
    
    if USE_PROXY:
        print(f"🌐 Используется {len(PROXY_LIST)} прокси для ротации")
        for i, proxy in enumerate(PROXY_LIST):
            status = "✅" if i == current_proxy_index else "⏳"
            print(f"  {status} {proxy['host']}:{proxy['port']}")
    else:
        print("🌐 Режим: без прокси")
    
    print("✅ Убрано сообщение 'Обрабатываю запрос'")
    print("✅ Кнопка завершения появляется только после ответа")
    print("✅ Добавлена автоматическая ротация прокси")
    print("="*50)
    
    # Создаем приложение с обработчиком ошибок
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("\n✅ Бот готов к работе!")
    
    # Запускаем с автоматическим переподключением
    while True:
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES, 
                drop_pending_updates=True,
                close_loop=False  # Не закрываем loop при ошибках
            )
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
            
            # Меняем прокси при перезапуске
            if USE_PROXY:
                rotate_proxy()
            
            # Пересоздаем приложение
            application = Application.builder().token(TELEGRAM_TOKEN).build()
            application.add_error_handler(error_handler)
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CallbackQueryHandler(button_handler))
            application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == '__main__':
    main()
