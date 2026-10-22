"""Business types (SPEC-BE-111): the one place that says which E-Commerce tabs and
product fields a company sees, and which product fields it may store.

Hiding a tab only hides it; no data is ever deleted when the type changes.
"""
from typing import Any

# Every tab the E-Commerce page knows: key -> (English, Bengali).
TAB_LABELS: dict[str, tuple[str, str]] = {
    "products": ("Products", "পণ্য"),
    "categories": ("Categories", "ক্যাটাগরি"),
    "inventory": ("Inventory", "স্টক"),
    "orders": ("Orders", "অর্ডার"),
    "customers": ("Customers", "গ্রাহক"),
    "shipping": ("Shipping", "শিপিং"),
    "payments": ("Payments", "পেমেন্ট"),
    "pricing-rules": ("Pricing Rules", "মূল্য নিয়ম"),
}

# Every product field: key -> (English, Bengali, input type).
FIELD_LABELS: dict[str, tuple[str, str, str]] = {
    "title": ("Product name", "পণ্যের নাম", "text"),
    "description": ("Description", "বিবরণ", "textarea"),
    "sku": ("SKU", "এসকেইউ", "text"),
    "category_id": ("Category", "ক্যাটাগরি", "category"),
    "price": ("Price", "দাম", "money"),
    "compare_at_price": ("Compare-at price (before discount)", "ছাড়ের আগের দাম", "money"),
    "cost": ("Cost per item", "প্রতি পিসের খরচ", "money"),
    "stock": ("Stock quantity", "স্টকের পরিমাণ", "integer"),
    "weight_grams": ("Weight (grams)", "ওজন (গ্রাম)", "integer"),
    "media_ids": ("Images", "ছবি", "images"),
    "status": ("Status", "অবস্থা", "status"),
    "delivery_note": ("How the buyer receives it", "ক্রেতা কীভাবে পাবেন", "textarea"),
}

_RETAIL_FIELDS = ["title", "description", "sku", "category_id", "price", "compare_at_price", "cost", "stock",
                  "weight_grams", "media_ids", "status"]

TYPES: dict[str, dict[str, Any]] = {
    "online_retail": {
        "label": "Online store (ships products)",
        "description": "You sell physical products online and ship them to customers.",
        "tabs": ["products", "categories", "inventory", "orders", "customers", "shipping", "payments", "pricing-rules"],
        "fields": _RETAIL_FIELDS,
        "required": ["title", "sku", "price"],
    },
    "physical_store": {
        "label": "Physical shop (pickup / in store)",
        "description": "Customers buy in your shop or pick up; you don't ship.",
        "tabs": ["products", "categories", "inventory", "orders", "customers", "payments", "pricing-rules"],
        "fields": [f for f in _RETAIL_FIELDS if f != "weight_grams"],
        "required": ["title", "sku", "price"],
    },
    "catalog": {
        "label": "Catalogue / enquiries",
        "description": "You show products and take enquiries; prices can be 'on request'.",
        "tabs": ["products", "categories", "customers", "orders"],
        "tab_overrides": {"orders": ("Enquiries", "জিজ্ঞাসা")},
        "fields": ["title", "description", "sku", "category_id", "price", "media_ids", "status"],
        "required": ["title", "sku"],
    },
    "digital": {
        "label": "Digital products",
        "description": "Downloads, courses, licences or codes: no stock, weight or shipping.",
        "tabs": ["products", "categories", "orders", "customers", "payments"],
        "fields": ["title", "description", "sku", "category_id", "price", "compare_at_price", "media_ids", "status",
                   "delivery_note"],
        "required": ["title", "sku", "price"],
    },
    "other": {
        "label": "Other",
        "description": "Something else: you get the full set of tabs.",
        "tabs": ["products", "categories", "inventory", "orders", "customers", "shipping", "payments", "pricing-rules"],
        "fields": _RETAIL_FIELDS,
        "required": ["title", "sku", "price"],
    },
}
DEFAULT_TYPE = "online_retail"
# A field the type doesn't use -> this message (422).
NOT_USED = {
    "stock": "{label} products don't have stock.",
    "weight_grams": "{label} products don't have a weight.",
    "compare_at_price": "{label} products don't use a compare-at price.",
    "cost": "{label} products don't track a cost.",
    "delivery_note": "Only digital products have a delivery note.",
}


def tabs(business_type: str) -> list[dict[str, str]]:
    spec = TYPES[business_type]
    overrides = spec.get("tab_overrides", {})
    return [{"key": k, "label": overrides.get(k, TAB_LABELS[k])[0], "label_bn": overrides.get(k, TAB_LABELS[k])[1]}
            for k in spec["tabs"]]


def product_fields(business_type: str) -> list[dict[str, Any]]:
    spec = TYPES[business_type]
    return [{"key": f, "label": FIELD_LABELS[f][0], "label_bn": FIELD_LABELS[f][1], "type": FIELD_LABELS[f][2],
             "required": f in spec["required"]} for f in spec["fields"]]


def order_fields(business_type: str) -> list[dict[str, Any]]:
    ships = "shipping" in TYPES[business_type]["tabs"]
    fields = [("customer", "Customer", True), ("items", "Items", True), ("discount", "Discount", False),
              ("payment_method", "Payment method", False), ("payment_status", "Payment status", False),
              ("notes", "Notes", False)]
    if ships:
        fields[2:2] = [("shipping_address", "Shipping address", False), ("shipping", "Shipping charge", False)]
    return [{"key": k, "label": label, "required": req} for k, label, req in fields]


def unused_message(business_type: str, field: str) -> str:
    label = TYPES[business_type]["label"].split(" (")[0]
    return NOT_USED.get(field, "{label} products don't use this field.").format(label=label)
