"""
Middleware для аутентификации и авторизации
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from loguru import logger

from config import settings
from database.session import get_db
from database.crud import get_user_by_telegram_id


class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации пользователя"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        user_id = event.from_user.id
        
        # Пропускаем команду /start
        if hasattr(event, 'text') and event.text and event.text.startswith('/start'):
            return await handler(event, data)
        
        # Проверяем, есть ли пользователь в БД
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user:
                await event.answer(
                    "❌ Вы не зарегистрированы в системе.\n"
                    "Используйте /start для регистрации."
                )
                return
            
            # Проверяем активность
            if not user.is_active:
                await event.answer(
                    "❌ Ваш аккаунт деактивирован.\n"
                    "Обратитесь к администратору."
                )
                return
            
            # Проверяем подписку для коммерческой версии
            if settings.enable_premium_check:
                if not user.is_premium:
                    await event.answer(
                        "❌ Требуется активная подписка.\n"
                        "Обратитесь к администратору для активации."
                    )
                    return
            
            # Добавляем пользователя в контекст
            data['user'] = user
        
        return await handler(event, data)