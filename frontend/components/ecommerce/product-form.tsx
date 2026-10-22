"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import MediaPicker from "@/components/organic/media-picker";
import { errorText } from "@/components/organic/shared";
import SideSheet from "@/components/ui/side-sheet";
import { archiveProduct, createProduct, ecommerceKeys, fetchCategories, fetchProduct, updateProduct } from "@/lib/api/ecommerce";
import { productKeys } from "@/lib/api/products";
import type { FieldInfo, ProductDetail, ProductSave } from "@/lib/types/ecommerce";

const INPUT = "w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

type Values = Record<string, string>;

function initial(p: ProductDetail | undefined): Values {
  if (!p) return { status: "draft" };
  const s = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    title: p.title, description: p.description ?? "", sku: p.sku, category_id: p.category_id ?? "",
    price: p.price_on_request ? "" : s(p.price), compare_at_price: s(p.compare_at_price), cost: s(p.cost),
    stock: s(p.stock), weight_grams: s(p.weight_grams), status: p.status, delivery_note: p.delivery_note ?? "",
  };
}

// Server 422 text per field ("price: …"), so a message lands next to its input.
function fieldErrors(err: unknown): { byField: Record<string, string>; general: string | null } {
  const text = errorText(err);
  const byField: Record<string, string> = {};
  for (const part of text.split(/(?<=\.)\s+(?=[a-z_]+: )/)) {
    const m = part.match(/^([a-z_]+): (.*)$/);
    if (m) byField[m[1]] = m[2];
  }
  return { byField, general: Object.keys(byField).length ? null : text };
}

function Form({ fields, product, onClose }: { fields: FieldInfo[]; product?: ProductDetail; onClose: () => void }) {
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ecommerceKeys.categories, queryFn: fetchCategories });
  const [v, setV] = useState<Values>(() => initial(product));
  const [media, setMedia] = useState<string[]>(() => (product?.images ?? []).map((i) => i.media_id ?? "").filter(Boolean));
  const set = (k: string, value: string) => setV((old) => ({ ...old, [k]: value }));
  const keys = new Set(fields.map((f) => f.key));
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: productKeys.list });
    void queryClient.invalidateQueries({ queryKey: ecommerceKeys.categories });
    if (product) void queryClient.invalidateQueries({ queryKey: ecommerceKeys.product(product.id) });
    onClose();
  };
  const save = useMutation({
    mutationFn: () => {
      const body: ProductSave = {};
      const text = (k: keyof ProductSave & string) => {
        if (!keys.has(k)) return;
        const raw = (v[k] ?? "").trim();
        if (product || raw) (body as Record<string, unknown>)[k] = raw || null;
      };
      text("title");
      text("description");
      text("sku");
      text("category_id");
      text("price");
      text("compare_at_price");
      text("cost");
      text("delivery_note");
      if (keys.has("status") && v.status) body.status = v.status;
      if (keys.has("stock") && (v.stock ?? "").trim() !== "") body.stock = Number(v.stock);
      if (keys.has("weight_grams")) {
        const w = (v.weight_grams ?? "").trim();
        if (w !== "" || product) body.weight_grams = w === "" ? null : Number(w);
      }
      if (keys.has("media_ids")) body.media_ids = media;
      return product ? updateProduct(product.id, body) : createProduct(body);
    },
    onSuccess: done,
  });
  const archive = useMutation({ mutationFn: () => archiveProduct(product!.id), onSuccess: done });
  const errs = save.isError ? fieldErrors(save.error) : { byField: {}, general: null };

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {fields.map((f) => {
        const label = `${f.label}${f.required ? " *" : ""}`;
        const err = errs.byField[f.key];
        let input;
        if (f.type === "textarea") {
          input = <textarea className={INPUT} rows={3} value={v[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />;
        } else if (f.type === "category") {
          input = (
            <select className={INPUT} value={v.category_id ?? ""} onChange={(e) => set("category_id", e.target.value)}>
              <option value="">No category</option>
              {(categories.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          );
        } else if (f.type === "status") {
          input = (
            <select className={INPUT} value={v.status ?? "draft"} onChange={(e) => set("status", e.target.value)}>
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="out_of_stock">Out of stock</option>
              {product && <option value="archived">Archived</option>}
            </select>
          );
        } else if (f.type === "images") {
          input = <MediaPicker value={media} onChange={(ids) => setMedia(ids)} kind="image" max={10} />;
        } else {
          const numeric = f.type === "money" || f.type === "integer";
          input = (
            <input
              className={INPUT}
              inputMode={numeric ? "decimal" : undefined}
              placeholder={f.key === "price" && !f.required ? "Leave empty for 'price on request'" : undefined}
              value={v[f.key] ?? ""}
              onChange={(e) => set(f.key, e.target.value)}
            />
          );
        }
        return (
          <label key={f.key} className="text-[12.5px] text-muted">
            {label}
            {input}
            {err && <span className="text-danger">{err}</span>}
          </label>
        );
      })}
      {errs.general && <p className="text-danger">{errs.general}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn" disabled={save.isPending}>
          {save.isPending ? "Saving…" : product ? "Save changes" : "Add product"}
        </button>
        {product && product.status !== "archived" && (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={archive.isPending}
            onClick={() => {
              if (window.confirm(`Archive ${product.title}? It stays on past orders but can't be ordered.`)) archive.mutate();
            }}
          >
            Archive
          </button>
        )}
      </div>
      {archive.isError && <p className="text-danger">{errorText(archive.error)}</p>}
    </form>
  );
}

// Add / edit product (SPEC-FE-075): the fields and required marks come from the
// business type (GET /ecommerce/config); the backend validates them again.
export default function ProductForm({
  fields,
  productId,
  onClose,
}: {
  fields: FieldInfo[];
  productId: string | null;
  onClose: () => void;
}) {
  const product = useQuery({
    queryKey: ecommerceKeys.product(productId ?? ""),
    queryFn: () => fetchProduct(productId!),
    enabled: !!productId,
  });
  return (
    <SideSheet title={productId ? "Edit product" : "Add product"} onClose={onClose} wide>
      {productId && product.isPending ? (
        <p className="text-muted">Loading…</p>
      ) : productId && product.isError ? (
        <p className="text-danger">{product.error.message}</p>
      ) : (
        <Form fields={fields} product={product.data} onClose={onClose} />
      )}
    </SideSheet>
  );
}
