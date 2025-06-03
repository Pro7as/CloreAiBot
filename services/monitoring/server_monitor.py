"""
Мониторинг серверов и ордеров
"""
import asyncio
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from database.session import get_db
from database.crud import (
    get_active_users, get_active_orders, update_order_status,
    save_server_snapshot, create_alert, save_order
)
from clore_api.client import CloreAPIClient


class ServerMonitor:
    """Сервис мониторинга серверов и ордеров"""
    
    def __init__(self):
        self.running = False
        self.check_interval = settings.server_check_interval
    
    async def start(self):
        """Запустить мониторинг"""
        self.running = True
        logger.info("Server monitor started")
        
        while self.running:
            try:
                await self._check_all_servers()
            except Exception as e:
                logger.error(f"Error in server monitor: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Остановить мониторинг"""
        self.running = False
        logger.info("Server monitor stopped")
    
    async def _check_all_servers(self):
        """Проверить серверы всех пользователей"""
        async with get_db() as db:
            users = await get_active_users(db)
            
            for user in users:
                try:
                    await self._check_user_servers(user)
                except Exception as e:
                    logger.error(f"Error checking servers for user {user.id}: {e}")
    
    async def _check_user_servers(self, user):
        """Проверить серверы и ордера пользователя"""
        async with CloreAPIClient(user.clore_api_key) as client:
            # Проверяем мои серверы (которые пользователь сдает)
            await self._check_my_servers(client, user)
            
            # Проверяем активные ордера (аренды)
            await self._check_active_orders(client, user)
            
            # Сохраняем снимки маркетплейса для аналитики
            await self._save_marketplace_snapshot(client, user)
    
    async def _check_my_servers(self, client: CloreAPIClient, user):
        """Проверить серверы пользователя"""
        try:
            servers_data = await client.get_my_servers()
            servers = servers_data.get('servers', [])
            
            async with get_db() as db:
                for server in servers:
                    # Проверяем изменение статуса
                    await self._check_server_status_change(db, user, server)
                    
                    # Сохраняем снимок
                    if server.get('connected') and server.get('specs'):
                        await save_server_snapshot(
                            db,
                            user_id=user.id,
                            server_data=server,
                            snapshot_type='my_server'
                        )
        except Exception as e:
            logger.error(f"Error checking my servers: {e}")
    
    async def _check_active_orders(self, client: CloreAPIClient, user):
        """Проверить активные ордера"""
        try:
            orders_data = await client.get_my_orders(return_completed=False)
            api_orders = orders_data.get('orders', [])
            
            async with get_db() as db:
                # Получаем активные ордера из БД
                db_orders = await get_active_orders(db, user.id)
                db_order_ids = {order.clore_order_id for order in db_orders}
                
                # Проверяем новые ордера
                for api_order in api_orders:
                    order_id = api_order.get('id')
                    
                    if order_id not in db_order_ids:
                        # Новый ордер - сохраняем
                        await save_order(db, user.id, api_order)
                    else:
                        # Обновляем существующий
                        await update_order_status(
                            db,
                            clore_order_id=order_id,
                            status='active',
                            total_spent=api_order.get('spend', 0)
                        )
                    
                    # Проверяем истечение срока
                    await self._check_order_expiry(db, user, api_order)
                
                # Проверяем завершенные ордера
                api_order_ids = {o.get('id') for o in api_orders}
                for db_order in db_orders:
                    if db_order.clore_order_id not in api_order_ids:
                        # Ордер больше не активен
                        await update_order_status(
                            db,
                            clore_order_id=db_order.clore_order_id,
                            status='expired'
                        )
                        
                        await create_alert(
                            db,
                            user_id=user.id,
                            alert_type='order_expired',
                            title='⏰ Аренда завершена',
                            message=f'Заказ #{db_order.clore_order_id} завершен'
                        )
        
        except Exception as e:
            logger.error(f"Error checking active orders: {e}")
    
    async def _check_server_status_change(self, db, user, server):
        """Проверить изменение статуса сервера"""
        # TODO: Реализовать отслеживание изменений статуса
        # Нужно хранить предыдущее состояние и сравнивать
        pass
    
    async def _check_order_expiry(self, db, user, order):
        """Проверить истечение срока аренды"""
        mrl = order.get('mrl', 0)  # максимальное время аренды в секундах
        created_at = order.get('ct', 0)
        
        if not mrl or not created_at:
            return
        
        expires_at = datetime.fromtimestamp(created_at + mrl)
        time_left = expires_at - datetime.now()
        hours_left = time_left.total_seconds() / 3600
        
        # Предупреждаем если осталось меньше порогового значения
        if 0 < hours_left <= user.alert_rental_expiry_hours:
            # Проверяем, не отправляли ли мы уже алерт
            # TODO: Добавить проверку на дубликаты алертов
            
            await create_alert(
                db,
                user_id=user.id,
                alert_type='order_expiring',
                title='⏳ Аренда скоро закончится',
                message=f'Заказ #{order.get("id")} истекает через {hours_left:.1f} часов'
            )
    
    async def _save_marketplace_snapshot(self, client: CloreAPIClient, user):
        """Сохранить снимок маркетплейса для аналитики"""
        try:
            # Сохраняем снимки только раз в час
            current_minute = datetime.now().minute
            if current_minute != 0:  # Только в начале часа
                return
            
            marketplace_data = await client.get_marketplace()
            servers = marketplace_data.get('servers', [])
            
            # Сохраняем только интересные серверы (например, с нужными GPU)
            interesting_gpus = ['4090', '3090', '3080', 'A100', 'H100']
            
            async with get_db() as db:
                for server in servers:
                    gpu_str = server.get('specs', {}).get('gpu', '')
                    
                    # Проверяем, интересен ли нам этот сервер
                    if any(gpu in gpu_str for gpu in interesting_gpus):
                        await save_server_snapshot(
                            db,
                            user_id=user.id,
                            server_data=server,
                            snapshot_type='marketplace'
                        )
        
        except Exception as e:
            logger.error(f"Error saving marketplace snapshot: {e}")