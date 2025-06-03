"""
Мониторинг баланса пользователей
"""
import asyncio
from datetime import datetime
from loguru import logger

from config import settings
from database.session import get_db
from database.crud import (
    get_active_users, save_balance_snapshot, 
    create_alert, get_balance_history
)
from clore_api.client import CloreAPIClient


class BalanceMonitor:
    """Сервис мониторинга балансов"""
    
    def __init__(self):
        self.running = False
        self.check_interval = settings.balance_check_interval
    
    async def start(self):
        """Запустить мониторинг"""
        self.running = True
        logger.info("Balance monitor started")
        
        while self.running:
            try:
                await self._check_all_balances()
            except Exception as e:
                logger.error(f"Error in balance monitor: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Остановить мониторинг"""
        self.running = False
        logger.info("Balance monitor stopped")
    
    async def _check_all_balances(self):
        """Проверить балансы всех активных пользователей"""
        async with get_db() as db:
            users = await get_active_users(db)
            
            for user in users:
                try:
                    await self._check_user_balance(user)
                except Exception as e:
                    logger.error(f"Error checking balance for user {user.id}: {e}")
    
    async def _check_user_balance(self, user):
        """Проверить баланс конкретного пользователя"""
        async with CloreAPIClient(user.clore_api_key) as client:
            # Получаем балансы
            wallets_data = await client.get_wallets()
            wallets = wallets_data.get('wallets', [])
            
            clore_balance = 0
            btc_balance = 0
            total_usd = 0
            
            for wallet in wallets:
                name = wallet.get('name', '')
                balance = wallet.get('balance', 0)
                
                if name == 'CLORE-Blockchain':
                    clore_balance = balance
                    total_usd += balance * settings.clore_to_usd
                elif name == 'bitcoin':
                    btc_balance = balance
                    total_usd += balance * settings.btc_to_usd
            
            # Сохраняем снимок
            async with get_db() as db:
                await save_balance_snapshot(
                    db,
                    user_id=user.id,
                    clore_balance=clore_balance,
                    btc_balance=btc_balance,
                    usd_equivalent=total_usd
                )
                
                # Проверяем пороговое значение
                if user.alert_balance_threshold and total_usd < user.alert_balance_threshold:
                    await self._create_low_balance_alert(db, user, total_usd)
                
                # Проверяем резкое падение баланса
                await self._check_balance_drop(db, user, clore_balance)
    
    async def _create_low_balance_alert(self, db, user, current_balance_usd):
        """Создать алерт о низком балансе"""
        await create_alert(
            db,
            user_id=user.id,
            alert_type='balance_low',
            title='⚠️ Низкий баланс',
            message=f'Ваш баланс (${current_balance_usd:.2f}) ниже установленного порога (${user.alert_balance_threshold:.2f})'
        )
    
    async def _check_balance_drop(self, db, user, current_clore_balance):
        """Проверить резкое падение баланса"""
        # Получаем историю за последний час
        history = await get_balance_history(db, user.id, hours=1)
        
        if not history:
            return
        
        # Берем самую старую запись из последнего часа
        oldest = history[-1] if history else None
        if not oldest:
            return
        
        # Проверяем падение более чем на 20%
        if oldest.clore_balance > 0:
            drop_percent = (oldest.clore_balance - current_clore_balance) / oldest.clore_balance * 100
            
            if drop_percent > 20:
                await create_alert(
                    db,
                    user_id=user.id,
                    alert_type='balance_drop',
                    title='📉 Резкое падение баланса',
                    message=f'Баланс CLORE упал на {drop_percent:.1f}% за последний час'
                )