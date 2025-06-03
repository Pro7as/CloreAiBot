"""
Утилиты для форматирования данных
"""
from typing import Union, Optional
from datetime import datetime, timedelta


def format_price(amount: float, currency: str = "USD") -> str:
    """Форматировать цену"""
    if currency == "USD":
        return f"${amount:.2f}"
    elif currency == "CLORE":
        return f"{amount:.2f} CLORE"
    elif currency == "BTC":
        return f"{amount:.8f} BTC"
    else:
        return f"{amount:.2f} {currency}"


def format_duration(seconds: int) -> str:
    """Форматировать продолжительность"""
    if seconds < 60:
        return f"{seconds}с"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}м"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}ч {minutes}м"
        return f"{hours}ч"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        if hours > 0:
            return f"{days}д {hours}ч"
        return f"{days}д"


def format_datetime(dt: datetime) -> str:
    """Форматировать дату и время"""
    now = datetime.now()
    diff = now - dt
    
    if diff < timedelta(minutes=1):
        return "только что"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} мин назад"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} ч назад"
    elif diff < timedelta(days=7):
        days = diff.days
        return f"{days} дн назад"
    else:
        return dt.strftime("%d.%m.%Y %H:%M")


def format_percentage(value: float, decimals: int = 1) -> str:
    """Форматировать процент"""
    return f"{value:.{decimals}f}%"


def format_size(bytes: int) -> str:
    """Форматировать размер файла/данных"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} PB"


def format_gpu_string(gpu_count: int, gpu_model: str) -> str:
    """Форматировать строку GPU"""
    if gpu_count == 1:
        return gpu_model
    return f"{gpu_count}x {gpu_model}"


def format_server_id(server_id: Union[int, str]) -> str:
    """Форматировать ID сервера"""
    return f"#{server_id}"


def escape_markdown(text: str) -> str:
    """Экранировать специальные символы для Markdown"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Обрезать текст до максимальной длины"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_list(items: list, separator: str = ", ", max_items: int = 10) -> str:
    """Форматировать список элементов"""
    if len(items) <= max_items:
        return separator.join(str(item) for item in items)
    
    displayed = items[:max_items]
    remaining = len(items) - max_items
    result = separator.join(str(item) for item in displayed)
    return f"{result} и еще {remaining}"


def format_balance_change(current: float, previous: float, currency: str = "CLORE") -> str:
    """Форматировать изменение баланса"""
    if previous == 0:
        return "—"
    
    change = current - previous
    percent = (change / previous) * 100
    
    if change > 0:
        emoji = "📈"
        sign = "+"
    elif change < 0:
        emoji = "📉"
        sign = ""
    else:
        return "без изменений"
    
    return f"{emoji} {sign}{change:.4f} {currency} ({sign}{percent:.1f}%)"


def format_rating(rating: float, count: int) -> str:
    """Форматировать рейтинг"""
    stars = "⭐" * int(rating)
    return f"{stars} {rating:.1f} ({count} отзывов)"


def format_reliability(reliability: float) -> str:
    """Форматировать надежность"""
    percent = reliability * 100
    if percent >= 99.9:
        emoji = "🟢"
    elif percent >= 99:
        emoji = "🟡"
    else:
        emoji = "🔴"
    
    return f"{emoji} {percent:.2f}%"


def format_power_consumption(power_watts: int, gpu_count: int = 1) -> str:
    """Форматировать энергопотребление"""
    total = power_watts * gpu_count
    if total < 1000:
        return f"⚡ {total}W"
    else:
        kw = total / 1000
        return f"⚡ {kw:.1f}kW"