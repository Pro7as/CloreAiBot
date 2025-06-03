"""
AI агент для работы с Clore API
"""
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import asyncio
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.tools import Tool
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

from clore_api.client import CloreAPIClient
from config import settings


class CloreAIAgent:
    """AI агент для интеллектуального взаимодействия с Clore API"""
    
    def __init__(self, api_key: str):
        self.clore_client = CloreAPIClient(api_key)
        self.llm = ChatOpenAI(
            model_name=settings.openai_model,
            temperature=0.3,
            openai_api_key=settings.openai_api_key
        )
        
        # Контекст последнего поиска для пагинации
        self.last_search_results = []
        self.current_page = 0
        
    async def close(self):
        """Закрыть соединения"""
        await self.clore_client.close()
    
    def _parse_filters(self, query: str) -> Dict[str, Any]:
        """Извлечь фильтры из запроса пользователя"""
        filters = {}
        
        # GPU модели
        gpu_models = ['4090', '3090', '3080', '3070', '3060', 'A100', 'A6000', 'H100']
        for model in gpu_models:
            if model.lower() in query.lower():
                filters['gpu_model'] = model
                break
        
        # Цена
        import re
        price_match = re.search(r'дешевле\s+(\d+(?:\.\d+)?)\s*(?:доллар|usd|\$)', query.lower())
        if price_match:
            filters['max_price'] = float(price_match.group(1))
        
        price_per_gpu_match = re.search(r'дешевле\s+(\d+(?:\.\d+)?)\s*(?:доллар|usd|\$)\s*за\s*карту', query.lower())
        if price_per_gpu_match:
            filters['max_price_per_gpu'] = float(price_per_gpu_match.group(1))
        
        # Количество GPU
        gpu_count_match = re.search(r'(\d+)\s*(?:карт|gpu|видеокарт)', query.lower())
        if gpu_count_match:
            filters['gpu_count'] = int(gpu_count_match.group(1))
        
        # PCIe
        if 'pcie x16' in query.lower() or 'pcie 16' in query.lower():
            filters['pcie_width'] = 16
        elif 'pcie x8' in query.lower() or 'pcie 8' in query.lower():
            filters['pcie_width'] = 8
        
        # Рейтинг
        rating_match = re.search(r'рейтинг(?:ом)?\s*(?:выше|больше|>)\s*(\d+(?:\.\d+)?)', query.lower())
        if rating_match:
            filters['min_rating'] = float(rating_match.group(1))
        
        # Страна
        countries = {
            'сша': 'US', 'америк': 'US',
            'канад': 'CA',
            'герман': 'DE',
            'франц': 'FR',
            'нидерланд': 'NL',
            'швец': 'SE'
        }
        for country_key, country_code in countries.items():
            if country_key in query.lower():
                filters['country'] = country_code
                break
        
        # Статус
        if 'свободн' in query.lower() or 'доступн' in query.lower():
            filters['available_only'] = True
        
        return filters
    
    def _filter_servers(self, servers: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Применить фильтры к списку серверов"""
        filtered = []
        
        for server in servers:
            # Пропускаем арендованные, если нужны только свободные
            if filters.get('available_only') and server.get('rented'):
                continue
            
            specs = server.get('specs', {})
            
            # Фильтр по GPU модели
            if 'gpu_model' in filters:
                gpu_str = specs.get('gpu', '')
                if filters['gpu_model'] not in gpu_str:
                    continue
            
            # Фильтр по количеству GPU
            if 'gpu_count' in filters:
                gpu_str = specs.get('gpu', '')
                gpu_count, _ = self.clore_client.extract_gpu_info(gpu_str)
                if gpu_count != filters['gpu_count']:
                    continue
            
            # Фильтр по цене
            price, _ = self.clore_client.extract_server_price(server)
            if price is None:
                continue
                
            if 'max_price' in filters and price > filters['max_price']:
                continue
            
            # Фильтр по цене за GPU
            if 'max_price_per_gpu' in filters:
                gpu_str = specs.get('gpu', '')
                gpu_count, _ = self.clore_client.extract_gpu_info(gpu_str)
                if gpu_count > 0:
                    price_per_gpu = price / gpu_count
                    if price_per_gpu > filters['max_price_per_gpu']:
                        continue
            
            # Фильтр по PCIe
            if 'pcie_width' in filters:
                pcie_width = specs.get('pcie_width', 0)
                if pcie_width < filters['pcie_width']:
                    continue
            
            # Фильтр по рейтингу
            if 'min_rating' in filters:
                rating = server.get('rating', {}).get('avg', 0)
                if rating < filters['min_rating']:
                    continue
            
            # Фильтр по стране
            if 'country' in filters:
                country = specs.get('net', {}).get('cc', '')
                if country != filters['country']:
                    continue
            
            filtered.append(server)
        
        return filtered
    
    async def process_query(self, query: str, user_context: Dict[str, Any] = None) -> str:
        """Обработать запрос пользователя"""
        query_lower = query.lower()
        
        logger.info(f"Processing query: {query}")
        
        try:
            # === Команды поиска и фильтрации ===
            if any(word in query_lower for word in ['покажи', 'найди', 'поиск', 'сервер', 'список']):
                # Проверяем, не запрос ли это на аренду
                if any(word in query_lower for word in ['арендовать', 'арендуй', 'снять', 'сними']):
                    logger.info("Detected rental request in search query")
                    return await self._handle_create_order(query)
                logger.info("Handling search request")
                return await self._handle_search(query)
            
            # === Информация о балансе ===
            elif any(word in query_lower for word in ['баланс', 'счет', 'деньги', 'средств']):
                return await self._handle_balance()
            
            # === Мои аренды ===
            elif any(word in query_lower for word in ['аренд', 'заказ', 'ордер']) and \
                 any(word in query_lower for word in ['мои', 'текущ', 'актив']):
                return await self._handle_my_orders()
            
            # === Создание аренды ===
            elif any(word in query_lower for word in ['арендовать', 'арендуй', 'снять', 'сними', 'создать заказ', 'заказать']):
                logger.info("Handling create order request")
                return await self._handle_create_order(query)
            
            # === Отмена аренды ===
            elif any(word in query_lower for word in ['отменить', 'отмена', 'завершить']):
                return await self._handle_cancel_order(query)
            
            # === Мои серверы (которые я сдаю) ===
            elif 'мои сервер' in query_lower and 'аренд' not in query_lower:
                return await self._handle_my_servers()
            
            # === Статистика по серверам ===
            elif any(word in query_lower for word in ['сколько', 'количество']) and \
                 any(word in query_lower for word in ['4090', '3090', '3080', 'сервер']):
                return await self._handle_server_count(query)
            
            # === Статистика и аналитика ===
            elif any(word in query_lower for word in ['статистик', 'аналитик', 'отчет']):
                return await self._handle_analytics(query)
            
            # === Продолжение аренды с параметрами ===
            elif ('арен' in query_lower or 'ubuntu' in query_lower or 'убунт' in query_lower) and \
                 re.search(r'\d{4,}', query):  # Если есть число из 4+ цифр (ID сервера)
                logger.info("Detected rental continuation request")
                return await self._handle_create_order(query)
            
            # === Помощь ===
            elif any(word in query_lower for word in ['помощь', 'help', 'команды', 'что умеешь']):
                return self._get_help_message()
            
            # === Неизвестная команда ===
            else:
                # Проверяем, может это просто номер сервера
                import re
                if re.match(r'^\d+$', query.strip()):
                    logger.info(f"Detected server ID: {query}")
                    return await self._handle_server_info(query)
                
                logger.info("Handling unknown query")
                return await self._handle_unknown(query)
                
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return f"❌ Произошла ошибка при обработке запроса: {str(e)}"
    
    async def _create_order_with_defaults(self, server_id: int, server_data: Dict, query: str) -> str:
        """Создать ордер с настройками по умолчанию"""
        try:
            # Проверяем, что у нас есть API ключ
            if not self.clore_client.api_key:
                return "❌ Не настроен Clore API ключ. Используйте /settings для настройки."
            
            # Определяем образ на основе запроса
            if 'ubuntu' in query.lower() or 'убунт' in query.lower():
                image = "cloreai/ubuntu:22.04"
                display_name = "Ubuntu 22.04"
            elif 'jupyter' in query.lower():
                image = "cloreai/jupyter:ubuntu24.04-v2"
                display_name = "Ubuntu 24.04 + Jupyter"
            elif 'pytorch' in query.lower():
                image = "pytorch/pytorch:latest"
                display_name = "PyTorch Latest"
            else:
                image = "cloreai/jupyter:ubuntu24.04-v2"
                display_name = "Ubuntu 24.04 + Jupyter (default)"
            
            # Показываем, что создаем заказ
            logger.info(f"Creating order for server {server_id} with image {image}")
            
            # Создаем ордер
            result = await self.clore_client.create_order(
                currency="CLORE-Blockchain",
                image=image,
                renting_server=server_id,
                order_type="on-demand",
                ports={"22": "tcp", "8888": "http"},
                jupyter_token="clore123",  # Временный токен
                ssh_password="clore123",   # Временный пароль
                command="#!/bin/sh\napt update -y",
                autossh_entrypoint=True
            )
            
            if result.get('code') == 0:
                # Получаем информацию о созданном ордере
                orders_data = await self.clore_client.get_my_orders()
                orders = orders_data.get('orders', [])
                
                # Находим наш ордер
                created_order = None
                for order in orders:
                    if order.get('si') == server_id:
                        created_order = order
                        break
                
                if created_order:
                    # Форматируем информацию о подключении
                    pub_cluster = created_order.get('pub_cluster', [])
                    tcp_ports = created_order.get('tcp_ports', [])
                    ssh_info = None
                    
                    for port_map in tcp_ports:
                        if port_map.startswith("22:"):
                            ssh_port = port_map.split(":")[1]
                            if pub_cluster:
                                ssh_info = f"ssh root@{pub_cluster[0]} -p {ssh_port}"
                            break
                    
                    response = (
                        f"✅ **Сервер #{server_id} успешно арендован!**\n\n"
                        f"📦 Заказ: #{created_order.get('id')}\n"
                        f"🐳 Образ: {display_name}\n"
                        f"💰 Цена: ${created_order.get('price', 0) * settings.clore_to_usd:.2f}/день\n\n"
                        f"**🔐 Доступы:**\n"
                        f"• SSH пароль: `clore123`\n"
                        f"• Jupyter токен: `clore123`\n"
                    )
                    
                    if ssh_info:
                        response += f"\n**🖥️ SSH подключение:**\n```\n{ssh_info}\n```"
                    
                    response += "\n\n⚠️ **Важно:** Смените пароли после первого входа!"
                    
                    return response
                else:
                    return "✅ Ордер создан, но не могу получить детали подключения. Проверьте через /orders"
            else:
                error = result.get('error', 'Unknown error')
                return f"❌ Ошибка создания ордера: {error}"
                
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return f"❌ Ошибка при создании заказа: {str(e)}"
    
    async def _handle_search(self, query: str) -> str:
        """Обработать запрос поиска серверов"""
        # Извлекаем фильтры
        filters = self._parse_filters(query)
        
        # Получаем список серверов
        marketplace_data = await self.clore_client.get_marketplace()
        servers = marketplace_data.get('servers', [])
        
        # Применяем фильтры
        filtered_servers = self._filter_servers(servers, filters)
        
        if not filtered_servers:
            return "🔍 Серверы по заданным критериям не найдены."
        
        # Сортировка по цене
        filtered_servers.sort(key=lambda s: self.clore_client.extract_server_price(s)[0] or float('inf'))
        
        # Сохраняем для пагинации
        self.last_search_results = filtered_servers
        self.current_page = 0
        
        # Формируем ответ
        total = len(filtered_servers)
        page_size = settings.servers_per_page
        start_idx = 0
        end_idx = min(page_size, total)
        
        response = f"🔍 Найдено серверов: {total}\n\n"
        
        for i in range(start_idx, end_idx):
            server = filtered_servers[i]
            response += f"{i+1}. {self.clore_client.format_server_short(server)}\n\n"
        
        if total > page_size:
            response += f"📄 Показаны {start_idx+1}-{end_idx} из {total}. Используйте кнопки для навигации."
        
        # Добавляем сводку по фильтрам
        if filters:
            response += "\n\n🔧 Применены фильтры:\n"
            if 'gpu_model' in filters:
                response += f"• GPU: {filters['gpu_model']}\n"
            if 'max_price' in filters:
                response += f"• Цена: до ${filters['max_price']}/день\n"
            if 'max_price_per_gpu' in filters:
                response += f"• Цена за GPU: до ${filters['max_price_per_gpu']}/день\n"
            if 'gpu_count' in filters:
                response += f"• Количество GPU: {filters['gpu_count']}\n"
            if 'pcie_width' in filters:
                response += f"• PCIe: x{filters['pcie_width']}\n"
            if 'min_rating' in filters:
                response += f"• Рейтинг: от {filters['min_rating']}\n"
            if 'country' in filters:
                response += f"• Страна: {filters['country']}\n"
        
        return response
    
    async def _handle_balance(self) -> str:
        """Получить информацию о балансе"""
        wallets_data = await self.clore_client.get_wallets()
        wallets = wallets_data.get('wallets', [])
        
        response = "💰 **Ваши балансы:**\n\n"
        
        total_usd = 0
        for wallet in wallets:
            name = wallet.get('name', 'Unknown')
            balance = wallet.get('balance', 0)
            
            # Конвертация в USD
            if name == 'bitcoin':
                usd_value = balance * settings.btc_to_usd
                symbol = 'BTC'
            elif name == 'CLORE-Blockchain':
                usd_value = balance * settings.clore_to_usd
                symbol = 'CLORE'
            else:
                usd_value = 0
                symbol = name
            
            total_usd += usd_value
            
            response += f"• {symbol}: {balance:.8f} (~${usd_value:.2f})\n"
            
            # Адрес для пополнения
            deposit = wallet.get('deposit')
            if deposit:
                response += f"  └ Адрес: `{deposit}`\n"
        
        response += f"\n💵 **Общий баланс:** ${total_usd:.2f}"
        
        return response
    
    async def _handle_my_orders(self) -> str:
        """Получить информацию о текущих арендах"""
        orders_data = await self.clore_client.get_my_orders(return_completed=False)
        orders = orders_data.get('orders', [])
        
        if not orders:
            return "📦 У вас нет активных аренд."
        
        response = f"📦 **Активные аренды:** {len(orders)}\n\n"
        
        total_cost_per_day = 0
        
        for idx, order in enumerate(orders, 1):
            order_id = order.get('id')
            server_id = order.get('si')
            order_type = "SPOT" if order.get('spot') else "ON-DEMAND"
            
            # Спецификации
            specs = order.get('specs', {})
            gpu = specs.get('gpu', 'N/A')
            cpu = specs.get('cpu', 'N/A')
            if len(cpu) > 30:
                cpu = cpu[:27] + '...'
            
            # Цена
            price = order.get('price', 0)
            currency = order.get('currency', 'unknown')
            if currency == 'CLORE-Blockchain':
                price_usd = price * settings.clore_to_usd
            elif currency == 'bitcoin':
                price_usd = price * settings.btc_to_usd
            else:
                price_usd = 0
            
            total_cost_per_day += price_usd
            
            # Время работы
            created_at = order.get('ct', 0)
            if created_at:
                created_dt = datetime.fromtimestamp(created_at)
                runtime = datetime.now() - created_dt
                hours = runtime.total_seconds() / 3600
                runtime_str = f"{hours:.1f}ч"
            else:
                runtime_str = "N/A"
            
            # Endpoints
            endpoints = []
            tcp_ports = order.get('tcp_ports', [])
            for port_map in tcp_ports:
                endpoints.append(f"SSH: {port_map}")
            
            http_port = order.get('http_port')
            if http_port:
                endpoints.append(f"HTTP: :{http_port}")
            
            response += (
                f"**{idx}. Заказ #{order_id}** ({order_type})\n"
                f"├ Сервер: #{server_id}\n"
                f"├ GPU: {gpu}\n"
                f"├ CPU: {cpu}\n"
                f"├ Цена: ${price_usd:.2f}/день\n"
                f"├ Время работы: {runtime_str}\n"
            )
            
            if endpoints:
                response += f"└ Доступ: {', '.join(endpoints)}\n"
            
            response += "\n"
        
        response += f"💸 **Общая стоимость:** ${total_cost_per_day:.2f}/день"
        
        # Предупреждение если аренда скоро закончится
        for order in orders:
            mrl = order.get('mrl', 0)  # максимальное время аренды в секундах
            created_at = order.get('ct', 0)
            if mrl and created_at:
                expires_at = created_at + mrl
                time_left = expires_at - datetime.now().timestamp()
                hours_left = time_left / 3600
                
                if hours_left < 5:
                    response += f"\n\n⚠️ Заказ #{order.get('id')} истекает через {hours_left:.1f} часов!"
        
        return response
    
    async def _handle_create_order(self, query: str) -> str:
        """Обработать запрос на создание аренды"""
        # Извлекаем номера серверов из запроса
        import re
        
        # Ищем паттерны вида "арендовать 3,5,7" или "снять серверы 123 456"
        numbers = re.findall(r'\d+', query)
        
        if not numbers:
            return (
                "❌ Не указаны номера серверов для аренды.\n\n"
                "Используйте формат: 'арендовать 123' или 'снять серверы 123,456,789'"
            )
        
        server_ids = [int(n) for n in numbers]
        
        # Ограничиваем количество серверов
        if len(server_ids) > 5:
            return "❌ Можно арендовать не более 5 серверов за раз."
        
        # Проверяем доступность серверов
        marketplace_data = await self.clore_client.get_marketplace()
        available_servers = {s['id']: s for s in marketplace_data.get('servers', [])}
        
        # Если только один сервер и упоминается образ - сразу арендуем
        if len(server_ids) == 1 and any(word in query.lower() for word in ['ubuntu', 'убунт', 'jupyter', 'pytorch']):
            server_id = server_ids[0]
            if server_id in available_servers and not available_servers[server_id].get('rented'):
                return await self._create_order_with_defaults(server_id, available_servers[server_id], query)
        
        results = []
        for server_id in server_ids:
            if server_id not in available_servers:
                results.append(f"❌ Сервер #{server_id} не найден")
                continue
            
            server = available_servers[server_id]
            if server.get('rented'):
                results.append(f"❌ Сервер #{server_id} уже арендован")
                continue
            
            # Здесь должна быть логика создания ордера
            # Пока просто показываем информацию
            price, _ = self.clore_client.extract_server_price(server)
            gpu = server.get('specs', {}).get('gpu', 'N/A')
            
            results.append(
                f"✅ Сервер #{server_id} готов к аренде:\n"
                f"   • GPU: {gpu}\n"
                f"   • Цена: ${price:.2f}/день\n"
                f"   • Используйте шаблон Docker для завершения"
            )
        
        response = "🛒 **Результаты проверки:**\n\n" + "\n\n".join(results)
        
        if any("✅" in r for r in results):
            response += (
                "\n\n💡 Для завершения аренды:\n"
                "• 'арендуй [ID] с ubuntu' - Ubuntu 22.04 + Jupyter\n"
                "• 'арендуй [ID] с pytorch' - PyTorch latest\n"
                "• Или используйте /settings для настройки SSH пароля"
            )
        
        return response
    
    async def _handle_cancel_order(self, query: str) -> str:
        """Обработать запрос на отмену аренды"""
        import re
        
        # Извлекаем ID ордера
        order_id_match = re.search(r'(\d+)', query)
        if not order_id_match:
            return "❌ Укажите номер заказа для отмены. Например: 'отменить заказ 123'"
        
        order_id = int(order_id_match.group(1))
        
        try:
            result = await self.clore_client.cancel_order(order_id)
            return f"✅ Заказ #{order_id} успешно отменен."
        except Exception as e:
            return f"❌ Ошибка при отмене заказа #{order_id}: {str(e)}"
    
    async def _handle_my_servers(self) -> str:
        """Получить информацию о моих серверах (которые я сдаю)"""
        servers_data = await self.clore_client.get_my_servers()
        servers = servers_data.get('servers', [])
        
        if not servers:
            return "🖥️ У вас нет зарегистрированных серверов."
        
        response = f"🖥️ **Ваши серверы:** {len(servers)}\n\n"
        
        for idx, server in enumerate(servers, 1):
            name = server.get('name', 'Unnamed')
            online = "🟢 Online" if server.get('online') else "🔴 Offline"
            visibility = server.get('visibility', 'hidden')
            
            # Цены
            pricing = server.get('pricing', {})
            btc_price = pricing.get('bitcoin', 0)
            usd_price = pricing.get('usd', 0)
            
            if btc_price:
                price_str = f"{btc_price:.8f} BTC/день"
            elif usd_price:
                price_str = f"${usd_price:.2f}/день"
            else:
                price_str = "Не установлена"
            
            response += (
                f"**{idx}. {name}** {online}\n"
                f"├ Видимость: {visibility}\n"
                f"├ Цена: {price_str}\n"
            )
            
            # Спецификации если есть
            specs = server.get('specs')
            if specs:
                gpu = specs.get('gpu', 'N/A')
                cpu = specs.get('cpu', 'N/A')
                if len(cpu) > 30:
                    cpu = cpu[:27] + '...'
                
                response += (
                    f"├ GPU: {gpu}\n"
                    f"├ CPU: {cpu}\n"
                )
            
            response += "\n"
        
        return response
    
    async def _handle_analytics(self, query: str) -> str:
        """Обработать запрос аналитики"""
        # Базовая аналитика
        response = "📊 **Аналитика использования:**\n\n"
        
        # Получаем историю ордеров
        orders_data = await self.clore_client.get_my_orders(return_completed=True)
        all_orders = orders_data.get('orders', [])
        
        active_orders = [o for o in all_orders if not o.get('expired')]
        completed_orders = [o for o in all_orders if o.get('expired')]
        
        response += f"• Активных аренд: {len(active_orders)}\n"
        response += f"• Завершенных аренд: {len(completed_orders)}\n"
        
        # Считаем общие расходы
        total_spent = 0
        for order in all_orders:
            spent = order.get('spend', 0)
            currency = order.get('currency', '')
            
            if currency == 'CLORE-Blockchain':
                total_spent += spent * settings.clore_to_usd
            elif currency == 'bitcoin':
                total_spent += spent * settings.btc_to_usd
        
        response += f"• Общие расходы: ${total_spent:.2f}\n"
        
        # Популярные GPU
        gpu_usage = {}
        for order in all_orders:
            gpu = order.get('specs', {}).get('gpu', 'Unknown')
            gpu_usage[gpu] = gpu_usage.get(gpu, 0) + 1
        
        if gpu_usage:
            response += "\n**Использование GPU:**\n"
            for gpu, count in sorted(gpu_usage.items(), key=lambda x: x[1], reverse=True)[:5]:
                response += f"• {gpu}: {count} раз\n"
        
        return response
    
    async def _handle_server_info(self, server_id_str: str) -> str:
        """Показать информацию о конкретном сервере"""
        try:
            server_id = int(server_id_str.strip())
            
            # Получаем информацию о сервере
            marketplace_data = await self.clore_client.get_marketplace()
            servers = marketplace_data.get('servers', [])
            
            server = None
            for s in servers:
                if s.get('id') == server_id:
                    server = s
                    break
            
            if not server:
                return f"❌ Сервер #{server_id} не найден на маркетплейсе."
            
            # Форматируем информацию
            info = self.clore_client.format_server_full(server)
            
            # Добавляем кнопки действий
            if not server.get('rented'):
                info += "\n\n💡 Для аренды используйте: 'арендовать " + str(server_id) + "'"
            else:
                info += "\n\n❌ Сервер уже арендован"
            
            return info
            
        except ValueError:
            return "❌ Неверный формат ID сервера"
        except Exception as e:
            logger.error(f"Error getting server info: {e}")
            return f"❌ Ошибка при получении информации о сервере: {str(e)}"
    
    async def _handle_server_count(self, query: str) -> str:
        """Подсчитать количество серверов по критериям"""
        # Получаем все серверы
        marketplace_data = await self.clore_client.get_marketplace()
        all_servers = marketplace_data.get('servers', [])
        
        # Извлекаем фильтры
        filters = self._parse_filters(query)
        
        # Если запрашивается конкретная модель GPU
        gpu_models = ['4090', '3090', '3080', '3070', '3060', 'A100', 'A6000', 'H100']
        requested_gpu = None
        for model in gpu_models:
            if model.lower() in query.lower():
                requested_gpu = model
                break
        
        # Подсчет по категориям
        stats = {
            'total': len(all_servers),
            'available': 0,
            'rented': 0,
            'by_gpu': {}
        }
        
        for server in all_servers:
            if server.get('rented'):
                stats['rented'] += 1
            else:
                stats['available'] += 1
            
            # Подсчет по GPU
            gpu_str = server.get('specs', {}).get('gpu', '')
            gpu_count, gpu_model = self.clore_client.extract_gpu_info(gpu_str)
            
            # Упрощаем название модели
            for model in gpu_models:
                if model in gpu_model:
                    if model not in stats['by_gpu']:
                        stats['by_gpu'][model] = {'total': 0, 'available': 0, 'count': 0}
                    
                    stats['by_gpu'][model]['total'] += 1
                    stats['by_gpu'][model]['count'] += gpu_count
                    if not server.get('rented'):
                        stats['by_gpu'][model]['available'] += 1
                    break
        
        # Формируем ответ
        if requested_gpu and requested_gpu in stats['by_gpu']:
            gpu_stats = stats['by_gpu'][requested_gpu]
            response = (
                f"📊 **Статистика по {requested_gpu}:**\n\n"
                f"• Всего серверов: {gpu_stats['total']}\n"
                f"• Доступно: {gpu_stats['available']}\n"
                f"• Арендовано: {gpu_stats['total'] - gpu_stats['available']}\n"
                f"• Всего карт: {gpu_stats['count']}\n"
            )
            
            # Добавляем цены
            if gpu_stats['available'] > 0:
                # Находим минимальную и максимальную цену
                prices = []
                for server in all_servers:
                    if not server.get('rented') and requested_gpu in server.get('specs', {}).get('gpu', ''):
                        price, _ = self.clore_client.extract_server_price(server)
                        if price:
                            gpu_count, _ = self.clore_client.extract_gpu_info(server.get('specs', {}).get('gpu', ''))
                            if gpu_count > 0:
                                price_per_gpu = price / gpu_count
                                prices.append(price_per_gpu)
                
                if prices:
                    response += (
                        f"\n💰 **Цены за карту/день:**\n"
                        f"• Минимум: ${min(prices):.2f}\n"
                        f"• Максимум: ${max(prices):.2f}\n"
                        f"• Средняя: ${sum(prices)/len(prices):.2f}"
                    )
        else:
            response = f"📊 **Статистика маркетплейса:**\n\n"
            response += f"• Всего серверов: {stats['total']}\n"
            response += f"• Доступно: {stats['available']}\n"
            response += f"• Арендовано: {stats['rented']}\n\n"
            
            if stats['by_gpu']:
                response += "**По моделям GPU:**\n"
                for model, gpu_stats in sorted(stats['by_gpu'].items(), key=lambda x: x[1]['total'], reverse=True):
                    response += f"• {model}: {gpu_stats['total']} серверов ({gpu_stats['available']} доступно)\n"
        
        return response
    
    async def _handle_unknown(self, query: str) -> str:
        """Обработать неизвестный запрос"""
        # Пробуем использовать LLM для понимания намерения
        system_prompt = """
        Ты - помощник для работы с платформой Clore.ai для аренды GPU серверов.
        Проанализируй запрос пользователя и определи, что он хочет сделать.
        Доступные действия: поиск серверов, проверка баланса, управление арендами,
        создание/отмена заказов, просмотр своих серверов, аналитика.
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        return (
            f"🤔 Я не уверен, что вы хотите сделать.\n\n"
            f"{response.content}\n\n"
            f"Попробуйте переформулировать запрос или используйте /help для списка команд."
        )
    
    def _get_help_message(self) -> str:
        """Получить справочное сообщение"""
        return """
🤖 **Я умею выполнять следующие операции:**

**🔍 Поиск серверов:**
• "Покажи серверы с 4090"
• "Найди серверы дешевле $1 за карту 4090"
• "Серверы с рейтингом выше 4"
• "Доступные серверы с PCIe x16"
• "Сколько всего 4090 на маркетплейсе?"

**💰 Финансы:**
• "Покажи баланс"
• "Сколько у меня денег"

**📦 Аренды:**
• "Мои текущие аренды"
• "Активные заказы"
• "Арендовать сервер 12345"
• "Арендуй 12345 с ubuntu"
• "Снять сервер 12345 с pytorch"
• "Отменить заказ 789"

**🖥️ Мои серверы:**
• "Мои серверы" (которые вы сдаете)
• "Статус моих серверов"

**📊 Аналитика:**
• "Покажи статистику"
• "Сколько я потратил"
• "Сколько серверов с 3090?"

**🐳 Docker образы для аренды:**
• Ubuntu 22.04 - "арендуй с ubuntu"
• Ubuntu + Jupyter - "арендуй с jupyter"
• PyTorch - "арендуй с pytorch"

**Фильтры поиска:**
• GPU модель: 4090, 3090, 3080, etc.
• Цена: "дешевле $X"
• Количество GPU: "4 карты"
• PCIe: "PCIe x16"
• Рейтинг: "рейтинг выше X"
• Страна: США, Канада, Германия

Просто опишите, что вам нужно!
"""