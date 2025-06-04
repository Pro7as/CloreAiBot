"""
AI агент для управления Clore.ai через естественный язык
Использует OpenAI Function Calling для стабильной работы
"""
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from loguru import logger
from dataclasses import dataclass
import asyncio

from openai import AsyncOpenAI

from clore_api.client import CloreAPIClient
from config import settings


@dataclass
class ServerInfo:
    """Информация о сервере в упрощенном формате"""
    id: int
    gpu: str
    gpu_count: int
    gpu_ram: int
    ram_gb: float
    cpu: str
    price_per_day: float
    price_per_hour: float
    rating: float
    location: str
    available: bool


class CloreAIAgent:
    """AI агент для управления Clore.ai через естественный язык"""
    
    def __init__(self, api_key: str):
        self.clore_client = CloreAPIClient(api_key)
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.conversations = {}  # user_id -> messages history
        self.search_cache = {}   # Кэш результатов поиска
        self.cache_ttl = 300     # 5 минут
        
        # Системный промпт
        self.system_prompt = f"""Ты - умный помощник для работы с платформой Clore.ai для аренды GPU серверов.
Отвечай на русском языке, используй эмодзи для лучшей читаемости.

Твои возможности:
- Поиск серверов по различным параметрам (GPU, цена, RAM, локация)
- Анализ и статистика по доступным серверам
- Помощь в выборе оптимального сервера для задач пользователя
- Информация о балансе и кошельках
- Показ активных аренд
- Создание заказов на аренду серверов
- Отмена заказов

Текущий курс: 1 CLORE = ${settings.clore_to_usd}

Важные правила:
1. Всегда используй актуальные данные через функции
2. Указывай ID серверов для возможности быстрой аренды
3. Показывай цены в USD за сутки
4. При выборе из нескольких вариантов показывай топ-5
5. Для аренды сервера:
   - Если пользователь просит "арендовать" или "снять" сервер - используй prepare_order для показа деталей
   - Если пользователь подтверждает ("да", "подтверждаю", "арендуй") после prepare_order - используй create_order
   - Если пользователь настойчиво просит арендовать конкретный сервер - сразу используй create_order
6. Будь дружелюбным и помогай пользователю сделать лучший выбор
7. Используй форматирование Markdown для красивого вывода"""
        
        # Определение функций для OpenAI
        self.functions = [
            {
                "name": "search_servers",
                "description": "Поиск серверов по параметрам (как доступных, так и арендованных)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "gpu_model": {
                            "type": "string",
                            "description": "Модель GPU (например: 4090, 3090, A100)"
                        },
                        "cpu_model": {
                            "type": "string", 
                            "description": "Модель CPU или ключевое слово (например: EPYC, Xeon, Ryzen)"
                        },
                        "max_price": {
                            "type": "number",
                            "description": "Максимальная цена в USD за сутки"
                        },
                        "min_gpu_count": {
                            "type": "integer",
                            "description": "Минимальное количество GPU"
                        },
                        "min_ram": {
                            "type": "integer",
                            "description": "Минимальный объем RAM в GB"
                        },
                        "location": {
                            "type": "string",
                            "description": "Код страны (например: US, DE, CA)"
                        },
                        "min_rating": {
                            "type": "number",
                            "description": "Минимальный рейтинг (0-5)"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["available", "rented", "all"],
                            "description": "Статус серверов: available - только доступные, rented - только арендованные, all - все",
                            "default": "available"
                        }
                    }
                }
            },
            {
                "name": "get_server_analytics",
                "description": "Получить аналитику по серверам (количество, цены, статистика)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": ["count", "avg_price", "min_price", "max_price", "gpu_distribution", "all"],
                            "description": "Тип метрики"
                        },
                        "gpu_model": {
                            "type": "string",
                            "description": "Модель GPU для фильтрации (опционально)"
                        }
                    },
                    "required": ["metric"]
                }
            },
            {
                "name": "get_balance",
                "description": "Получить баланс кошельков пользователя",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_my_orders",
                "description": "Получить список активных аренд пользователя",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_completed": {
                            "type": "boolean",
                            "description": "Включить завершенные заказы",
                            "default": False
                        }
                    }
                }
            },
            {
                "name": "get_server_details",
                "description": "Получить подробную информацию о конкретном сервере",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server_id": {
                            "type": "integer",
                            "description": "ID сервера"
                        }
                    },
                    "required": ["server_id"]
                }
            },
            {
                "name": "prepare_order",
                "description": "Подготовить и показать детали заказа на аренду сервера для подтверждения пользователем. Используй когда пользователь ВПЕРВЫЕ просит арендовать сервер.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server_id": {
                            "type": "integer",
                            "description": "ID сервера для аренды"
                        },
                        "docker_image": {
                            "type": "string",
                            "description": "Docker образ (ubuntu, jupyter, pytorch)",
                            "default": "jupyter"
                        }
                    },
                    "required": ["server_id"]
                }
            },
            {
                "name": "create_order",
                "description": "Создать реальный заказ на аренду сервера. Используй когда: 1) пользователь подтверждает после prepare_order, 2) пользователь ПОВТОРНО или НАСТОЙЧИВО просит арендовать, 3) в запросе есть слова 'создай заказ'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server_id": {
                            "type": "integer",
                            "description": "ID сервера для аренды"
                        },
                        "docker_image": {
                            "type": "string",
                            "description": "Docker образ: ubuntu, jupyter, pytorch, tensorflow",
                            "default": "jupyter"
                        },
                        "ssh_password": {
                            "type": "string",
                            "description": "SSH пароль (по умолчанию clore123)",
                            "default": "clore123"
                        },
                        "jupyter_token": {
                            "type": "string", 
                            "description": "Jupyter токен (по умолчанию clore123)",
                            "default": "clore123"
                        }
                    },
                    "required": ["server_id"]
                }
            },
            {
                "name": "cancel_order",
                "description": "Отменить активный заказ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "integer",
                            "description": "ID заказа для отмены"
                        }
                    },
                    "required": ["order_id"]
                }
            },
            {
                "name": "get_usage_statistics",
                "description": "Получить статистику использования и расходов",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "period_days": {
                            "type": "integer",
                            "description": "Период в днях (по умолчанию 30)",
                            "default": 30
                        }
                    }
                }
            }
        ]
    
    async def close(self):
        """Закрыть соединения"""
        await self.clore_client.close()
    
    def get_conversation(self, user_id: int) -> List[Dict]:
        """Получить историю разговора"""
        if user_id not in self.conversations:
            self.conversations[user_id] = [
                {"role": "system", "content": self.system_prompt}
            ]
        return self.conversations[user_id]
    
    def add_message(self, user_id: int, role: str, content: str):
        """Добавить сообщение в историю"""
        messages = self.get_conversation(user_id)
        messages.append({"role": role, "content": content})
        
        # Ограничиваем историю последними 20 сообщениями + системный промпт
        if len(messages) > 21:
            self.conversations[user_id] = [messages[0]] + messages[-20:]
    
    async def execute_function(self, function_name: str, arguments: Dict) -> Any:
        """Выполнить функцию и вернуть результат"""
        try:
            if function_name == "search_servers":
                # Проверяем кэш
                cache_key = f"search_{json.dumps(arguments, sort_keys=True)}"
                if cache_key in self.search_cache:
                    cached_time, cached_result = self.search_cache[cache_key]
                    if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                        logger.info("Используем кэшированный результат поиска")
                        return cached_result
                
                # Получаем маркетплейс
                marketplace_data = await self.clore_client.get_marketplace()
                servers = marketplace_data.get('servers', [])
                
                # Фильтруем серверы
                filtered_servers = []
                for server in servers:
                    # Фильтр по статусу
                    status_filter = arguments.get("status", "available")
                    if status_filter == "available" and server.get('rented'):
                        continue
                    elif status_filter == "rented" and not server.get('rented'):
                        continue
                    # status == "all" - показываем все
                    
                    specs = server.get('specs', {})
                    
                    # Фильтр по GPU модели
                    if arguments.get("gpu_model"):
                        gpu_str = specs.get('gpu', '')
                        if arguments["gpu_model"].upper() not in gpu_str.upper():
                            continue
                    
                    # Фильтр по CPU модели
                    if arguments.get("cpu_model"):
                        cpu_str = specs.get('cpu', '')
                        if arguments["cpu_model"].upper() not in cpu_str.upper():
                            continue
                    
                    # Фильтр по цене (только для доступных)
                    if not server.get('rented'):
                        price, _ = self.clore_client.extract_server_price(server)
                        if price is None:
                            continue
                        if arguments.get("max_price") and price > arguments["max_price"]:
                            continue
                    else:
                        # Для арендованных серверов цена может быть недоступна
                        price = None
                    
                    # Фильтр по количеству GPU
                    gpu_count, gpu_model = self.clore_client.extract_gpu_info(specs.get('gpu', ''))
                    if arguments.get("min_gpu_count") and gpu_count < arguments["min_gpu_count"]:
                        continue
                    
                    # Фильтр по RAM
                    ram = specs.get('ram', 0)
                    if arguments.get("min_ram") and ram < arguments["min_ram"]:
                        continue
                    
                    # Фильтр по локации
                    if arguments.get("location"):
                        location = specs.get('net', {}).get('cc', '')
                        if location != arguments["location"].upper():
                            continue
                    
                    # Фильтр по рейтингу (только для доступных)
                    if not server.get('rented') and arguments.get("min_rating"):
                        rating = server.get('rating', {}).get('avg', 0)
                        if rating < arguments["min_rating"]:
                            continue
                    
                    # Добавляем в результаты
                    server_info = {
                        "id": server.get('id'),
                        "gpu": specs.get('gpu', 'Unknown'),
                        "gpu_count": gpu_count,
                        "gpu_ram": specs.get('gpuram', 0),
                        "cpu": specs.get('cpu', 'Unknown')[:100],  # Увеличил лимит для CPU
                        "ram": round(ram, 1),
                        "location": specs.get('net', {}).get('cc', 'Unknown'),
                        "status": "rented" if server.get('rented') else "available"
                    }
                    
                    # Добавляем цену и рейтинг только для доступных
                    if not server.get('rented'):
                        server_info["price_per_day"] = round(price, 2) if price else 0
                        server_info["price_per_hour"] = round(price / 24, 3) if price else 0
                        server_info["rating"] = round(server.get('rating', {}).get('avg', 0), 1)
                        server_info["reliability"] = round(server.get('reliability', 0) * 100, 1)
                    
                    filtered_servers.append(server_info)
                
                # Сортируем по цене (только доступные) или по ID
                if arguments.get("status", "available") == "available":
                    filtered_servers.sort(key=lambda x: x.get('price_per_day', float('inf')))
                else:
                    filtered_servers.sort(key=lambda x: x['id'])
                
                # Ограничиваем до 20 результатов
                result = filtered_servers[:20]
                
                # Кэшируем результат
                self.search_cache[cache_key] = (datetime.now(), result)
                
                return result
            
            elif function_name == "get_server_analytics":
                marketplace_data = await self.clore_client.get_marketplace()
                servers = marketplace_data.get('servers', [])
                
                # Фильтруем по GPU если указано
                if arguments.get("gpu_model"):
                    gpu_filter = arguments["gpu_model"].upper()
                    servers = [s for s in servers 
                             if gpu_filter in s.get('specs', {}).get('gpu', '').upper()]
                
                # Разделяем на доступные и арендованные
                available_servers = [s for s in servers if not s.get('rented')]
                rented_servers = [s for s in servers if s.get('rented')]
                
                metric = arguments["metric"]
                analytics = {}
                
                if metric in ["count", "all"]:
                    analytics["total_servers"] = len(servers)
                    analytics["available_servers"] = len(available_servers)
                    analytics["rented_servers"] = len(rented_servers)
                    analytics["rental_rate"] = f"{(len(rented_servers) / len(servers) * 100):.1f}%" if servers else "0%"
                
                if metric in ["avg_price", "all"] and available_servers:
                    prices = []
                    for server in available_servers:
                        price, _ = self.clore_client.extract_server_price(server)
                        if price:
                            prices.append(price)
                    
                    if prices:
                        analytics["avg_price"] = round(sum(prices) / len(prices), 2)
                
                if metric in ["min_price", "all"] and available_servers:
                    min_price = float('inf')
                    min_server = None
                    
                    for server in available_servers:
                        price, _ = self.clore_client.extract_server_price(server)
                        if price and price < min_price:
                            min_price = price
                            min_server = server
                    
                    if min_server:
                        analytics["min_price"] = {
                            "price": round(min_price, 2),
                            "server_id": min_server.get('id'),
                            "gpu": min_server.get('specs', {}).get('gpu', 'Unknown')
                        }
                
                if metric in ["gpu_distribution", "all"]:
                    gpu_counts = {"available": {}, "rented": {}}
                    
                    for server in servers:
                        gpu = server.get('specs', {}).get('gpu', 'Unknown')
                        status = "rented" if server.get('rented') else "available"
                        
                        # Извлекаем модель GPU
                        for model in ['4090', '3090', '3080', '3070', '3060', 'A100', 'H100', 'A6000', 'P106']:
                            if model in gpu:
                                gpu_counts[status][model] = gpu_counts[status].get(model, 0) + 1
                                break
                    
                    analytics["gpu_distribution"] = gpu_counts
                
                # Добавляем статистику по CPU если запрашивается
                if metric == "all":
                    cpu_stats = {"epyc_count": 0, "xeon_count": 0, "ryzen_count": 0, "other_count": 0}
                    
                    for server in servers:
                        cpu = server.get('specs', {}).get('cpu', '').upper()
                        if 'EPYC' in cpu:
                            cpu_stats["epyc_count"] += 1
                        elif 'XEON' in cpu:
                            cpu_stats["xeon_count"] += 1
                        elif 'RYZEN' in cpu:
                            cpu_stats["ryzen_count"] += 1
                        else:
                            cpu_stats["other_count"] += 1
                    
                    analytics["cpu_distribution"] = cpu_stats
                
                return analytics
            
            elif function_name == "get_balance":
                wallets_data = await self.clore_client.get_wallets()
                wallets = wallets_data.get('wallets', [])
                
                balance_info = []
                total_usd = 0
                
                for wallet in wallets:
                    name = wallet.get('name', 'Unknown')
                    balance = wallet.get('balance', 0)
                    
                    if name == 'bitcoin':
                        usd_value = balance * settings.btc_to_usd
                        balance_info.append({
                            "currency": "BTC",
                            "balance": balance,
                            "usd_value": round(usd_value, 2)
                        })
                        total_usd += usd_value
                    elif name == 'CLORE-Blockchain':
                        usd_value = balance * settings.clore_to_usd
                        balance_info.append({
                            "currency": "CLORE",
                            "balance": round(balance, 2),
                            "usd_value": round(usd_value, 2)
                        })
                        total_usd += usd_value
                
                return {
                    "wallets": balance_info,
                    "total_usd": round(total_usd, 2)
                }
            
            elif function_name == "get_my_orders":
                include_completed = arguments.get("include_completed", False)
                orders_data = await self.clore_client.get_my_orders(return_completed=include_completed)
                orders = orders_data.get('orders', [])
                
                orders_info = []
                total_cost_per_day = 0
                
                for order in orders:
                    # Только активные если не запрошено иное
                    if not include_completed and order.get('expired'):
                        continue
                    
                    order_id = order.get('id')
                    server_id = order.get('si')
                    gpu = order.get('specs', {}).get('gpu', 'Unknown')
                    
                    # Цена
                    price = order.get('price', 0)
                    currency = order.get('currency', 'unknown')
                    if currency == 'CLORE-Blockchain':
                        price_usd = price * settings.clore_to_usd
                    else:
                        price_usd = 0
                    
                    if not order.get('expired'):
                        total_cost_per_day += price_usd
                    
                    # Время работы
                    created_at = order.get('ct', 0)
                    runtime_hours = 0
                    if created_at:
                        runtime_hours = (datetime.now().timestamp() - created_at) / 3600
                    
                    orders_info.append({
                        "order_id": order_id,
                        "server_id": server_id,
                        "gpu": gpu,
                        "price_per_day": round(price_usd, 2),
                        "runtime_hours": round(runtime_hours, 1),
                        "status": "expired" if order.get('expired') else "active",
                        "image": order.get('image', 'Unknown')
                    })
                
                return {
                    "orders": orders_info,
                    "total_cost_per_day": round(total_cost_per_day, 2),
                    "active_count": len([o for o in orders_info if o['status'] == 'active'])
                }
            
            elif function_name == "get_server_details":
                server_id = arguments["server_id"]
                
                marketplace_data = await self.clore_client.get_marketplace()
                servers = marketplace_data.get('servers', [])
                
                server = None
                for s in servers:
                    if s.get('id') == server_id:
                        server = s
                        break
                
                if not server:
                    return {"error": f"Сервер #{server_id} не найден"}
                
                # Форматируем подробную информацию
                return {
                    "id": server_id,
                    "full_info": self.clore_client.format_server_full(server),
                    "available": not server.get('rented')
                }
            
            elif function_name == "prepare_order":
                server_id = arguments["server_id"]
                docker_image = arguments.get("docker_image", "jupyter")
                
                # Проверяем доступность сервера
                marketplace_data = await self.clore_client.get_marketplace()
                server = None
                for s in marketplace_data.get('servers', []):
                    if s.get('id') == server_id:
                        server = s
                        break
                
                if not server:
                    return {"error": f"Сервер #{server_id} не найден"}
                
                if server.get('rented'):
                    return {"error": f"Сервер #{server_id} уже арендован"}
                
                # Определяем образ
                image_map = {
                    "ubuntu": "cloreai/ubuntu:22.04",
                    "jupyter": "cloreai/jupyter:ubuntu24.04-v2",
                    "pytorch": "pytorch/pytorch:latest",
                    "tensorflow": "tensorflow/tensorflow:latest-gpu"
                }
                
                image = image_map.get(docker_image.lower(), "cloreai/jupyter:ubuntu24.04-v2")
                
                # Возвращаем информацию для подтверждения
                price, _ = self.clore_client.extract_server_price(server)
                
                return {
                    "status": "requires_confirmation",
                    "server_id": server_id,
                    "gpu": server.get('specs', {}).get('gpu', 'Unknown'),
                    "price_per_day": round(price, 2) if price else 0,
                    "docker_image": image,
                    "message": f"Готов к аренде сервера #{server_id}"
                }
            
            elif function_name == "create_order":
                server_id = arguments["server_id"]
                docker_image = arguments.get("docker_image", "jupyter")
                ssh_password = arguments.get("ssh_password", "clore123")
                jupyter_token = arguments.get("jupyter_token", "clore123")
                
                # Проверяем доступность сервера
                marketplace_data = await self.clore_client.get_marketplace()
                server = None
                for s in marketplace_data.get('servers', []):
                    if s.get('id') == server_id:
                        server = s
                        break
                
                if not server:
                    return {"error": f"Сервер #{server_id} не найден"}
                
                if server.get('rented'):
                    return {"error": f"Сервер #{server_id} уже арендован"}
                
                # Определяем образ
                image_map = {
                    "ubuntu": "cloreai/ubuntu:22.04",
                    "jupyter": "cloreai/jupyter:ubuntu24.04-v2",
                    "pytorch": "pytorch/pytorch:latest",
                    "tensorflow": "tensorflow/tensorflow:latest-gpu"
                }
                
                image = image_map.get(docker_image.lower(), "cloreai/jupyter:ubuntu24.04-v2")
                
                try:
                    # Создаем реальный заказ
                    result = await self.clore_client.create_order(
                        currency="CLORE-Blockchain",
                        image=image,
                        renting_server=server_id,
                        order_type="on-demand",
                        ports={"22": "tcp", "8888": "http"},
                        jupyter_token=jupyter_token,
                        ssh_password=ssh_password,
                        command="#!/bin/sh\napt update -y",
                        autossh_entrypoint=True
                    )
                    
                    if result.get('code') == 0:
                        # Получаем информацию о созданном заказе
                        await asyncio.sleep(2)  # Небольшая задержка
                        orders_data = await self.clore_client.get_my_orders()
                        
                        # Находим наш заказ
                        created_order = None
                        for order in orders_data.get('orders', []):
                            if order.get('si') == server_id and not order.get('expired'):
                                created_order = order
                                break
                        
                        if created_order:
                            return {
                                "status": "success",
                                "order_id": created_order.get('id'),
                                "server_id": server_id,
                                "gpu": server.get('specs', {}).get('gpu', 'Unknown'),
                                "price_per_day": created_order.get('price', 0) * settings.clore_to_usd,
                                "ssh_password": ssh_password,
                                "jupyter_token": jupyter_token,
                                "pub_cluster": created_order.get('pub_cluster', []),
                                "tcp_ports": created_order.get('tcp_ports', []),
                                "http_port": created_order.get('http_port'),
                                "message": f"Заказ #{created_order.get('id')} успешно создан!"
                            }
                        else:
                            return {
                                "status": "success",
                                "server_id": server_id,
                                "message": "Заказ создан, проверьте детали командой 'мои аренды'"
                            }
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        return {"error": f"Ошибка создания заказа: {error_msg}"}
                        
                except Exception as e:
                    logger.error(f"Error creating order: {e}")
                    return {"error": f"Ошибка при создании заказа: {str(e)}"}
            
            elif function_name == "cancel_order":
                order_id = arguments["order_id"]
                
                try:
                    result = await self.clore_client.cancel_order(order_id)
                    return {"status": "success", "message": f"Заказ #{order_id} успешно отменен"}
                except Exception as e:
                    return {"error": f"Не удалось отменить заказ: {str(e)}"}
            
            elif function_name == "get_usage_statistics":
                period_days = arguments.get("period_days", 30)
                
                # Получаем все заказы
                orders_data = await self.clore_client.get_my_orders(return_completed=True)
                all_orders = orders_data.get('orders', [])
                
                # Фильтруем по периоду
                cutoff_time = datetime.now().timestamp() - (period_days * 24 * 3600)
                period_orders = [o for o in all_orders if o.get('ct', 0) > cutoff_time]
                
                # Считаем статистику
                total_spent = 0
                gpu_usage = {}
                total_hours = 0
                
                for order in period_orders:
                    # Расходы
                    spent = order.get('spend', 0)
                    currency = order.get('currency', '')
                    if currency == 'CLORE-Blockchain':
                        total_spent += spent * settings.clore_to_usd
                    
                    # GPU использование
                    gpu = order.get('specs', {}).get('gpu', 'Unknown')
                    gpu_usage[gpu] = gpu_usage.get(gpu, 0) + 1
                    
                    # Время использования
                    created_at = order.get('ct', 0)
                    if created_at:
                        if order.get('expired'):
                            # Для завершенных считаем полное время
                            runtime = order.get('runtime', 0)
                        else:
                            # Для активных считаем от создания
                            runtime = datetime.now().timestamp() - created_at
                        total_hours += runtime / 3600
                
                return {
                    "period_days": period_days,
                    "total_orders": len(period_orders),
                    "active_orders": len([o for o in period_orders if not o.get('expired')]),
                    "total_spent_usd": round(total_spent, 2),
                    "total_hours": round(total_hours, 1),
                    "avg_cost_per_day": round(total_spent / max(total_hours / 24, 1), 2),
                    "popular_gpus": dict(sorted(gpu_usage.items(), key=lambda x: x[1], reverse=True)[:5])
                }
            
            else:
                return {"error": f"Неизвестная функция: {function_name}"}
                
        except Exception as e:
            logger.error(f"Ошибка выполнения функции {function_name}: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def process_query(self, query: str, user_context: Dict[str, Any] = None) -> str:
        """Обработать запрос пользователя"""
        user_id = user_context.get('user_id', 0) if user_context else 0
        
        # Проверяем простые приветствия
        query_lower = query.lower()
        greetings = ['привет', 'здравствуй', 'добрый день', 'добрый вечер', 'доброе утро', 'hi', 'hello']
        if any(greeting in query_lower for greeting in greetings):
            response = """Привет! 👋 Я ваш AI-помощник для работы с Clore.ai.

Я могу помочь вам:
🔍 Найти GPU серверы по любым параметрам
💰 Проверить баланс и расходы
📦 Управлять арендами
📊 Анализировать рынок серверов

Просто опишите, что вам нужно! Например:
• "Найди дешевые серверы с RTX 3090"
• "Покажи мой баланс"
• "Какая средняя цена на A100?"
"""
            self.add_message(user_id, "user", query)
            self.add_message(user_id, "assistant", response)
            return response
        
        # Проверяем команды аренды
        rent_words = ['арендуй', 'арендовать', 'сними', 'снять', 'возьми', 'хочу арендовать']
        confirm_words = ['да', 'подтверждаю', 'согласен', 'ок', 'ok', 'yes', 'конечно']
        
        # Проверяем, есть ли в запросе ID сервера
        server_id_match = re.search(r'\b(\d{4,})\b', query)
        
        # Если есть слова аренды и ID сервера - сразу создаем заказ
        if any(word in query_lower for word in rent_words) and server_id_match:
            # Проверяем контекст - если последнее сообщение было prepare_order
            messages = self.get_conversation(user_id)
            last_assistant_msg = None
            for msg in reversed(messages):
                if msg['role'] == 'assistant':
                    last_assistant_msg = msg['content']
                    break
            
            # Если это повторный запрос после подготовки - сразу арендуем
            if last_assistant_msg and 'готов к аренде' in last_assistant_msg.lower():
                # Меняем запрос для прямого создания заказа
                query = f"создай заказ на сервер {server_id_match.group(1)}"
        
        # Добавляем сообщение пользователя
        self.add_message(user_id, "user", query)
        
        try:
            # Получаем ответ от GPT с возможностью вызова функций
            messages = self.get_conversation(user_id)
            
            response = await self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                functions=self.functions,
                function_call="auto",
                temperature=0.7,
                max_tokens=800
            )
            
            message_response = response.choices[0].message
            
            # Если GPT хочет вызвать функцию
            if hasattr(message_response, 'function_call') and message_response.function_call:
                function_name = message_response.function_call.name
                function_args = json.loads(message_response.function_call.arguments)
                
                logger.info(f"Вызов функции: {function_name} с аргументами: {function_args}")
                
                # Выполняем функцию
                function_result = await self.execute_function(function_name, function_args)
                
                # Добавляем результат функции в контекст
                if message_response.content:
                    self.add_message(user_id, "assistant", message_response.content)
                
                # Добавляем результат функции как отдельное сообщение
                messages = self.get_conversation(user_id)
                messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps(function_result, ensure_ascii=False)
                })
                
                # Получаем финальный ответ от GPT
                messages = self.get_conversation(user_id)
                final_response = await self.openai_client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=800
                )
                
                final_message = final_response.choices[0].message.content
                self.add_message(user_id, "assistant", final_message)
                
                return final_message
            
            else:
                # Простой ответ без вызова функций
                assistant_message = message_response.content
                self.add_message(user_id, "assistant", assistant_message)
                return assistant_message
                
        except Exception as e:
            logger.error(f"Ошибка обработки запроса: {e}", exc_info=True)
            logger.error(f"Query: {query}")
            logger.error(f"User context: {user_context}")
            return "❌ Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз."
    
    def clear_conversation(self, user_id: int):
        """Очистить историю разговора"""
        if user_id in self.conversations:
            self.conversations[user_id] = [
                {"role": "system", "content": self.system_prompt}
            ]
    
    def get_usage_stats(self) -> Dict:
        """Получить статистику использования"""
        return {
            "active_conversations": len(self.conversations),
            "cached_searches": len(self.search_cache),
            "total_messages": sum(len(msgs) for msgs in self.conversations.values())
        }
