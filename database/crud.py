"""
CRUD операции для базы данных
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    User, BalanceHistory, Order, ServerSnapshot, 
    DockerTemplate, HuntTask, ExchangeRate, Alert
)


# === Users ===

async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
    """Получить пользователя по Telegram ID"""
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> User:
    """Создать нового пользователя"""
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_api_key(db: AsyncSession, telegram_id: int, api_key: str) -> bool:
    """Обновить API ключ пользователя"""
    result = await db.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(clore_api_key=api_key, updated_at=datetime.utcnow())
    )
    await db.commit()
    return result.rowcount > 0


async def get_active_users(db: AsyncSession) -> List[User]:
    """Получить активных пользователей с API ключами"""
    result = await db.execute(
        select(User).where(
            and_(
                User.is_active == True,
                User.clore_api_key.isnot(None)
            )
        )
    )
    return result.scalars().all()


# === Balance History ===

async def save_balance_snapshot(
    db: AsyncSession,
    user_id: int,
    clore_balance: float,
    btc_balance: float,
    usd_equivalent: float
) -> BalanceHistory:
    """Сохранить снимок баланса"""
    # Получаем предыдущие записи для расчета изменений
    prev_10min = await db.execute(
        select(BalanceHistory)
        .where(
            and_(
                BalanceHistory.user_id == user_id,
                BalanceHistory.timestamp >= datetime.utcnow() - timedelta(minutes=10)
            )
        )
        .order_by(BalanceHistory.timestamp.desc())
        .limit(1)
    )
    prev_10min_record = prev_10min.scalar_one_or_none()
    
    prev_1hour = await db.execute(
        select(BalanceHistory)
        .where(
            and_(
                BalanceHistory.user_id == user_id,
                BalanceHistory.timestamp >= datetime.utcnow() - timedelta(hours=1)
            )
        )
        .order_by(BalanceHistory.timestamp.desc())
        .limit(1)
    )
    prev_1hour_record = prev_1hour.scalar_one_or_none()
    
    # Расчет изменений
    change_10min = clore_balance - prev_10min_record.clore_balance if prev_10min_record else 0
    change_1hour = clore_balance - prev_1hour_record.clore_balance if prev_1hour_record else 0
    
    # Создаем запись
    balance = BalanceHistory(
        user_id=user_id,
        clore_balance=clore_balance,
        btc_balance=btc_balance,
        usd_equivalent=usd_equivalent,
        clore_change_10min=change_10min,
        clore_change_1hour=change_1hour,
        clore_change_24hour=0  # TODO: Implement 24h calculation
    )
    
    db.add(balance)
    await db.commit()
    return balance


async def get_balance_history(
    db: AsyncSession,
    user_id: int,
    hours: int = 24
) -> List[BalanceHistory]:
    """Получить историю баланса за период"""
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(BalanceHistory)
        .where(
            and_(
                BalanceHistory.user_id == user_id,
                BalanceHistory.timestamp >= since
            )
        )
        .order_by(BalanceHistory.timestamp.desc())
    )
    return result.scalars().all()


# === Orders ===

async def save_order(
    db: AsyncSession,
    user_id: int,
    order_data: Dict[str, Any]
) -> Order:
    """Сохранить информацию о заказе"""
    order = Order(
        user_id=user_id,
        clore_order_id=order_data['id'],
        server_id=order_data.get('si'),
        order_type='spot' if order_data.get('spot') else 'on-demand',
        status='active',
        price_per_day=order_data.get('price', 0),
        currency=order_data.get('currency', 'unknown'),
        total_spent=order_data.get('spend', 0),
        creation_fee=order_data.get('creation_fee', 0),
        image=order_data.get('image'),
        ports=order_data.get('tcp_ports', {}),
        env=order_data.get('env', {}),
        command=order_data.get('command'),
        ssh_password=order_data.get('ssh_password'),
        jupyter_token=order_data.get('jupyter_token'),
        pub_cluster=order_data.get('pub_cluster', []),
        tcp_ports=order_data.get('tcp_ports', {}),
        http_port=order_data.get('http_port'),
        created_at=datetime.fromtimestamp(order_data.get('ct', 0)),
        server_specs=order_data.get('specs', {})
    )
    
    # Рассчитываем время истечения
    if order_data.get('mrl'):
        order.expires_at = order.created_at + timedelta(seconds=order_data['mrl'])
    
    db.add(order)
    await db.commit()
    return order


async def update_order_status(
    db: AsyncSession,
    clore_order_id: int,
    status: str,
    total_spent: Optional[float] = None
) -> bool:
    """Обновить статус заказа"""
    values = {'status': status}
    if total_spent is not None:
        values['total_spent'] = total_spent
    if status == 'cancelled':
        values['cancelled_at'] = datetime.utcnow()
    
    result = await db.execute(
        update(Order)
        .where(Order.clore_order_id == clore_order_id)
        .values(**values)
    )
    await db.commit()
    return result.rowcount > 0


async def get_active_orders(db: AsyncSession, user_id: int) -> List[Order]:
    """Получить активные заказы пользователя"""
    result = await db.execute(
        select(Order)
        .where(
            and_(
                Order.user_id == user_id,
                Order.status == 'active'
            )
        )
        .order_by(Order.created_at.desc())
    )
    return result.scalars().all()


# === Server Snapshots ===

async def save_server_snapshot(
    db: AsyncSession,
    user_id: int,
    server_data: Dict[str, Any],
    snapshot_type: str = 'marketplace'
) -> ServerSnapshot:
    """Сохранить снимок сервера"""
    from clore_api.client import CloreAPIClient
    from config import settings
    
    client = CloreAPIClient("")  # Временный клиент для вспомогательных методов
    
    # Извлекаем данные
    specs = server_data.get('specs', {})
    gpu_str = specs.get('gpu', '')
    gpu_count, gpu_model = client.extract_gpu_info(gpu_str)
    
    # Цены
    price_usd, price_source = client.extract_server_price(server_data)
    price_data = server_data.get('price', {})
    price_clore = price_data.get('on_demand', {}).get('CLORE-Blockchain')
    
    # Power limit
    power_limits = server_data.get('specs', {}).get('stock_pl', [])
    avg_power = sum(power_limits) / len(power_limits) if power_limits else 0
    
    # Рейтинг
    rating_data = server_data.get('rating', {})
    
    snapshot = ServerSnapshot(
        user_id=user_id,
        server_id=server_data.get('id'),
        snapshot_type=snapshot_type,
        raw_data=server_data,
        gpu_model=gpu_model,
        gpu_count=gpu_count,
        gpu_ram=specs.get('gpuram', 0),
        cpu_model=specs.get('cpu', ''),
        ram_gb=specs.get('ram', 0),
        price_clore=price_clore,
        price_usd=price_usd,
        price_source='fixed' if price_source == 'CLORE_FIXED' else 'market',
        is_rented=server_data.get('rented', False),
        is_online=server_data.get('online', False),
        pcie_width=specs.get('pcie_width', 0),
        power_limit=int(avg_power),
        reliability=server_data.get('reliability', 0),
        rating=rating_data.get('avg', 0),
        rating_count=rating_data.get('cnt', 0)
    )
    
    db.add(snapshot)
    await db.commit()
    return snapshot


async def get_server_price_history(
    db: AsyncSession,
    server_id: int,
    hours: int = 24
) -> List[ServerSnapshot]:
    """Получить историю цен сервера"""
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(ServerSnapshot)
        .where(
            and_(
                ServerSnapshot.server_id == server_id,
                ServerSnapshot.timestamp >= since
            )
        )
        .order_by(ServerSnapshot.timestamp.desc())
    )
    return result.scalars().all()


# === Docker Templates ===

async def get_docker_templates(
    db: AsyncSession,
    user_id: Optional[int] = None,
    include_global: bool = True
) -> List[DockerTemplate]:
    """Получить Docker шаблоны"""
    conditions = []
    
    if user_id:
        conditions.append(DockerTemplate.user_id == user_id)
    
    if include_global:
        conditions.append(DockerTemplate.user_id.is_(None))
    
    if conditions:
        where_clause = or_(*conditions)
    else:
        where_clause = True
    
    result = await db.execute(
        select(DockerTemplate)
        .where(where_clause)
        .order_by(DockerTemplate.usage_count.desc())
    )
    return result.scalars().all()


async def create_docker_template(
    db: AsyncSession,
    name: str,
    image: str,
    user_id: Optional[int] = None,
    **kwargs
) -> DockerTemplate:
    """Создать Docker шаблон"""
    template = DockerTemplate(
        user_id=user_id,
        name=name,
        image=image,
        description=kwargs.get('description'),
        category=kwargs.get('category'),
        is_public=kwargs.get('is_public', False),
        ports=kwargs.get('ports', {}),
        env=kwargs.get('env', {}),
        command=kwargs.get('command'),
        min_gpu_ram=kwargs.get('min_gpu_ram'),
        min_gpu_count=kwargs.get('min_gpu_count'),
        required_gpu_models=kwargs.get('required_gpu_models', [])
    )
    
    db.add(template)
    await db.commit()
    return template


# === Hunt Tasks ===

async def create_hunt_task(
    db: AsyncSession,
    user_id: int,
    name: str,
    filters: Dict[str, Any],
    **kwargs
) -> HuntTask:
    """Создать задачу охоты"""
    task = HuntTask(
        user_id=user_id,
        name=name,
        filters=filters,
        is_active=kwargs.get('is_active', True),
        auto_rent=kwargs.get('auto_rent', False),
        max_servers=kwargs.get('max_servers', 1),
        docker_template_id=kwargs.get('docker_template_id')
    )
    
    db.add(task)
    await db.commit()
    return task


async def get_active_hunt_tasks(db: AsyncSession) -> List[HuntTask]:
    """Получить активные задачи охоты"""
    result = await db.execute(
        select(HuntTask)
        .where(HuntTask.is_active == True)
        .order_by(HuntTask.created_at)
    )
    return result.scalars().all()


# === Exchange Rates ===

async def get_current_exchange_rate(
    db: AsyncSession,
    currency_from: str,
    currency_to: str
) -> Optional[float]:
    """Получить текущий курс обмена"""
    result = await db.execute(
        select(ExchangeRate.rate)
        .where(
            and_(
                ExchangeRate.currency_from == currency_from,
                ExchangeRate.currency_to == currency_to
            )
        )
        .order_by(ExchangeRate.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_exchange_rate(
    db: AsyncSession,
    currency_from: str,
    currency_to: str,
    rate: float,
    source: str = "manual"
) -> ExchangeRate:
    """Обновить курс обмена"""
    # Проверяем существующую запись
    result = await db.execute(
        select(ExchangeRate)
        .where(
            and_(
                ExchangeRate.currency_from == currency_from,
                ExchangeRate.currency_to == currency_to
            )
        )
    )
    exchange_rate = result.scalar_one_or_none()
    
    if exchange_rate:
        # Обновляем существующую
        exchange_rate.rate = rate
        exchange_rate.source = source
        exchange_rate.updated_at = datetime.utcnow()
    else:
        # Создаем новую
        exchange_rate = ExchangeRate(
            currency_from=currency_from,
            currency_to=currency_to,
            rate=rate,
            source=source
        )
        db.add(exchange_rate)
    
    await db.commit()
    return exchange_rate


# === Alerts ===

async def create_alert(
    db: AsyncSession,
    user_id: int,
    alert_type: str,
    title: str,
    message: str
) -> Alert:
    """Создать уведомление"""
    alert = Alert(
        user_id=user_id,
        alert_type=alert_type,
        title=title,
        message=message
    )
    
    db.add(alert)
    await db.commit()
    return alert


async def get_unsent_alerts(db: AsyncSession, user_id: int) -> List[Alert]:
    """Получить неотправленные уведомления"""
    result = await db.execute(
        select(Alert)
        .where(
            and_(
                Alert.user_id == user_id,
                Alert.is_sent == False
            )
        )
        .order_by(Alert.created_at)
    )
    return result.scalars().all()


async def mark_alert_sent(
    db: AsyncSession,
    alert_id: int,
    error: Optional[str] = None
) -> bool:
    """Отметить уведомление как отправленное"""
    values = {
        'is_sent': True,
        'sent_at': datetime.utcnow()
    }
    if error:
        values['error'] = error
    
    result = await db.execute(
        update(Alert)
        .where(Alert.id == alert_id)
        .values(**values)
    )
    await db.commit()
    return result.rowcount > 0