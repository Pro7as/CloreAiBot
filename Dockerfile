FROM python:3.10-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директорий для данных
RUN mkdir -p /app/data /app/logs

# Пользователь для безопасности
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# Запуск бота
CMD ["python", "main.py"]