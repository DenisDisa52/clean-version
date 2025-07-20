import os
import sqlite3
from datetime import date, timedelta
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

from database_manager import get_db_connection

"""
Модуль, реализующий логику Telegram-бота для взаимодействия с пользователем.
Позволяет выбирать и настраивать подписку на контент от разных "персон".
Также отвечает за доставку готовых дайджестов.
"""

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# --- Функции для работы с базой данных ---

def add_or_update_user(user_id: int, username: str | None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)"
        cursor.execute(sql, (user_id, username))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка БД (add_or_update_user): {e}")
    finally:
        if conn:
            conn.close()


def get_all_personas():
    try:
        conn = get_db_connection()
        personas = conn.execute("SELECT id, persona_name FROM personas ORDER BY id").fetchall()
        return personas
    except sqlite3.Error as e:
        print(f"Ошибка БД (get_all_personas): {e}")
        return []
    finally:
        if conn:
            conn.close()


# --- ФУНКЦИЯ для получения полной информации о персоне и ее плане ---
def get_persona_details(persona_id: int):
    details = {}
    try:
        conn = get_db_connection()
        # Получаем основную информацию о персоне
        persona_info = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
        if not persona_info:
            return None
        details['info'] = persona_info

        # Получаем недельный план для этой персоны

        today = date.today()
        week_start_date = today - timedelta(days=today.weekday())
        week_start_str = week_start_date.strftime('%Y-%m-%d')

        plan_info = conn.execute(
            "SELECT category, target_count FROM weekly_plan WHERE persona_id = ? AND week_start_date = ?",
            (persona_id, week_start_str)
        ).fetchall()
        details['plan'] = plan_info

        return details
    except sqlite3.Error as e:
        print(f"Ошибка БД (get_persona_details): {e}")
        return None
    finally:
        if conn:
            conn.close()


def set_user_persona(user_id: int, persona_id: int):
    try:
        conn = get_db_connection()
        conn.execute("UPDATE users SET subscribed_persona_id = ? WHERE id = ?", (persona_id, user_id))
        conn.commit()
        print(f"Пользователю {user_id} установлена персона с ID: {persona_id}")
    except sqlite3.Error as e:
        print(f"Ошибка БД (set_user_persona): {e}")
    finally:
        if conn:
            conn.close()


# --- Вспомогательные функции для создания сообщений и клавиатур ---

def create_selection_keyboard():
    """Создает клавиатуру для первоначального выбора персоны."""
    personas = get_all_personas()
    keyboard = []
    for persona in personas:
        # ПРЕФИКС 'select_persona_' для идентификации действия
        button = [InlineKeyboardButton(persona['persona_name'], callback_data=f"select_persona_{persona['id']}")]
        keyboard.append(button)
    return InlineKeyboardMarkup(keyboard)


def create_confirmation_keyboard(persona_id: int):
    """Создает клавиатуру с кнопками 'Подтвердить' и 'Назад'."""
    keyboard = [
        [  # Один ряд с двумя кнопками
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_persona_{persona_id}"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_selection")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# --- Обработчики Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет начальное сообщение с выбором персон."""
    user = update.effective_user
    if not user: return
    add_or_update_user(user.id, user.username)

    reply_markup = create_selection_keyboard()
    await update.message.reply_text(
        "Добро пожаловать! Пожалуйста, выберите ваш основной стиль для генерации статей:",
        reply_markup=reply_markup
    )


async def show_confirmation_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, persona_id: int):
    """Показывает экран с описанием персоны и кнопками подтверждения."""
    query = update.callback_query
    details = get_persona_details(persona_id)
    if not details:
        await query.edit_message_text("Ошибка: не удалось найти информацию о данном стиле.")
        return

    # Формируем текст сообщения
    persona_info = details['info']
    plan_info = details['plan']

    text = f"Вы выбрали: *{persona_info['persona_name']}*\n\n"
    text += f"_{persona_info['description']}_\n\n"

    if plan_info:
        text += "📝 *План на эту неделю:*\n"
        for item in plan_info:
            text += f"  - {item['category']}: {item['target_count']} шт.\n"
    else:
        text += "📝 *План на эту неделю еще не сформирован.*\n"

    reply_markup = create_confirmation_keyboard(persona_id)
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='Markdown')


async def confirm_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, persona_id: int):
    """Окончательно сохраняет выбор пользователя."""
    query = update.callback_query
    user_id = query.from_user.id
    set_user_persona(user_id, persona_id)

    details = get_persona_details(persona_id)
    persona_name = details['info']['persona_name'] if details else "Выбранный стиль"

    await query.edit_message_text(text=f"Отлично! Ваш выбор сохранен: *{persona_name}*.\n\n"
                                       f"Вы будете получать статьи, написанные в этой манере.",
                                  parse_mode='Markdown')


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главный обработчик-диспетчер для всех кнопок."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data

    if callback_data.startswith("select_persona_"):
        persona_id = int(callback_data.split("_")[2])
        await show_confirmation_screen(update, context, persona_id)

    elif callback_data.startswith("confirm_persona_"):
        persona_id = int(callback_data.split("_")[2])
        await confirm_selection(update, context, persona_id)

    elif callback_data == "back_to_selection":
        # Просто отправляем исходное сообщение с выбором заново
        reply_markup = create_selection_keyboard()
        await query.edit_message_text(
            "Пожалуйста, выберите ваш основной стиль для генерации статей:",
            reply_markup=reply_markup
        )

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ ГОТОВЫХ АРХИВОВ ---

async def send_digest_to_user(application: Application, user_id: int, zip_path: str):
    """
    Асинхронно отправляет готовый ZIP-архив указанному пользователю.
    """
    try:
        with open(zip_path, 'rb') as zip_file:
            await application.bot.send_document(
                chat_id=user_id,
                document=zip_file,
                filename=os.path.basename(zip_path),
                caption="✅ Ваш ежедневный дайджест готов!"
            )
        print(f"     [DELIVERY] ZIP-архив успешно отправлен пользователю {user_id}.")
        return True

    except Exception as e:
        print(f"     [DELIVERY_ERROR] Не удалось отправить архив пользователю {user_id}: {e}")
        return False


def main() -> None:
    if not BOT_TOKEN:
        print("ОШИБКА: Токен для Telegram бота не найден.")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запускается в режиме long polling...")
    application.run_polling()


if __name__ == '__main__':
    main()