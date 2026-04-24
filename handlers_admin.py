import os
import asyncio
import logging
from datetime import datetime, timedelta, time
from urllib.parse import quote
from zoneinfo import ZoneInfo

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InputMediaPhoto

import database as db
import keyboards as kb

logger = logging.getLogger("TurboBot.Admin")

ADMIN_IDS = {int(item.strip()) for item in os.getenv("ADMIN_IDS", "").split(",") if item.strip().isdigit()}
SHOP_GROUP_ID = os.getenv("SHOP_GROUP_ID")
KYIV_TZ = ZoneInfo("Europe/Kyiv")
SLOT_HOURS = (9, 15, 20)

MEDIA_GROUP_BUFFER = {}
MEDIA_GROUP_TASKS = {}
MEDIA_GROUP_LOCK = asyncio.Lock()

FIELD_LABELS = {
    "article": "Артикул",
    "brand": "Бренд",
    "model": "Модель",
    "category": "Категорія",
    "season": "Сезон",
    "price": "Ціна",
    "sizes": "Розміри",
    "description": "Опис",
    "photo_ids": "Фото",
    "stock": "Залишок",
    "status": "Статус",
}


def is_admin(user_id):
    return int(user_id) in ADMIN_IDS


def _main_menu_for(user_id):
    return kb.main_menu(is_admin=is_admin(user_id))


def _get_article(product):
    if not isinstance(product, dict):
        return ""
    return str(product.get("Артикул") or product.get("article") or "").strip()


def _get_product_id(product):
    if not isinstance(product, dict):
        return ""
    return str(product.get("product_id") or product.get("ID") or "").strip()


def _get_status(product):
    if not isinstance(product, dict):
        return "draft"
    return str(product.get("Статус") or product.get("status") or "draft").strip()


def _get_publish_status(product):
    if not isinstance(product, dict):
        return ""
    return str(product.get("publish_status") or "").strip()


def _format_publish_at(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _build_schedule_datetime(day: str, hour: str):
    now = datetime.now(KYIV_TZ)
    target_date = now.date() if day == "today" else (now + timedelta(days=1)).date()
    target_dt = datetime.combine(target_date, time(hour=int(hour), minute=0), KYIV_TZ)
    rolled_to_tomorrow = False

    if target_dt <= now:
        target_dt = target_dt + timedelta(days=1)
        rolled_to_tomorrow = True

    return target_dt, rolled_to_tomorrow


def _next_future_slots(limit: int):
    now = datetime.now(KYIV_TZ)
    slots = []
    cursor_date = now.date()

    while len(slots) < limit:
        for hour in SLOT_HOURS:
            candidate = datetime.combine(cursor_date, time(hour=hour, minute=0), KYIV_TZ)
            if candidate > now:
                slots.append(candidate)
                if len(slots) >= limit:
                    break
        cursor_date = cursor_date + timedelta(days=1)

    return slots


def _is_schedulable_product(product):
    article = _get_article(product)
    status = _get_status(product).lower()
    publish_status = _get_publish_status(product).lower()

    if not article:
        return False

    if status in {"hidden", "sold_out"}:
        return False

    if publish_status in {"queued", "published"}:
        return False

    return True


def _product_exists(product, article):
    if not isinstance(product, dict):
        return False

    if product.get("ok") is False:
        return False

    product_article = _get_article(product)
    return bool(product_article and product_article == str(article).strip())


def _parse_photo_ids(raw_photos):
    raw = str(raw_photos or "")
    for delimiter in (";", "\n", "\r"):
        raw = raw.replace(delimiter, ",")
    photos = [photo.strip() for photo in raw.split(",") if photo.strip() and photo.strip().lower() != "none"]
    return list(dict.fromkeys(photos))


def _product_caption(product):
    article = _get_article(product)
    description = str(product.get("Опис") or product.get("description") or "").strip()
    short_description = description[:300] if description else "Опис буде додано менеджером."
    sizes = str(product.get("Розміри") or product.get("sizes") or "—").strip()

    return (
        f"👟 <b>{product.get('Бренд') or product.get('brand')} {product.get('Модель') or product.get('model')}</b>\n"
        f"🗂 Категорія: <b>{product.get('Категорія') or product.get('category') or '—'}</b>\n"
        f"🍂 Сезон: <b>{product.get('Сезон') or product.get('season') or '—'}</b>\n"
        f"💰 Ціна: <b>{product.get('Ціна') or product.get('price')} грн</b>\n"
        f"📏 Розміри: <b>{sizes}</b>\n"
        f"🆔 Артикул: <code>{article}</code>\n\n"
        f"{short_description}"
    )


def _draft_preview_text(data):
    return (
        f"Перевірте дані товару:\n\n"
        f"Артикул: {data.get('article', '—')}\n"
        f"Бренд: {data.get('brand', '—')}\n"
        f"Модель: {data.get('model', '—')}\n"
        f"Категорія: {data.get('category', '—')}\n"
        f"Сезон: {data.get('season', '—')}\n"
        f"Ціна: {data.get('price', '—')} грн\n"
        f"Розміри: {data.get('sizes', '—')}\n"
        f"Опис: {data.get('description', '—')}\n"
        f"Фото: {len(data.get('photo_ids', []))} шт.\n"
        f"Залишок: {data.get('stock', '—')}"
    )


def _draft_edit_menu_text(data):
    return (
        f"Що змінити?\n\n"
        f"Артикул: <code>{data.get('article', '—')}</code>\n"
        f"Бренд: <b>{data.get('brand', '—')}</b>\n"
        f"Модель: <b>{data.get('model', '—')}</b>\n"
        f"Категорія: <b>{data.get('category', '—')}</b>\n"
        f"Сезон: <b>{data.get('season', '—')}</b>\n"
        f"Ціна: <b>{data.get('price', '—')}</b>\n"
        f"Розміри: <b>{data.get('sizes', '—')}</b>\n"
        f"Опис: <i>{data.get('description', '—')}</i>\n"
        f"Фото: <b>{len(data.get('photo_ids', []))} шт.</b>\n"
        f"Залишок: <b>{data.get('stock', '—')}</b>\n\n"
        f"Натисни поле, яке треба змінити."
    )


def _saved_edit_menu_text(product):
    photos = _parse_photo_ids(product.get("Фото") or product.get("photo_ids") or "")
    return (
        f"Що змінити?\n\n"
        f"Артикул: <code>{_get_article(product)}</code>\n"
        f"Бренд: <b>{product.get('Бренд') or product.get('brand') or '—'}</b>\n"
        f"Модель: <b>{product.get('Модель') or product.get('model') or '—'}</b>\n"
        f"Категорія: <b>{product.get('Категорія') or product.get('category') or '—'}</b>\n"
        f"Сезон: <b>{product.get('Сезон') or product.get('season') or '—'}</b>\n"
        f"Ціна: <b>{product.get('Ціна') or product.get('price') or '—'}</b>\n"
        f"Розміри: <b>{product.get('Розміри') or product.get('sizes') or '—'}</b>\n"
        f"Опис: <i>{product.get('Опис') or product.get('description') or '—'}</i>\n"
        f"Фото: <b>{len(photos)} шт.</b>\n"
        f"Залишок: <b>{product.get('Залишок') or product.get('stock') or '—'}</b>\n"
        f"Статус: <b>{_get_status(product)}</b>\n\n"
        f"Натисни поле, яке треба змінити."
    )


async def _send_album_or_photo(bot, chat_id, photos, caption, reply_markup=None, action_text="Оформити замовлення 👇"):
    photos = list(dict.fromkeys([str(photo).strip() for photo in photos if str(photo).strip()]))

    if not photos:
        return await bot.send_photo(
            chat_id,
            photo="https://via.placeholder.com/500",
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    if len(photos) == 1:
        return await bot.send_photo(
            chat_id,
            photo=photos[0],
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    media = []
    for index, photo in enumerate(photos[:10]):
        if index == 0:
            media.append(InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=photo))

    messages = await bot.send_media_group(chat_id=chat_id, media=media)

    if reply_markup:
        await bot.send_message(
            chat_id,
            text=action_text,
            reply_markup=reply_markup,
        )

    return messages[0] if messages else None


async def _send_draft_preview(message_or_callback_message, state: FSMContext):
    data = await state.get_data()
    photo_ids = data.get("photo_ids", [])

    if not photo_ids:
        return await message_or_callback_message.answer("Спочатку додайте хоча б одне фото.")

    await AddProductState.confirmation.set()

    await _send_album_or_photo(
        message_or_callback_message.bot,
        message_or_callback_message.chat.id,
        photo_ids,
        _draft_preview_text(data),
        reply_markup=kb.get_save_or_publish_keyboard(),
        action_text="Дія з товаром 👇",
    )


def _validate_draft_value(field, value):
    value = str(value or "").strip()

    if not value:
        return None, "Значення не може бути порожнім."

    if field in {"price", "stock"}:
        raw = value.replace(" ", "").replace(",", ".")
        try:
            return int(float(raw)), None
        except ValueError:
            return None, "Тут має бути число. Наприклад: 3490"

    if field == "sizes":
        cleaned = ", ".join([item.strip() for item in value.replace(";", ",").split(",") if item.strip()])
        if not cleaned:
            return None, "Вкажи хоча б один розмір."
        return cleaned, None

    return value, None


class AddProductState(StatesGroup):
    waiting_for_article = State()
    waiting_for_brand = State()
    waiting_for_model = State()
    waiting_for_category = State()
    waiting_for_season = State()
    waiting_for_price = State()
    waiting_for_sizes = State()
    waiting_for_description = State()
    waiting_for_photos = State()
    waiting_for_stock = State()
    confirmation = State()


class EditDraftState(StatesGroup):
    waiting_for_value = State()
    waiting_for_photos = State()


class EditSavedState(StatesGroup):
    waiting_for_value = State()
    waiting_for_photos = State()


async def start_add_product(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("У вас немає доступу до цієї дії.")

    await state.finish()
    await AddProductState.waiting_for_article.set()
    await state.update_data(photo_ids=[])
    await message.answer("Введіть артикул товару:", reply_markup=kb.get_cancel_keyboard())


async def save_article(message: types.Message, state: FSMContext):
    article = str(message.text).strip()
    if not article:
        return await message.answer("Артикул обов'язковий.")

    existing = await db.get_product_by_article(article)

    if _product_exists(existing, article):
        return await message.answer("Товар з таким артикулом уже існує. Введіть інший артикул.")

    await state.update_data(article=article)
    await AddProductState.next()
    await message.answer("Введіть бренд:")


async def save_brand(message: types.Message, state: FSMContext):
    brand = str(message.text).strip()
    if not brand:
        return await message.answer("Бренд не може бути порожнім.")

    await state.update_data(brand=brand)
    await AddProductState.next()
    await message.answer("Введіть модель:")


async def save_model(message: types.Message, state: FSMContext):
    model = str(message.text).strip()
    if not model:
        return await message.answer("Модель не може бути порожньою.")

    await state.update_data(model=model)
    await AddProductState.next()
    await message.answer("Введіть категорію (наприклад, Чоловічі / Жіночі):")


async def save_category(message: types.Message, state: FSMContext):
    category = str(message.text).strip()
    if not category:
        return await message.answer("Категорія не може бути порожньою.")

    await state.update_data(category=category)
    await AddProductState.next()
    await message.answer("Введіть сезон (наприклад, демісезон / літо / зима):")


async def save_season(message: types.Message, state: FSMContext):
    season = str(message.text).strip()
    if not season:
        return await message.answer("Сезон не може бути порожнім.")

    await state.update_data(season=season)
    await AddProductState.next()
    await message.answer("Введіть ціну у грн:")


async def save_price(message: types.Message, state: FSMContext):
    value, error = _validate_draft_value("price", message.text)
    if error:
        return await message.answer(error)

    await state.update_data(price=value)
    await AddProductState.next()
    await message.answer("Введіть розміри через кому, наприклад: 36, 37, 38")


async def save_sizes(message: types.Message, state: FSMContext):
    value, error = _validate_draft_value("sizes", message.text)
    if error:
        return await message.answer(error)

    await state.update_data(sizes=value)
    await AddProductState.next()
    await message.answer("Додайте опис товару:")


async def save_description(message: types.Message, state: FSMContext):
    description = str(message.text).strip()
    if not description:
        return await message.answer("Опис не може бути порожнім.")

    await state.update_data(description=description)
    await AddProductState.next()
    await message.answer(
        "Надішліть одне або кілька фото товару. Коли завершите, натисніть '✅ Фото готово'.",
        reply_markup=kb.get_cancel_keyboard("✅ Фото готово"),
    )


async def _flush_media_group(key, state: FSMContext, message: types.Message):
    await asyncio.sleep(1.2)

    async with MEDIA_GROUP_LOCK:
        new_photo_ids = MEDIA_GROUP_BUFFER.pop(key, [])
        MEDIA_GROUP_TASKS.pop(key, None)

    if not new_photo_ids:
        return

    data = await state.get_data()
    current_photo_ids = list(data.get("photo_ids", []))

    added = 0
    for photo_id in new_photo_ids:
        if photo_id not in current_photo_ids:
            current_photo_ids.append(photo_id)
            added += 1

    await state.update_data(photo_ids=current_photo_ids)

    await message.answer(f"✅ Додано фото: {added}. Всього фото: {len(current_photo_ids)}")


async def collect_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        return await message.answer("Будь ласка, надішліть фото як зображення Telegram.")

    photo_id = message.photo[-1].file_id
    media_group_id = message.media_group_id

    if not media_group_id:
        data = await state.get_data()
        photo_ids = list(data.get("photo_ids", []))

        if photo_id not in photo_ids:
            photo_ids.append(photo_id)
            await state.update_data(photo_ids=photo_ids)
            return await message.answer(f"✅ Фото додано: {len(photo_ids)}")

        return await message.answer(f"⚠️ Це фото вже додано. Всього фото: {len(photo_ids)}")

    key = (message.chat.id, message.from_user.id, media_group_id)

    async with MEDIA_GROUP_LOCK:
        if key not in MEDIA_GROUP_BUFFER:
            MEDIA_GROUP_BUFFER[key] = []

        if photo_id not in MEDIA_GROUP_BUFFER[key]:
            MEDIA_GROUP_BUFFER[key].append(photo_id)

        if key not in MEDIA_GROUP_TASKS:
            MEDIA_GROUP_TASKS[key] = asyncio.create_task(_flush_media_group(key, state, message))


async def finish_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_ids = data.get("photo_ids", [])
    if not photo_ids:
        return await message.answer("Спочатку додайте хоча б одне фото.")

    current_state = await state.get_state()

    if current_state == EditDraftState.waiting_for_photos.state:
        await state.update_data(photo_ids=photo_ids)
        await message.answer("✅ Фото оновлено.", reply_markup=kb.get_cancel_keyboard())
        return await _send_draft_preview(message, state)

    if current_state == EditSavedState.waiting_for_photos.state:
        article = data.get("edit_article")
        result = await db.update_product_field(article, "photo_ids", ",".join(photo_ids))

        if result is None:
            return await message.answer("❌ Не вдалося оновити фото в таблиці. Перевір GAS.")

        await state.finish()
        product = await db.get_product_by_article(article)
        await message.answer("✅ Фото оновлено.")
        return await send_publish_preview(message.chat.id, product, message.bot)

    await AddProductState.next()
    await message.answer("Введіть залишок на складі:", reply_markup=kb.get_cancel_keyboard())


async def save_stock(message: types.Message, state: FSMContext):
    value, error = _validate_draft_value("stock", message.text)
    if error:
        return await message.answer(error)

    await state.update_data(stock=value)
    await _send_draft_preview(message, state)


async def start_edit_draft_product(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer()

    data = await state.get_data()
    if not data:
        return await callback_query.message.answer("Немає даних для редагування.")

    await callback_query.message.answer(
        _draft_edit_menu_text(data),
        parse_mode="HTML",
        reply_markup=kb.get_draft_edit_fields_keyboard(),
    )


async def choose_draft_edit_field(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer()

    field = callback_query.data.replace("admin_edit_draft_field_", "", 1).strip()

    if field not in FIELD_LABELS:
        return await callback_query.message.answer("Невідоме поле.")

    data = await state.get_data()
    current_value = data.get(field, "")

    if field == "photo_ids":
        await EditDraftState.waiting_for_photos.set()
        await state.update_data(photo_ids=[])
        return await callback_query.message.answer(
            f"Поточних фото: {len(data.get('photo_ids', []))} шт.\n\n"
            f"Надішли нові фото. Старі фото будуть замінені.\n"
            f"Коли завершиш, натисни '✅ Фото готово'.",
            reply_markup=kb.get_cancel_keyboard("✅ Фото готово"),
        )

    await EditDraftState.waiting_for_value.set()
    await state.update_data(edit_field=field)

    await callback_query.message.answer(
        f"Поле: <b>{FIELD_LABELS[field]}</b>\n\n"
        f"Поточне значення:\n"
        f"<code>{current_value or '—'}</code>\n\n"
        f"Надішли нове значення:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard(),
    )


async def save_draft_edited_field(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("edit_field")

    if not field:
        return await message.answer("Не знайдено поле для редагування.")

    value, error = _validate_draft_value(field, message.text)
    if error:
        return await message.answer(error)

    if field == "article":
        existing = await db.get_product_by_article(str(value))
        if _product_exists(existing, str(value)):
            return await message.answer("Товар з таким артикулом уже існує. Введіть інший артикул.")

    await state.update_data({field: value, "edit_field": None})
    await message.answer(f"✅ Поле «{FIELD_LABELS[field]}» оновлено.")
    await _send_draft_preview(message, state)


async def back_to_draft_preview(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await _send_draft_preview(callback_query.message, state)


async def _save_product_from_state(state: FSMContext):
    data = await state.get_data()
    payload = {
        "article": data["article"],
        "brand": data["brand"],
        "model": data["model"],
        "category": data["category"],
        "season": data["season"],
        "price": data["price"],
        "sizes": data["sizes"],
        "description": data["description"],
        "photo_ids": ",".join(data.get("photo_ids", [])),
        "status": "draft",
        "stock": data["stock"],
    }
    return await db.create_product(payload), payload


async def confirm_save_product(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer("Зберігаю...")

    result, _ = await _save_product_from_state(state)
    await state.finish()

    if result is None:
        await callback_query.message.answer(
            "Не вдалося зберегти товар у Google Sheets. Перевірте GAS.",
            reply_markup=_main_menu_for(callback_query.from_user.id),
        )
    else:
        await callback_query.message.answer(
            "✅ Товар збережено як чернетку.",
            reply_markup=_main_menu_for(callback_query.from_user.id),
        )


async def save_and_publish_product(callback_query: types.CallbackQuery, state: FSMContext, bot):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer("Зберігаю...")

    result, payload = await _save_product_from_state(state)
    await state.finish()

    if result is None:
        return await callback_query.message.answer(
            "Не вдалося зберегти товар у Google Sheets. Перевірте GAS.",
            reply_markup=_main_menu_for(callback_query.from_user.id),
        )

    await callback_query.message.answer("✅ Товар збережено. Відкриваю прев'ю перед публікацією...")

    product = await db.get_product_by_article(payload["article"])
    if not product or not _product_exists(product, payload["article"]):
        return await callback_query.message.answer("Товар збережено, але не вдалося завантажити прев'ю.")

    await send_publish_preview(callback_query.message.chat.id, product, bot)


async def cancel_admin_flow(event, state: FSMContext):
    user_id = event.from_user.id
    await state.finish()
    answer = "Дію скасовано."
    if isinstance(event, types.CallbackQuery):
        await event.message.answer(answer, reply_markup=_main_menu_for(user_id))
        await event.answer()
    else:
        await event.answer(answer, reply_markup=_main_menu_for(user_id))


async def start_publish_product(message: types.Message):
    await send_publish_list(message.answer, message.from_user.id)


async def schedule_all_posts(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("У вас немає доступу до цієї дії.")

    products = await db.get_products()
    schedulable = [product for product in products if _is_schedulable_product(product)]
    schedulable.sort(key=lambda product: _get_article(product), reverse=True)

    selected = schedulable[:30]

    if not selected:
        return await message.answer("Немає товарів для планування.")

    slots = _next_future_slots(len(selected))
    scheduled_lines = []

    for product, slot in zip(selected, slots):
        article = _get_article(product)
        publish_at = _format_publish_at(slot)

        result = await db.update_product_fields(
            article,
            {
                "publish_status": "queued",
                "publish_at": publish_at,
                "published_at": "",
            }
        )

        if result is None:
            logger.warning("Failed to schedule article %s", article)
            continue

        scheduled_lines.append(f"{article} → {publish_at}")

    if not scheduled_lines:
        return await message.answer("❌ Не вдалося розпланувати товари. Перевір GAS.")

    summary = "\n".join(scheduled_lines)
    await message.answer(
        f"✅ Розплановано: {len(scheduled_lines)} товарів\n\n{summary}",
        reply_markup=_main_menu_for(message.from_user.id),
    )


async def send_publish_list(answer_method, user_id):
    if not is_admin(user_id):
        return await answer_method("У вас немає доступу до цієї дії.")

    products = await db.get_products()

    publishable = []
    for product in products:
        article = _get_article(product)
        status = _get_status(product).lower()

        if article and status not in {"hidden", "sold_out"}:
            publishable.append(product)

    if not publishable:
        return await answer_method("Немає товарів для публікації. Перевірте, чи товари не hidden/sold_out.")

    publishable.sort(key=lambda product: _get_article(product), reverse=True)

    summary_lines = [
        (
            f"• <code>{_get_article(product)}</code> | "
            f"{product.get('Бренд') or product.get('brand') or ''} "
            f"{product.get('Модель') or product.get('model') or ''} | "
            f"{product.get('Ціна') or product.get('price') or ''} грн | "
            f"<b>{_get_status(product)}</b>"
        )
        for product in publishable[:20]
    ]

    text = "Оберіть товар для публікації:\n\n" + "\n".join(summary_lines)
    await answer_method(text, parse_mode="HTML", reply_markup=kb.get_publish_products_keyboard(publishable))


async def send_publish_preview(chat_id, product, bot):
    if not product:
        return await bot.send_message(chat_id, "Товар не знайдено.")

    article = _get_article(product)
    publish_status = _get_publish_status(product)
    publish_at = str(product.get("publish_at") or "").strip()

    caption = (
        f"Прев'ю перед публікацією:\n\n"
        f"{_product_caption(product)}\n\n"
        f"Статус: <b>{_get_status(product)}</b>"
    )

    if publish_status or publish_at:
        caption += f"\nПланування: <b>{publish_status or '—'}</b> {publish_at or ''}"

    photos = _parse_photo_ids(product.get("Фото") or product.get("photo_ids") or "")

    await _send_album_or_photo(
        bot,
        chat_id,
        photos,
        caption,
        reply_markup=kb.get_publish_preview_keyboard(article),
        action_text="Дія з товаром 👇",
    )


async def preview_publish_product(callback_query: types.CallbackQuery, bot):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer()

    article = callback_query.data.replace("preview_publish_", "", 1).strip()
    product = await db.get_product_by_article(article)

    if not product:
        return await callback_query.message.answer("❌ Товар не знайдено.")

    product_article = _get_article(product)
    if product_article != article:
        logger.error("Article mismatch in preview. callback=%s product=%s", article, product_article)
        return await callback_query.message.answer(
            f"❌ Помилка артикула.\n"
            f"Натиснуто: {article}\n"
            f"Отримано з таблиці: {product_article or 'порожньо'}"
        )

    await send_publish_preview(callback_query.message.chat.id, product, bot)


async def start_schedule_product(callback_query: types.CallbackQuery, bot):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer()

    article = callback_query.data.replace("schedule_product_", "", 1).strip()
    product = await db.get_product_by_article(article)

    if not product:
        return await callback_query.message.answer("❌ Товар не знайдено.")

    await callback_query.message.answer(
        f"Оберіть час публікації для товару {article}:",
        reply_markup=kb.get_schedule_product_keyboard(article),
    )


async def schedule_one_product(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    raw = callback_query.data.replace("schedule_one_", "", 1).strip()

    try:
        article, day, hour = raw.rsplit("_", 2)
    except ValueError:
        return await callback_query.answer("Некоректні дані планування.", show_alert=True)

    if day not in {"today", "tomorrow"} or hour not in {"09", "15", "20"}:
        return await callback_query.answer("Некоректний час планування.", show_alert=True)

    product = await db.get_product_by_article(article)
    if not product:
        return await callback_query.message.answer("❌ Товар не знайдено.")

    publish_dt, moved_to_tomorrow = _build_schedule_datetime(day, hour)
    publish_at = _format_publish_at(publish_dt)

    result = await db.update_product_fields(
        article,
        {
            "publish_status": "queued",
            "publish_at": publish_at,
            "published_at": "",
        }
    )

    if result is None:
        return await callback_query.message.answer("❌ Не вдалося записати розклад у таблицю. Перевір GAS.")

    await callback_query.answer("Заплановано.")

    extra_note = ""
    if moved_to_tomorrow and day == "today":
        extra_note = "\nℹ️ Обраний час на сьогодні вже минув, тому пост автоматично перенесено на завтра."

    await callback_query.message.answer(
        f"✅ Товар {article} заплановано на {publish_at}{extra_note}",
        reply_markup=_main_menu_for(callback_query.from_user.id),
    )


async def start_edit_saved_product(callback_query: types.CallbackQuery, bot):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer()

    article = callback_query.data.replace("edit_product_", "", 1).strip()
    product = await db.get_product_by_article(article)

    if not product:
        return await callback_query.message.answer("❌ Товар не знайдено.")

    await callback_query.message.answer(
        _saved_edit_menu_text(product),
        parse_mode="HTML",
        reply_markup=kb.get_saved_edit_fields_keyboard(article),
    )


async def choose_saved_edit_field(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    await callback_query.answer()

    raw = callback_query.data.replace("edit_saved_field_", "", 1)
    article, field = raw.rsplit("_", 1)

    if field not in FIELD_LABELS:
        return await callback_query.message.answer("Невідоме поле.")

    product = await db.get_product_by_article(article)
    if not product:
        return await callback_query.message.answer("❌ Товар не знайдено.")

    if field == "photo_ids":
        photos = _parse_photo_ids(product.get("Фото") or product.get("photo_ids") or "")
        await EditSavedState.waiting_for_photos.set()
        await state.update_data(edit_article=article, edit_field=field, photo_ids=[])

        return await callback_query.message.answer(
            f"Поточних фото: {len(photos)} шт.\n\n"
            f"Надішли нові фото товару. Старі фото будуть замінені.\n"
            f"Коли завершиш, натисни '✅ Фото готово'.",
            reply_markup=kb.get_cancel_keyboard("✅ Фото готово"),
        )

    current_value = (
        product.get(field)
        or product.get("Артикул" if field == "article" else "")
        or product.get(FIELD_LABELS.get(field, ""))
        or ""
    )

    await EditSavedState.waiting_for_value.set()
    await state.update_data(edit_article=article, edit_field=field)

    await callback_query.message.answer(
        f"Поле: <b>{FIELD_LABELS[field]}</b>\n\n"
        f"Поточне значення:\n"
        f"<code>{current_value or '—'}</code>\n\n"
        f"Надішли нове значення:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard(),
    )


async def save_saved_edited_field(message: types.Message, state: FSMContext, bot):
    data = await state.get_data()
    article = data.get("edit_article")
    field = data.get("edit_field")

    if not article or not field:
        await state.finish()
        return await message.answer("Не знайдено товар або поле.")

    value, error = _validate_draft_value(field, message.text)
    if error:
        return await message.answer(error)

    result = await db.update_product_field(article, field, value)

    if result is None:
        return await message.answer("❌ Не вдалося оновити поле в таблиці. Перевір GAS.")

    await state.finish()
    product = await db.get_product_by_article(article)
    await message.answer(f"✅ Поле «{FIELD_LABELS[field]}» оновлено.")
    await send_publish_preview(message.chat.id, product, bot)


async def publish_selected_product(callback_query: types.CallbackQuery, bot):
    if not is_admin(callback_query.from_user.id):
        return await callback_query.answer("Немає доступу.", show_alert=True)

    if not SHOP_GROUP_ID:
        return await callback_query.answer("SHOP_GROUP_ID не налаштований.", show_alert=True)

    article = callback_query.data.replace("publish_", "", 1).strip()

    await callback_query.answer("Публікую товар...")

    product = await db.get_product_by_article(article)
    if not product:
        return await callback_query.message.answer("❌ Товар не знайдено.")

    product_article = _get_article(product)
    if product_article != article:
        logger.error("Article mismatch while publishing. callback=%s product=%s", article, product_article)
        return await callback_query.message.answer(
            f"❌ Помилка артикула.\n"
            f"Натиснуто: {article}\n"
            f"Отримано з таблиці: {product_article or 'порожньо'}"
        )

    photo_ids = _parse_photo_ids(product.get("Фото") or product.get("photo_ids") or "")

    caption = _product_caption(product)

    if len(photo_ids) <= 1:
        sent_message = await bot.send_photo(
            SHOP_GROUP_ID,
            photo=photo_ids[0] if photo_ids else "https://via.placeholder.com/500",
            caption=caption,
            parse_mode="HTML",
        )
    else:
        media = []
        for index, photo_id in enumerate(photo_ids[:10]):
            if index == 0:
                media.append(InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML"))
            else:
                media.append(InputMediaPhoto(media=photo_id))

        album_messages = await bot.send_media_group(chat_id=SHOP_GROUP_ID, media=media)
        sent_message = album_messages[0]

    me = await bot.get_me()
    deep_link = f"https://t.me/{me.username}?start={quote(f'buy_{article}_post{sent_message.message_id}')}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(text="🛒 Оформити замовлення", url=deep_link))

    button_message = await bot.send_message(
        SHOP_GROUP_ID,
        text="Оформити замовлення 👇",
        reply_markup=markup,
    )

    await db.create_post_log(
        {
            "product_id": _get_product_id(product),
            "article": article,
            "chat_id": SHOP_GROUP_ID,
            "message_id": button_message.message_id,
            "status": "published",
        }
    )

    await db.update_product_status(article, "published")
    await db.update_product_fields(
        article,
        {
            "publish_status": "published",
            "published_at": _format_publish_at(datetime.now(KYIV_TZ)),
        }
    )

    await callback_query.message.answer(
        f"✅ Товар {article} опубліковано в магазині.",
        reply_markup=_main_menu_for(callback_query.from_user.id),
    )
