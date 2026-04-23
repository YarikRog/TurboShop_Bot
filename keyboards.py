from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_admin=False):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👟 Чоловічі"), KeyboardButton("👠 Жіночі"))
    keyboard.row(KeyboardButton("🔥 Наші новинки"), KeyboardButton("🎯 Підібрати пару"))
    keyboard.row(KeyboardButton("🛒 Кошик"), KeyboardButton("💬 Менеджер"))
    if is_admin:
        keyboard.row(KeyboardButton("➕ Додати товар"), KeyboardButton("📤 Опублікувати товар"))
    return keyboard


def get_brands_keyboard(brands):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for brand in brands:
        keyboard.insert(KeyboardButton(f"🔹 {brand}"))
    keyboard.add(KeyboardButton("🏠 Головне меню"))
    return keyboard


def get_sizes_keyboard(sizes):
    keyboard = InlineKeyboardMarkup(row_width=4)
    buttons = [InlineKeyboardButton(text=str(size), callback_data=f"size_{str(size)[:20]}") for size in sizes]
    keyboard.add(*buttons)
    return keyboard


def get_product_navigation(index, total, article, sizes=None, current_size=None, enable_size_picker=False):
    keyboard = InlineKeyboardMarkup(row_width=2)

    if enable_size_picker and sizes:
        size_buttons = []
        for size in sizes[:12]:
            label = f"• {size}" if str(size) == str(current_size) else str(size)
            size_buttons.append(InlineKeyboardButton(text=label, callback_data=f"picksize_{article}:{size}"))
        keyboard.add(*size_buttons)

    btns = []
    if index > 0:
        btns.append(InlineKeyboardButton(text="⬅️", callback_data=f"prev_{index}"))
    btns.append(InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="ignore"))
    if index < total - 1:
        btns.append(InlineKeyboardButton(text="➡️", callback_data=f"next_{index}"))
    keyboard.row(*btns)

    keyboard.row(InlineKeyboardButton(text="📝 ОПИС ТА СКЛАД", callback_data=f"descr_{article}"))
    keyboard.row(InlineKeyboardButton(text="💎 ЗАМОВИТИ ЦЮ МОДЕЛЬ 💎", callback_data=f"buy_{article}"))
    keyboard.row(
        InlineKeyboardButton(text="📸 ВСІ ФОТО", callback_data=f"more_photos_{article}"),
        InlineKeyboardButton(text="📐 РОЗМІРНА СІТКА", callback_data="show_grid_alert")
    )
    return keyboard


def get_contact_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("📱 Поділитися номером телефону", request_contact=True))
    keyboard.add(KeyboardButton("❌ Скасувати"))
    return keyboard


def get_cancel_keyboard(*extra_buttons):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for text in extra_buttons:
        keyboard.add(KeyboardButton(text))
    keyboard.add(KeyboardButton("❌ Скасувати"))
    return keyboard


def get_confirm_keyboard(confirm_data="admin_save_product", cancel_data="admin_cancel_product"):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton(text="✅ Зберегти", callback_data=confirm_data),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=cancel_data),
    )
    return keyboard


def get_save_or_publish_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.row(InlineKeyboardButton(text="✅ Зберегти", callback_data="admin_save_product"))
    keyboard.row(InlineKeyboardButton(text="📤 Зберегти і опублікувати", callback_data="admin_save_and_publish_product"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_product"))
    return keyboard


def get_publish_products_keyboard(products):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for product in products[:20]:
        article = str(product.get("Артикул", "")).strip()
        title = f"{article} | {product.get('Бренд', '')} {product.get('Модель', '')}"
        keyboard.add(InlineKeyboardButton(text=title[:64], callback_data=f"preview_publish_{article}"))
    keyboard.add(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_publish"))
    return keyboard


def get_publish_preview_keyboard(article):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.row(InlineKeyboardButton(text="📤 Опублікувати в групу", callback_data=f"publish_{article}"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад до списку", callback_data="back_to_publish_list"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_publish"))
    return keyboard
