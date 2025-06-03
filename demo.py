#!/usr/bin/env python3
"""
Демонстрация возможностей Clore Bot Pro
"""
import asyncio
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn
import random

console = Console()


async def demo_main():
    """Основная демонстрация"""
    console.clear()
    
    # Заголовок
    console.print(Panel.fit(
        "[bold cyan]Clore Bot Pro[/bold cyan]\n"
        "[dim]Продвинутый бот для управления GPU серверами[/dim]",
        border_style="cyan"
    ))
    
    await asyncio.sleep(1)
    
    # Демо функций
    await demo_search()
    await demo_balance()
    await demo_orders()
    await demo_ai_chat()
    await demo_monitoring()
    
    console.print("\n[bold green]✨ Демонстрация завершена![/bold green]")
    console.print("Для запуска бота используйте: [cyan]python main.py[/cyan]")


async def demo_search():
    """Демонстрация поиска серверов"""
    console.print("\n[bold yellow]🔍 Демонстрация поиска серверов[/bold yellow]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Поиск серверов с RTX 4090...", total=None)
        await asyncio.sleep(2)
    
    # Таблица результатов
    table = Table(title="Найденные серверы")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("GPU", style="magenta")
    table.add_column("CPU", style="green")
    table.add_column("Цена", style="yellow")
    table.add_column("Рейтинг", style="blue")
    
    servers = [
        ("12345", "4x RTX 4090", "AMD EPYC 7763", "$32.50/день", "⭐ 4.8"),
        ("23456", "2x RTX 4090", "Intel Xeon Gold", "$16.25/день", "⭐ 4.5"),
        ("34567", "8x RTX 4090", "AMD EPYC 7713", "$65.00/день", "⭐ 5.0"),
    ]
    
    for server in servers:
        table.add_row(*server)
    
    console.print(table)
    await asyncio.sleep(2)


async def demo_balance():
    """Демонстрация проверки баланса"""
    console.print("\n[bold yellow]💰 Демонстрация проверки баланса[/bold yellow]")
    
    balance_info = """
[bold]Ваши балансы:[/bold]
• CLORE: 1,234.56 (~$24.69)
• BTC: 0.00123456 (~$123.46)

[bold]Общий баланс:[/bold] $148.15

[dim]Изменение за час: +$2.34 (+1.6%)[/dim]
    """
    
    console.print(Panel(balance_info, title="Баланс", border_style="green"))
    await asyncio.sleep(2)


async def demo_orders():
    """Демонстрация активных заказов"""
    console.print("\n[bold yellow]📦 Демонстрация активных аренд[/bold yellow]")
    
    orders_table = Table(title="Активные аренды")
    orders_table.add_column("Заказ", style="cyan")
    orders_table.add_column("Сервер", style="magenta")
    orders_table.add_column("Время", style="green")
    orders_table.add_column("Стоимость", style="yellow")
    
    orders_table.add_row("#78901", "4x RTX 3090", "12ч 34м", "$45.60")
    orders_table.add_row("#89012", "2x RTX 4090", "3д 5ч", "$195.00")
    
    console.print(orders_table)
    console.print("[yellow]Общая стоимость:[/yellow] [bold]$240.60/день[/bold]")
    await asyncio.sleep(2)


async def demo_ai_chat():
    """Демонстрация AI чата"""
    console.print("\n[bold yellow]🤖 Демонстрация AI ассистента[/bold yellow]")
    
    conversations = [
        ("Найди самые дешевые серверы с RTX 3080", 
         "Нашел 5 серверов с RTX 3080:\n1. #45678 - 2x RTX 3080 - $8.50/день\n2. #56789 - 1x RTX 3080 - $4.25/день\n..."),
        
        ("Арендуй сервер 45678",
         "Создаю заказ для сервера #45678...\n✅ Заказ #90123 успешно создан!\nSSH: ssh root@node1.clore.ai -p 10022"),
        
        ("Сколько я потратил за последнюю неделю?",
         "Анализирую расходы за 7 дней:\n• Общие расходы: $284.75\n• Средний расход: $40.68/день\n• Самый дорогой заказ: #78901 ($125.50)")
    ]
    
    for user_msg, bot_response in conversations:
        console.print(f"\n[bold cyan]Вы:[/bold cyan] {user_msg}")
        await asyncio.sleep(1)
        console.print(f"[bold green]Бот:[/bold green] {bot_response}")
        await asyncio.sleep(2)


async def demo_monitoring():
    """Демонстрация мониторинга"""
    console.print("\n[bold yellow]📊 Демонстрация мониторинга[/bold yellow]")
    
    with Live(generate_monitoring_display(), refresh_per_second=2) as live:
        for _ in range(6):
            await asyncio.sleep(0.5)
            live.update(generate_monitoring_display())


def generate_monitoring_display():
    """Генерация дисплея мониторинга"""
    layout = Layout()
    
    # Случайные данные для демонстрации
    balance = 1234.56 + random.uniform(-10, 10)
    active_orders = random.randint(3, 5)
    
    monitoring_text = f"""
[bold]Мониторинг системы[/bold]
Время: {datetime.now().strftime('%H:%M:%S')}

[green]● Баланс CLORE:[/green] {balance:.2f}
[green]● Активных аренд:[/green] {active_orders}
[yellow]● Проверка серверов:[/yellow] OK
[blue]● AI агент:[/blue] Готов

[dim]Следующая проверка через 5 мин[/dim]
    """
    
    return Panel(monitoring_text, title="Статус", border_style="blue")


if __name__ == "__main__":
    try:
        import rich
    except ImportError:
        print("Для запуска демо установите rich: pip install rich")
        exit(1)
    
    asyncio.run(demo_main())