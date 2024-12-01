import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# Токен вашего бота
BOT_TOKEN = "XXXXXXXXX"

# ID чата, куда будут отправляться заявки
COMMON_CHAT_ID = -XXXXX


# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("support_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            phone_number TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            group_name TEXT,
            problem TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Клавиатуры
phone_request_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
phone_request_kb.add(KeyboardButton("📞 Отправить номер телефона", request_contact=True))

group_menu = ReplyKeyboardMarkup(resize_keyboard=True)
group_menu.add(
    KeyboardButton("Проблема с МИС"),
    KeyboardButton("Проблема с сетью")
)
group_menu.add(
    KeyboardButton("Проблема с оборудованием"),
    KeyboardButton("Проблема с другим ПО")
)
group_menu.add(
    KeyboardButton("Проблема с ЭЦП"),
    KeyboardButton("Назад")
)

main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(KeyboardButton("Оставить заявку"))

# Обработчики
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    """Приветственное сообщение с запросом номера телефона."""
    await message.answer(
        "Привет! Пожалуйста, отправьте свой номер телефона для продолжения.",
        reply_markup=phone_request_kb
    )

@dp.message_handler(content_types=["contact"])
async def handle_contact(message: types.Message):
    """Сохраняет номер телефона пользователя."""
    if message.contact and message.contact.user_id == message.from_user.id:
        user_id = message.from_user.id
        username = message.from_user.username
        phone_number = message.contact.phone_number

        conn = sqlite3.connect("support_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, phone_number) VALUES (?, ?, ?)",
            (user_id, username, phone_number)
        )
        conn.commit()
        conn.close()

        await message.answer(
            "Спасибо! Ваш номер телефона сохранён. Теперь вы можете оставить заявку.",
            reply_markup=main_menu
        )
    else:
        await message.answer("Ошибка: пожалуйста, отправьте свой номер через кнопку.")

@dp.message_handler(lambda message: message.text == "Оставить заявку")
async def select_group(message: types.Message):
    """Позволяет выбрать группу заявки."""
    await message.answer("Выберите группу вашей заявки:", reply_markup=group_menu)

@dp.message_handler(lambda message: message.text in [
    "Проблема с МИС",
    "Проблема с сетью",
    "Проблема с оборудованием",
    "Проблема с другим ПО",
    "Проблема с ЭЦП"
])
async def request_problem_description(message: types.Message):
    """Запрашивает описание проблемы для выбранной группы."""
    group_name = message.text
    conn = sqlite3.connect("support_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tickets (user_id, username, group_name, status) VALUES (?, ?, ?, ?)",
        (message.from_user.id, message.from_user.username, group_name, "in_progress")
    )
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await message.answer(
        f"Вы выбрали группу: {group_name}. Теперь опишите вашу проблему.",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад")),
    )

@dp.message_handler(lambda message: True, content_types=["text"])
async def save_ticket(message: types.Message):
    """Сохраняет описание заявки и отправляет её в общий чат."""
    conn = sqlite3.connect("support_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, group_name FROM tickets WHERE user_id = ? AND status = 'in_progress' ORDER BY id DESC LIMIT 1",
        (message.from_user.id,)
    )
    ticket = cursor.fetchone()

    if not ticket:
        await message.answer("Пожалуйста, выберите группу заявки, прежде чем описывать проблему.")
        return

    ticket_id, group_name = ticket
    cursor.execute(
        "UPDATE tickets SET problem = ?, status = 'open' WHERE id = ?",
        (message.text, ticket_id)
    )
        # Извлекаем номер телефона пользователя
    cursor.execute("SELECT phone_number FROM users WHERE user_id = ?", (message.from_user.id,))
    user = cursor.fetchone()
    phone_number = user[0] if user else "номер отсутствует"
    conn.commit()
    conn.close()

    inline_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(f"Выполнено (ID: {ticket_id})", callback_data=f"complete_{ticket_id}")
    )

    await bot.send_message(
        COMMON_CHAT_ID,
        f"🆕 Новая заявка (ID: {ticket_id}):\n"
        f"👤 Пользователь: @{message.from_user.username}\n"
        f"📂 Группа: {group_name}\n"
        f"📞 Номер телефона: {phone_number}\n"
        f"📝 Проблема: {message.text}",
        reply_markup=inline_kb,
    )

    await message.answer("Ваша заявка успешно отправлена! Ожидайте ответа.", reply_markup=main_menu)

@dp.callback_query_handler(lambda call: call.data.startswith("complete_"))
async def complete_ticket(call: types.CallbackQuery):
    """Помечает заявку как выполненную и уведомляет пользователя."""
    ticket_id = int(call.data.split("_")[1])

    conn = sqlite3.connect("support_bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, username, problem FROM tickets WHERE id = ? AND status = 'open'", (ticket_id,))
    ticket = cursor.fetchone()

    if not ticket:
        await call.answer("Эта заявка уже обработана или не существует.", show_alert=True)
        return

    ticket_id, user_id, username, problem = ticket

    cursor.execute("SELECT phone_number FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    phone_number = user[0] if user else "номер отсутствует"

    cursor.execute("UPDATE tickets SET status = 'completed' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()

    await call.message.edit_text(
        call.message.text + "\n\n✅ Статус: Выполнено",
        reply_markup=None
    )
    await call.answer("Заявка помечена как выполненная.")

    try:
        await bot.send_message(
            user_id,
            f"✅ Ваша заявка (ID: {ticket_id}) выполнена!\n\n"
            f"📝 Описание: {problem}\n"
            f"📞 Номер телефона: {phone_number}\n"
            "Спасибо за обращение в техподдержку!"
        )
    except Exception as e:
        print(f"Не удалось отправить сообщение пользователю @{username}: {e}")

    await bot.send_message(
        COMMON_CHAT_ID,
        f"✅ Заявка (ID: {ticket_id}) от @{username} выполнена.\n"
        f"📞 Номер телефона: {phone_number}\n"
        f"📝 Описание: {problem}"
    )

@dp.message_handler(lambda message: message.text == "Назад")
async def go_back(message: types.Message):
    """Возвращает пользователя в главное меню."""
    await message.answer("Вы вернулись в главное меню.", reply_markup=main_menu)

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
