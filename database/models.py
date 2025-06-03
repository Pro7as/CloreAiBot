"""
Модели базы данных для Clore Bot Pro
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    """Пользователи бота"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(64))
    first_name = Column(String(64))
    last_name = Column(String(64))
    
    # API ключи
    clore_api_key = Column(String(256))
    
    # Настройки SSH/Jupyter по умолчанию
    default_ssh_password = Column(String(32))
    default_jupyter_token = Column(String(32))
    
    # Статус и подписка
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime)
    
    # Настройки уведомлений
    alert_sound_enabled = Column(Boolean, default=True)
    alert_balance_threshold = Column(Float)
    alert_rental_expiry_hours = Column(Integer, default=5)
    
    # Статистика
    total_spent = Column(Float, default=0)
    total_orders = Column(Integer, default=0)
    
    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    balance_history = relationship("BalanceHistory", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    server_snapshots = relationship("ServerSnapshot", back_populates="user", cascade="all, delete-orphan")
    docker_templates = relationship("DockerTemplate", back_populates="user", cascade="all, delete-orphan")
    hunt_tasks = relationship("HuntTask", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class BalanceHistory(Base):
    """История изменения баланса"""
    __tablename__ = 'balance_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Балансы
    clore_balance = Column(Float)
    btc_balance = Column(Float)
    usd_equivalent = Column(Float)  # Общий эквивалент в USD
    
    # Изменения
    clore_change_10min = Column(Float)
    clore_change_1hour = Column(Float)
    clore_change_24hour = Column(Float)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Связи
    user = relationship("User", back_populates="balance_history")
    
    __table_args__ = (
        Index('idx_balance_history_user_timestamp', 'user_id', 'timestamp'),
    )


class Order(Base):
    """Ордера (аренды)"""
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # ID из Clore API
    clore_order_id = Column(Integer, unique=True, index=True)
    server_id = Column(Integer, index=True)
    
    # Тип и статус
    order_type = Column(String(16))  # 'on-demand' или 'spot'
    status = Column(String(16))  # 'active', 'expired', 'cancelled'
    
    # Цены
    price_per_day = Column(Float)
    currency = Column(String(16))  # 'CLORE-Blockchain', 'bitcoin'
    total_spent = Column(Float)
    creation_fee = Column(Float)
    
    # Docker конфигурация
    image = Column(String(256))
    ports = Column(JSON)  # {"22": "tcp", "8888": "http"}
    env = Column(JSON)    # {"VAR": "value"}
    command = Column(Text)
    
    # Доступы
    ssh_password = Column(String(32))
    jupyter_token = Column(String(32))
    ssh_key = Column(Text)
    
    # Endpoints
    pub_cluster = Column(JSON)  # ["n1.c1.clorecloud.net"]
    tcp_ports = Column(JSON)    # {"22": "10000"}
    http_port = Column(String(16))
    
    # Время
    created_at = Column(DateTime)
    expires_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # Снимок спецификаций сервера
    server_specs = Column(JSON)
    
    # Связи
    user = relationship("User", back_populates="orders")
    
    __table_args__ = (
        Index('idx_orders_status_expires', 'status', 'expires_at'),
    )


class ServerSnapshot(Base):
    """Снимки состояния серверов"""
    __tablename__ = 'server_snapshots'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Идентификация
    server_id = Column(Integer, index=True)
    snapshot_type = Column(String(16))  # 'marketplace', 'my_server'
    
    # Полный снимок данных
    raw_data = Column(JSON, nullable=False)
    
    # Индексированные поля для быстрого поиска
    gpu_model = Column(String(64), index=True)  # 'RTX 4090', 'RTX 3070'
    gpu_count = Column(Integer)
    gpu_ram = Column(Integer)
    
    cpu_model = Column(String(128))
    ram_gb = Column(Float)
    
    # Цены
    price_clore = Column(Float)
    price_usd = Column(Float)
    price_source = Column(String(16))  # 'fixed' или 'market'
    
    # Состояние
    is_rented = Column(Boolean)
    is_online = Column(Boolean)
    
    # Характеристики
    pcie_width = Column(Integer)
    power_limit = Column(Integer)  # Средний PL для всех GPU
    reliability = Column(Float)
    rating = Column(Float)
    rating_count = Column(Integer)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Связи
    user = relationship("User", back_populates="server_snapshots")
    
    __table_args__ = (
        Index('idx_snapshots_gpu_price', 'gpu_model', 'price_usd'),
        Index('idx_snapshots_timestamp', 'timestamp'),
    )


class DockerTemplate(Base):
    """Шаблоны Docker конфигураций"""
    __tablename__ = 'docker_templates'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))  # NULL = глобальный шаблон
    
    # Информация о шаблоне
    name = Column(String(128), nullable=False)
    description = Column(Text)
    category = Column(String(64))  # 'mining', 'ai', 'rendering', etc.
    is_public = Column(Boolean, default=False)
    
    # Docker конфигурация
    image = Column(String(256), nullable=False)
    ports = Column(JSON)
    env = Column(JSON)
    command = Column(Text)
    
    # Требования
    min_gpu_ram = Column(Integer)
    min_gpu_count = Column(Integer)
    required_gpu_models = Column(JSON)  # ["RTX 4090", "RTX 3090"]
    
    # Статистика использования
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="docker_templates")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='_user_template_name_uc'),
    )


class HuntTask(Base):
    """Задачи охоты на серверы"""
    __tablename__ = 'hunt_tasks'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Параметры поиска
    name = Column(String(128))
    filters = Column(JSON)  # {"gpu_model": "RTX 4090", "max_price_per_gpu": 1.0}
    
    # Настройки
    is_active = Column(Boolean, default=True)
    auto_rent = Column(Boolean, default=False)
    max_servers = Column(Integer, default=1)
    docker_template_id = Column(Integer, ForeignKey('docker_templates.id'))
    
    # Статистика
    servers_found = Column(Integer, default=0)
    servers_rented = Column(Integer, default=0)
    last_found_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="hunt_tasks")
    results = relationship("HuntResult", back_populates="task", cascade="all, delete-orphan")


class HuntResult(Base):
    """Результаты охоты"""
    __tablename__ = 'hunt_results'
    
    id = Column(Integer, primary_key=True)
    hunt_task_id = Column(Integer, ForeignKey('hunt_tasks.id'), nullable=False)
    
    server_id = Column(Integer)
    server_data = Column(JSON)
    
    found_at = Column(DateTime, default=datetime.utcnow)
    rented = Column(Boolean, default=False)
    rent_order_id = Column(Integer)
    
    # Связи
    task = relationship("HuntTask", back_populates="results")


class ExchangeRate(Base):
    """Курсы валют"""
    __tablename__ = 'exchange_rates'
    
    id = Column(Integer, primary_key=True)
    
    currency_from = Column(String(32), nullable=False)  # 'CLORE'
    currency_to = Column(String(32), nullable=False)    # 'USD'
    rate = Column(Float, nullable=False)
    
    source = Column(String(64))  # 'manual', 'coingecko', 'calculated'
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('currency_from', 'currency_to', name='_currency_pair_uc'),
        Index('idx_exchange_rates_updated', 'updated_at'),
    )


class Alert(Base):
    """История уведомлений"""
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    alert_type = Column(String(32))  # 'balance_low', 'server_rented', 'order_expiring'
    title = Column(String(256))
    message = Column(Text)
    
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime)
    error = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)