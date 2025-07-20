import os
import asyncio
from typing import Dict, List

from huggingface_hub import InferenceClient
from dotenv import load_dotenv

from database_manager import get_image_generation_tasks, update_article_image_path

from alerter import send_admin_alert
from io import BytesIO
from PIL import Image
from pathlib import Path

"""
Асинхронный модуль генерации  изображений для статей с использованием нескольких AI-моделей.
Получает задачи из базы данных, формирует промпты и последовательно обращается к API.
"""
# --- Конфигурация ---
OUTPUT_IMAGE_DIR = "Gen_Photo"
API_KEY_NAMES = ["HF_TOKEN"]
ENV_FILE = '.env'

MODEL_CONFIGS = [
    {
        "model_name": "stabilityai/stable-diffusion-3.5-large",
        "provider": "hf-inference"
    },
    {
        "model_name": "stabilityai/stable-diffusion-xl-base-1.0",
        "provider": "nebius"
    },
    {
        "model_name": "black-forest-labs/FLUX.1-schnell",
        "provider": "together"
    }
]


# --- Логика генерации ---

async def generate_single_image(task: Dict, api_key: str) -> bool:
    article_id = task['generated_article_id']
    title = task['title']
    style_prompt = task['image_prompt_style']

    final_prompt = f"{style_prompt} -- A creative digital illustration about '{title}'"

    for i, config in enumerate(MODEL_CONFIGS):
        model_name = config["model_name"]
        provider = config["provider"]

        try:
            print(f"     [INFO] Попытка генерации для статьи ID {article_id} с использованием модели: {model_name}")

            client = InferenceClient(
                provider=provider,
                api_key=api_key
            )

            image = await asyncio.to_thread(
                client.text_to_image,
                prompt=final_prompt,
                model=model_name,
            )

            os.makedirs(OUTPUT_IMAGE_DIR, exist_ok=True)
            image_filename = f"article_id_{article_id}.png"
            image_filepath = os.path.join(OUTPUT_IMAGE_DIR, image_filename)
            image.save(image_filepath)

            update_article_image_path(article_id, image_filepath)
            print(f"     [SUCCESS] Изображение для статьи ID {article_id} сгенерировано ({model_name}) и сохранено.")
            await asyncio.sleep(15) # Пауза 15 секунд для избежания rate limit
            return True

        except Exception as e:
            print(f"     [ERROR] Произошла ошибка с моделью {model_name}: {e}")
            is_last_model = (i == len(MODEL_CONFIGS) - 1)
            if not is_last_model:
                print(f"     [INFO] Пробуем другую модель через 30 секунд...")
                await asyncio.sleep(30)

    print(f"     [FAILURE] Не удалось сгенерировать изображение для статьи ID {article_id} после всех попыток.")
    return False


# --- Главная функция ---

async def async_run_generator(tasks: List[Dict]):
    load_dotenv(ENV_FILE)
    api_keys = [os.getenv(key) for key in API_KEY_NAMES if os.getenv(key)]
    if not api_keys:
        print("     [ERROR] API-ключи для генерации изображений не найдены.")
        return

    task_queue = asyncio.Queue()
    for task in tasks:
        await task_queue.put(task)

    async def worker(worker_id: int, api_key: str):
        while not task_queue.empty():
            try:
                task = task_queue.get_nowait()
                print(f"     [Image Worker {worker_id}] Взял в работу статью ID: {task['generated_article_id']}...")
                await generate_single_image(task, api_key)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                print(f"     [CRITICAL_WORKER_ERROR] Worker {worker_id} упал: {e}")

    workers = [worker(i + 1, api_key) for i, api_key in enumerate(api_keys)]
    await asyncio.gather(*workers)


def run_picture_generator() -> bool:
    print("  -> Запуск picture_generator.py...")

    tasks = get_image_generation_tasks()
    if not tasks:
        print("     [INFO] Нет задач на генерацию изображений.")
        return True

    print(f"     Найдено {len(tasks)} изображений для генерации. Запуск...")

    asyncio.run(async_run_generator(tasks))

    print("     Генерация изображений завершена.")
    return True


if __name__ == '__main__':
    if run_picture_generator():
        print("\n--- Модуль Picture Generator успешно завершил работу ---")
    else:
        print("\n--- Работа модуля Picture Generator завершилась с ошибкой ---")