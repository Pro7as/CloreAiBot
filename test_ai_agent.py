#!/usr/bin/env python3
"""
Тестирование улучшенного AI агента
"""
import asyncio
import sys
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

# Добавляем путь к проекту
sys.path.append('.')

from ai_agent.agent import CloreAIAgent
from config import settings

console = Console()


async def test_agent():
    """Интерактивное тестирование агента"""
    console.clear()
    
    # Заголовок
    console.print(Panel.fit(
        "[bold cyan]Тестирование Clore AI Agent[/bold cyan]\n"
        "[dim]Введите 'exit' для выхода[/dim]",
        border_style="cyan"
    ))
    
    # Проверяем наличие API ключей
    if not settings.openai_api_key:
        console.print("[red]❌ Не настроен OpenAI API ключ![/red]")
        return
    
    # Запрашиваем Clore API ключ
    console.print("\n[yellow]Введите ваш Clore API ключ:[/yellow]")
    api_key = input("> ").strip()
    
    if not api_key:
        console.print("[red]❌ API ключ не введен![/red]")
        return
    
    # Создаем агента
    console.print("\n[green]Инициализация агента...[/green]")
    agent = CloreAIAgent(api_key)
    
    console.print("[green]✅ Агент готов к работе![/green]\n")
    
    # Примеры запросов
    examples = [
        "Покажи мой баланс",
        "Найди дешевые серверы с RTX 3080",
        "Мне нужен сервер для машинного обучения",
        "Арендуй сервер 12345",
        "Сколько я потратил за последнюю неделю?",
        "Покажи мои активные аренды"
    ]
    
    console.print("[dim]Примеры запросов:[/dim]")
    for example in examples:
        console.print(f"[dim]• {example}[/dim]")
    
    console.print("\n" + "="*50 + "\n")
    
    # Основной цикл
    try:
        while True:
            # Запрос пользователя
            console.print("[bold cyan]Вы:[/bold cyan]", end=" ")
            query = input().strip()
            
            if query.lower() in ['exit', 'quit', 'выход']:
                break
            
            if not query:
                continue
            
            # Обработка запроса
            console.print("\n[dim]🤖 Обрабатываю запрос...[/dim]")
            
            try:
                response = await agent.process_query(query)
                
                # Выводим ответ
                console.print("\n[bold green]AI Agent:[/bold green]")
                
                # Форматируем markdown
                if response.startswith("#") or "**" in response or "```" in response:
                    md = Markdown(response)
                    console.print(md)
                else:
                    console.print(response)
                
            except Exception as e:
                console.print(f"\n[red]❌ Ошибка: {str(e)}[/red]")
                logger.error(f"Error processing query: {e}", exc_info=True)
            
            console.print("\n" + "="*50 + "\n")
    
    finally:
        # Закрываем агента
        await agent.close()
        console.print("\n[yellow]Сеанс завершен. До свидания![/yellow]")


async def test_specific_queries():
    """Тестирование конкретных запросов"""
    # Тестовые запросы
    test_queries = [
        "Привет! Что ты умеешь?",
        "Покажи серверы с 4090 дешевле 10 долларов",
        "Найди серверы в Германии с хорошим рейтингом",
        "Мне нужно 4 карты 3090 для рендеринга",
        "Сколько стоит самый дешевый сервер с A100?",
        "Покажи статистику моих расходов"
    ]
    
    console.print("[bold]Тестирование типовых запросов:[/bold]\n")
    
    # Создаем агента с тестовым ключом
    agent = CloreAIAgent("test_api_key")
    
    for query in test_queries:
        console.print(f"[cyan]Запрос:[/cyan] {query}")
        
        try:
            response = await agent.process_query(query)
            console.print(f"[green]Ответ:[/green] {response[:200]}...")
        except Exception as e:
            console.print(f"[red]Ошибка:[/red] {str(e)}")
        
        console.print("-" * 50)
        await asyncio.sleep(1)
    
    await agent.close()


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Тестирование Clore AI Agent")
    parser.add_argument(
        "--mode", 
        choices=["interactive", "test"], 
        default="interactive",
        help="Режим работы: interactive - интерактивный чат, test - тестовые запросы"
    )
    
    args = parser.parse_args()
    
    # Настройка логирования
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    try:
        if args.mode == "interactive":
            await test_agent()
        else:
            await test_specific_queries()
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Критическая ошибка: {str(e)}[/red]")
        logger.error("Critical error", exc_info=True)


if __name__ == "__main__":
    # Проверяем наличие rich
    try:
        import rich
    except ImportError:
        print("Установите rich для красивого вывода: pip install rich")
        sys.exit(1)
    
    asyncio.run(main())
