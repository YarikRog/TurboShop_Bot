from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# 1. Головне меню (Вибір статі)
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("👟 Чоловічі"), KeyboardButton("👠 Жіночі"))
    return keyboard

# 2. Кнопки брендів
def get_brands_keyboard(brands):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for brand in brands:
        keyboard.insert(KeyboardButton(f"🔹 {brand}"))
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

# 3. Кнопки вибору розміру
def get_sizes_keyboard(sizes):
    keyboard = InlineKeyboardMarkup(row_width=4)
    buttons = []
    for size in sizes:
        buttons.append(InlineKeyboardButton(text=str(size), callback_data=f"size_{size}"))
    keyboard.add(*buttons)
    return keyboard

# 4. ГОЛОВНИЙ ГОРТАЧ (Оновлений UX: Замовити — головна кнопка на весь рядок)
def get_product_navigation(index, total, article):
    keyboard = InlineKeyboardMarkup(row_width=3)

    # 1 РЯД: Навігація (стрілки та лічильник)
    btn_prev = InlineKeyboardButton(text="⬅️", callback_data=f"prev_{index}")
    btn_count = InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="ignore_count")
    btn_next = InlineKeyboardButton(text="➡️", callback_data=f"next_{index}")

    nav_row = []
    if index > 0:
        nav_row.append(btn_prev)
    nav_row.append(btn_count)
    if index < total - 1:
        nav_row.append(btn_next)

    keyboard.row(*nav_row)

    # 2 РЯД: ГОЛОВНА КНОПКА ЗАМОВЛЕННЯ (Тепер вона величезна і по центру)
    # Використовуємо .add(), щоб кнопка розтягнулася на всю ширину
    btn_buy = InlineKeyboardButton(text="💎 ЗАМОВИТИ ЦЮ МОДЕЛЬ 💎", callback_data=f"buy_{index}")
    keyboard.add(btn_buy)

    # 3 РЯД: Сервісні кнопки (Додаткові фото та сітка в одному рядку)
    btn_more_photos = InlineKeyboardButton(text="📸 Додаткові фото", callback_data=f"more_photos_{article}")
    btn_grid = InlineKeyboardButton(text="📐 Розмірна сітка", callback_data="show_grid_now")

    keyboard.row(btn_more_photos, btn_grid)

    return keyboard

# 5. Кнопка запиту ТЕЛЕФОНУ
def get_contact_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    button = KeyboardButton("📱 Поділитися номером телефону", request_contact=True)
    keyboard.add(button)
    return keyboard