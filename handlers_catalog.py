import logging
import asyncio
from aiogram import types
import keyboards as kb

logger = logging.getLogger("TurboBot.Catalog")


def _parse_sizes(raw_sizes):
    raw = str(raw_sizes or "").replace(";", ",")
    return [size.strip() for size in raw.split(",") if size.strip() and size.strip().lower() != "none"]


async def show_product(bot, user_id, index, state, message_to_edit=None, all_products=None):
    if not all_products:
        logger.error(f"Cache empty for user {user_id}")
        return

    data = await state.get_data()
    product_ids = data.get('product_ids', [])
    current_size = data.get('size', '—')
    
    if not product_ids:
        await bot.send_message(user_id, "⚠️ Сесія застаріла. Почніть з меню.", reply_markup=kb.main_menu())
        return

    index = max(0, min(index, len(product_ids) - 1))
    article = str(product_ids[index]).strip()
    
    product = next((i for i in all_products if str(i.get('Артикул', '')).strip() == article), None)
    
    if not product:
        await bot.send_message(user_id, "❌ Товар не знайдено або видалено з бази.")
        return

    await state.update_data(current_index=index)

    caption = (
        f"⠀👟 <b>{product.get('Бренд')} {product.get('Модель') or product.get('Model', '')}</b>\n"
        f"⠀🗂 Категорія: <b>{product.get('Категорія') or '—'}</b>\n"
        f"⠀💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
        f"⠀📏 Розмір: <b>{current_size}</b>\n"
        f"⠀🆔 Артикул: <code>{article}</code>"
    )

    description = str(product.get("Опис", "")).strip()
    if description:
        caption += f"\n⠀📝 {description[:250]}"
    
    photo_raw = str(product.get('Фото', ''))
    photos = [p.strip() for p in photo_raw.split(',') if p.strip() and p.lower() != 'none']
    photo = photos[0] if photos else "https://via.placeholder.com/500"

    available_sizes = _parse_sizes(product.get("Розміри", ""))
    show_size_picker = bool(available_sizes) and (
        len(product_ids) == 1 or current_size in ["—", "Оберіть розмір", "New Arrivals", "Не вказано"]
    )
    markup = kb.get_product_navigation(index, len(product_ids), article, available_sizes, current_size, show_size_picker)

    try:
        if message_to_edit:
            media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
            await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=markup)
        else:
            await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.warning(f"Failed to edit/send photo: {e}")
        await bot.send_message(user_id, caption, reply_markup=markup, parse_mode="HTML")

async def show_more_photos(callback_query, state, ALL_PRODUCTS, bot):
    user_id = callback_query.from_user.id
    article = callback_query.data.replace("more_photos_", "").strip()
    
    data = await state.get_data()
    # Чистка старих альбомів (fail-safe)
    for msg_id in data.get('last_album_ids', []):
        try: await bot.delete_message(user_id, msg_id)
        except: pass

    product = next((i for i in ALL_PRODUCTS if str(i.get('Артикул', '')).strip() == article), None)
    if not product: return

    photos = [p.strip() for p in str(product.get('Фото', '')).split(',') if p.strip() and p.lower() != 'none']
    
    if len(photos) <= 1:
        return await callback_query.answer("Додаткових фото немає ❌", show_alert=True)

    media = types.MediaGroup()
    for p_id in photos[1:10]: media.attach_photo(p_id)

    try:
        await callback_query.answer("Завантажую альбом...")
        msgs = await bot.send_media_group(user_id, media=media)
        await state.update_data(last_album_ids=[m.message_id for m in msgs])
    except Exception as e:
        logger.error(f"Album error: {e}")
        await callback_query.answer("Помилка завантаження фото ⚠️")

async def show_novinki(message, state, ALL_PRODUCTS, bot):
    novinki = ALL_PRODUCTS[-12:] # Беремо трохи більше для вибору
    ids = [str(i.get('Артикул')) for i in novinki if i.get('Артикул')]
    await state.update_data(product_ids=ids, size="Оберіть розмір", last_album_ids=[])
    await show_product(bot, message.from_user.id, 0, state, all_products=ALL_PRODUCTS)

async def show_brands(message, state, ALL_PRODUCTS):
    data = await state.get_data()
    category = data.get('category', 'Чоловічі')
    brands = sorted(list(set([str(i.get('Бренд')).strip() for i in ALL_PRODUCTS if str(i.get('Категорія')).strip() == category])))
    if not brands: return await message.answer(f"Категорія {category} порожня.")
    await message.answer(f"Оберіть бренд ({category}):", reply_markup=kb.get_brands_keyboard(brands))

async def choose_size(message, state, ALL_PRODUCTS):
    brand = message.text.replace("🔹 ", "").strip()
    category = (await state.get_data()).get('category', 'Чоловічі')
    await state.update_data(brand=brand)
    
    all_sizes = []
    for i in ALL_PRODUCTS:
        if str(i.get('Категорія')).strip() == category and str(i.get('Бренд')).strip() == brand:
            raw = str(i.get('Розміри', '')).replace(';', ',')
            all_sizes.extend([s.strip() for s in raw.split(',') if s.strip()])
    
    sizes = sorted(list(set(all_sizes)))
    if not sizes: return await message.answer("Розміри відсутні.")
    await message.answer(f"Оберіть розмір {brand}:", reply_markup=kb.get_sizes_keyboard(sizes))


async def select_product_size(callback_query, state, all_products, bot):
    payload = callback_query.data.replace("picksize_", "", 1)
    if ":" not in payload:
        return await callback_query.answer("Некоректний розмір.", show_alert=True)

    article, size = payload.split(":", 1)
    product = next((item for item in all_products if str(item.get("Артикул", "")).strip() == article.strip()), None)
    if not product:
        return await callback_query.answer("Товар не знайдено.", show_alert=True)

    await state.update_data(product_ids=[article.strip()], size=size.strip(), current_index=0)
    await show_product(bot, callback_query.from_user.id, 0, state, callback_query.message.message_id, all_products=all_products)
    await callback_query.answer(f"Розмір {size.strip()} обрано")
