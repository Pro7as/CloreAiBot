"""
Сервис отправки уведомлений
"""
import asyncio
from typing import Optional
from datetime import datetime
from loguru import logger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.session import get_db
from database.crud import get_unsent_alerts, mark_alert_sent


class AlertService:
    """Сервис для отправки уведомлений пользователям"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.check_interval = 30  # Проверка каждые 30 секунд
    
    async def start(self):
        """Запустить сервис уведомлений"""
        self.running = True
        logger.info("Alert service started")
        
        while self.running:
            try:
                await self._process_alerts()
            except Exception as e:
                logger.error(f"Error in alert service: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Остановить сервис"""
        self.running = False
        logger.info("Alert service stopped")
    
    async def _process_alerts(self):
        """Обработать неотправленные уведомления"""
        async with get_db() as db:
            # Получаем всех пользователей с неотправленными алертами
            result = await db.execute(
                """
                SELECT DISTINCT user_id FROM alerts 
                WHERE is_sent = false
                """
            )
            user_ids = [row[0] for row in result.fetchall()]
            
            for user_id in user_ids:
                user_alerts = await get_unsent_alerts(db, user_id)
                
                for alert in user_alerts:
                    await self._send_alert(alert)
    
    async def _send_alert(self, alert):
        """Отправить конкретное уведомление"""
        try:
            # Получаем пользователя для telegram_id
            async with get_db() as db:
                result = await db.execute(
                    f"SELECT telegram_id, alert_sound_enabled FROM users WHERE id = {alert.user_id}"
                )
                user_data = result.fetchone()
                
                if not user_data:
                    logger.error(f"User {alert.user_id} not found for alert {alert.id}")
                    return
                
                telegram_id, sound_enabled = user_data
                
                # Формируем сообщение
                message = f"**{alert.title}**\n\n{alert.message}"
                
                # Добавляем клавиатуру в зависимости от типа
                keyboard = self._get_alert_keyboard(alert.alert_type)
                
                # Отправляем
                await self.bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                    disable_notification=not sound_enabled
                )
                
                # Отмечаем как отправленное
                await mark_alert_sent(db, alert.id)
                
        except Exception as e:
            logger.error(f"Failed to send alert {alert.id}: {e}")
            async with get_db() as db:
                await mark_alert_sent(db, alert.id, error=str(e))
    
    def _get_alert_keyboard(self, alert_type: str) -> Optional[InlineKeyboardMarkup]:
        """Получить клавиатуру для типа уведомления"""
        keyboard = []
        
        if alert_type in ['balance_low', 'balance_drop']:
            keyboard.append([
                InlineKeyboardButton(text="💰 Проверить баланс", callback_data="action:balance")
            ])
        
        elif alert_type in ['order_expiring', 'order_expired']:
            keyboard.append([
                InlineKeyboardButton(text="📦 Мои аренды", callback_data="action:orders")
            ])
        
        elif alert_type == 'server_rented':
            keyboard.append([
                InlineKeyboardButton(text="🖥️ Мои серверы", callback_data="action:my_servers")
            ])
        
        elif alert_type == 'hunt_found':
            keyboard.append([
                InlineKeyboardButton(text="🎯 Результаты охоты", callback_data="action:hunt_results")
            ])
        
        if keyboard:
            return InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        return None


async def send_custom_alert(
    bot: Bot,
    telegram_id: int,
    title: str,
    message: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    sound: bool = True
):
    """Отправить кастомное уведомление напрямую"""
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"**{title}**\n\n{message}",
            parse_mode="Markdown",
            reply_markup=keyboard,
            disable_notification=not sound
        )
    except Exception as e:
        logger.error(f"Failed to send custom alert to {telegram_id}: {e}")