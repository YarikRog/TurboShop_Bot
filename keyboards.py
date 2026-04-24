from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_admin=False):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("👟 Чоловічі"), KeyboardButton("👠 Жіночі"))
    keyboard.row(KeyboardButton("🔥 Наші новинки"), KeyboardButton("🎯 Підібрати пару"))
    keyboard.row(KeyboardButton("🛒 Кошик"), KeyboardButton("💬 Менеджер"))
    if is_admin:
        keyboard.row(KeyboardButton("➕ Додати товар"), KeyboardButton("📤 Опублікувати товар"))
        keyboard.row(KeyboardButton("📅 Розпланувати всі пости"))
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


def get_order_confirmation_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("✅ Підтвердити замовлення"))
    keyboard.row(KeyboardButton("✏️ Змінити телефон"), KeyboardButton("✏️ Змінити ім’я"))
    keyboard.row(KeyboardButton("✏️ Змінити доставку"))
    keyboard.row(KeyboardButton("❌ Скасувати"))
    return keyboard


def get_after_order_keyboard(manager_username=None, is_admin=False):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    if manager_username:
        username = str(manager_username).strip().replace("@", "")
        keyboard.row(KeyboardButton(f"💬 Написати менеджеру @{username}"))

    keyboard.row(KeyboardButton("🏠 Головне меню"))

    if is_admin:
        keyboard.row(KeyboardButton("➕ Додати товар"), KeyboardButton("📤 Опублікувати товар"))
        keyboard.row(KeyboardButton("📅 Розпланувати всі пости"))

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
    keyboard.row(InlineKeyboardButton(text="✏️ Змінити", callback_data="admin_edit_draft_product"))
    keyboard.row(InlineKeyboardButton(text="✅ Зберегти", callback_data="admin_save_product"))
    keyboard.row(InlineKeyboardButton(text="📤 Зберегти і опублікувати", callback_data="admin_save_and_publish_product"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_product"))
    return keyboard


def get_draft_edit_fields_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)

    fields = [
        ("Артикул", "article"),
        ("Бренд", "brand"),
        ("Модель", "model"),
        ("Категорія", "category"),
        ("Сезон", "season"),
        ("Ціна", "price"),
        ("Розміри", "sizes"),
        ("Опис", "description"),
        ("Фото", "photo_ids"),
        ("Залишок", "stock"),
    ]

    for title, field in fields:
        keyboard.insert(InlineKeyboardButton(text=title, callback_data=f"admin_edit_draft_field_{field}"))

    keyboard.row(InlineKeyboardButton(text="⬅️ Назад до перевірки", callback_data="admin_back_to_draft_preview"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_product"))
    return keyboard


def get_publish_products_keyboard(products):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for product in products[:20]:
        article = str(product.get("Артикул") or product.get("article") or "").strip()
        brand = str(product.get("Бренд") or product.get("brand") or "").strip()
        model = str(product.get("Модель") or product.get("model") or "").strip()
        status = str(product.get("Статус") or product.get("status") or "draft").strip()

        if not article:
            continue

        title = f"{article} | {brand} {model} | {status}"
        keyboard.add(InlineKeyboardButton(text=title[:64], callback_data=f"preview_publish_{article}"))

    keyboard.add(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_publish"))
    return keyboard


def get_publish_preview_keyboard(article):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.row(InlineKeyboardButton(text="✏️ Змінити", callback_data=f"edit_product_{article}"))
    keyboard.row(InlineKeyboardButton(text="📤 Опублікувати в групу", callback_data=f"publish_{article}"))
    keyboard.row(InlineKeyboardButton(text="🕒 Запланувати пост", callback_data=f"schedule_product_{article}"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад до списку", callback_data="back_to_publish_list"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_publish"))
    return keyboard


def get_schedule_product_keyboard(article):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton(text="Сьогодні 09:00", callback_data=f"schedule_one_{article}_today_09"),
        InlineKeyboardButton(text="Сьогодні 15:00", callback_data=f"schedule_one_{article}_today_15"),
    )
    keyboard.row(
        InlineKeyboardButton(text="Сьогодні 20:00", callback_data=f"schedule_one_{article}_today_20"),
    )
    keyboard.row(
        InlineKeyboardButton(text="Завтра 09:00", callback_data=f"schedule_one_{article}_tomorrow_09"),
        InlineKeyboardButton(text="Завтра 15:00", callback_data=f"schedule_one_{article}_tomorrow_15"),
    )
    keyboard.row(
        InlineKeyboardButton(text="Завтра 20:00", callback_data=f"schedule_one_{article}_tomorrow_20"),
    )
    keyboard.row(InlineKeyboardButton(text="⬅️ Назад до прев’ю", callback_data=f"preview_publish_{article}"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_publish"))
    return keyboard


def get_saved_edit_fields_keyboard(article):
    keyboard = InlineKeyboardMarkup(row_width=2)

    fields = [
        ("Бренд", "brand"),
        ("Модель", "model"),
        ("Категорія", "category"),
        ("Сезон", "season"),
        ("Ціна", "price"),
        ("Розміри", "sizes"),
        ("Опис", "description"),
        ("Фото", "photo_ids"),
        ("Залишок", "stock"),
        ("Статус", "status"),
    ]

    for title, field in fields:
        keyboard.insert(InlineKeyboardButton(text=title, callback_data=f"edit_saved_field_{article}_{field}"))

    keyboard.row(InlineKeyboardButton(text="⬅️ Назад до прев’ю", callback_data=f"preview_publish_{article}"))
    keyboard.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel_publish"))
    return keyboard
