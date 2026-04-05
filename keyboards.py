from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# 1. Головне меню
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👟 Чоловічі"), KeyboardButton("👠 Жіночі"))
    keyboard.row(KeyboardButton("🔥 Наші новинки"), KeyboardButton("🎯 Підібрати пару"))
    keyboard.row(KeyboardButton("🛒 Кошик"), KeyboardButton("💬 Менеджер"))
    return keyboard

# 2. Кнопки брендів
def get_brands_keyboard(brands):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for brand in brands:
        keyboard.insert(KeyboardButton(f"🔹 {brand}"))
    keyboard.add(KeyboardButton("🏠 Головне меню"))
    return keyboard

# 3. Кнопки вибору розміру
def get_sizes_keyboard(sizes):
    keyboard = InlineKeyboardMarkup(row_width=4)
    buttons = [InlineKeyboardButton(text=str(size), callback_data=f"size_{size}") for size in sizes]
    keyboard.add(*buttons)
    return keyboard

# 4. Картка товару (Навігація як на скріні)
def get_product_navigation(index, total, article):
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Ряд 1: Навігація
    btn_prev = InlineKeyboardButton(text="⬅️", callback_data=f"prev_{index}")
    btn_count = InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="ignore")
    btn_next = InlineKeyboardButton(text="➡️", callback_data=f"next_{index}")
    keyboard.row(btn_prev, btn_count, btn_next)

    # Ряд 2: Замовити
    keyboard.row(InlineKeyboardButton(text="💎 ЗАМОВИТИ ЦЮ МОДЕЛЬ 💎", callback_data=f"buy_{index}"))

    # Ряд 3: Сервіс (📸 ВСІ ФОТО та 📐 СІТКА в один ряд)
    btn_photos = InlineKeyboardButton(text="📸 ВСІ ФОТО", callback_data=f"more_photos_{article}")
    btn_grid = InlineKeyboardButton(text="📐 РОЗМІРНА СІТКА", callback_data="show_grid_alert")
    keyboard.row(btn_photos, btn_grid)

    return keyboard

# 5. Контакт
def get_contact_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("📱 Поділитися номером телефону", request_contact=True))
    return keyboard
