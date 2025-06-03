"""
Управление сессиями базы данных
"""
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import select, func

from config import settings
from database.models import Base


# Создаем асинхронный движок
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
    
    # Добавляем начальные данные
    await init_exchange_rates()


async def init_exchange_rates():
    """Инициализация курсов валют"""
    from database.models import ExchangeRate
    
    async with get_db() as db:
        # Проверяем, есть ли уже курсы
        stmt = select(func.count()).select_from(ExchangeRate).where(
            (ExchangeRate.currency_from == 'CLORE') & 
            (ExchangeRate.currency_to == 'USD')
        )
        result = await db.execute(stmt)
        count = result.scalar()
        
        if count == 0:
            # Добавляем начальный курс
            rate = ExchangeRate(
                currency_from="CLORE",
                currency_to="USD",
                rate=settings.clore_to_usd,
                source="manual"
            )
            db.add(rate)
            await db.commit()


@asynccontextmanager
async def get_db():
    """Получить сессию базы данных"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
