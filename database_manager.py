import sqlite3
from collections import defaultdict

DB_NAME = 'neuro_crypto.db'

'''
Модуль для управления базой данных проекта.
Содержит функцию для инициализации всех таблиц согласно финальной архитектуре.
'''


def get_db_connection():
    """Устанавливает соединение с БД и возвращает объект соединения."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# --- ФУНКЦИИ ДЛЯ ЭТАПА ГЕНЕРАЦИИ ---

def get_generation_tasks() -> list:
    """
    Возвращает список тем, запланированных для генерации,
    объединяя данные из таблиц topics и personas.
    """
    conn = get_db_connection()
    try:
        # Используем JOIN, чтобы сразу получить всю нужную информацию
        sql = """
        SELECT
            t.id AS topic_id,
            t.title,
            t.source_news_text,
            t.assigned_user_id,
            t.assigned_persona_id,
            p.persona_code,
            p.provider_name
        FROM topics t
        JOIN personas p ON t.assigned_persona_id = p.id
        WHERE t.status = 'planned_for_generation'
        """
        cursor = conn.execute(sql)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении задач на генерацию: {e}")
        return []
    finally:
        if conn:
            conn.close()

def save_generated_article(topic_id: int, user_id: int, persona_id: int, title: str, content: str) -> bool:
    """Сохраняет готовую сгенерированную статью в базу данных."""
    conn = get_db_connection()
    try:
        sql = """
        INSERT INTO generated_articles (topic_id, user_id, persona_id, title, content)
        VALUES (?, ?, ?, ?, ?)
        """
        conn.execute(sql, (topic_id, user_id, persona_id, title, content))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при сохранении сгенерированной статьи для topic_id {topic_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_all_personas() -> list:
    """Возвращает список всех персон из БД."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT * FROM personas")
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении списка персон: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_persona_image_style(persona_id: int, new_style: str):
    """Обновляет стиль для генерации изображений для указанной персоны."""
    conn = get_db_connection()
    try:
        sql = "UPDATE personas SET image_prompt_style = ? WHERE id = ?"
        conn.execute(sql, (new_style, persona_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при обновлении стиля изображения для persona_id {persona_id}: {e}")
    finally:
        if conn:
            conn.close()


def initialize_database():
    """
    Проверяет и инициализирует базу данных.
    Создает все необходимые таблицы согласно финальной, согласованной схеме.
    """
    print(f"Проверка и инициализация базы данных '{DB_NAME}'...")
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys = ON;")

        # 1. Таблица для хранения информации о персонах/стилях
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_code TEXT NOT NULL UNIQUE,
            persona_name TEXT NOT NULL,
            provider_name TEXT,
            image_prompt_style TEXT,
            description TEXT
        )
        ''')

        # 2. Таблица для хранения недельного плана публикаций
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start_date TEXT NOT NULL,
            day_of_week TEXT NOT NULL, -- Mon, Tue, Wed...
            persona_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            target_count INTEGER NOT NULL,
            FOREIGN KEY (persona_id) REFERENCES personas (id) ON DELETE CASCADE,
            UNIQUE(week_start_date, day_of_week, persona_id, category)
        )
        ''')

        # 3. Таблица для пользователей Telegram и их подписок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            registration_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            subscribed_persona_id INTEGER,
            FOREIGN KEY (subscribed_persona_id) REFERENCES personas (id) ON DELETE SET NULL
        )
        ''')

        # 4. Таблица для хранения статей, спарсенных с Bybit
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bybit_article_id INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL,
            bybit_category_id INTEGER,
            publication_date TEXT
        )
        ''')

        # 5. Таблица для хранения тем, сгенерированных из новостей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            source_news_text TEXT,
            creation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            assigned_persona_id INTEGER,
            FOREIGN KEY (assigned_persona_id) REFERENCES personas (id) ON DELETE SET NULL
        )
        ''')

        # 6. Таблица для хранения сгенерированных нами статей (финальный продукт)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS generated_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            persona_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_path TEXT,
            generation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (persona_id) REFERENCES personas (id) ON DELETE CASCADE
        )
        ''')

        # 7. Таблица для логирования доставок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS delivery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_date TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            planned_count INTEGER NOT NULL,
            actual_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        ''')

        # Триггер для автоматического обновления поля last_updated в таблице topics
        cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_topics_last_updated
        AFTER UPDATE ON topics
        FOR EACH ROW
        BEGIN
            UPDATE topics
            SET last_updated = CURRENT_TIMESTAMP
            WHERE id = OLD.id;
        END;
        ''')

        conn.commit()
        print("Инициализация базы данных успешно завершена. Все таблицы созданы согласно схеме 2.1.")

    except sqlite3.Error as e:
        print(f"Ошибка при инициализации SQLite: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# --- НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ТЕМАМИ ---

def get_topics_by_status(status: str) -> list:
    """Возвращает список тем с указанным статусом."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT * FROM topics WHERE status = ?", (status,))
        # Преобразуем результат в список словарей для удобства
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении тем по статусу '{status}': {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_last_published_titles(category: str, limit: int = 10) -> list[str]:
    """
    Возвращает список последних заголовков для указанной категории
    из таблицы source_articles (статьи с Bybit).
    """
    conn = get_db_connection()
    try:
        # ПРИМЕЧАНИЕ: Мы ищем по bybit_category_id, а не по нашему внутреннему 'category'.
        # Это может потребовать доработки, если ID категорий не совпадают.
        # Пока оставляем так, как было в MVP.
        cursor = conn.execute(
            "SELECT title FROM source_articles WHERE bybit_category_id = ? ORDER BY id DESC LIMIT ?",
            (category, limit)
        )
        return [row['title'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении заголовков из source_articles: {e}")
        return []
    finally:
        if conn:
            conn.close()

# --- ФУНКЦИИ ДЛЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ ---

def get_image_generation_tasks() -> list:
    """
    Возвращает список статей, для которых нужно сгенерировать изображение.
    Ищет статьи, где image_path еще не установлен.
    """
    conn = get_db_connection()
    try:
        # Используем JOIN, чтобы сразу получить и стиль для промпта
        sql = """
        SELECT
            ga.id AS generated_article_id,
            ga.title,
            p.image_prompt_style
        FROM generated_articles ga
        JOIN personas p ON ga.persona_id = p.id
        WHERE ga.image_path IS NULL
        """
        cursor = conn.execute(sql)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении задач на генерацию изображений: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_article_image_path(generated_article_id: int, image_path: str):
    """Обновляет путь к изображению для сгенерированной статьи."""
    conn = get_db_connection()
    try:
        sql = "UPDATE generated_articles SET image_path = ? WHERE id = ?"
        conn.execute(sql, (image_path, generated_article_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при обновлении пути к изображению для статьи ID {generated_article_id}: {e}")
    finally:
        if conn:
            conn.close()


def update_topic_with_title(topic_id: int, new_title: str):
    """Обновляет тему, добавляя ей заголовок и меняя статус на 'ready_for_planning'."""
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE topics SET title = ?, status = 'ready_for_planning' WHERE id = ?",
            (new_title, topic_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при обновлении темы {topic_id}: {e}")
    finally:
        if conn:
            conn.close()

def update_topic_status(topic_id: int, new_status: str):
    """Универсальная функция для обновления статуса темы (например, при ошибке)."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE topics SET status = ? WHERE id = ?", (new_status, topic_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при обновлении статуса темы {topic_id}: {e}")
    finally:
        if conn:
            conn.close()

# --- НОВАЯ ФУНКЦИЯ ДЛЯ СБОРКИ ДОКУМЕНТОВ ---

def get_articles_for_delivery() -> dict:
    """
    Возвращает словарь {user_id: [article_1, article_2, ...]}
    для всех статей, сгенерированных сегодня.
    """
    conn = get_db_connection()
    articles_by_user = defaultdict(list)
    try:
        # Ищем статьи, сгенерированные за последние 24 часа
        sql = """
        SELECT
            ga.id,
            ga.user_id,
            ga.title,
            ga.content,
            ga.image_path,
            ga.matched_tokens,
            t.category,
            u.username
        FROM generated_articles ga
        JOIN topics t ON ga.topic_id = t.id
        JOIN users u ON ga.user_id = u.id
        WHERE ga.generation_date >= date('now')
        ORDER BY ga.user_id, ga.id
        """
        cursor = conn.execute(sql)
        for row in cursor.fetchall():
            articles_by_user[row['user_id']].append(dict(row))
        return dict(articles_by_user)
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при получении статей для доставки: {e}")
        return {}
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    initialize_database()