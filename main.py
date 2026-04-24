import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.redis import RedisStorage2

import database as db
import keyboards as kb
import handlers_order as order
import handlers_catalog as catalog
import handlers_admin as admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TurboBot.Main")

TOKEN = os.getenv("BOT_TOKEN")

storage = RedisStorage2(
    host=os.getenv("REDIS_HOST", "ballast.proxy.rlwy.net"),
    port=int(os.getenv("REDIS_PORT", 28367)),
    password=os.getenv("REDIS_PASSWORD"),
    db=5,
    pool_size=10
)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)


class ProductCache:
    def __init__(self):
        self._products = []
        self._lock = asyncio.Lock()

    async def update(self):
        data = await db.get_all_items()
        if data:
            async with self._lock:
                self._products = data
            logger.info(f"Cache updated: {len(data)} items")

    def get_all(self):
        return self._products

    def get_by_id(self, article):
        return next(
            (
                i for i in self._products
                if str(i.get("Артикул", "")).strip() == str(article).strip()
            ),
            None
        )


cache = ProductCache()


async def on_startup(_):
    await cache.update()
    asyncio.create_task(cache_refresher())


async def cache_refresher():
    while True:
        await asyncio.sleep(60)
        await cache.update()


@dp.message_handler(commands=["start"], state="*")
async def start_cmd(m: types.Message, state: FSMContext):
    await state.finish()
    args = m.get_args().strip()
    source = "direct"

    if args.startswith("buy_"):
        raw_payload = args.replace("buy_", "", 1)
        article, _, source_suffix = raw_payload.partition("_")
        source = source_suffix or "deep_link"

        product = await db.get_product_by_article(article)
        if product:
            all_products = cache.get_all()
            if not any(str(item.get("Артикул", "")).strip() == article for item in all_products):
                all_products = [*all_products, product]

            await state.update_data(
                product_ids=[article],
                size="Оберіть розмір",
                source=source,
                last_album_ids=[]
            )

            await catalog.show_product(
                bot,
                m.from_user.id,
                0,
                state,
                all_products=all_products
            )
        else:
            await m.answer(
                "Товар за посиланням не знайдено.",
                reply_markup=kb.main_menu(admin.is_admin(m.from_user.id))
            )
    else:
        await m.answer(
            "Вітаємо у TurboShop! 👟\n\nОберіть дію:",
            reply_markup=kb.main_menu(admin.is_admin(m.from_user.id))
        )

    asyncio.create_task(
        db.register_user(
            {
                "telegram_id": m.from_user.id,
                "username": m.from_user.username or "",
                "source": source,
            }
        )
    )


@dp.message_handler(lambda m: m.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def back_to_menu(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer(
        "Головне меню:",
        reply_markup=kb.main_menu(admin.is_admin(m.from_user.id))
    )


@dp.message_handler(lambda m: m.text == "❌ Скасувати", state="*")
async def cancel_flow(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer(
        "Дію скасовано.",
        reply_markup=kb.main_menu(admin.is_admin(m.from_user.id))
    )


@dp.message_handler(lambda m: m.text == "🔥 Наші новинки", state="*")
async def novinki_h(m: types.Message, state: FSMContext):
    await catalog.show_novinki(m, state, cache.get_all(), bot)


@dp.message_handler(lambda m: m.text == "💬 Менеджер", state="*")
async def manager_h(m: types.Message):
    username = os.getenv("MANAGER_USERNAME", "").strip().replace("@", "")
    if username:
        await m.answer(f"Напишіть менеджеру: @{username}")
    else:
        await m.answer("Менеджер скоро буде доданий. Поки можете написати нам у чаті.")


@dp.message_handler(lambda m: m.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def category_h(m: types.Message, state: FSMContext):
    cat = m.text.replace("👟", "").replace("👠", "").strip()
    await state.update_data(category=cat)
    await catalog.show_brands(m, state, cache.get_all())


@dp.message_handler(lambda m: m.text.startswith("🔹 "), state="*")
async def brand_h(m: types.Message, state: FSMContext):
    await catalog.choose_size(m, state, cache.get_all())


@dp.message_handler(lambda m: m.text == "➕ Додати товар", state="*")
async def add_product_h(m: types.Message, state: FSMContext):
    await admin.start_add_product(m, state)


@dp.message_handler(lambda m: m.text == "📤 Опублікувати товар", state="*")
async def publish_product_h(m: types.Message):
    await admin.start_publish_product(m)


@dp.message_handler(lambda m: m.text == "📅 Розпланувати всі пости", state="*")
async def schedule_all_posts_h(m: types.Message):
    await admin.schedule_all_posts(m)
    await cache.update()


@dp.callback_query_handler(lambda c: c.data.startswith("size_"), state="*")
async def size_select_h(c: types.CallbackQuery, state: FSMContext):
    size = c.data.replace("size_", "")
    data = await state.get_data()
    all_items = cache.get_all()

    products = [
        i for i in all_items
        if str(i.get("Категорія")).strip() == data.get("category")
        and str(i.get("Бренд")).strip() == data.get("brand")
        and size in [s.strip() for s in str(i.get("Розміри", "")).replace(";", ",").split(",")]
    ]

    if not products:
        return await c.answer("❌ Товарів цього розміру немає.", show_alert=True)

    ids = [str(i.get("Артикул")) for i in products if i.get("Артикул")]
    await state.update_data(product_ids=ids, size=size)
    await catalog.show_product(bot, c.from_user.id, 0, state, all_products=all_items)
    await c.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("picksize_"), state="*")
async def pick_size_h(c: types.CallbackQuery, state: FSMContext):
    all_products = cache.get_all()
    payload = c.data.replace("picksize_", "", 1)
    article = payload.split(":", 1)[0].strip()

    if not any(str(item.get("Артикул", "")).strip() == article for item in all_products):
        product = await db.get_product_by_article(article)
        if product:
            all_products = [*all_products, product]

    await catalog.select_product_size(c, state, all_products, bot)


@dp.callback_query_handler(lambda c: c.data.startswith(("next_", "prev_")), state="*")
async def nav_h(c: types.CallbackQuery, state: FSMContext):
    action, idx = c.data.split("_")
    new_idx = int(idx) + 1 if action == "next" else int(idx) - 1
    await catalog.show_product(
        bot,
        c.from_user.id,
        new_idx,
        state,
        c.message.message_id,
        cache.get_all()
    )
    await c.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("buy_"), state="*")
async def buy_h(c: types.CallbackQuery, state: FSMContext):
    all_products = cache.get_all()
    article = c.data.replace("buy_", "").strip()

    if not any(str(item.get("Артикул", "")).strip() == article for item in all_products):
        product = await db.get_product_by_article(article)
        if product:
            all_products = [*all_products, product]

    await order.process_buy(c, state, all_products)


@dp.callback_query_handler(lambda c: c.data.startswith("more_photos_"), state="*")
async def more_photos_h(c: types.CallbackQuery, state: FSMContext):
    all_products = cache.get_all()
    article = c.data.replace("more_photos_", "").strip()

    if not any(str(item.get("Артикул", "")).strip() == article for item in all_products):
        product = await db.get_product_by_article(article)
        if product:
            all_products = [*all_products, product]

    await catalog.show_more_photos(c, state, all_products, bot)


@dp.callback_query_handler(lambda c: c.data.startswith("descr_"), state="*")
async def descr_h(c: types.CallbackQuery):
    art = c.data.replace("descr_", "")
    item = cache.get_by_id(art)
    if not item:
        item = await db.get_product_by_article(art)

    txt = item.get("Опис", "Опис скоро буде 😉") if item else "Не знайдено"
    await c.answer(txt, show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "show_grid_alert", state="*")
async def grid_alert_h(c: types.CallbackQuery):
    await c.answer(
        "Розмірну сітку додамо окремим повідомленням або шаблоном бренду.",
        show_alert=True
    )


@dp.callback_query_handler(lambda c: c.data == "ignore", state="*")
async def ignore_h(c: types.CallbackQuery):
    await c.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_save_product", state=admin.AddProductState.confirmation)
async def admin_save_h(c: types.CallbackQuery, state: FSMContext):
    await admin.confirm_save_product(c, state)
    await cache.update()


@dp.callback_query_handler(lambda c: c.data == "admin_save_and_publish_product", state=admin.AddProductState.confirmation)
async def admin_save_and_publish_h(c: types.CallbackQuery, state: FSMContext):
    await admin.save_and_publish_product(c, state, bot)
    await cache.update()


@dp.callback_query_handler(lambda c: c.data == "admin_edit_draft_product", state=admin.AddProductState.confirmation)
async def admin_edit_draft_product_h(c: types.CallbackQuery, state: FSMContext):
    await admin.start_edit_draft_product(c, state)


@dp.callback_query_handler(lambda c: c.data.startswith("admin_edit_draft_field_"), state="*")
async def admin_edit_draft_field_h(c: types.CallbackQuery, state: FSMContext):
    await admin.choose_draft_edit_field(c, state)


@dp.callback_query_handler(lambda c: c.data == "admin_back_to_draft_preview", state="*")
async def admin_back_to_draft_preview_h(c: types.CallbackQuery, state: FSMContext):
    await admin.back_to_draft_preview(c, state)


@dp.callback_query_handler(lambda c: c.data in ["admin_cancel_product", "admin_cancel_publish"], state="*")
async def admin_cancel_cb_h(c: types.CallbackQuery, state: FSMContext):
    await admin.cancel_admin_flow(c, state)


@dp.callback_query_handler(lambda c: c.data == "back_to_publish_list", state="*")
async def admin_publish_back_h(c: types.CallbackQuery):
    await admin.show_publish_filters(c)


@dp.callback_query_handler(lambda c: c.data == "publish_filters", state="*")
async def admin_publish_filters_h(c: types.CallbackQuery):
    await admin.show_publish_filters(c)


@dp.callback_query_handler(lambda c: c.data.startswith("publish_filter_"), state="*")
async def admin_publish_filter_page_h(c: types.CallbackQuery):
    await admin.send_publish_filtered_page(c)


@dp.callback_query_handler(lambda c: c.data == "publish_search", state="*")
async def admin_publish_search_h(c: types.CallbackQuery, state: FSMContext):
    await admin.start_publish_search(c, state)


@dp.callback_query_handler(lambda c: c.data.startswith("preview_publish_"), state="*")
async def admin_publish_preview_h(c: types.CallbackQuery):
    await admin.preview_publish_product(c, bot)


@dp.callback_query_handler(lambda c: c.data.startswith("schedule_product_"), state="*")
async def admin_schedule_product_h(c: types.CallbackQuery):
    await admin.start_schedule_product(c, bot)


@dp.callback_query_handler(lambda c: c.data.startswith("schedule_one_"), state="*")
async def admin_schedule_one_product_h(c: types.CallbackQuery):
    await admin.schedule_one_product(c)
    await cache.update()


@dp.callback_query_handler(lambda c: c.data.startswith("edit_product_"), state="*")
async def admin_edit_saved_product_h(c: types.CallbackQuery):
    await admin.start_edit_saved_product(c, bot)


@dp.callback_query_handler(lambda c: c.data.startswith("edit_saved_field_"), state="*")
async def admin_edit_saved_field_h(c: types.CallbackQuery, state: FSMContext):
    await admin.choose_saved_edit_field(c, state)


@dp.callback_query_handler(lambda c: c.data.startswith("publish_"), state="*")
async def admin_publish_selected_h(c: types.CallbackQuery):
    await admin.publish_selected_product(c, bot)
    await cache.update()


# =========================
# ORDER UX HANDLERS
# =========================

@dp.message_handler(lambda m: m.text == "✅ Підтвердити замовлення", state=order.OrderState.confirmation)
async def confirm_order_h(m: types.Message, state: FSMContext):
    await order.confirm_order(m, state, bot)


@dp.message_handler(lambda m: m.text == "✏️ Змінити телефон", state=order.OrderState.confirmation)
async def edit_order_phone_h(m: types.Message, state: FSMContext):
    await order.edit_order_phone(m, state)


@dp.message_handler(lambda m: m.text == "✏️ Змінити ім’я", state=order.OrderState.confirmation)
async def edit_order_fio_h(m: types.Message, state: FSMContext):
    await order.edit_order_fio(m, state)


@dp.message_handler(lambda m: m.text == "✏️ Змінити доставку", state=order.OrderState.confirmation)
async def edit_order_delivery_h(m: types.Message, state: FSMContext):
    await order.edit_order_delivery(m, state)


@dp.message_handler(content_types=["contact", "text"], state=order.OrderState.waiting_for_phone)
async def phone_h(m: types.Message, state: FSMContext):
    await order.get_phone(m, state)


@dp.message_handler(state=order.OrderState.waiting_for_fio)
async def fio_h(m: types.Message, state: FSMContext):
    await order.get_fio(m, state)


@dp.message_handler(state=order.OrderState.waiting_for_delivery)
async def deliv_h(m: types.Message, state: FSMContext):
    await order.get_delivery(m, state, bot)


# =========================
# ADMIN ADD PRODUCT FSM
# =========================

@dp.message_handler(state=admin.AddProductState.waiting_for_article)
async def admin_article_h(m: types.Message, state: FSMContext):
    await admin.save_article(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_brand)
async def admin_brand_h(m: types.Message, state: FSMContext):
    await admin.save_brand(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_model)
async def admin_model_h(m: types.Message, state: FSMContext):
    await admin.save_model(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_category)
async def admin_category_h(m: types.Message, state: FSMContext):
    await admin.save_category(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_season)
async def admin_season_h(m: types.Message, state: FSMContext):
    await admin.save_season(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_price)
async def admin_price_h(m: types.Message, state: FSMContext):
    await admin.save_price(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_sizes)
async def admin_sizes_h(m: types.Message, state: FSMContext):
    await admin.save_sizes(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_description)
async def admin_description_h(m: types.Message, state: FSMContext):
    await admin.save_description(m, state)


@dp.message_handler(content_types=["photo"], state=admin.AddProductState.waiting_for_photos)
async def admin_photo_h(m: types.Message, state: FSMContext):
    await admin.collect_photo(m, state)


@dp.message_handler(lambda m: m.text == "✅ Фото готово", state=admin.AddProductState.waiting_for_photos)
async def admin_finish_photos_h(m: types.Message, state: FSMContext):
    await admin.finish_photos(m, state)


@dp.message_handler(state=admin.AddProductState.waiting_for_stock)
async def admin_stock_h(m: types.Message, state: FSMContext):
    await admin.save_stock(m, state)


# =========================
# ADMIN PUBLISH SEARCH FSM
# =========================

@dp.message_handler(state=admin.PublishSearchState.waiting_for_query)
async def admin_publish_search_query_h(m: types.Message, state: FSMContext):
    await admin.handle_publish_search_query(m, state)


# =========================
# ADMIN EDIT DRAFT FSM
# =========================

@dp.message_handler(content_types=["photo"], state=admin.EditDraftState.waiting_for_photos)
async def admin_edit_draft_photo_h(m: types.Message, state: FSMContext):
    await admin.collect_photo(m, state)


@dp.message_handler(lambda m: m.text == "✅ Фото готово", state=admin.EditDraftState.waiting_for_photos)
async def admin_edit_draft_finish_photos_h(m: types.Message, state: FSMContext):
    await admin.finish_photos(m, state)


@dp.message_handler(state=admin.EditDraftState.waiting_for_value)
async def admin_edit_draft_value_h(m: types.Message, state: FSMContext):
    await admin.save_draft_edited_field(m, state)


# =========================
# ADMIN EDIT SAVED FSM
# =========================

@dp.message_handler(content_types=["photo"], state=admin.EditSavedState.waiting_for_photos)
async def admin_edit_saved_photo_h(m: types.Message, state: FSMContext):
    await admin.collect_photo(m, state)


@dp.message_handler(lambda m: m.text == "✅ Фото готово", state=admin.EditSavedState.waiting_for_photos)
async def admin_edit_saved_finish_photos_h(m: types.Message, state: FSMContext):
    await admin.finish_photos(m, state)
    await cache.update()


@dp.message_handler(state=admin.EditSavedState.waiting_for_value)
async def admin_edit_saved_value_h(m: types.Message, state: FSMContext):
    await admin.save_saved_edited_field(m, state, bot)
    await cache.update()


if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
