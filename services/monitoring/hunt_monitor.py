"""
Сервис охоты на серверы
"""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from database.session import get_db
from database.crud import (
    get_active_hunt_tasks, create_alert, 
    get_docker_templates, save_order
)
from database.models import HuntTask, HuntResult
from clore_api.client import CloreAPIClient


class HuntMonitor:
    """Сервис автоматической охоты на серверы"""
    
    def __init__(self):
        self.running = False
        self.check_interval = 30  # Проверка каждые 30 секунд
        self.found_servers = {}  # Кеш найденных серверов
    
    async def start(self):
        """Запустить охоту"""
        self.running = True
        logger.info("Hunt monitor started")
        
        while self.running:
            try:
                await self._process_hunt_tasks()
            except Exception as e:
                logger.error(f"Error in hunt monitor: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Остановить охоту"""
        self.running = False
        logger.info("Hunt monitor stopped")
    
    async def _process_hunt_tasks(self):
        """Обработать все активные задачи охоты"""
        async with get_db() as db:
            tasks = await get_active_hunt_tasks(db)
            
            for task in tasks:
                try:
                    await self._process_single_task(task)
                except Exception as e:
                    logger.error(f"Error processing hunt task {task.id}: {e}")
    
    async def _process_single_task(self, task: HuntTask):
        """Обработать одну задачу охоты"""
        # Получаем пользователя и его API ключ
        async with get_db() as db:
            user = await db.get(type(task.user), task.user_id)
            
            if not user or not user.clore_api_key:
                logger.warning(f"User {task.user_id} has no API key")
                return
        
        # Создаем клиент API
        async with CloreAPIClient(user.clore_api_key) as client:
            # Получаем список серверов
            marketplace_data = await client.get_marketplace()
            servers = marketplace_data.get('servers', [])
            
            # Фильтруем по критериям
            matching_servers = self._filter_servers_by_criteria(
                servers, 
                task.filters
            )
            
            if not matching_servers:
                return
            
            # Обрабатываем найденные серверы
            await self._process_found_servers(
                client, task, user, matching_servers
            )
    
    def _filter_servers_by_criteria(
        self, 
        servers: List[Dict], 
        criteria: Dict[str, Any]
    ) -> List[Dict]:
        """Фильтровать серверы по критериям охоты"""
        filtered = []
        
        for server in servers:
            # Пропускаем арендованные
            if server.get('rented'):
                continue
            
            # Проверяем все критерии
            if not self._server_matches_criteria(server, criteria):
                continue
            
            filtered.append(server)
        
        return filtered
    
    def _server_matches_criteria(
        self, 
        server: Dict, 
        criteria: Dict[str, Any]
    ) -> bool:
        """Проверить, соответствует ли сервер критериям"""
        specs = server.get('specs', {})
        
        # GPU модель
        if 'gpu_models' in criteria and criteria['gpu_models']:
            gpu_str = specs.get('gpu', '').upper()
            if not any(model.upper() in gpu_str for model in criteria['gpu_models']):
                return False
        
        # Максимальная цена за GPU
        if 'max_price_per_gpu' in criteria:
            from clore_api.client import CloreAPIClient
            client = CloreAPIClient("")
            
            price, _ = client.extract_server_price(server)
            if price is None:
                return False
            
            gpu_count, _ = client.extract_gpu_info(specs.get('gpu', ''))
            if gpu_count > 0:
                price_per_gpu = price / gpu_count
                if price_per_gpu > criteria['max_price_per_gpu']:
                    return False
        
        # Количество GPU
        if 'min_gpu_count' in criteria:
            gpu_str = specs.get('gpu', '')
            count = int(gpu_str.split('x')[0]) if 'x' in gpu_str else 1
            if count < criteria['min_gpu_count']:
                return False
        
        if 'max_gpu_count' in criteria:
            gpu_str = specs.get('gpu', '')
            count = int(gpu_str.split('x')[0]) if 'x' in gpu_str else 1
            if count > criteria['max_gpu_count']:
                return False
        
        # RAM
        if 'min_ram_gb' in criteria:
            ram = specs.get('ram', 0)
            if ram < criteria['min_ram_gb']:
                return False
        
        # Локация
        if 'locations' in criteria and criteria['locations']:
            location = specs.get('net', {}).get('cc', '')
            if location not in criteria['locations']:
                return False
        
        # Рейтинг
        if 'min_rating' in criteria:
            rating = server.get('rating', {}).get('avg', 0)
            if rating < criteria['min_rating']:
                return False
        
        return True
    
    async def _process_found_servers(
        self,
        client: CloreAPIClient,
        task: HuntTask,
        user,
        servers: List[Dict]
    ):
        """Обработать найденные серверы"""
        # Проверяем лимит серверов
        if task.servers_rented >= task.max_servers:
            return
        
        # Сортируем по цене
        servers.sort(
            key=lambda s: client.extract_server_price(s)[0] or float('inf')
        )
        
        for server in servers:
            server_id = server['id']
            
            # Проверяем, не обрабатывали ли мы уже этот сервер
            cache_key = f"{task.id}:{server_id}"
            if cache_key in self.found_servers:
                last_found = self.found_servers[cache_key]
                if datetime.now() - last_found < timedelta(hours=1):
                    continue
            
            # Сохраняем в кеш
            self.found_servers[cache_key] = datetime.now()
            
            # Создаем алерт о находке
            async with get_db() as db:
                await self._create_found_alert(db, task, user, server)
                
                # Обновляем статистику
                task.servers_found += 1
                task.last_found_at = datetime.utcnow()
                await db.commit()
            
            # Если включена автоаренда
            if task.auto_rent:
                success = await self._auto_rent_server(
                    client, task, user, server
                )
                
                if success:
                    task.servers_rented += 1
                    
                    # Проверяем лимит
                    if task.servers_rented >= task.max_servers:
                        task.is_active = False
                        logger.info(f"Hunt task {task.id} reached limit")
                        break
    
    async def _create_found_alert(
        self, 
        db, 
        task: HuntTask, 
        user, 
        server: Dict
    ):
        """Создать уведомление о найденном сервере"""
        gpu = server.get('specs', {}).get('gpu', 'Unknown')
        price, _ = CloreAPIClient("").extract_server_price(server)
        
        message = (
            f"🎯 Найден сервер по задаче '{task.name}':\n"
            f"• ID: #{server['id']}\n"
            f"• GPU: {gpu}\n"
            f"• Цена: ${price:.2f}/день\n"
        )
        
        if task.auto_rent:
            message += "\n🤖 Пытаюсь арендовать автоматически..."
        else:
            message += "\n💡 Используйте 'арендовать {server['id']}' для аренды"
        
        await create_alert(
            db,
            user_id=user.id,
            alert_type='hunt_found',
            title='🎯 Сервер найден!',
            message=message
        )
    
    async def _auto_rent_server(
        self,
        client: CloreAPIClient,
        task: HuntTask,
        user,
        server: Dict
    ) -> bool:
        """Автоматически арендовать сервер"""
        try:
            # Получаем настройки аренды
            rent_settings = task.rent_settings or {}
            
            # Если есть шаблон Docker
            if task.docker_template_id:
                async with get_db() as db:
                    template = await db.get(
                        DockerTemplate, 
                        task.docker_template_id
                    )
                    if template:
                        rent_settings.update({
                            'image': template.image,
                            'ports': template.ports,
                            'env': template.env,
                            'command': template.command
                        })
            
            # Параметры по умолчанию
            image = rent_settings.get('image', 'cloreai/jupyter:ubuntu24.04-v2')
            ports = rent_settings.get('ports', {"22": "tcp", "8888": "http"})
            
            # Создаем заказ
            result = await client.create_order(
                currency="CLORE-Blockchain",
                image=image,
                renting_server=server['id'],
                order_type="on-demand",
                ports=ports,
                env=rent_settings.get('env', {}),
                jupyter_token=user.default_jupyter_token or "auto",
                ssh_password=user.default_ssh_password or "auto",
                command=rent_settings.get('command'),
                autossh_entrypoint=True
            )
            
            # Сохраняем информацию о заказе
            if result.get('code') == 0:
                async with get_db() as db:
                    # Здесь должна быть логика сохранения заказа
                    await create_alert(
                        db,
                        user_id=user.id,
                        alert_type='hunt_rented',
                        title='✅ Сервер арендован!',
                        message=f'Сервер #{server["id"]} успешно арендован по задаче "{task.name}"'
                    )
                
                return True
            
        except Exception as e:
            logger.error(f"Failed to auto-rent server {server['id']}: {e}")
        
        return False