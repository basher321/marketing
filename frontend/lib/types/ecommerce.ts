/** Business type, products by hand and categories (SPEC-FE-075), mirroring app/schemas/ecommerce.py (SPEC-BE-111). */
export type BusinessType = "online_retail" | "physical_store" | "catalog" | "digital" | "other";

export interface TabInfo {
  key: string;
  label: string;
  label_bn: string;
}

export interface FieldInfo {
  key: string;
  label: string;
  label_bn: string | null;
  /** text | textarea | money | integer | images | status | category */
  type: string | null;
  required: boolean;
}

export interface EcommerceConfig {
  business_type: BusinessType;
  confirmed: boolean;
  confirmed_at: string | null;
  suggestion: { type: BusinessType | null; reasons: string[] };
  tabs: TabInfo[];
  product_fields: FieldInfo[];
  order_fields: FieldInfo[];
  types: { key: BusinessType; label: string; description: string }[];
}

export interface ProductDetail {
  id: string;
  sku: string;
  title: string;
  description: string | null;
  category_id: string | null;
  category: string | null;
  price: number | null;
  price_on_request: boolean;
  compare_at_price: number | null;
  cost: number | null;
  currency: string;
  stock: number | null;
  weight_grams: number | null;
  images: { media_id?: string | null; url?: string | null; alt?: string | null }[];
  status: string;
  delivery_note: string | null;
  updated_at: string;
}

/** Money values as strings (Decimal on the backend); null clears a field. */
export interface ProductSave {
  title?: string;
  description?: string | null;
  sku?: string;
  category_id?: string | null;
  price?: string | null;
  compare_at_price?: string | null;
  cost?: string | null;
  stock?: number;
  weight_grams?: number | null;
  media_ids?: string[];
  status?: string;
  delivery_note?: string | null;
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  parent_id: string | null;
  product_count: number;
}
