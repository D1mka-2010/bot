import os
import logging
import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация - ваши данные
TELEGRAM_TOKEN = "8569245180:AAFAkYJ56d6BPzMXIjHOjOkKX56KL5rFi_4"
OPENROUTER_API_KEY = "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"

# URL для OpenRouter API
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Настройки модели
MODEL = "openai/gpt-3.5-turbo"  # Используем доступную модель

# Системный промпт для настройки поведения бота
SYSTEM_PROMPT = "Ты полезный ассистент, который отвечает на вопросы пользователей на русском языке."

# Словарь для хранения истории разговоров
user_conversations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот на основе ChatGPT (через OpenRouter).\n"
        "Задай мне любой вопрос, и я постараюсь помочь!\n\n"
        "Команды:\n"
        "/start - Показать это сообщение\n"
        "/clear - Очистить историю диалога\n"
        "/model - Информация о текущей модели\n"
        "/help - Получить помощь"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "🤖 Как пользоваться ботом:\n\n"
        "Просто отправь мне сообщение с вопросом, и я отвечу!\n\n"
        "💡 Советы:\n"
        "• Чем точнее вопрос, тем лучше ответ\n"
        "• Используй /clear для сброса диалога\n"
        "• Бот помнит контекст разговора\n\n"
        f"Текущая модель: {MODEL}"
    )

async def model_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о текущей модели"""
    await update.message.reply_text(
        f"🤖 Текущая модель: {MODEL}\n\n"
        "Популярные модели на OpenRouter:\n"
        "• openai/gpt-3.5-turbo\n"
        "• openai/gpt-4\n"
        "• anthropic/claude-2\n"
        "• meta-llama/llama-2-70b-chat"
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка истории диалога"""
    user_id = update.effective_user.id
    if user_id in user_conversations:
        del user_conversations[user_id]
    await update.message.reply_text("🧹 История диалога очищена!")

def ask_openrouter_sync(messages):
    """Синхронный запрос к OpenRouter API"""
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Опционально можно добавить информацию о сайте
    # "HTTP-Referer": "http://localhost:8000",
    # "X-Title": "Telegram Bot",
    
    data = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.7,
    }
    
    try:
        response = requests.post(
            url=OPENROUTER_URL,
            headers=headers,
            data=json.dumps(data),
            timeout=30  # Таймаут 30 секунд
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'], None
        else:
            error_text = response.text
            logger.error(f"Ошибка API: {response.status_code} - {error_text}")
            return None, f"Ошибка API: {response.status_code}"
            
    except requests.exceptions.Timeout:
        logger.error("Таймаут запроса к OpenRouter")
        return None, "Превышено время ожидания ответа от API"
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к OpenRouter")
        return None, "Ошибка подключения к API"
    except Exception as e:
        logger.error(f"Исключение при запросе: {e}")
        return None, str(e)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Показываем, что бот печатает
    await update.message.chat.send_action(action="typing")
    
    try:
        # Получаем или создаем историю диалога для пользователя
        if user_id not in user_conversations:
            user_conversations[user_id] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
        
        # Добавляем сообщение пользователя в историю
        user_conversations[user_id].append({"role": "user", "content": user_message})
        
        # Ограничиваем историю последними 10 сообщениями
        if len(user_conversations[user_id]) > 11:  # system + 10 сообщений
            user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]
        
        # Отправляем запрос к OpenRouter (в отдельном потоке, чтобы не блокировать бота)
        bot_response, error = await context.application.loop.run_in_executor(
            None,  # Используем стандартный executor
            ask_openrouter_sync,
            user_conversations[user_id]
        )
        
        if error:
            await update.message.reply_text(f"❌ Произошла ошибка: {error}")
            return
        
        # Добавляем ответ бота в историю
        user_conversations[user_id].append({"role": "assistant", "content": bot_response})
        
        # Отправляем ответ пользователю (разбиваем если слишком длинный)
        if len(bot_response) > 4096:
            for x in range(0, len(bot_response), 4096):
                await update.message.reply_text(bot_response[x:x+4096])
        else:
            await update.message.reply_text(bot_response)
        
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        await update.message.reply_text("❌ Произошла неизвестная ошибка. Попробуй позже.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

def main():
    """Главная функция запуска бота"""
    
    print("🚀 Запуск бота...")
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("model", model_info))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    print("✅ Бот успешно запущен! Нажми Ctrl+C для остановки.")
    application.run_polling()

if __name__ == "__main__":
    main()
