import sqlite3
import json
from datetime import date, timedelta
from collections import defaultdict
from typing import Dict, List

from database_manager import get_db_connection
from alerter import send_admin_alert

'''
Модуль ежедневного тактического планирования.
Читает детальный дневной план из БД, выбирает из запаса конкретные темы
и назначает их пользователям для последующей генерации.
'''


# --- Функции для работы с БД ---

def get_user_subscriptions() -> Dict[int, List[int]]:
    """Возвращает словарь {persona_id: [user_id_1, ...]}."""
    conn = get_db_connection()
    subscriptions = defaultdict(list)
    try:
        cursor = conn.execute("SELECT id, subscribed_persona_id FROM users WHERE subscribed_persona_id IS NOT NULL")
        for row in cursor.fetchall():
            subscriptions[row['subscribed_persona_id']].append(row['id'])
        return subscriptions
    finally:
        if conn:
            conn.close()


def get_daily_plan_from_db(week_start: str, day_of_week_str: str) -> Dict[int, Dict[str, int]]:
    """Возвращает план на сегодня в виде {persona_id: {category: count, ...}}."""
    conn = get_db_connection()
    daily_plan = defaultdict(dict)
    try:
        cursor = conn.execute(
            "SELECT persona_id, category, target_count FROM weekly_plan WHERE week_start_date = ? AND day_of_week = ?",
            (week_start, day_of_week_str)
        )
        for row in cursor.fetchall():
            daily_plan[row['persona_id']][row['category']] = row['target_count']
        return daily_plan
    finally:
        if conn:
            conn.close()


def get_available_topics_by_category() -> Dict[str, List[Dict]]:
    """Возвращает словарь {category: [topic_1, ...]} для тем, готовых к планированию."""
    conn = get_db_connection()
    available_topics = defaultdict(list)
    try:
        cursor = conn.execute("SELECT * FROM topics WHERE status = 'ready_for_planning' ORDER BY creation_date ASC")
        for row in cursor.fetchall():
            available_topics[row['category']].append(dict(row))
        return available_topics
    finally:
        if conn:
            conn.close()


def assign_topics_in_db(assignments: List[Dict]) -> int:
    """Обновляет статус и назначает темы в БД. Возвращает количество обновленных строк."""
    if not assignments:
        return 0
    to_update = [
        ('planned_for_generation', item['user_id'], item['persona_id'], item['topic_id'])
        for item in assignments
    ]
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = "UPDATE topics SET status = ?, assigned_user_id = ?, assigned_persona_id = ? WHERE id = ?"
        cursor.executemany(sql, to_update)
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as e:
        print(f"     [DB_ERROR] Ошибка при назначении тем: {e}")
        return 0
    finally:
        if conn:
            conn.close()


# --- Основная логика ---

def run_daily_planner() -> bool:
    print("  -> Запуск daily_planner.py...")

    today = date.today()
    week_start_str = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    day_of_week_str = today.strftime('%a')

    # 1. Загрузка дневного плана из БД
    daily_plan = get_daily_plan_from_db(week_start_str, day_of_week_str)
    if not daily_plan:
        print(f"     [INFO] На сегодня ({day_of_week_str}) нет запланированных статей в БД.")
        return True

    print(f"     План на сегодня ({day_of_week_str}): {json.dumps(dict(daily_plan), indent=2)}")

    # 2. Получаем подписки и доступные темы
    subscriptions = get_user_subscriptions()
    available_topics = get_available_topics_by_category()
    if not subscriptions:
        print("     [INFO] Нет активных подписок. Планирование не требуется.")
        return True

    # 3. Формируем общий "пул заказов", умножая план на кол-во подписчиков
    total_demand = defaultdict(int)
    for persona_id, user_ids in subscriptions.items():
        persona_plan = daily_plan.get(persona_id, {})
        for category, count in persona_plan.items():
            total_demand[category] += count * len(user_ids)

    if not total_demand:
        print("     [INFO] План на сегодня не затрагивает активных подписчиков.")
        return True
    print("     Общая потребность в темах на сегодня:", dict(total_demand))

    # 4. "Бронируем" темы и проверяем нехватку
    booked_topics = defaultdict(list)
    shortage_alerts = []
    for category, needed_count in total_demand.items():
        available_in_cat = available_topics.get(category, [])
        available_count = len(available_in_cat)
        if available_count < needed_count:
            alert = f"Нехватка тем '{category}': нужно {needed_count}, доступно {available_count}."
            print(f"     [WARNING] {alert}")
            shortage_alerts.append(alert)
            booked_topics[category] = available_in_cat  # Берем все, что есть
        else:
            booked_topics[category] = available_in_cat[:needed_count]  # Берем нужное количество

    if shortage_alerts:
        send_admin_alert("⚠️ *Нехватка тем в Daily Planner:*\n" + "\n".join(shortage_alerts))
        # TODO: Сохранить информацию о нехватке для уведомления пользователей

    # 5. Распределяем "забронированные" темы по пользователям
    assignments = []
    topic_counters = defaultdict(int)
    for persona_id, user_ids in subscriptions.items():
        persona_plan = daily_plan.get(persona_id, {})
        for user_id in user_ids:
            for category, count in persona_plan.items():
                start_index = topic_counters[category]
                end_index = start_index + count
                topics_for_user = booked_topics.get(category, [])[start_index:end_index]

                for topic in topics_for_user:
                    assignments.append({"topic_id": topic['id'], "user_id": user_id, "persona_id": persona_id})

                # Сдвигаем счетчик для следующей "порции" тем
                topic_counters[category] += len(topics_for_user)

    # 6. Сохраняем назначения в БД
    assigned_count = assign_topics_in_db(assignments)
    print(f"     Всего назначено {assigned_count} тем для генерации.")

    return True


if __name__ == '__main__':
    if run_daily_planner():
        print("\n--- Модуль Daily Planner успешно завершил работу ---")
    else:
        print("\n--- Работа модуля Daily Planner завершилась с ошибкой ---")