#!/usr/bin/env python3
"""
Скрипт первоначальной настройки Clore Bot Pro
"""
import os
import sys
import asyncio
from pathlib import Path
from getpass import getpass
import secrets


async def main():
    """Основная функция настройки"""
    print("🚀 Добро пожаловать в мастер настройки Clore Bot Pro!")
    print("=" * 50)
    
    # Проверка Python версии
    if sys.version_info < (3, 10):
        print("❌ Требуется Python 3.10 или выше!")
        sys.exit(1)
    
    # Создание .env файла
    env_path = Path(".env")
    if env_path.exists():
        overwrite = input("\n⚠️  Файл .env уже существует. Перезаписать? (y/N): ")
        if overwrite.lower() != 'y':
            print("Настройка отменена.")
            return
    
    print("\n📝 Настройка переменных окружения...")
    
    # Сбор данных
    config = {}
    
    # Telegram Bot
    print("\n1. Telegram Bot")
    config['BOT_TOKEN'] = input("   Bot Token (@BotFather): ").strip()
    config['BOT_USERNAME'] = input("   Bot Username (без @): ").strip()
    
    # OpenAI
    print("\n2. OpenAI")
    config['OPENAI_API_KEY'] = getpass("   API Key: ").strip()
    config['OPENAI_MODEL'] = input("   Model (по умолчанию gpt-4-turbo-preview): ").strip() or "gpt-4-turbo-preview"
    
    # База данных
    print("\n3. База данных")
    db_type = input("   Тип БД (sqlite/postgresql) [sqlite]: ").strip().lower() or "sqlite"
    
    if db_type == "postgresql":
        db_host = input("   Host [localhost]: ").strip() or "localhost"
        db_port = input("   Port [5432]: ").strip() or "5432"
        db_name = input("   Database name [clorebot]: ").strip() or "clorebot"
        db_user = input("   Username [clore]: ").strip() or "clore"
        db_pass = getpass("   Password: ").strip()
        config['DATABASE_URL'] = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    else:
        config['DATABASE_URL'] = "sqlite+aiosqlite:///./clore_bot.db"
    
    # Админы
    print("\n4. Администраторы")
    admin_ids = input("   Telegram ID админов (через запятую): ").strip()
    config['ADMIN_IDS'] = admin_ids
    
    # Курсы валют
    print("\n5. Курсы валют")
    config['CLORE_TO_USD'] = input("   Курс CLORE/USD [0.02]: ").strip() or "0.02"
    config['BTC_TO_USD'] = input("   Курс BTC/USD [100000]: ").strip() or "100000"
    
    # Дополнительные настройки
    config['CLORE_API_BASE_URL'] = "https://api.clore.ai/v1"
    config['BALANCE_CHECK_INTERVAL'] = "600"
    config['SERVER_CHECK_INTERVAL'] = "300"
    config['SERVERS_PER_PAGE'] = "10"
    config['ENABLE_PREMIUM_CHECK'] = "false"
    
    # Запись в файл
    print("\n💾 Сохранение конфигурации...")
    
    with open(".env", "w") as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    print("✅ Файл .env создан!")
    
    # Создание директорий
    print("\n📁 Создание директорий...")
    dirs = ["logs", "data", "backups"]
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"   ✓ {dir_name}/")
    
    # Инициализация БД
    init_db = input("\n🗄️  Инициализировать базу данных? (Y/n): ")
    if init_db.lower() != 'n':
        print("   Инициализация БД...")
        
        # Временно добавляем переменные окружения
        for key, value in config.items():
            os.environ[key] = value
        
        try:
            from database.session import init_db
            await init_db()
            print("   ✅ База данных инициализирована!")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    # Создание Docker шаблонов
    create_templates = input("\n🐳 Создать базовые Docker шаблоны? (Y/n): ")
    if create_templates.lower() != 'n':
        await create_default_templates()
    
    print("\n" + "=" * 50)
    print("🎉 Настройка завершена!")
    print("\nДля запуска бота используйте:")
    print("  python main.py")
    print("\nИли с Docker:")
    print("  docker-compose up -d")
    print("\nУдачи! 🚀")


async def create_default_templates():
    """Создать базовые Docker шаблоны"""
    print("   Создание Docker шаблонов...")
    
    try:
        from database.session import get_db
        from database.crud import create_docker_template
        
        templates = [
            {
                "name": "Ubuntu + Jupyter",
                "image": "cloreai/jupyter:ubuntu24.04-v2",
                "description": "Ubuntu 24.04 с Jupyter Notebook",
                "category": "computing",
                "ports": {"22": "tcp", "8888": "http"},
                "command": "#!/bin/sh\napt update -y"
            },
            {
                "name": "PyTorch Latest",
                "image": "pytorch/pytorch:latest",
                "description": "Официальный образ PyTorch",
                "category": "ai",
                "ports": {"22": "tcp"},
                "min_gpu_ram": 8
            },
            {
                "name": "TensorFlow GPU",
                "image": "tensorflow/tensorflow:latest-gpu",
                "description": "TensorFlow с поддержкой GPU",
                "category": "ai",
                "ports": {"22": "tcp", "8888": "http"},
                "min_gpu_ram": 8
            }
        ]
        
        async with get_db() as db:
            for template_data in templates:
                await create_docker_template(db, **template_data)
        
        print(f"   ✅ Создано {len(templates)} шаблонов")
        
    except Exception as e:
        print(f"   ⚠️  Не удалось создать шаблоны: {e}")


if __name__ == "__main__":
    asyncio.run(main())
