from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👟 Чоловічі"), KeyboardButton("👠 Жіночі"))
    keyboard.row(KeyboardButton("🔥 Наші новинки"), KeyboardButton("🎯 Підібрати пару"))
    keyboard.row(KeyboardButton("🛒 Кошик"), KeyboardButton("💬 Менеджер"))
    return keyboard

def get_brands_keyboard(brands):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for brand in brands:
        keyboard.insert(KeyboardButton(f"🔹 {brand}"))
    keyboard.add(KeyboardButton("🏠 Головне меню"))
    return keyboard

def get_sizes_keyboard(sizes):
    keyboard = InlineKeyboardMarkup(row_width=4)
    # Обмеження на довжину callback_data для уникнення Error 400
    buttons = [InlineKeyboardButton(text=str(size), callback_data=f"size_{str(size)[:20]}") for size in sizes]
    keyboard.add(*buttons)
    return keyboard

def get_product_navigation(index, total, article):
    keyboard = InlineKeyboardMarkup(row_width=2)
    # Ряд 1: Навігація
    btns = []
    if index > 0: btns.append(InlineKeyboardButton(text="⬅️", callback_data=f"prev_{index}"))
    btns.append(InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="ignore"))
    if index < total - 1: btns.append(InlineKeyboardButton(text="➡️", callback_data=f"next_{index}"))
    keyboard.row(*btns)

    # Ряд 2: Опис
    keyboard.row(InlineKeyboardButton(text="📝 ОПИС ТА СКЛАД", callback_data=f"descr_{article}"))
    # Ряд 3: Замовлення
    keyboard.row(InlineKeyboardButton(text="💎 ЗАМОВИТИ ЦЮ МОДЕЛЬ 💎", callback_data=f"buy_{article}"))
    
    # Ряд 4: Додатково
    keyboard.row(
        InlineKeyboardButton(text="📸 ВСІ ФОТО", callback_data=f"more_photos_{article}"),
        InlineKeyboardButton(text="📐 РОЗМІРНА СІТКА", callback_data="show_grid_alert")
    )
    return keyboard

def get_contact_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(
        KeyboardButton("📱 Поділитися номером телефону", request_contact=True)
    )
