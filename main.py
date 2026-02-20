import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncio
import time
import socks
import socket
from groq import Groq

# Токены
TELEGRAM_TOKEN = "8515320919:AAHvp2FNdO_bOgH_02K95CBCSaE6t2ufp70"
GROQ_API_KEY = "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"

# ============================================
# НАСТРОЙКА ПРОКСИ
# ============================================
USE_PROXY = False  # Прокси отключен
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
            InlineKeyboardButton("🔄 Новый диалог", callback_data="new_dialog")
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
            "in_dialog": False,
            "dialog_menu_shown": False
        }
    
    welcome_text = (
        f"👋 **Привет, {update.effective_user.first_name}!**\n\n"
        f"📌 **Сейчас:** {MODES[user_data[user_id]['mode']]['name']} | {get_model_name(user_data[user_id]['model'])}\n\n"
        f"💡 **Как пользоваться:**\n"
        f"• Пиши сообщения - начнется диалог\n"
        f"• После ответа появится кнопка ЗАВЕРШИТЬ ДИАЛОГ\n"
        f"• Нажми её - вернёшься в меню (история сохранится)\n"
        f"• Кнопка 🔄 Новый диалог - очистит историю"
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
    
    if user_message == "❌ ЗАВЕРШИТЬ ДИАЛОГ":
        await end_dialog(update, context)
        return
    
    await delete_menu(user_id, context)
    
    # Просто убираем клавиатуру с кнопкой завершения без лишних сообщений
    try:
        await update.message.reply_text(
            "⠋",  # Минимальный символ, чтобы убрать клавиатуру
            reply_markup=ReplyKeyboardRemove()
        )
        # Сразу удаляем это служебное сообщение
        await context.bot.delete_message(
            chat_id=user_id,
            message_id=update.message.message_id + 1
        )
    except:
        pass
    
    current_time = time.time()
    if user_id in user_last_message and current_time - user_last_message[user_id] < 1:
        return
    user_last_message[user_id] = current_time
    
    if user_id not in user_data:
        user_data[user_id] = {
            "model": DEFAULT_MODEL,
            "mode": DEFAULT_MODE,
            "history": [{"role": "system", "content": MODES[DEFAULT_MODE]["system_prompt"]}],
            "in_dialog": True,
            "dialog_menu_shown": False
        }
    else:
        user_data[user_id]["in_dialog"] = True
    
    # Показываем "печатает..."
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
        
        # Отправляем ответ и ПОКАЗЫВАЕМ кнопку завершения диалога
        await update.message.reply_text(
            assistant_message,
            reply_markup=get_end_dialog_keyboard()
        )
        
        # Устанавливаем флаг, что меню диалога показано
        user_data[user_id]["dialog_menu_shown"] = True
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(
            "❌ Ошибка. Попробуйте позже.",
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
    """Завершение диалога (история СОХРАНЯЕТСЯ)"""
    user_id = update.effective_user.id
    
    if user_id in user_data:
        # НЕ очищаем историю! Только меняем флаг диалога
        user_data[user_id]["in_dialog"] = False
        user_data[user_id]["dialog_menu_shown"] = False
    
    # Убираем клавиатуру с кнопкой завершения
    try:
        await update.message.reply_text(
            "⠋",
            reply_markup=ReplyKeyboardRemove()
        )
        # Удаляем служебное сообщение
        await context.bot.delete_message(
            chat_id=user_id,
            message_id=update.message.message_id + 1
        )
        await update.message.delete()
    except:
        pass
    
    # Считаем сообщения в истории
    user_msgs = len([msg for msg in user_data[user_id]["history"] if msg["role"] == "user"])
    
    # Возвращаем главное меню
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=(
            f"✅ **Диалог завершен!**\n\n"
            f"📝 История сохранена ({user_msgs} сообщений)\n"
            f"➡️ Зайди в меню «История», чтобы посмотреть\n\n"
            f"Текущие настройки:\n"
            f"• Режим: {MODES[user_data[user_id]['mode']]['name']}\n"
            f"• Модель: {get_model_name(user_data[user_id]['model'])}"
        ),
        reply_markup=get_main_keyboard(user_id),
        parse_mode='Markdown'
    )
    menu_messages[user_id] = msg.message_id

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
            "dialog_menu_shown": False
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
        # При смене режима - новый системный промпт, но история остается?
        # Лучше спросить пользователя
        keyboard = [
            [InlineKeyboardButton("✅ Оставить историю", callback_data=f"mode_{mode_id}_keep")],
            [InlineKeyboardButton("🗑 Очистить историю", callback_data=f"mode_{mode_id}_clear")],
            [InlineKeyboardButton("◀️ Отмена", callback_data="back_to_main")]
        ]
        await query.edit_message_text(
            f"🔄 **Смена режима на {MODES[mode_id]['name']}**\n\n"
            f"Что сделать с текущей историей диалога?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("mode_") and ("_keep" in query.data or "_clear" in query.data):
        parts = query.data.split("_")
        mode_id = parts[1]
        action = parts[2]
        
        user_data[user_id]["mode"] = mode_id
        
        if action == "clear":
            # Очищаем историю и ставим новый системный промпт
            user_data[user_id]["history"] = [{"role": "system", "content": MODES[mode_id]["system_prompt"]}]
            history_msg = "История очищена"
        else:
            # Меняем только системный промпт, историю сохраняем
            if user_data[user_id]["history"] and user_data[user_id]["history"][0]["role"] == "system":
                user_data[user_id]["history"][0] = {"role": "system", "content": MODES[mode_id]["system_prompt"]}
            else:
                user_data[user_id]["history"].insert(0, {"role": "system", "content": MODES[mode_id]["system_prompt"]})
            history_msg = "История сохранена"
        
        await query.edit_message_text(
            f"✅ Режим изменен на {MODES[mode_id]['name']}\n{history_msg}",
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
        assistant_msgs = [msg for msg in history if msg["role"] == "assistant"]
        
        if user_msgs:
            # Показываем последние 10 сообщений
            text = f"📋 **История диалога**\n\n"
            text += f"👤 Сообщений от вас: {len(user_msgs)}\n"
            text += f"🤖 Ответов бота: {len(assistant_msgs)}\n"
            text += f"💬 Всего в памяти: {len(history)-1}\n\n"
            text += "**Последние сообщения:**\n"
            
            # Показываем последние 10 сообщений (кроме системного)
            for msg in history[-10:]:
                if msg["role"] == "user":
                    text += f"👤 {msg['content'][:50]}{'...' if len(msg['content']) > 50 else ''}\n"
                elif msg["role"] == "assistant":
                    text += f"🤖 {msg['content'][:50]}{'...' if len(msg['content']) > 50 else ''}\n"
            
            # Добавляем кнопку очистки истории
            keyboard = [
                [InlineKeyboardButton("🗑 Очистить историю", callback_data="clear_history")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
            ]
        else:
            text = "📋 История пуста.\n\nНапиши что-нибудь боту, чтобы начать диалог!"
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
        
        await query.edit_message_text(
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode='Markdown'
        )
    
    elif query.data == "clear_history":
        # Очищаем историю, оставляя только системный промпт
        current_mode = user_data[user_id]["mode"]
        user_data[user_id]["history"] = [{"role": "system", "content": MODES[current_mode]["system_prompt"]}]
        
        await query.edit_message_text(
            "✅ **История очищена!**",
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = query.message.message_id
    
    elif query.data == "settings":
        mode_name = MODES[user_data[user_id]["mode"]]["name"]
        model_name = get_model_name(user_data[user_id]["model"])
        user_msgs = len([msg for msg in user_data[user_id]["history"] if msg["role"] == "user"])
        assistant_msgs = len([msg for msg in user_data[user_id]["history"] if msg["role"] == "assistant"])
        
        text = (
            f"ℹ️ **Информация**\n\n"
            f"👤 Пользователь: {query.from_user.first_name}\n"
            f"🎭 Режим: {mode_name}\n"
            f"🚀 Модель: {model_name}\n"
            f"💬 Статистика:\n"
            f"  • Ваших сообщений: {user_msgs}\n"
            f"  • Ответов бота: {assistant_msgs}\n\n"
            f"📌 **Режимы:**\n"
            f"• 💬 Обычный - вежливые ответы\n"
            f"• 😈 Хам - грубые и саркастичные\n"
            f"• 🤬 Мат - с нецензурной лексикой"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == "new_dialog":
        # Полный сброс диалога (новая история)
        current_mode = user_data[user_id]["mode"]
        user_data[user_id]["history"] = [{"role": "system", "content": MODES[current_mode]["system_prompt"]}]
        user_data[user_id]["in_dialog"] = False
        user_data[user_id]["dialog_menu_shown"] = False
        
        await query.edit_message_text(
            f"🔄 **Новый диалог начат!**\n\n"
            f"Старая история удалена.\n"
            f"Можешь писать сообщения.",
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = query.message.message_id
    
    elif query.data == "back_to_main":
        user_msgs = len([msg for msg in user_data[user_id]["history"] if msg["role"] == "user"])
        status = "⚡" if user_data[user_id]["in_dialog"] else "💤"
        
        await query.edit_message_text(
            f"{status} **Главное меню**\n\n"
            f"{MODES[user_data[user_id]['mode']]['name']} | {get_model_name(user_data[user_id]['model'])}\n"
            f"Сообщений в истории: {user_msgs}",
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        menu_messages[user_id] = query.message.message_id

def main():
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        pass

if __name__ == '__main__':
    main()
