"""
Тестовый запуск бота без фоновых сервисов
"""
import asyncio
import sys
from loguru import logger

from telegram_bot.bot import CloreBot
from database.session import init_db
from config import settings

# Настройка логирования
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

async def main():
    """Главная функция запуска"""
    logger.info("Starting Clore Bot Pro (TEST MODE - без мониторинга)...")
    
    try:
        # Инициализация базы данных
        logger.info("Initializing database...")
        await init_db()
        
        # Создание бота
        bot = CloreBot()
        
        # Запуск только бота без мониторинга
        logger.info("Starting Telegram bot...")
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Clore Bot Pro stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
