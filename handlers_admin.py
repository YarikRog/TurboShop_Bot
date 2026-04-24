import os
import asyncio
import logging
from urllib.parse import quote

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import database as db
import keyboards as kb

logger = logging.getLogger("TurboBot.Admin")

ADMIN_IDS = {int(item.strip()) for item in os.getenv("ADMIN_IDS", "").split(",") if item.strip().isdigit()}
SHOP_GROUP_ID = os.getenv("SHOP_GROUP_ID")

MEDIA_GROUP_BUFFER = {}
MEDIA_GROUP_TASKS = {}
MEDIA_GROUP_LOCK = asyncio.Lock()


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


def _product_exists(product, article):
    if not isinstance(product, dict):
        return False

    if product.get("ok") is False:
        return False

    product_article = _get_article(product)
    return bool(product_article and product_article == str(article).strip())


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
        f"{short_description}\n\n"
        "Натискайте кнопку нижче, щоб перейти до замовлення."
    )


def _parse_photo_ids(raw_photos):
    raw = str(raw_photos or "")
    for delimiter in (";", "\n", "\r"):
        raw = raw.replace(delimiter, ",")
    photos = [photo.strip() for photo in raw.split(",") if photo.strip() and photo.strip().lower() != "none"]
    return list(dict.fromkeys(photos))


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
    raw_price = str(message.text).replace(" ", "").replace(",", ".")
    try:
        price = int(float(raw_price))
    except ValueError:
        return await message.answer("Ціна має бути числом, наприклад 3490.")

    await state.update_data(price=price)
    await AddProductState.next()
    await message.answer("Введіть розміри через кому, наприклад: 36, 37, 38")


async def save_sizes(message: types.Message, state: FSMContext):
    sizes = ", ".join([item.strip() for item in str(message.text).replace(";", ",").split(",") if item.strip()])
    if not sizes:
        return await message.answer("Вкажіть хоча б один розмір.")

    await state.update_data(sizes=sizes)
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

    await message.answer(
        f"✅ Додано фото: {added}. Всього фото: {len(current_photo_ids)}"
    )


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
            MEDIA_GROUP_TASKS[key] = asyncio.create_task(
                _flush_media_group(key, state, message)
            )


async def finish_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_ids = data.get("photo_ids", [])
    if not photo_ids:
        return await message.answer("Спочатку додайте хоча б одне фото.")

    await AddProductState.next()
    await message.answer("Введіть залишок на складі:", reply_markup=kb.get_cancel_keyboard())


async def save_stock(message: types.Message, state: FSMContext):
    raw_stock = str(message.text).strip()
    if not raw_stock.isdigit():
        return await message.answer("Залишок має бути числом.")

    await state.update_data(stock=int(raw_stock))
    await AddProductState.next()

    data = await state.get_data()
    preview_text = (
        f"Перевірте дані товару:\n\n"
        f"Артикул: {data['article']}\n"
        f"Бренд: {data['brand']}\n"
        f"Модель: {data['model']}\n"
        f"Категорія: {data['category']}\n"
        f"Сезон: {data['season']}\n"
        f"Ціна: {data['price']} грн\n"
        f"Розміри: {data['sizes']}\n"
        f"Опис: {data['description']}\n"
        f"Фото: {len(data.get('photo_ids', []))} шт.\n"
        f"Залишок: {data['stock']}"
    )

    first_photo = data["photo_ids"][0]
    await message.answer_photo(
        first_photo,
        caption=preview_text,
        reply_markup=kb.get_save_or_publish_keyboard(),
        parse_mode="HTML",
    )


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
    caption = (
        f"Прев'ю перед публікацією:\n\n"
        f"{_product_caption(product)}\n\n"
        f"Статус: <b>{_get_status(product)}</b>"
    )

    photos = _parse_photo_ids(product.get("Фото") or product.get("photo_ids") or "")
    preview_photo = photos[0] if photos else "https://via.placeholder.com/500"

    await bot.send_photo(
        chat_id,
        photo=preview_photo,
        caption=caption,
        parse_mode="HTML",
        reply_markup=kb.get_publish_preview_keyboard(article),
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

    sent_message = await bot.send_photo(
        SHOP_GROUP_ID,
        photo=photo_ids[0] if photo_ids else "https://via.placeholder.com/500",
        caption=_product_caption(product),
        parse_mode="HTML",
    )

    me = await bot.get_me()
    deep_link = f"https://t.me/{me.username}?start={quote(f'buy_{article}_post{sent_message.message_id}')}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(text="Купити", url=deep_link))

    await bot.edit_message_reply_markup(
        chat_id=SHOP_GROUP_ID,
        message_id=sent_message.message_id,
        reply_markup=markup,
    )

    await db.create_post_log(
        {
            "product_id": _get_product_id(product),
            "article": article,
            "chat_id": SHOP_GROUP_ID,
            "message_id": sent_message.message_id,
            "status": "published",
        }
    )

    await db.update_product_status(article, "published")

    await callback_query.message.answer(
        f"✅ Товар {article} опубліковано в магазині.",
        reply_markup=_main_menu_for(callback_query.from_user.id),
    )