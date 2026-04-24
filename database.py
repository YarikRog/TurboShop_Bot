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
    publish_status = str(product.get("publish_status") or "").strip()
    publish_at = str(product.get("publish_at") or "").strip()
    published_at = str(product.get("published_at") or "").strip()
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
