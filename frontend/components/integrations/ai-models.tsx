"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import PasswordInput from "@/components/auth/password-input";
import { apiErrorText } from "@/components/integrations/connect-panel";
import {
  deleteAIModelKey,
  fetchAIModels,
  fetchProviderModels,
  integrationKeys,
  setAIModelOrder,
  testAIModel,
  updateAIModel,
} from "@/lib/api/integrations";
import type { AIModelList, AIModelProvider, AIModelTestResult, ModelOption } from "@/lib/types/integrations";
import { aiCampaignKeys, deleteMCPTool, fetchCreativeSettings, saveCreativeOrder, saveMCPTool, testMCPTool } from "@/lib/api/ai-campaigns";
import type { CreativeKind, CreativeSettings, MCPTool, MCPToolTest } from "@/lib/types/ai-campaigns";

const FORBIDDEN = "Only managers and above can change integrations.";

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}

const OTHER = "__other__";

// Model picker (SPEC-FE-037 amendment 2026-10-02): the provider's live list for
// the saved key, plus "Other…" to type any name the list doesn't show yet.
function ModelPicker({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: ModelOption[] | undefined;
  onChange: (v: string) => void;
}) {
  const listed = Boolean(options?.some((o) => o.id === value));
  const [custom, setCustom] = useState(false);
  const hasList = Boolean(options && options.length > 0);
  const typing = !hasList || custom || (value !== "" && !listed);
  return (
    <div className="form-row mb-2">
      <label htmlFor={id} className="text-xs">
        {label}
      </label>
      {hasList && (
        <select
          id={typing ? undefined : id}
          aria-label={typing ? label : undefined}
          value={typing ? OTHER : value}
          onChange={(e) => {
            if (e.target.value === OTHER) {
              setCustom(true);
            } else {
              setCustom(false);
              onChange(e.target.value);
            }
          }}
        >
          <option value="" disabled>
            Choose a model
          </option>
          {options?.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label === o.id ? o.id : `${o.label} (${o.id})`}
            </option>
          ))}
          <option value={OTHER}>Other… (type a name)</option>
        </select>
      )}
      {typing && (
        <input
          id={id}
          className={hasList ? "mt-1" : undefined}
          value={value}
          placeholder="Type the model name"
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

function ModelCard({
  item,
  index,
  count,
  onMove,
}: {
  item: AIModelProvider;
  index: number;
  count: number;
  onMove: (from: number, to: number) => void;
}) {
  const queryClient = useQueryClient();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(item.model ?? "");
  const [imageModel, setImageModel] = useState(item.image_model ?? "");
  const [videoModel, setVideoModel] = useState(item.video_model ?? "");
  const [test, setTest] = useState<AIModelTestResult | null>(null);
  const listKey = [...integrationKeys.aiModels, item.provider, "models"];
  // The provider's live list, only once a key is saved (it's called with that key).
  const list = useQuery({
    queryKey: listKey,
    queryFn: () => fetchProviderModels(item.provider),
    enabled: Boolean(item.key_masked),
    staleTime: 10 * 60 * 1000,
  });
  // No built-in default: an empty field is pre-filled with the provider's
  // suggestion from the live list. Nothing is saved until Save / Save & test.
  // Runs only when a new list arrives, so the user's own edits are kept.
  const listData = list.data;
  useEffect(() => {
    if (!listData?.ok) return;
    setModel((m) => m || listData.suggested.chat || "");
    if (item.has_images) setImageModel((m) => m || listData.suggested.image || "");
  }, [listData, item.has_images]);
  const done = (d: AIModelList) => {
    queryClient.setQueryData(integrationKeys.aiModels, d);
    setKey("");
    void queryClient.invalidateQueries({ queryKey: listKey });
  };
  const body = (chat: string) => ({
    ...(key.trim() ? { api_key: key.trim() } : {}),
    ...(chat.trim() ? { model: chat.trim() } : {}),
    ...(item.has_images ? { image_model: imageModel.trim() } : {}),
    ...(item.has_video ? { video_model: videoModel.trim() } : {}),
  });
  const save = useMutation({ mutationFn: () => updateAIModel(item.provider, body(model)), onSuccess: done });
  const toggle = useMutation({ mutationFn: () => updateAIModel(item.provider, { enabled: !item.enabled }), onSuccess: done });
  const remove = useMutation({ mutationFn: () => deleteAIModelKey(item.provider), onSuccess: done });
  // SPEC-FE-037 amendment: Test checks what's on screen. Unsaved key/model
  // changes are saved first ("Save & test"); a failed save skips the test.
  const dirty =
    Boolean(key.trim()) ||
    model.trim() !== (item.model ?? "") ||
    (item.has_images && imageModel.trim() !== (item.image_model ?? "")) ||
    (item.has_video && videoModel.trim() !== (item.video_model ?? ""));
  const runTest = useMutation({
    // `chosen` comes from a "Switch to" button: save that model, then test it.
    mutationFn: async (chosen: string | undefined) => {
      if (dirty || chosen) done(await updateAIModel(item.provider, body(chosen ?? model)));
      return testAIModel(item.provider);
    },
    onSuccess: (r) => {
      setTest(r);
      void queryClient.invalidateQueries({ queryKey: integrationKeys.aiModels });
    },
  });
  const err = save.error ?? toggle.error ?? remove.error ?? runTest.error;
  const switchTo = (m: string) => {
    setModel(m);
    runTest.mutate(m);
  };
  const needsModel = Boolean(item.key_masked) && !item.model;

  let listNote: ReactNode = null;
  if (list.isFetching) listNote = "Loading the models your key can use…";
  else if (list.data?.ok) listNote = `${list.data.chat.length} models from ${item.label}.`;
  else if (list.data?.error) listNote = <span className="text-danger">Couldn&apos;t load the model list: {list.data.error}</span>;
  else if (list.isError) listNote = <span className="text-danger">{apiErrorText(list.error, FORBIDDEN)}</span>;

  return (
    <div className="integration-card" data-provider={item.provider}>
      <div className="integration-header">
        <div className="integration-name">
          <span className="mr-1.5 text-muted">#{index + 1}</span>
          {item.label}
        </div>
        <span className={`badge ${item.enabled ? "badge-success" : needsModel ? "badge-warn" : "badge-neutral"}`}>
          {item.enabled ? "Active" : !item.key_masked ? "No key" : needsModel ? "Choose a model" : "Off"}
        </span>
      </div>
      <div className="form-row mb-2">
        <label htmlFor={`ai_key_${item.provider}`} className="text-xs">
          API key {item.key_masked && <span className="font-normal text-muted">(saved {item.key_masked})</span>}
        </label>
        <PasswordInput
          id={`ai_key_${item.provider}`}
          autoComplete="off"
          placeholder={item.key_masked ? "Leave empty to keep the saved key" : "Paste your API key"}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </div>
      <ModelPicker id={`ai_model_${item.provider}`} label="Model" value={model} options={list.data?.chat} onChange={setModel} />
      {item.has_images && (
        <ModelPicker
          id={`ai_image_model_${item.provider}`}
          label="Image model (used by Create with AI)"
          value={imageModel}
          options={list.data?.image}
          onChange={setImageModel}
        />
      )}
      {item.has_video && (
        <ModelPicker
          id={`ai_video_model_${item.provider}`}
          label="Video model (Organic › Video Generation; optional)"
          value={videoModel}
          options={list.data?.video}
          onChange={setVideoModel}
        />
      )}
      {item.key_masked ? (
        <p className="m-0 mb-2 text-xs text-muted">
          {listNote}{" "}
          <button type="button" className="text-accent underline" disabled={list.isFetching} onClick={() => void list.refetch()}>
            Refresh list
          </button>
        </p>
      ) : (
        <p className="m-0 mb-2 text-xs text-muted">Save your key to choose from the models it can use.</p>
      )}
      {item.last_error ? (
        <p className="m-0 mb-2 text-xs text-danger">Last error: {item.last_error}</p>
      ) : item.last_ok_at ? (
        <p className="m-0 mb-2 text-xs text-success">Last worked: {when(item.last_ok_at)}</p>
      ) : null}
      {test && (
        <div className={`m-0 mb-2 text-xs ${test.ok ? "text-success" : "text-danger"}`} role="status">
          {test.ok ? `Test OK — ${test.model} answered in ${test.latency_ms} ms` : `Test failed: ${test.error}`}
          {!test.ok && test.suggestions.length > 0 && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {test.suggestions.map((m) => (
                <button
                  key={m}
                  type="button"
                  className={m === test.suggested ? "btn btn-sm" : "btn btn-secondary btn-sm"}
                  disabled={runTest.isPending}
                  onClick={() => switchTo(m)}
                >
                  Switch to {m}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" className="btn btn-sm" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={(!item.key_masked && !key.trim()) || !model.trim() || runTest.isPending}
          title={model.trim() ? undefined : "Choose a model first"}
          onClick={() => runTest.mutate(undefined)}
        >
          {runTest.isPending ? "Testing…" : dirty ? "Save & test" : "Test"}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={!item.key_masked || (!item.enabled && !item.model) || toggle.isPending}
          title={needsModel ? "Choose and save a model first" : undefined}
          onClick={() => toggle.mutate()}
        >
          {item.enabled ? "Disable" : "Enable"}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move ${item.label} up`} disabled={index === 0} onClick={() => onMove(index, index - 1)}>
          ↑
        </button>
        <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move ${item.label} down`} disabled={index === count - 1} onClick={() => onMove(index, index + 1)}>
          ↓
        </button>
        {item.key_masked && (
          <button
            type="button"
            className="btn btn-ghost btn-sm text-danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Remove the ${item.label} key?`)) remove.mutate();
            }}
          >
            Remove key
          </button>
        )}
      </div>
      <a href={item.docs_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs text-accent">
        Get an API key ↗
      </a>
      {err && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {apiErrorText(err, FORBIDDEN)}
        </p>
      )}
    </div>
  );
}

// AI Models (SPEC-FE-037 / SPEC-BE-053): the company's own LLM keys, tried in
// this order; if one fails the next answers automatically.
export default function AIModels() {
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: integrationKeys.aiModels, queryFn: fetchAIModels });
  const reorder = useMutation({
    mutationFn: (order: AIModelProvider["provider"][]) => setAIModelOrder(order),
    onSuccess: (d) => queryClient.setQueryData(integrationKeys.aiModels, d),
  });
  const move = (from: number, to: number) => {
    if (!models.data) return;
    const order = models.data.providers.map((p) => p.provider);
    const [item] = order.splice(from, 1);
    order.splice(to, 0, item);
    reorder.mutate(order);
  };

  return (
    <section className="mb-8">
      <h2 className="section-title">AI Models</h2>
      <p className="m-0 mb-3 text-[13px] text-muted">
        Add one or more AI providers. They&apos;re tried in this order: if the first model fails (error, timeout or
        quota), the next one answers automatically. Keys are stored encrypted and never shown again.
      </p>
      {models.isPending ? (
        <p className="text-[13px] text-muted">Loading AI models…</p>
      ) : models.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load AI models: {models.error.message}
        </p>
      ) : (
        <>
          <div className="integrations-grid">
            {models.data.providers.map((p, i) => (
              <ModelCard key={p.provider} item={p} index={i} count={models.data.providers.length} onMove={move} />
            ))}
          </div>
          <p className="mb-0 mt-2 text-xs text-muted">
            {models.data.providers.some((p) => p.enabled)
              ? "AI features use the active models above, in order."
              : models.data.env_fallback.configured
                ? `No model is active here, so the server default (${models.data.env_fallback.provider}) is used.`
                : "No AI model is active yet — AI features (creative generation, reply drafts, command chat) need at least one."}
          </p>
          {reorder.isError && (
            <p className="mb-0 mt-2 text-xs text-danger" role="alert">
              {apiErrorText(reorder.error, FORBIDDEN)}
            </p>
          )}
        </>
      )}
      <CreativeSettingsSection />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Creative providers (SPEC-BE-070): which source the AI Ad Autopilot tries
// first for each task, and MCP creative tools (generators only; they never
// get ad platform access).
// ---------------------------------------------------------------------------
const KIND_LABEL: Record<CreativeKind, string> = { plan: "Campaign plan", copy: "Ad copy", review: "Policy review", image: "Images", video: "Videos" };

function OrderRow({ kind, data, onSave, saving }: { kind: CreativeKind; data: CreativeSettings; onSave: (keys: string[]) => void; saving: boolean }) {
  const order = data.order[kind] ?? [];
  const label = (key: string) => data.available[kind]?.find((a) => a.key === key)?.label ?? key;
  const ready = (key: string) => data.available[kind]?.find((a) => a.key === key)?.ready ?? false;
  const move = (i: number, d: number) => {
    const next = [...order];
    const [k] = next.splice(i, 1);
    next.splice(i + d, 0, k);
    onSave(next);
  };
  return (
    <div className="mb-2 text-[13px]" data-kind={kind}>
      <b>{KIND_LABEL[kind]}:</b>{" "}
      {order.length === 0 && <span className="text-muted">none set up</span>}
      {order.map((key, i) => (
        <span key={key} className="mr-2 inline-flex items-center gap-1">
          {i + 1}. {label(key)}
          {!ready(key) && <span className="text-xs text-warn">(not set up)</span>}
          <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move ${label(key)} earlier`} disabled={i === 0 || saving} onClick={() => move(i, -1)}>
            ↑
          </button>
        </span>
      ))}
    </div>
  );
}

function MCPForm({ tool, onSaved, onCancel }: { tool: MCPTool | null; onSaved: (d: CreativeSettings) => void; onCancel: () => void }) {
  const [id, setId] = useState(tool?.id ?? "");
  const [name, setName] = useState(tool?.name ?? "");
  const [url, setUrl] = useState(tool?.url ?? "https://");
  const [token, setToken] = useState("");
  const [tools, setTools] = useState<Partial<Record<CreativeKind, string>>>(tool?.tools ?? {});
  const [args, setArgs] = useState(JSON.stringify(tool?.arguments?.image ?? { prompt: "{prompt}", aspect_ratio: "{aspect_ratio}" }));
  const [cost, setCost] = useState(String(tool?.cost_cents_per_call ?? 0));
  const [argsError, setArgsError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(args) as Record<string, unknown>;
      } catch {
        setArgsError('Arguments must be JSON, e.g. {"prompt": "{prompt}"}.');
        throw new Error("Arguments must be valid JSON.");
      }
      setArgsError(null);
      const argumentMap = Object.fromEntries((Object.keys(tools) as CreativeKind[]).filter((k) => tools[k]).map((k) => [k, parsed]));
      return saveMCPTool(id.trim(), {
        name: name.trim(),
        url: url.trim(),
        ...(token.trim() ? { token: token.trim() } : {}),
        enabled: true,
        tools,
        arguments: argumentMap,
        cost_cents_per_call: Number(cost) || 0,
      });
    },
    onSuccess: onSaved,
  });
  return (
    <div className="card mb-3" data-testid="mcp-form">
      <div className="grid gap-x-4 sm:grid-cols-2">
        <div className="form-row">
          <label htmlFor="mcp_id">Short ID (letters, numbers, - or _)</label>
          <input id="mcp_id" value={id} disabled={Boolean(tool)} onChange={(e) => setId(e.target.value.toLowerCase())} placeholder="brand-images" />
        </div>
        <div className="form-row">
          <label htmlFor="mcp_name">Name</label>
          <input id="mcp_name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="form-row sm:col-span-2">
          <label htmlFor="mcp_url">MCP server URL (Streamable HTTP, https)</label>
          <input id="mcp_url" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="mcp_token">
            Bearer token {tool?.token_masked && <span className="font-normal text-muted">(saved {tool.token_masked})</span>}
          </label>
          <PasswordInput id="mcp_token" value={token} onChange={(e) => setToken(e.target.value)} placeholder={tool?.token_masked ? "Leave empty to keep the saved token" : "Optional"} />
        </div>
        <div className="form-row">
          <label htmlFor="mcp_cost">Cost per call (US cents, for your AI limit)</label>
          <input id="mcp_cost" type="number" min={0} value={cost} onChange={(e) => setCost(e.target.value)} />
        </div>
      </div>
      <fieldset className="form-row">
        <legend className="text-xs font-semibold">Tool name on the server, per task (leave empty if it doesn&apos;t do that task)</legend>
        <div className="grid gap-x-4 sm:grid-cols-4">
          {(Object.keys(KIND_LABEL) as CreativeKind[]).map((k) => (
            <div key={k} className="form-row">
              <label htmlFor={`mcp_tool_${k}`}>{KIND_LABEL[k]}</label>
              <input id={`mcp_tool_${k}`} value={tools[k] ?? ""} onChange={(e) => setTools((cur) => ({ ...cur, [k]: e.target.value }))} />
            </div>
          ))}
        </div>
      </fieldset>
      <div className="form-row">
        <label htmlFor="mcp_args">Tool arguments (JSON; placeholders {"{prompt}"}, {"{aspect_ratio}"}, {"{system}"})</label>
        <input id="mcp_args" value={args} onChange={(e) => setArgs(e.target.value)} />
        {argsError && <span className="text-xs text-danger">{argsError}</span>}
      </div>
      {save.isError && !argsError && <p className="text-xs text-danger">{apiErrorText(save.error, FORBIDDEN)}</p>}
      <div className="flex gap-2">
        <button type="button" className="btn btn-sm" disabled={save.isPending || !id.trim() || !name.trim()} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function CreativeSettingsSection() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: aiCampaignKeys.creative, queryFn: fetchCreativeSettings });
  const [editing, setEditing] = useState<MCPTool | "new" | null>(null);
  const [tested, setTested] = useState<Record<string, MCPToolTest>>({});
  const store = (d: CreativeSettings) => queryClient.setQueryData(aiCampaignKeys.creative, d);
  const order = useMutation({ mutationFn: ({ kind, keys }: { kind: CreativeKind; keys: string[] }) => saveCreativeOrder({ [kind]: keys }), onSuccess: store });
  const remove = useMutation({ mutationFn: (id: string) => deleteMCPTool(id), onSuccess: store });
  const test = useMutation({
    mutationFn: (id: string) => testMCPTool(id),
    onSuccess: (r, id) => {
      setTested((cur) => ({ ...cur, [id]: r }));
      void queryClient.invalidateQueries({ queryKey: aiCampaignKeys.creative });
    },
  });
  const failure = remove.error ?? test.error;
  return (
    <div className="mt-6" data-testid="creative-settings">
      <h3 className="mb-1 mt-0 text-[15px]">Creative (AI campaigns)</h3>
      <p className="m-0 mb-2 text-[13px] text-muted">
        Which source &quot;Create with AI&quot; tries first for each task; the next one is used if it fails. Images reuse your OpenAI and Gemini keys above.
      </p>
      {settings.isPending ? (
        <p className="text-[13px] text-muted">Loading…</p>
      ) : settings.isError ? (
        <p className="text-[13px] text-danger">{settings.error.message}</p>
      ) : (
        <>
          {(Object.keys(KIND_LABEL) as CreativeKind[]).map((k) => (
            <OrderRow key={k} kind={k} data={settings.data} saving={order.isPending} onSave={(keys) => order.mutate({ kind: k, keys })} />
          ))}
          {order.isError && <p className="text-xs text-danger">{apiErrorText(order.error, FORBIDDEN)}</p>}
          <h4 className="mb-1 mt-4 text-[14px]">Creative tools (MCP)</h4>
          <p className="m-0 mb-2 text-xs text-muted">
            Plug in an MCP server that generates images or copy. It only creates content: publishing and spending always go through your own ad connections and approvals.
          </p>
          {settings.data.mcp_tools.map((t) => (
            <div key={t.id} className="mb-2 flex flex-wrap items-center gap-2 text-[13px]" data-mcp={t.id}>
              <b>{t.name}</b>
              <span className="text-xs text-muted">{t.url}</span>
              <span className="text-xs text-muted">
                ({(Object.keys(t.tools) as CreativeKind[]).filter((k) => t.tools[k]).map((k) => KIND_LABEL[k]).join(", ")})
              </span>
              {tested[t.id] ? (
                <span className={`text-xs ${tested[t.id].ok ? "text-success" : "text-danger"}`}>{tested[t.id].message}</span>
              ) : t.last_error ? (
                <span className="text-xs text-danger">{t.last_error}</span>
              ) : null}
              <button type="button" className="btn btn-secondary btn-sm" disabled={test.isPending} onClick={() => test.mutate(t.id)}>
                Test
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(t)}>
                Edit
              </button>
              <button type="button" className="btn btn-ghost btn-sm" disabled={remove.isPending} onClick={() => remove.mutate(t.id)}>
                Delete
              </button>
            </div>
          ))}
          {editing ? (
            <MCPForm
              tool={editing === "new" ? null : editing}
              onSaved={(d) => {
                store(d);
                setEditing(null);
              }}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing("new")}>
              + Add MCP creative tool
            </button>
          )}
          {failure && <p className="text-xs text-danger">{apiErrorText(failure, FORBIDDEN)}</p>}
        </>
      )}
    </div>
  );
}
