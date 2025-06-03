"""
Главный файл запуска Clore Bot Pro
"""
import asyncio
import sys
from loguru import logger

from telegram_bot.bot import CloreBot
from database.session import init_db
from services.monitoring.balance_monitor import BalanceMonitor
from services.monitoring.server_monitor import ServerMonitor
from config import settings


# Настройка логирования
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    settings.log_path / "clore_bot.log",
    rotation="1 day",
    retention="7 days",
    level="DEBUG"
)


async def main():
    """Главная функция запуска"""
    logger.info("Starting Clore Bot Pro...")
    
    try:
        # Инициализация базы данных
        logger.info("Initializing database...")
        await init_db()
        
        # Создание экземпляров сервисов
        bot = CloreBot()
        balance_monitor = BalanceMonitor()
        server_monitor = ServerMonitor()
        
        # Запуск фоновых задач
        logger.info("Starting background services...")
        monitor_tasks = [
            asyncio.create_task(balance_monitor.start()),
            asyncio.create_task(server_monitor.start())
        ]
        
        # Запуск бота
        logger.info("Starting Telegram bot...")
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # Остановка всех сервисов
        logger.info("Stopping services...")
        
        # Отмена фоновых задач
        for task in monitor_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Остановка бота
        await bot.stop()
        
        logger.info("Clore Bot Pro stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")