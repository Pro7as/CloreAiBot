#!/usr/bin/env python3
"""
Проверка работы OpenAI API
"""
import asyncio
from openai import AsyncOpenAI
from config import settings

async def test_openai():
    """Тест подключения к OpenAI"""
    print("🔍 Проверка OpenAI API...")
    
    if not settings.openai_api_key:
        print("❌ OpenAI API ключ не настроен в .env!")
        return
    
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        # Простой тест
        print("📝 Отправка тестового запроса...")
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in Russian"}
            ],
            max_tokens=50
        )
        
        print(f"✅ Ответ получен: {response.choices[0].message.content}")
        print(f"✅ Модель: {response.model}")
        print(f"✅ OpenAI API работает корректно!")
        
    except Exception as e:
        print(f"❌ Ошибка OpenAI API: {e}")
        print("\nВозможные причины:")
        print("1. Неверный API ключ")
        print("2. Закончились кредиты")
        print("3. Проблемы с сетью")

if __name__ == "__main__":
    asyncio.run(test_openai())
