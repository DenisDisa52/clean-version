import sqlite3
from database_manager import get_db_connection

"""
Модуль для первоначального заполнения базы данных (seeding).
Единоразово добавляет в систему предопределенные роли-персоны,
необходимыми для дальнейшей генерации контента.
"""

def seed_personas():
    """
    Заполняет таблицу 'personas' начальными данными.
    Если персона с таким `persona_code` уже существует, она будет пропущена.
    """
    # Данные для наших пяти персон
    personas_data = [
        {
            "persona_code": "main",
            "persona_name": "Профессор",
            "provider_name": "gemini",
            "image_prompt_style": "High-resolution, educational infographic style, clean lines, minimalist color palette (blues, greys), abstract representation of data, digital art.",
            "description": "Writes foundational, evergreen educational content. Ignores short-term hype."
        },
        {
            "persona_code": "t1",
            "persona_name": "Стратег",
            "provider_name": "grok",
            "image_prompt_style": "Dynamic digital art, stock market chart motifs, bull and bear symbols, green and red neon glow, sense of urgency and volatility, data streams.",
            "description": "Reacts to market volatility. Activity spikes during volatility."
        },
        {
            "persona_code": "t2",
            "persona_name": "Визионер",
            "provider_name": "gemini",
            "image_prompt_style": "Ethereal, futuristic digital painting, cyberpunk aesthetics, holographic elements, deep space background, philosophical and abstract concepts, vibrant purples and cyans.",
            "description": "Writes about future/philosophy of technology. Creative bursts."
        },
        {
            "persona_code": "t3",
            "persona_name": "Практик",
            "provider_name": "gemini",
            "image_prompt_style": "Clean, user-friendly UI/UX design style, screenshots with annotations, step-by-step process visualization, friendly and approachable, light and bright colors.",
            "description": "Consistently produces useful how-to guides for beginners."
        },
        {
            "persona_code": "t4",
            "persona_name": "Провокатор",
            "provider_name": "grok",
            "image_prompt_style": "Glitch art style, mysterious and dark theme, hooded figures, binary code overlays, dramatic lighting, sense of conspiracy and hidden information, cinematic.",
            "description": "Unpredictable. Simulates 'leaks' or 'insider takes' on events."
        }
    ]

    print("Запускаю процесс заполнения таблицы 'personas'...")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        sql = """
        INSERT OR IGNORE INTO personas 
        (persona_code, persona_name, provider_name, image_prompt_style, description) 
        VALUES (:persona_code, :persona_name, :provider_name, :image_prompt_style, :description)
        """

        for persona in personas_data:
            cursor.execute(sql, persona)
            if cursor.rowcount > 0:
                print(f"  - Добавлена новая персона: '{persona['persona_name']}'")
            else:
                print(f"  - Персона '{persona['persona_name']}' уже существует, пропущена.")

        conn.commit()
        print("\nЗаполнение таблицы 'personas' успешно завершено.")

    except sqlite3.Error as e:
        print(f"\nПроизошла ошибка при заполнении БД: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    seed_personas()