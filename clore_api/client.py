"""
Клиент для работы с Clore API
"""
import httpx
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import orjson
from loguru import logger

from config import settings


class CloreAPIError(Exception):
    """Базовое исключение для ошибок Clore API"""
    def __init__(self, code: int, message: str, response: Dict[str, Any] = None):
        self.code = code
        self.message = message
        self.response = response
        super().__init__(f"Clore API Error [{code}]: {message}")


class CloreAPIClient:
    """Асинхронный клиент для Clore API"""
    
    ERROR_CODES = {
        0: "NORMAL",
        1: "DATABASE ERROR",
        2: "INVALID INPUT DATA",
        3: "INVALID API TOKEN",
        4: "INVALID ENDPOINT",
        5: "EXCEEDED 1 request/second limit",
        6: "Error specified in error field"
    }
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = settings.clore_api_base_url
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"auth": api_key}
        )
        self._last_request_time = None
        self._request_delay = 1.1  # 1.1 секунды между запросами
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Закрыть HTTP клиент"""
        await self.client.aclose()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Выполнить запрос к API с учетом rate limiting"""
        # Соблюдаем rate limit
        if self._last_request_time:
            time_since_last = datetime.now() - self._last_request_time
            if time_since_last < timedelta(seconds=self._request_delay):
                wait_time = self._request_delay - time_since_last.total_seconds()
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            self._last_request_time = datetime.now()
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            
            data = orjson.loads(response.content)
            
            # Проверяем код ответа
            code = data.get("code", -1)
            if code != 0:
                error_msg = self.ERROR_CODES.get(code, "Unknown error")
                if code == 6:
                    error_msg = data.get("error", error_msg)
                raise CloreAPIError(code, error_msg, data)
            
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            raise CloreAPIError(-1, f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            logger.error(f"Request error: {e}")
            raise CloreAPIError(-1, str(e))
    
    # === Endpoints ===
    
    async def get_wallets(self) -> Dict[str, Any]:
        """Получить балансы кошельков"""
        return await self._make_request("GET", "wallets")
    
    async def get_my_servers(self) -> Dict[str, Any]:
        """Получить список моих серверов"""
        return await self._make_request("GET", "my_servers")
    
    async def get_server_config(self, server_name: str) -> Dict[str, Any]:
        """Получить конфигурацию сервера"""
        return await self._make_request(
            "GET", 
            "server_config",
            json={"server_name": server_name}
        )
    
    async def get_marketplace(self) -> Dict[str, Any]:
        """Получить список доступных серверов"""
        return await self._make_request("GET", "marketplace")
    
    async def get_my_orders(self, return_completed: bool = False) -> Dict[str, Any]:
        """Получить мои ордера"""
        params = {"return_completed": str(return_completed).lower()}
        return await self._make_request("GET", "my_orders", params=params)
    
    async def get_spot_marketplace(self, server_id: int) -> Dict[str, Any]:
        """Получить спот маркет для сервера"""
        params = {"market": server_id}
        return await self._make_request("GET", "spot_marketplace", params=params)
    
    async def set_server_settings(
        self,
        name: str,
        availability: bool,
        mrl: int,
        on_demand: float,
        spot: float,
        clore_on_demand: float,
        clore_spot: float
    ) -> Dict[str, Any]:
        """Настроить параметры сервера"""
        data = {
            "name": name,
            "availability": availability,
            "mrl": mrl,
            "on_demand": on_demand,
            "spot": spot,
            "CLORE-Blockchain_on_demand": clore_on_demand,
            "CLORE-Blockchain_spot": clore_spot
        }
        return await self._make_request("POST", "set_server_settings", json=data)
    
    async def set_spot_price(self, order_id: int, desired_price: float) -> Dict[str, Any]:
        """Изменить цену спот предложения"""
        data = {
            "order_id": order_id,
            "desired_price": desired_price
        }
        return await self._make_request("POST", "set_spot_price", json=data)
    
    async def cancel_order(self, order_id: int, issue: Optional[str] = None) -> Dict[str, Any]:
        """Отменить ордер"""
        data = {"id": order_id}
        if issue:
            data["issue"] = issue[:2048]  # Максимум 2048 символов
        return await self._make_request("POST", "cancel_order", json=data)
    
    async def create_order(
        self,
        currency: str,
        image: str,
        renting_server: int,
        order_type: str,  # "on-demand" или "spot"
        spotprice: Optional[float] = None,
        ports: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
        jupyter_token: Optional[str] = None,
        ssh_password: Optional[str] = None,
        ssh_key: Optional[str] = None,
        command: Optional[str] = None,
        required_price: Optional[float] = None,
        autossh_entrypoint: bool = False
    ) -> Dict[str, Any]:
        """Создать ордер на аренду сервера"""
        data = {
            "currency": currency,
            "image": image,
            "renting_server": renting_server,
            "type": order_type
        }
        
        # Опциональные параметры
        if order_type == "spot" and spotprice is not None:
            data["spotprice"] = spotprice
        if ports:
            data["ports"] = ports
        if env:
            data["env"] = env
        if jupyter_token:
            data["jupyter_token"] = jupyter_token[:32]
        if ssh_password:
            data["ssh_password"] = ssh_password[:32]
        if ssh_key:
            data["ssh_key"] = ssh_key[:3072]
        if command:
            data["command"] = command
        if required_price is not None:
            data["required_price"] = required_price
        if autossh_entrypoint:
            data["autossh_entrypoint"] = autossh_entrypoint
        
        return await self._make_request("POST", "create_order", json=data)
    
    async def get_poh_balance(self) -> Dict[str, Any]:
        """Получить информацию о PoH балансе"""
        return await self._make_request("GET", "poh_balance")
    
    # === Вспомогательные методы ===
    
    def extract_server_price(self, server_data: Dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
        """
        Извлечь актуальную цену сервера
        Returns: (price, currency_type)
        """
        price_data = server_data.get('price', {})
        
        # Приоритет 1: Цена в USD (конвертированная)
        usd_price = price_data.get('usd', {}).get('on_demand_clore')
        if usd_price is not None:
            return usd_price, 'USD'
        
        # Приоритет 2: Фиксированная цена в CLORE
        clore_price = price_data.get('on_demand', {}).get('CLORE-Blockchain')
        if clore_price is not None:
            # Конвертируем в USD используя курс
            usd_equivalent = clore_price * settings.clore_to_usd
            return usd_equivalent, 'CLORE_FIXED'
        
        return None, None
    
    def extract_gpu_info(self, gpu_string: str) -> tuple[int, str]:
        """
        Извлечь количество и модель GPU из строки
        Example: "4x NVIDIA GeForce RTX 3070" -> (4, "RTX 3070")
        """
        parts = gpu_string.split('x ', 1)
        if len(parts) == 2:
            count = int(parts[0])
            model = parts[1].replace('NVIDIA GeForce ', '').replace('NVIDIA ', '')
            return count, model
        return 1, gpu_string
    
    def format_server_short(self, server_data: Dict[str, Any]) -> str:
        """Форматировать краткую информацию о сервере"""
        server_id = server_data.get('id', 'N/A')
        specs = server_data.get('specs', {})
        
        # GPU
        gpu_str = specs.get('gpu', 'No GPU')
        gpu_count, gpu_model = self.extract_gpu_info(gpu_str)
        gpu_ram = specs.get('gpuram', 0)
        
        # CPU
        cpu = specs.get('cpu', 'Unknown CPU')
        if len(cpu) > 30:
            cpu = cpu[:27] + '...'
        
        # Цена
        price, price_type = self.extract_server_price(server_data)
        if price:
            price_str = f"${price:.2f}/day"
            if price_type == 'CLORE_FIXED':
                price_str += " (fixed)"
        else:
            price_str = "Price N/A"
        
        # PCIe и Power
        pcie = specs.get('pcie_width', 'N/A')
        power_limits = server_data.get('specs', {}).get('stock_pl', [])
        avg_power = sum(power_limits) / len(power_limits) if power_limits else 0
        
        # Рейтинг
        rating_data = server_data.get('rating', {})
        rating = rating_data.get('avg', 0)
        rating_count = rating_data.get('cnt', 0)
        
        return (
            f"🖥️ Server #{server_id}\n"
            f"├ GPU: {gpu_count}x {gpu_model} ({gpu_ram}GB, PCIe x{pcie})\n"
            f"├ CPU: {cpu}\n"
            f"├ Price: {price_str}\n"
            f"├ Power: {avg_power:.0f}W x{gpu_count}\n"
            f"└ Rating: ⭐ {rating:.1f} ({rating_count} reviews)"
        )
    
    def format_server_full(self, server_data: Dict[str, Any]) -> str:
        """Форматировать полную информацию о сервере"""
        server_id = server_data.get('id', 'N/A')
        specs = server_data.get('specs', {})
        
        # Локация
        country = specs.get('net', {}).get('cc', 'Unknown')
        
        # GPU
        gpu_str = specs.get('gpu', 'No GPU')
        gpu_ram = specs.get('gpuram', 0)
        
        # CPU
        cpu = specs.get('cpu', 'Unknown CPU')
        cpus = specs.get('cpus', 'N/A')
        
        # RAM и диск
        ram = specs.get('ram', 0)
        disk = specs.get('disk', 'N/A')
        disk_speed = specs.get('disk_speed', 0)
        
        # Сеть
        net_down = specs.get('net', {}).get('down', 0)
        net_up = specs.get('net', {}).get('up', 0)
        
        # CUDA и PCIe
        cuda = server_data.get('cuda_version', 'N/A')
        pcie_rev = server_data.get('specs', {}).get('pcie_rev', 'N/A')
        pcie_width = specs.get('pcie_width', 'N/A')
        
        # Power
        power_limits = server_data.get('specs', {}).get('stock_pl', [])
        power_str = ', '.join(f"{pl}W" for pl in power_limits) if power_limits else 'N/A'
        
        # Надежность
        reliability = server_data.get('reliability', 0) * 100
        
        # Цена
        price, price_type = self.extract_server_price(server_data)
        price_data = server_data.get('price', {})
        clore_price = price_data.get('on_demand', {}).get('CLORE-Blockchain', 0)
        
        if price:
            if price_type == 'USD':
                price_str = f"{clore_price} CLORE/day (${price:.2f})"
            else:
                price_str = f"{clore_price} CLORE/day (fixed, ~${price:.2f})"
        else:
            price_str = "Price N/A"
        
        # Рейтинг
        rating_data = server_data.get('rating', {})
        rating = rating_data.get('avg', 0)
        rating_count = rating_data.get('cnt', 0)
        
        return (
            f"🖥️ Server #{server_id} ({country} 🌍)\n"
            f"├ GPU: {gpu_str} ({gpu_ram}GB VRAM)\n"
            f"├ CPU: {cpu} ({cpus} threads)\n"
            f"├ RAM: {ram:.1f} GB\n"
            f"├ Disk: {disk} ({disk_speed:.0f} MB/s)\n"
            f"├ Network: ↓{net_down:.0f} ↑{net_up:.0f} Mbps\n"
            f"├ CUDA: {cuda}\n"
            f"├ PCIe: Gen{pcie_rev} x{pcie_width}\n"
            f"├ Power Limit: {power_str}\n"
            f"├ Reliability: {reliability:.2f}%\n"
            f"├ Price: {price_str}\n"
            f"└ Rating: ⭐ {rating:.1f} ({rating_count} reviews)"
        )
