from aiogram import types
import database as db
import keyboards as kb
import logging

logger = logging.getLogger(__name__)

async def show_product(bot, user_id, index, state, message_to_edit=None):
    # Отримуємо дані без проксі, щоб не блокувати стан
    data = await state.get_data()
    product_ids = data.get('product_ids', [])
    current_size = data.get('size', '—')
    
    if not product_ids:
        await bot.send_message(user_id, "⚠️ Дані застаріли. Почни заново з меню.", reply_markup=kb.main_menu())
        return

    # Валідація індексу
    if index < 0: index = 0
    elif index >= len(product_ids): index = len(product_ids) - 1
    
    # Дістаємо товар напряму з бази через database.py, щоб не було циклічного імпорту з main
    article = product_ids[index]
    all_items = await db.get_all_items() # Беремо актуальний список
    
    product = next((i for i in all_items if str(i.get('Артикул')) == str(article)), None)
    
    if not product:
        await bot.send_message(user_id, "❌ Товар не знайдено в базі.")
        return

    total = len(product_ids)
    await state.update_data(current_index=index)

    caption = (
        f"⠀👟 <b>{product.get('Бренд')} {product.get('Модель')}</b>\n"
        f"⠀💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
        f"⠀📏 Розмір: {current_size}\n"
        f"⠀🆔 Артикул: <code>{product.get('Артикул')}</code>"
    )
    
    # Чистимо посилання на фото
    photo_field = str(product.get('Фото', ''))
    photos = [p.strip() for p in photo_field.split(',') if p.strip() and p.lower() != 'none']
    photo = photos[0] if photos else None

    markup = kb.get_product_navigation(index, total, article)

    try:
        if message_to_edit:
            if photo:
                try:
                    media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
                    await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=markup)
                except Exception as e:
                    # Якщо не вдалося відредагувати (наприклад, те саме фото), просто шлемо нове
                    await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
            else:
                await bot.send_message(user_id, f"🖼 (Фото очікується)\n\n{caption}", parse_mode="HTML", reply_markup=markup)
        else:
            if photo:
                await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
            else:
                await bot.send_message(user_id, f"🖼 (Фото очікується)\n\n{caption}", parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in show_product: {e}")
        # Запасний варіант — просто текст
        await bot.send_message(user_id, caption, parse_mode="HTML", reply_markup=markup)

async def show_more_photos(callback_query, state, ALL_PRODUCTS, bot):
    user_id = callback_query.from_user.id
    article = callback_query.data.replace("more_photos_", "")
    
    data = await state.get_data()
    last_album = data.get('last_album_ids', [])
    
    # Видаляємо старі фото альбому
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
    for p_id in photos[1:10]: 
        media.attach_photo(p_id)

    try:
        msgs = await bot.send_media_group(user_id, media=media)
        await state.update_data(last_album_ids=[m.message_id for m in msgs])
        await bot.answer_callback_query(callback_query.id)
    except Exception as e:
        logger.error(f"Album error: {e}")
        await bot.answer_callback_query(callback_query.id, text="Помилка завантаження альбому")

async def show_novinki(message, state, ALL_PRODUCTS, bot):
    novinki = ALL_PRODUCTS[-10:]
    if not novinki:
        return await message.answer("Скоро будуть! 😉")
    
    ids = [str(i.get('Артикул')) for i in novinki if i.get('Артикул')]
    await state.update_data(product_ids=ids, size="Всі новинки", last_album_ids=[])
    await show_product(bot, message.from_user.id, 0, state)

async def show_brands(message, state, ALL_PRODUCTS):
    # Тут ми вже отримуємо "чисту" категорію з main.py
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
    
    sizes = db.get_available_sizes(ALL_PRODUCTS, category, brand) 
    
    if not sizes:
        return await message.answer("На жаль, розмірів немає.")
        
    await message.answer(f"Який розмір {brand} ({category}) шукаємо?", reply_markup=kb.get_sizes_keyboard(sizes))
