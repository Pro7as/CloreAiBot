"""
Основной модуль Telegram бота
"""
import asyncio
from typing import Optional
from loguru import logger

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.session import get_db
from database.models import User
from database.crud import get_user_by_telegram_id, create_user, update_user_api_key
from ai_agent.agent import CloreAIAgent
from telegram_bot.keyboards.inline import (
    get_main_menu_keyboard, 
    get_settings_keyboard,
    get_server_list_keyboard,
    get_confirm_keyboard
)
from telegram_bot.middlewares.auth import AuthMiddleware


class UserStates(StatesGroup):
    """Состояния пользователя"""
    entering_api_key = State()
    entering_ssh_password = State()
    entering_jupyter_token = State()
    selecting_servers = State()
    confirming_order = State()


class CloreBot:
    """Основной класс Telegram бота"""
    
    def __init__(self):
        self.bot = Bot(token=settings.bot_token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.agents = {}  # Кеш AI агентов по user_id
        
        # Регистрируем middleware
        self.dp.message.middleware(AuthMiddleware())
        
        # Регистрируем обработчики
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        # Команды
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command("help"))
        self.dp.message.register(self.cmd_settings, Command("settings"))
        self.dp.message.register(self.cmd_balance, Command("balance"))
        self.dp.message.register(self.cmd_orders, Command("orders"))
        self.dp.message.register(self.cmd_servers, Command("servers"))
        self.dp.message.register(self.cmd_menu, Command("menu"))
        
        # Callback handlers
        self.dp.callback_query.register(self.callback_main_menu, lambda c: c.data == "main_menu")
        self.dp.callback_query.register(self.callback_settings, lambda c: c.data.startswith("settings:"))
        self.dp.callback_query.register(self.callback_server_action, lambda c: c.data.startswith("server:"))
        self.dp.callback_query.register(self.callback_page_navigation, lambda c: c.data.startswith("page:"))
        
        # Состояния
        self.dp.message.register(self.process_api_key, UserStates.entering_api_key)
        self.dp.message.register(self.process_ssh_password, UserStates.entering_ssh_password)
        self.dp.message.register(self.process_jupyter_token, UserStates.entering_jupyter_token)
        
        # AI агент - обработка любых сообщений
        self.dp.message.register(self.process_ai_query)
    
    async def cmd_start(self, message: Message, state: FSMContext):
        """Обработчик команды /start"""
        user_id = message.from_user.id
        
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user:
                # Создаем нового пользователя
                user = await create_user(
                    db,
                    telegram_id=user_id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name
                )
                
                await message.answer(
                    "👋 Добро пожаловать в Clore Bot Pro!\n\n"
                    "Я помогу вам управлять арендой GPU серверов на платформе Clore.ai\n\n"
                    "Для начала работы необходимо настроить API ключ.",
                    reply_markup=get_settings_keyboard(has_api_key=False)
                )
            else:
                await message.answer(
                    f"👋 С возвращением, {user.first_name}!\n\n"
                    "Выберите действие:",
                    reply_markup=get_main_menu_keyboard()
                )
    
    async def cmd_help(self, message: Message):
        """Обработчик команды /help"""
        help_text = """
📚 **Справка по командам:**

/start - Начать работу с ботом
/menu - Главное меню
/settings - Настройки (API ключи, пароли)
/balance - Проверить баланс
/orders - Мои активные аренды
/servers - Поиск серверов

**🤖 AI Помощник:**
Просто напишите, что вам нужно:
• "Покажи серверы с RTX 4090"
• "Найди дешевые серверы с 3070"
• "Сколько я трачу на аренду?"
• "Арендовать сервер 12345"

**💡 Советы:**
• Используйте фильтры: цена, GPU, рейтинг
• AI понимает естественный язык
• Можно арендовать несколько серверов сразу
"""
        await message.answer(help_text)
    
    async def cmd_settings(self, message: Message):
        """Обработчик команды /settings"""
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, message.from_user.id)
            
        await message.answer(
            "⚙️ **Настройки:**",
            reply_markup=get_settings_keyboard(has_api_key=bool(user.clore_api_key))
        )
    
    async def cmd_balance(self, message: Message):
        """Обработчик команды /balance"""
        await self._execute_ai_command(message, "покажи баланс")
    
    async def cmd_orders(self, message: Message):
        """Обработчик команды /orders"""
        await self._execute_ai_command(message, "мои активные аренды")
    
    async def cmd_servers(self, message: Message):
        """Обработчик команды /servers"""
        await self._execute_ai_command(message, "покажи доступные серверы")
    
    async def cmd_menu(self, message: Message):
        """Показать главное меню"""
        await message.answer(
            "📋 Главное меню:",
            reply_markup=get_main_menu_keyboard()
        )
    
    async def callback_main_menu(self, callback: CallbackQuery):
        """Обработчик возврата в главное меню"""
        await callback.message.edit_text(
            "📋 Главное меню:",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()
    
    async def callback_settings(self, callback: CallbackQuery, state: FSMContext):
        """Обработчик настроек"""
        action = callback.data.split(":")[1]
        
        if action == "api_key":
            await callback.message.answer(
                "🔑 Введите ваш Clore API ключ:\n\n"
                "Получить ключ можно на https://clore.ai/profile/api"
            )
            await state.set_state(UserStates.entering_api_key)
            
        elif action == "ssh_password":
            await callback.message.answer(
                "🔐 Введите пароль SSH по умолчанию:\n"
                "(макс. 32 символа)"
            )
            await state.set_state(UserStates.entering_ssh_password)
            
        elif action == "jupyter_token":
            await callback.message.answer(
                "🎫 Введите токен Jupyter по умолчанию:\n"
                "(макс. 32 символа)"
            )
            await state.set_state(UserStates.entering_jupyter_token)
            
        elif action == "back":
            await callback.message.edit_text(
                "📋 Главное меню:",
                reply_markup=get_main_menu_keyboard()
            )
        
        await callback.answer()
    
    async def process_api_key(self, message: Message, state: FSMContext):
        """Обработка ввода API ключа"""
        api_key = message.text.strip()
        
        # Проверяем ключ
        try:
            from clore_api.client import CloreAPIClient
            async with CloreAPIClient(api_key) as client:
                await client.get_wallets()
            
            # Сохраняем ключ
            async with get_db() as db:
                await update_user_api_key(db, message.from_user.id, api_key)
            
            await message.answer(
                "✅ API ключ успешно сохранен!",
                reply_markup=get_main_menu_keyboard()
            )
            
        except Exception as e:
            await message.answer(
                f"❌ Ошибка проверки ключа: {str(e)}\n"
                "Проверьте правильность ключа и попробуйте снова."
            )
        
        await state.clear()
    
    async def process_ssh_password(self, message: Message, state: FSMContext):
        """Обработка ввода SSH пароля"""
        password = message.text.strip()[:32]
        
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, message.from_user.id)
            user.default_ssh_password = password
            await db.commit()
        
        await message.answer(
            "✅ SSH пароль сохранен!",
            reply_markup=get_main_menu_keyboard()
        )
        await state.clear()
    
    async def process_jupyter_token(self, message: Message, state: FSMContext):
        """Обработка ввода Jupyter токена"""
        token = message.text.strip()[:32]
        
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, message.from_user.id)
            user.default_jupyter_token = token
            await db.commit()
        
        await message.answer(
            "✅ Jupyter токен сохранен!",
            reply_markup=get_main_menu_keyboard()
        )
        await state.clear()
    
    async def callback_server_action(self, callback: CallbackQuery):
        """Обработчик действий с серверами"""
        parts = callback.data.split(":")
        action = parts[1]
        
        if action == "search":
            await callback.message.answer(
                "🔍 Введите параметры поиска:\n\n"
                "Примеры:\n"
                "• Серверы с RTX 4090\n"
                "• Дешевле $2 за карту 3080\n"
                "• 4 карты с рейтингом выше 4"
            )
        elif action == "hunt":
            await callback.message.answer(
                "🎯 Функция 'Охота на серверы' будет доступна в следующей версии!"
            )
        
        await callback.answer()
    
    async def callback_page_navigation(self, callback: CallbackQuery):
        """Обработчик навигации по страницам"""
        # TODO: Реализовать навигацию
        await callback.answer("В разработке")
    
    async def process_ai_query(self, message: Message):
        """Обработка запроса через AI агента"""
        await self._execute_ai_command(message, message.text)
    
    async def _execute_ai_command(self, message: Message, query: str):
        """Выполнить команду через AI агента"""
        user_id = message.from_user.id
        
        # Получаем пользователя и проверяем API ключ
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user or not user.clore_api_key:
                await message.answer(
                    "❌ Для работы необходимо настроить API ключ Clore.\n"
                    "Используйте /settings",
                    reply_markup=get_settings_keyboard(has_api_key=False)
                )
                return
        
        # Показываем индикатор загрузки
        loading_msg = await message.answer("🤖 Обрабатываю запрос...")
        
        try:
            # Получаем или создаем агента для пользователя
            if user_id not in self.agents:
                self.agents[user_id] = CloreAIAgent(user.clore_api_key)
            
            agent = self.agents[user_id]
            
            # Выполняем запрос с контекстом пользователя
            user_context = {
                'user_id': user_id,
                'username': message.from_user.username,
                'first_name': message.from_user.first_name
            }
            response = await agent.process_query(query, user_context)
            
            # Отправляем ответ
            await loading_msg.delete()
            
            # Разбиваем длинные сообщения
            if len(response) > 4000:
                parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
                for part in parts:
                    await message.answer(part, parse_mode="Markdown")
            else:
                await message.answer(response, parse_mode="Markdown")
                
        except Exception as e:
            logger.error(f"Error processing AI query: {e}")
            await loading_msg.edit_text(
                f"❌ Произошла ошибка: {str(e)}"
            )
    
    async def start(self):
        """Запуск бота"""
        logger.info("Starting Clore Bot Pro...")
        
        # Устанавливаем команды бота
        await self.bot.set_my_commands([
            types.BotCommand(command="start", description="Начать работу"),
            types.BotCommand(command="menu", description="Главное меню"),
            types.BotCommand(command="settings", description="Настройки"),
            types.BotCommand(command="balance", description="Проверить баланс"),
            types.BotCommand(command="orders", description="Мои аренды"),
            types.BotCommand(command="servers", description="Поиск серверов"),
            types.BotCommand(command="help", description="Справка"),
        ])
        
        # Запускаем polling
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping Clore Bot Pro...")
        
        # Закрываем все AI агенты
        for agent in self.agents.values():
            await agent.close()
        
        await self.bot.session.close()
