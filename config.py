"""
Конфигурация приложения Clore Bot Pro
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Основные настройки приложения"""
    
    # Bot settings
    bot_token: str
    bot_username: str = "clore_pro_bot"
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./clore_bot.db"
    
    # Clore API
    clore_api_base_url: str = "https://api.clore.ai/v1"
    
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4-turbo-preview"
    
    # Admin
    admin_ids: str = ""  # Строка с ID через запятую
    
    # Premium features
    enable_premium_check: bool = False
    
    # Exchange rates
    clore_to_usd: float = 0.02  # 1 CLORE = $0.02
    btc_to_usd: float = 100000.0
    
    # Monitoring
    balance_check_interval: int = 600  # 10 минут в секундах
    server_check_interval: int = 300   # 5 минут
    
    # Pagination
    servers_per_page: int = 10
    orders_per_page: int = 10
    
    # Limits
    max_gpu_per_order: int = 10
    max_active_orders: int = 50
    
    # Features
    enable_spot_market: bool = True
    enable_server_hunt: bool = True
    enable_sound_alerts: bool = True
    
    # Paths
    log_path: Path = Path("logs")
    data_path: Path = Path("data")
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Создаем необходимые директории
        self.log_path.mkdir(exist_ok=True)
        self.data_path.mkdir(exist_ok=True)
    
    @property
    def admin_id_list(self) -> list[int]:
        """Получить список admin ID из строки"""
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(',') if x.strip().isdigit()]

# Глобальный экземпляр настроек
settings = Settings()
