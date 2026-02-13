import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Твой токен (уже вставлен)
BOT_TOKEN = '8569245180:AAFAkYJ56d6BPzMXIjHOjOkKX56KL5rFi_4'

# Создаем объекты бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.full_name}!\n"
        f"Я простой эхо-бот. Отправь мне любое сообщение, и я повторю его."
    )

# Обработчик команды /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Я умею:\n"
        "/start - Поздороваться\n"
        "/help - Показать эту справку\n"
        "(и просто повторять любой твой текст)"
    )

# Обработчик для любого текстового сообщения (эхо)
@dp.message()
async def echo_message(message: types.Message):
    if message.text:
        await message.answer(f"Ты написал: {message.text}")

# Функция запуска бота
async def main():
    print("Бот запущен! Напиши ему в Telegram: @твой_бот")
    print("(Чтобы остановить, нажми Ctrl+C)")
    await dp.start_polling(bot)

# Запускаем бота
if __name__ == "__main__":
    asyncio.run(main())
