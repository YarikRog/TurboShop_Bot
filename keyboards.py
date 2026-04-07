from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👟 Чоловічі"), KeyboardButton("👠 Жіночі"))
    keyboard.row(KeyboardButton("🔥 Наші новинки"), KeyboardButton("💬 Менеджер"))
    return keyboard

def get_product_navigation(index, total, article):
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Ряд 1: Навігація
    btns = []
    if index > 0:
        btns.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"prev_{index}"))
    if index < total - 1:
        btns.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"next_{index}"))
    keyboard.row(*btns)

    # Ряд 2: Опис та Купити (ТУТ ВИПРАВЛЕНО НА ARTICLE)
    keyboard.row(InlineKeyboardButton(text="📝 Опис", callback_data=f"descr_{article}"))
    keyboard.row(InlineKeyboardButton(text="💎 ЗАМОВИТИ 💎", callback_data=f"buy_{article}"))

    # Ряд 3: Додатково
    keyboard.row(
        InlineKeyboardButton(text="📸 Більше фото", callback_data=f"more_photos_{article}"),
        InlineKeyboardButton(text="📐 Таблиця", callback_data="size_grid")
    )
    return keyboard

def get_contact_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(
        KeyboardButton("📱 Надіслати контакт", request_contact=True)
    )

def get_brands_keyboard(brands):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for b in brands: markup.insert(KeyboardButton(f"🔹 {b}"))
    markup.add(KeyboardButton("🏠 Головне меню"))
    return markup

def get_sizes_keyboard(sizes):
    markup = InlineKeyboardMarkup(row_width=4)
    markup.add(*[InlineKeyboardButton(text=str(s), callback_data=f"size_{s}") for s in sizes])
    return markup
