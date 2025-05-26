# Используем лёгкий официальный образ Python
FROM python:3.12-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# 1) Копируем только requirements.txt и кешируем pip install
COPY requirements.txt .

# 2) Устанавливаем зависимости один раз
RUN pip install --no-cache-dir -r requirements.txt

# 3) Копируем остальной код
COPY . .

# 4) Экспонируем порт (тот же, что указали в Railway)
EXPOSE 8000

# 5) Команда старта
CMD ["python3", "telegram_ogonek_bot.py"]
