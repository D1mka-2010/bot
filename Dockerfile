FROM python:3.14

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём директорию для данных
RUN mkdir -p /app/data

# Открываем порт
EXPOSE 8080

# Запускаем бота
CMD ["python", "main.py"]
