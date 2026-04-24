import os
import logging
import asyncio
from typing import Any

import aiohttp

GAS_URL = os.getenv("GAS_URL")
logger = logging.getLogger("TurboBot.Database")
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _is_successful_response(data: Any) -> bool:
    if data is None:
        return False

    if isinstance(data, dict):
        if data.get("ok") is False:
            return False
        if data.get("success") is False:
            return False

    return True


def _normalize_product(item: dict[str, Any]) -> dict[str, Any]:
    product = dict(item or {})

    article = str(product.get("article") or product.get("Артикул") or "").strip()
    brand = str(product.get("brand") or product.get("Бренд") or "").strip()
    model = str(product.get("model") or product.get("Модель") or product.get("Model") or "").strip()
    category = str(product.get("category") or product.get("Категорія") or "").strip()
    season = str(product.get("season") or product.get("Сезон") or "").strip()
    price = product.get("price", product.get("Ціна", ""))
    sizes = str(product.get("sizes") or product.get("Розміри") or "").strip()
    description = str(product.get("description") or product.get("Опис") or "").strip()
    photo_ids = str(product.get("photo_ids") or product.get("Фото") or "").strip()
    status = str(product.get("status") or product.get("Статус") or "draft").strip()
    stock = str(product.get("stock") or product.get("Залишок") or "").strip()
    publish_status = str(product.get("publish_status") or product.get("Publish Status") or "").strip()
    publish_at = str(product.get("publish_at") or product.get("Publish At") or "").strip()
    published_at = str(product.get("published_at") or product.get("Published At") or "").strip()
    product_id = product.get("product_id", product.get("ID", product.get("productId", "")))

    product.update(
        {
            "product_id": product_id,
            "article": article,
            "brand": brand,
            "model": model,
            "category": category,
            "season": season,
            "price": price,
            "sizes": sizes,
            "description": description,
            "photo_ids": photo_ids,
            "status": status,
            "stock": stock,
            "publish_status": publish_status,
            "publish_at": publish_at,
            "published_at": published_at,

            "Артикул": article,
            "Бренд": brand,
            "Модель": model,
            "Model": model,
            "Категорія": category,
            "Сезон": season,
            "Ціна": price,
            "Розміри": sizes,
            "Опис": description,
            "Фото": photo_ids,
            "Статус": status,
            "Залишок": stock,
            "publish_status": publish_status,
            "publish_at": publish_at,
            "published_at": published_at,
        }
    )
    return product


def _extract_products(data: Any) -> list[dict[str, Any]]:
    if not _is_successful_response(data):
        return []

    if isinstance(data, list):
        return [_normalize_product(item) for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("products", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [_normalize_product(item) for item in value if isinstance(item, dict)]

        item = data.get("item")
        if isinstance(item, dict):
            return [_normalize_product(item)]

        if data.get("article") or data.get("Артикул"):
            return [_normalize_product(data)]

    return []


async def _request_json(
    method: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
):
    if not GAS_URL:
        logger.error("GAS_URL is not defined in environment variables")
        return None

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.request(method, GAS_URL, params=params, json=payload) as response:
                text = await response.text()

                if response.status != 200:
                    logger.error("GAS request failed: %s %s", response.status, text[:500])
                    return None

                try:
                    return await response.json(content_type=None)
                except Exception:
                    logger.warning("GAS returned non-JSON response: %s", text[:500])
                    return {"ok": True, "raw": text}

    except asyncio.TimeoutError:
        logger.error("GAS request timed out after %ss", HTTP_TIMEOUT.total)
    except Exception as exc:
        logger.error("Critical GAS request error: %s", exc, exc_info=True)

    return None


async def get_products():
    data = await _request_json("GET")
    return _extract_products(data)


async def get_all_items():
    return await get_products()


async def get_product_by_article(article: str):
    article = str(article or "").strip()
    if not article:
        return None

    data = await _request_json(
        "POST",
        payload={
            "action": "get_product_by_article",
            "article": article,
        },
    )

    if not _is_successful_response(data):
        logger.info("Product not found or GAS returned error for article %s: %s", article, data)
        return None

    products = _extract_products(data)

    if products:
        exact = next(
            (item for item in products if str(item.get("Артикул", "")).strip() == article),
            None,
        )
        return exact or products[0]

    all_products = await get_products()

    return next(
        (item for item in all_products if str(item.get("Артикул", "")).strip() == article),
        None,
    )


async def create_product(payload: dict[str, Any]):
    request_payload = {**payload, "action": "create_product"}
    data = await _request_json("POST", payload=request_payload)

    if not _is_successful_response(data):
        logger.error("create_product failed: %s", data)
        return None

    return data


async def create_order(payload: dict[str, Any]):
    request_payload = {**payload, "action": "create_order"}
    data = await _request_json("POST", payload=request_payload)

    if _is_successful_response(data):
        return data

    logger.warning("Structured create_order failed, trying legacy payload: %s", data)

    legacy_payload = {
        "article": payload.get("article", ""),
        "item": payload.get("item", ""),
        "size": payload.get("size", ""),
        "price": payload.get("price", ""),
        "fio": payload.get("customer_name", ""),
        "phone": payload.get("phone", ""),
        "delivery": payload.get("delivery", ""),
        "user": payload.get("telegram_username", ""),
        "source": payload.get("source", "direct"),
    }

    data = await _request_json("POST", payload=legacy_payload)

    if not _is_successful_response(data):
        logger.error("Legacy create_order failed: %s", data)
        return None

    return data


async def register_user(payload: dict[str, Any]):
    request_payload = {**payload, "action": "register_user"}
    data = await _request_json("POST", payload=request_payload)

    if not _is_successful_response(data):
        logger.error("register_user failed: %s", data)
        return None

    return data


async def create_post_log(payload: dict[str, Any]):
    request_payload = {**payload, "action": "create_post_log"}
    data = await _request_json("POST", payload=request_payload)

    if not _is_successful_response(data):
        logger.error("create_post_log failed: %s", data)
        return None

    return data


async def update_product_status(article: str, status: str):
    payload = {
        "action": "update_product_status",
        "article": str(article).strip(),
        "status": str(status).strip(),
    }

    data = await _request_json("POST", payload=payload)

    if not _is_successful_response(data):
        logger.warning("update_product_status failed: %s", data)
        return None

    return data


async def update_product_field(article: str, field: str, value: Any):
    payload = {
        "action": "update_product_field",
        "article": str(article).strip(),
        "field": str(field).strip(),
        "value": value,
    }

    data = await _request_json("POST", payload=payload)

    if not _is_successful_response(data):
        logger.error("update_product_field failed: %s", data)
        return None

    return data


async def update_product_fields(article: str, fields: dict[str, Any]):
    article = str(article or "").strip()
    if not article or not isinstance(fields, dict) or not fields:
        return None

    payload = {
        "action": "update_product_fields",
        "article": article,
        "fields": fields,
    }

    data = await _request_json("POST", payload=payload)
    if _is_successful_response(data):
        return data

    logger.warning("update_product_fields failed, fallback to update_product_field: %s", data)

    last_result = None
    for field, value in fields.items():
        last_result = await update_product_field(article, field, value)
        if last_result is None:
            return None

    return last_result


async def get_stats():
    return await _request_json("POST", payload={"action": "get_stats"})


def get_available_sizes(all_products, category, brand_name):
    if not all_products:
        return []

    sizes = set()
    category = str(category).strip()
    brand_name = str(brand_name).strip()

    for item in all_products:
        if str(item.get("Категорія")).strip() == category and str(item.get("Бренд")).strip() == brand_name:
            raw_val = str(item.get("Розміри", "")).replace(" ", "")
            if raw_val and raw_val.lower() != "none":
                item_sizes = [s.strip() for s in raw_val.replace(";", ",").split(",") if s.strip()]
                sizes.update(item_sizes)

    try:
        return sorted(
            list(sizes),
            key=lambda value: (
                float(value.replace(",", "."))
                if value.replace(",", "", 1).replace(".", "", 1).isdigit()
                else value
            ),
        )
    except Exception:
        return sorted(list(sizes))
