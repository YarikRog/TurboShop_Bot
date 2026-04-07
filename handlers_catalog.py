import logging
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database as db
import keyboards as kb

logger = logging.getLogger(__name__)

# ================= ОСНОВНА ФУНКЦІЯ ПЕРЕГЛЯДУ ТОВАРУ =================
async def show_product(bot, user_id, index, state, message_to_edit=None, all_products=None):
    if not all_products:
        logger.error("Кеш (all_products) порожній у show_product")
        return

    data = await state.get_data()
    product_ids = data.get('product_ids', [])
    current_size = data.get('size', '—')
    
    if not product_ids:
        await bot.send_message(user_id, "⚠️ Дані застаріли. Почни заново з меню.", reply_markup=kb.main_menu())
        return

    # Валідація індексу
    if index < 0: index = 0
    elif index >= len(product_ids): index = len(product_ids) - 1
    
    article = product_ids[index]
    
    # Шукаємо товар у кеші за артикулом
    product = next((i for i in all_products if str(i.get('Артикул')) == str(article)), None)
    
    if not product:
        await bot.send_message(user_id, "❌ Товар не знайдено.")
        return

    total = len(product_ids)
    await state.update_data(current_index=index)

    # Формуємо текст
    caption = (
        f"⠀👟 <b>{product.get('Бренд')} {product.get('Модель') or product.get('Model')}</b>\n"
        f"⠀💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
        f"⠀📏 Розмір: {current_size}\n"
        f"⠀🆔 Артикул: <code>{article}</code>"
    )
    
    # Робота з фото
    photo_field = str(product.get('Фото', ''))
    photos = [p.strip() for p in photo_field.split(',') if p.strip() and p.lower() != 'none']
    photo = photos[0] if photos else "https://via.placeholder.com/500"

    # Клавіатура (використовуємо твою функцію з keyboards або створюємо тут)
    # ВАЖЛИВО: Передаємо article у кнопки Купити та Опис
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🛍 Купити", callback_data=f"buy_{article}"),
        InlineKeyboardButton("📝 Опис", callback_data=f"descr_{article}")
    )

    # Навігація
    nav_btns = []
    if index > 0:
        nav_btns.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"prev_{index}"))
    if index < total - 1:
        nav_btns.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"next_{index}"))
    
    if nav_btns:
        markup.row(*nav_btns)
    
    markup.add(InlineKeyboardButton("🖼 Більше фото", callback_data=f"more_photos_{article}"))

    try:
        if message_to_edit:
            # Редагуємо існуюче повідомлення
            media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
            await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=markup)
        else:
            # Надсилаємо нове
            await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in show_product: {e}")
        # Якщо не вдалося редагувати, просто шлемо новим повідомленням
        await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)

# ================= ІНШІ ОБРОБНИКИ =================

async def show_more_photos(callback_query, state, ALL_PRODUCTS, bot):
    user_id = callback_query.from_user.id
    article = callback_query.data.replace("more_photos_", "")
    
    data = await state.get_data()
    last_album = data.get('last_album_ids', [])
    
    # Видаляємо старі фото альбому, щоб не засмічувати чат
    for msg_id in last_album:
        try: await bot.delete_message(user_id, msg_id)
        except: pass

    product = next((i for i in ALL_PRODUCTS if str(i.get('Артикул')) == str(article)), None)
    if not product: return
    
    photo_field = str(product.get('Фото', ''))
    photos = [p.strip() for p in photo_field.split(',') if p.strip() and p.lower() != 'none']
    
    if len(photos) <= 1:
        return await bot.answer_callback_query(callback_query.id, text="Більше фото немає", show_alert=True)

    media = types.MediaGroup()
    for p_id in photos[1:10]: # Максимум 10 фото в альбомі за лімітами ТГ
        media.attach_photo(p_id)

    try:
        msgs = await bot.send_media_group(user_id, media=media)
        await state.update_data(last_album_ids=[m.message_id for m in msgs])
        await bot.answer_callback_query(callback_query.id)
    except Exception as e:
        logger.error(f"Album error: {e}")
        await bot.answer_callback_query(callback_query.id, text="Помилка завантаження альбому")

async def show_novinki(message, state, ALL_PRODUCTS, bot):
    novinki = ALL_PRODUCTS[-10:] # Останні 10 доданих
    if not novinki:
        return await message.answer("Скоро будуть! 😉")
    
    ids = [str(i.get('Артикул')) for i in novinki if i.get('Артикул')]
    await state.update_data(product_ids=ids, size="Всі новинки", last_album_ids=[])
    await show_product(bot, message.from_user.id, 0, state, all_products=ALL_PRODUCTS)

async def show_brands(message, state, ALL_PRODUCTS):
    data = await state.get_data()
    category = data.get('category', 'Чоловічі')
    await state.update_data(last_album_ids=[])
    
    brands = sorted(list(set([
        str(i.get('Бренд')).strip() 
        for i in ALL_PRODUCTS if str(i.get('Категорія')).strip() == category
    ])))
    
    if not brands:
        return await message.answer(f"На жаль, у категорії {category} зараз порожньо.")
    
    await message.answer(f"Обери бренд ({category}):", reply_markup=kb.get_brands_keyboard(brands))

async def choose_size(message, state, ALL_PRODUCTS):
    brand = message.text.replace("🔹 ", "").strip()
    user_data = await state.get_data()
    category = user_data.get('category', 'Чоловічі')
    
    await state.update_data(brand=brand)
    
    # Отримуємо розміри через кеш
    all_sizes = []
    for i in ALL_PRODUCTS:
        if str(i.get('Категорія')).strip() == category and str(i.get('Бренд')).strip() == brand:
            raw_sizes = str(i.get('Розміри', ''))
            all_sizes.extend([s.strip() for s in raw_sizes.replace(';', ',').split(',') if s.strip()])
    
    sizes = sorted(list(set(all_sizes)))
    
    if not sizes:
        return await message.answer("На жаль, розмірів немає.")
        
    await message.answer(f"Який розмір {brand} ({category}) шукаємо?", reply_markup=kb.get_sizes_keyboard(sizes))
