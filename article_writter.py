import os
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict

# Импорты для разных AI клиентов
import google.generativeai as genai
from openai import AsyncOpenAI  # Используем асинхронный клиент
from dotenv import load_dotenv

from database_manager import (
    get_generation_tasks,
    save_generated_article,
    update_topic_status
)

'''
Модуль асинхронной генерации статей.
Читает запланированные темы из БД, для каждой темы вызывает соответствующий AI 
(Grok, Gemini, OpenAI) и сохраняет готовую статью обратно в базу данных.
'''

# --- Конфигурация ---
PROMPT_FILE = os.path.join('Prompts', 'article_writer_prompt.txt')
ENV_FILE = '.env'

# Ключи для асинхронных воркеров
API_KEYS = {
    "gemini": ["GEMINI_API_KEY_5", "GEMINI_API_KEY_6", "GEMINI_API_KEY_11"],
    "grok": ["GROK_API_KEY"],
    "openai": ["OPENAI_API_KEY"]
}


# --- "Фабрика" AI клиентов и генераторов ---

async def generate_with_gemini(api_key: str, model_name: str, user_prompt: str) -> str:
    """Асинхронный вызов Gemini."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = await model.generate_content_async(user_prompt)
    return response.text


async def generate_with_openai_compatible(client: AsyncOpenAI, model_name: str, user_prompt: str) -> str:
    """Асинхронный вызов для OpenAI-совместимых API (Grok, OpenAI)."""
    completion = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )
    return completion.choices[0].message.content


# --- Асинхронная логика ---

async def generate_single_article(task: Dict[str, Any], prompt_template: str, client: Any):
    """
    Асинхронно генерирует и сохраняет одну статью, используя предоставленный AI клиент.
    """
    topic_id = task['topic_id']
    provider = task['provider_name']

    # 1. Формируем промпт
    # Используем title и source_news_text для максимального контекста
    full_user_prompt = f"{prompt_template}\n\nWrite an in-depth, 700-1000 word article on a topic: '{task['title']}'\n\nBase your article on the following news summary:\n{task['source_news_text']}"

    try:
        # 2. Вызываем нужный AI
        generated_content = ""
        if provider == 'gemini':
            # Для Gemini мы передаем ключ напрямую
            generated_content = await generate_with_gemini(
                api_key=client,  # ИСПРАВЛЕНИЕ: client здесь - это и есть api_key
                model_name="gemini-2.5-pro",
                user_prompt=full_user_prompt
            )
        elif provider in ['grok', 'openai']:
            model_map = {'grok': 'grok-3', 'openai': 'gpt-4.1-mini-2025-04-14'}
            generated_content = await generate_with_openai_compatible(
                client=client, model_name=model_map[provider],
                user_prompt=full_user_prompt
            )
        else:
            raise ValueError(f"Неизвестный провайдер: {provider}")

        # 3. Сохраняем результат в БД
        if generated_content:
            save_generated_article(
                topic_id=topic_id, user_id=task['assigned_user_id'],
                persona_id=task['assigned_persona_id'], title=task['title'],
                content=generated_content
            )
            update_topic_status(topic_id, 'article_generated')
            print(f"     [SUCCESS] Статья для темы ID {topic_id} ({provider}) сгенерирована и сохранена.")
        else:
            raise ValueError("AI вернул пустой ответ.")

    except Exception as e:
        print(f"     [ERROR] Ошибка при генерации статьи для темы ID {topic_id}: {e}")
        update_topic_status(topic_id, 'article_generation_failed')


# --- Главная функция ---

async def async_run_writer(tasks: List[Dict], prompt_template: str):
    """Управляет асинхронным выполнением задач по генерации статей."""
    load_dotenv(ENV_FILE)

    tasks_by_provider = defaultdict(list)
    for task in tasks:
        tasks_by_provider[task['provider_name']].append(task)

    all_workers = []

    # --- Создаем воркеров для каждого провайдера ---
    provider_clients = {}
    # Инициализируем клиентов для OpenAI и Grok
    grok_key = os.getenv(API_KEYS['grok'][0])
    if grok_key:
        provider_clients['grok'] = AsyncOpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")

    openai_key = os.getenv(API_KEYS['openai'][0])
    if openai_key:
        provider_clients['openai'] = AsyncOpenAI(api_key=openai_key)

    async def worker(worker_id: int, provider: str, task_queue: asyncio.Queue, api_key: str = None):
        client = provider_clients.get(provider)  # Используем уже созданный клиент
        while not task_queue.empty():
            try:
                task = task_queue.get_nowait()
                print(f"     [{provider.capitalize()} Worker {worker_id}] Взял в работу тему ID: {task['topic_id']}...")
                # Для Gemini передаем ключ, для остальных - готовый клиент
                await generate_single_article(task, prompt_template, client or api_key)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                print(f"     [CRITICAL_WORKER_ERROR] Worker {worker_id} ({provider}) упал: {e}")

    # Запускаем воркеров
    for provider, provider_tasks in tasks_by_provider.items():
        keys = [os.getenv(key_name) for key_name in API_KEYS.get(provider, []) if os.getenv(key_name)]
        if not keys and provider not in provider_clients:
            print(
                f"     [WARNING] Нет ключей или клиентов для провайдера {provider}. Пропускаем {len(provider_tasks)} задач.")
            continue

        task_queue = asyncio.Queue()
        for task in provider_tasks:
            await task_queue.put(task)

        # Для Gemini и других, у кого может быть много ключей
        for i, key in enumerate(keys):
            all_workers.append(worker(i + 1, provider, task_queue, api_key=key))

        # Для OpenAI/Grok, где клиент один
        if provider in provider_clients and not keys:
            all_workers.append(worker(1, provider, task_queue))

    if all_workers:
        await asyncio.gather(*all_workers)


def run_article_writer() -> bool:
    """Основная синхронная обертка для запуска модуля."""
    print("  -> Запуск article_writer.py...")

    try:
        prompt_template = Path(PROMPT_FILE).read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f"     [ERROR] Файл с промптом {PROMPT_FILE} не найден.")
        return False

    tasks = get_generation_tasks()
    if not tasks:
        print("     [INFO] Нет задач на генерацию статей.")
        return True

    print(f"     Найдено {len(tasks)} статей для генерации. Запуск...")

    asyncio.run(async_run_writer(tasks, prompt_template))

    print("     Генерация статей завершена.")
    return True


if __name__ == '__main__':
    if run_article_writer():
        print("\n--- Модуль Article Writer успешно завершил работу ---")
    else:
        print("\n--- Работа модуля Article Writer завершилась с ошибкой ---")