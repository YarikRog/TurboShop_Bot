from aiogram import types
import database as db
import keyboards as kb

# Ми прибрали зайві аргументи, тепер все беремо зі state
async def show_product(bot, user_id, index, state, message_to_edit=None):
    # Отримуємо дані з Redis
    async with state.proxy() as data:
        product_ids = data.get('product_ids', [])
        current_size = data.get('size', '—')
        
        if not product_ids:
            await bot.send_message(user_id, "⚠️ Дані застаріли. Почни заново з меню.", reply_markup=kb.main_menu())
            return

        # Валідація індексу
        if index < 0: index = 0
        elif index >= len(product_ids): index = len(product_ids) - 1
        
        # Отримуємо товар через імпортований cache (він має бути доступний або переданий)
        # Для чистоти коду, ми дістанемо товар з ALL_PRODUCTS за ID
        from main import cache # Імпортуємо твій новий кеш
        article = product_ids[index]
        product = cache.get_by_id(article)
        
        if not product:
            await bot.send_message(user_id, "❌ Товар видалено з бази.")
            return

        total = len(product_ids)
        data['current_index'] = index # Запам'ятовуємо, де зупинився юзер

        caption = (
            f"⠀👟 <b>{product.get('Бренд')} {product.get('Модель')}</b>\n"
            f"⠀💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
            f"⠀📏 Розмір: {current_size}\n"
            f"⠀🆔 Артикул: <code>{product.get('Артикул')}</code>"
        )
        
        # Отримуємо фото (тут можна залишити db.get_product_photos або брати з product)
        photo_field = product.get('Фото', '')
        photos = photo_field.split(',') if photo_field else []
        photo = photos[0].strip() if photos and str(photos[0]).strip() not in ["None", ""] else None

        markup = kb.get_product_navigation(index, total, article)

        if message_to_edit:
            try:
                if photo:
                    media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
                    await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=markup)
                else:
                    await bot.send_message(user_id, f"🖼 (Фото очікується)\n\n{caption}", parse_mode="HTML", reply_markup=markup)
            except Exception:
                await bot.send_message(user_id, caption, parse_mode="HTML", reply_markup=markup)
        else:
            if photo:
                await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
            else:
                await bot.send_message(user_id, f"🖼 (Фото очікується)\n\n{caption}", parse_mode="HTML", reply_markup=markup)

async def show_more_photos(callback_query, state, ALL_PRODUCTS, bot):
    user_id = callback_query.from_user.id
    article = callback_query.data.replace("more_photos_", "")
    
    # Очищуємо старі фото через state
    async with state.proxy() as data:
        last_album = data.get('last_album_ids', [])
        for msg_id in last_album:
            try: await bot.delete_message(user_id, msg_id)
            except: pass
        data['last_album_ids'] = []

        from main import cache
        product = cache.get_by_id(article)
        if not product: return
        
        photo_field = product.get('Фото', '')
        photos = [p.strip() for p in photo_field.split(',') if p.strip() not in ["", "None"]]
        
        if len(photos) <= 1:
            return await bot.answer_callback_query(callback_query.id, text="Більше фото немає", show_alert=True)

        media = types.MediaGroup()
        for p_id in photos[1:10]: 
            media.attach_photo(p_id)

        try:
            msgs = await bot.send_media_group(user_id, media=media)
            data['last_album_ids'] = [m.message_id for m in msgs]
            await bot.answer_callback_query(callback_query.id)
        except Exception:
            await bot.answer_callback_query(callback_query.id, text="Помилка завантаження альбому")

async def show_novinki(message, state, ALL_PRODUCTS, bot):
    novinki = ALL_PRODUCTS[-10:]
    if not novinki:
        return await message.answer("Скоро будуть! 😉")
    
    ids = [str(i.get('Артикул')) for i in novinki if i.get('Артикул')]
    await state.update_data(product_ids=ids, size="Всі новинки", last_album_ids=[])
    await show_product(bot, message.from_user.id, 0, state)

async def show_brands(message, state, ALL_PRODUCTS):
    category = "Чоловічі" if "Чоловічі" in message.text else "Жіночі"
    # Очищуємо дані старого пошуку
    await state.update_data(category=category, last_album_ids=[])
    
    brands = sorted(list(set([
        str(i.get('Бренд')).strip() 
        for i in ALL_PRODUCTS if str(i.get('Категорія')).strip() == category
    ])))
    
    if not brands:
        return await message.answer("На жаль, зараз порожньо.")
    
    await message.answer(f"Обери бренд ({category}):", reply_markup=kb.get_brands_keyboard(brands))

async def choose_size(message, state, ALL_PRODUCTS):
    brand = message.text.replace("🔹 ", "").strip()
    user_data = await state.get_data()
    category = user_data.get('category', 'Чоловічі')
    
    await state.update_data(brand=brand)
    
    # Використовуємо твій існуючий db.get_available_sizes
    sizes = db.get_available_sizes(ALL_PRODUCTS, category, brand) 
    
    if not sizes:
        return await message.answer("На жаль, розмірів немає.")
        
    await message.answer(f"Який розмір {brand} ({category}) шукаємо?", reply_markup=kb.get_sizes_keyboard(sizes))
