import os
import json
from pathlib import Path
from typing import List, Dict
import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import GenerationConfig

from alerter import send_admin_alert
from database_manager import get_all_personas, update_persona_image_style

'''
Модуль ежедневной генерации стилей для изображений.
Запускает "Art Director" промпт, получает от Gemini 5 уникальных стилей
для каждой персоны и обновляет их в базе данных.
'''

# --- Конфигурация ---
PROMPT_FILE = os.path.join('Prompts', 'image_style_generator_prompt.txt')
API_KEY_NAMES = ["GEMINI_API_KEY_7", "GEMINI_API_KEY_8"]
MODEL_NAME = "gemini-2.5-pro"
ENV_FILE = '.env'


# --- Основная логика ---

def get_image_styles_from_ai(prompt: str) -> List[Dict] | None:
    """
    Делает запрос к Gemini, перебирая API-ключи, и ожидает JSON-массив.
    """
    load_dotenv(ENV_FILE)
    api_keys = [os.getenv(key) for key in API_KEY_NAMES if os.getenv(key)]
    if not api_keys:
        print("     [ERROR] API-ключи для генератора стилей не найдены в .env")
        return None

    generation_config = GenerationConfig(
        response_mime_type="application/json",
        temperature=1.0
    )

    for i, api_key in enumerate(api_keys):
        print(f"     Попытка {i + 1}/{len(api_keys)} с ключом ...{api_key[-4:]}")
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content(contents=prompt, generation_config=generation_config)

            parsed_response = json.loads(response.text)

            # Проверяем, что это список из 5 элементов
            if isinstance(parsed_response, list) and len(parsed_response) == 5:
                print("     Успешный ответ и валидация JSON-массива получены.")
                return parsed_response
            else:
                print(f"     [WARNING] Ответ API не является списком из 5 элементов. Ответ: {parsed_response}")
        except Exception as e:
            print(f"     [ERROR] Ошибка с ключом ...{api_key[-4:]}: {e}")
            continue

    print("     [CRITICAL] Ни один из API-ключей не сработал или не вернул корректный формат.")
    return None


def run_image_prompt_generator() -> bool:
    """
    Основная функция-оркестратор для генерации стилей изображений.
    """
    print("  -> Запуск image_prompt_generator.py...")

    # 1. Загружаем промпт
    try:
        prompt_text = Path(PROMPT_FILE).read_text(encoding='utf-8')
    except FileNotFoundError:
        send_admin_alert(f"🔥 *Критический сбой в Image Prompt Generator:*\nНе найден файл с промптом `{PROMPT_FILE}`")
        return False  # Это критическая ошибка конфигурации

    # 2. Получаем стили от Gemini
    generated_styles = get_image_styles_from_ai(prompt_text)

    # 3. Обрабатываем результат
    if not generated_styles:
        error_message = "Не удалось сгенерировать стили изображений от Gemini. Будут использованы старые стили."
        print(f"     [WARNING] {error_message}")
        send_admin_alert(f"⚠️ *Сбой в Image Prompt Generator:*\n{error_message}")
        return True

    # 4. Получаем карту персон из БД для сопоставления
    personas = get_all_personas()
    personas_map = {p['persona_code']: p['id'] for p in personas}

    # 5. Обновляем стили в БД
    updated_count = 0
    for style_data in generated_styles:
        persona_code = style_data.get('persona_code')
        new_style = style_data.get('image_prompt_style')

        if persona_code and new_style and persona_code in personas_map:
            persona_id = personas_map[persona_code]
            update_persona_image_style(persona_id, new_style)
            updated_count += 1
        else:
            print(f"     [WARNING] Пропущена некорректная запись из AI: {style_data}")

    print(f"     Успешно обновлено {updated_count} из 5 стилей в базе данных.")
    return True


if __name__ == '__main__':
    if run_image_prompt_generator():
        print("\n--- Модуль Image Prompt Generator успешно завершил работу ---")
    else:
        print("\n--- Работа модуля Image Prompt Generator завершилась с ошибкой ---")