from aiogram import types
import database as db
import keyboards as kb

async def show_product(bot, user_id, index, user_products, ALL_PRODUCTS, message_to_edit=None):
    data = user_products.get(user_id)
    if not data or 'products' not in data or not data['products']:
        await bot.send_message(user_id, "⚠️ Дані застаріли. Почни заново з меню.", reply_markup=kb.main_menu())
        return

    product = data['products'][index]
    total = len(data['products'])
    
    caption = (
        f"⠀👟 <b>{product.get('Бренд')} {product.get('Модель')}</b>\n"
        f"⠀💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
        f"⠀📏 Розмір: {data.get('size', '—')}\n"
        f"⠀🆔 Артикул: <code>{product.get('Артикул')}</code>"
    )
    
    photos = db.get_product_photos(ALL_PRODUCTS, product.get('Артикул'))
    photo = photos[0] if photos else "https://via.placeholder.com/500"
    markup = kb.get_product_navigation(index, total, product.get('Артикул'))

    if message_to_edit:
        try:
            media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
            await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=markup)
        except: pass
    else:
        await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)

async def show_novinki(message: types.Message, user_products, ALL_PRODUCTS, bot):
    novinki = ALL_PRODUCTS[-10:]
    if not novinki:
        await message.answer("Скоро будуть! 😉")
        return
    user_products[message.from_user.id] = {'products': novinki, 'size': 'Всі', 'last_album_ids': []}
    await show_product(bot, message.from_user.id, 0, user_products, ALL_PRODUCTS)

async def show_brands(message: types.Message, user_products, ALL_PRODUCTS):
    category = "Чоловічі" if "Чоловічі" in message.text else "Жіночі"
    user_products[message.from_user.id] = {'category': category, 'last_album_ids': []}
    brands = sorted(list(set([str(i.get('Бренд')).strip() for i in ALL_PRODUCTS if str(i.get('Категорія')).strip() == category])))
    if not brands:
        await message.answer("На жаль, зараз порожньо.")
        return
    await message.answer(f"Обери бренд ({category}):", reply_markup=kb.get_brands_keyboard(brands))

async def choose_size(message: types.Message, user_products, ALL_PRODUCTS):
    brand = message.text.replace("🔹 ", "").strip()
    user_id = message.from_user.id
    if user_id not in user_products: user_products[user_id] = {'last_album_ids': []}
    user_products[user_id]['brand'] = brand
    category = user_products[user_id].get('category', 'Чоловічі')
    sizes = db.get_available_sizes(ALL_PRODUCTS, category, brand) 
    await message.answer(f"Який розмір {brand} шукаємо?", reply_markup=kb.get_sizes_keyboard(sizes))
