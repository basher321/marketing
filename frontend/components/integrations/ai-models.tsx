"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import PasswordInput from "@/components/auth/password-input";
import { apiErrorText } from "@/components/integrations/connect-panel";
import {
  AI_BASE,
  deleteAIModelKey,
  fetchAIModels,
  fetchProviderModels,
  integrationKeys,
  PLATFORM_AI_BASE,
  setAIModelOrder,
  testAIModel,
  updateAIModel,
} from "@/lib/api/integrations";
import { platformKeys } from "@/lib/api/platform";
import type { AIModelList, AIModelProvider, AIModelTestResult, ModelOption } from "@/lib/types/integrations";
import {
  aiCampaignKeys,
  fetchCreativeSettings,
  fetchVideoAudio,
  saveCreativeOrder,
  saveVideoAudio,
} from "@/lib/api/ai-campaigns";
import { fetchMedia, mediaKeys, uploadMedia } from "@/lib/api/media";
import { TTS_VOICES } from "@/lib/types/ai-campaigns";
import type { CreativeKind, CreativeSettings, TTSVoice, VideoAudioSave, VideoAudioSettings } from "@/lib/types/ai-campaigns";

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
  base,
  qk,
}: {
  item: AIModelProvider;
  index: number;
  count: number;
  onMove: (from: number, to: number) => void;
  /** SPEC-FE-068: PLATFORM_AI_BASE on the Super admin screen. */
  base: string;
  qk: readonly unknown[];
}) {
  const queryClient = useQueryClient();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(item.model ?? "");
  const [imageModel, setImageModel] = useState(item.image_model ?? "");
  const [videoModel, setVideoModel] = useState(item.video_model ?? "");
  const [test, setTest] = useState<AIModelTestResult | null>(null);
  const listKey = [...qk, item.provider, "models"];
  // A local provider (Ollama, SPEC-BE-088) takes no key: it counts as "has a key".
  const hasKey = Boolean(item.key_masked) || !item.needs_key;
  // The provider's live list, only once a key is saved (it's called with that key).
  const list = useQuery({
    queryKey: listKey,
    queryFn: () => fetchProviderModels(item.provider, base),
    enabled: hasKey,
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
    queryClient.setQueryData(qk, d);
    setKey("");
    void queryClient.invalidateQueries({ queryKey: listKey });
  };
  const body = (chat: string) => ({
    ...(key.trim() ? { api_key: key.trim() } : {}),
    ...(chat.trim() ? { model: chat.trim() } : {}),
    ...(item.has_images ? { image_model: imageModel.trim() } : {}),
    ...(item.has_video ? { video_model: videoModel.trim() } : {}),
  });
  const save = useMutation({ mutationFn: () => updateAIModel(item.provider, body(model), base), onSuccess: done });
  const toggle = useMutation({ mutationFn: () => updateAIModel(item.provider, { enabled: !item.enabled }, base), onSuccess: done });
  const remove = useMutation({ mutationFn: () => deleteAIModelKey(item.provider, base), onSuccess: done });
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
      if (dirty || chosen) done(await updateAIModel(item.provider, body(chosen ?? model), base));
      return testAIModel(item.provider, base);
    },
    onSuccess: (r) => {
      setTest(r);
      void queryClient.invalidateQueries({ queryKey: qk });
    },
  });
  const err = save.error ?? toggle.error ?? remove.error ?? runTest.error;
  const switchTo = (m: string) => {
    setModel(m);
    runTest.mutate(m);
  };
  const needsModel = hasKey && !item.model;

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
          {item.enabled ? "Active" : !hasKey ? "No key" : needsModel ? "Choose a model" : "Off"}
        </span>
      </div>
      <div className="form-row mb-2">
        <label htmlFor={`ai_key_${item.provider}`} className="text-xs">
          API key {item.key_masked && <span className="font-normal text-muted">(saved {item.key_masked})</span>}
        </label>
        <PasswordInput
          id={`ai_key_${item.provider}`}
          autoComplete="off"
          placeholder={item.key_masked ? "Leave empty to keep the saved key" : item.needs_key ? "Paste your API key" : "No key needed for a local Ollama"}
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
      {hasKey ? (
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
          disabled={(!hasKey && !key.trim()) || !model.trim() || runTest.isPending}
          title={model.trim() ? undefined : "Choose a model first"}
          onClick={() => runTest.mutate(undefined)}
        >
          {runTest.isPending ? "Testing…" : dirty ? "Save & test" : "Test"}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={!hasKey || (!item.enabled && !item.model) || toggle.isPending}
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
        {item.needs_key ? "Get an API key ↗" : "Download Ollama ↗"}
      </a>
      {err && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {apiErrorText(err, FORBIDDEN)}
        </p>
      )}
    </div>
  );
}

// AI Models (SPEC-FE-037 / SPEC-BE-053). SPEC-FE-068 / SPEC-BE-101: the keys are
// PilotSonic's. `admin` = the Super admin's editor (keys, models, order, test);
// otherwise the company's read-only view, plus its own creative order and the
// slideshow sound settings.
export default function AIModels({ admin = false }: { admin?: boolean }) {
  const queryClient = useQueryClient();
  const base = admin ? PLATFORM_AI_BASE : AI_BASE;
  const qk = admin ? platformKeys.aiModels : integrationKeys.aiModels;
  const models = useQuery({ queryKey: qk, queryFn: () => fetchAIModels(base) });
  const reorder = useMutation({
    mutationFn: (order: AIModelProvider["provider"][]) => setAIModelOrder(order, base),
    onSuccess: (d) => queryClient.setQueryData(qk, d),
  });
  const move = (from: number, to: number) => {
    if (!models.data) return;
    const order = models.data.providers.map((p) => p.provider);
    const [item] = order.splice(from, 1);
    order.splice(to, 0, item);
    reorder.mutate(order);
  };

  if (!admin) {
    const active = (models.data?.providers ?? []).filter((p) => p.enabled);
    return (
      <section className="mb-8" data-testid="ai-models-provided">
        <h2 className="section-title">AI Models</h2>
        <p className="m-0 mb-3 text-[13px] text-muted">
          AI is provided by PilotSonic: there&apos;s no key to add. The models below are tried in this order; if one
          fails, the next answers automatically.
        </p>
        {models.isPending ? (
          <p className="text-[13px] text-muted">Loading AI models…</p>
        ) : models.isError ? (
          <p className="text-[13px] text-danger" role="alert">
            Failed to load AI models: {models.error.message}
          </p>
        ) : active.length === 0 ? (
          <p className="text-[13px] text-warn">PilotSonic&apos;s AI isn&apos;t set up yet. The Super admin adds the AI models.</p>
        ) : (
          <div className="integrations-grid">
            {active.map((p, i) => (
              <div key={p.provider} className="integration-card" data-provider={p.provider}>
                <div className="integration-header">
                  <div className="integration-name">
                    <span className="mr-1.5 text-muted">#{i + 1}</span>
                    {p.label}
                  </div>
                  <span className={`badge ${p.last_error ? "badge-warn" : "badge-success"}`}>{p.last_error ? "Unavailable now" : "Ready"}</span>
                </div>
                <p className="m-0 text-xs text-muted">Model: {p.model}</p>
                {p.image_model && <p className="m-0 text-xs text-muted">Images: {p.image_model}</p>}
                {p.video_model && <p className="m-0 text-xs text-muted">Video: {p.video_model}</p>}
              </div>
            ))}
          </div>
        )}
        <CreativeSettingsSection />
        <VideoAudioSection />
      </section>
    );
  }

  return (
    <section className="mb-8" data-testid="ai-models-admin">
      <h2 className="section-title">AI providers</h2>
      <p className="m-0 mb-3 text-[13px] text-muted">
        PilotSonic&apos;s own keys, used by every company. They&apos;re tried in this order: if the first model fails (error,
        timeout or quota), the next one answers automatically. Keys are stored encrypted and never shown again.
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
              <ModelCard key={p.provider} item={p} index={i} count={models.data.providers.length} onMove={move} base={base} qk={qk} />
            ))}
          </div>
          <p className="mb-0 mt-2 text-xs text-muted">
            {models.data.providers.some((p) => p.enabled)
              ? "Every company's AI features use the active models above, in order."
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

function CreativeSettingsSection() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: aiCampaignKeys.creative, queryFn: fetchCreativeSettings });
  const store = (d: CreativeSettings) => queryClient.setQueryData(aiCampaignKeys.creative, d);
  const order = useMutation({ mutationFn: ({ kind, keys }: { kind: CreativeKind; keys: string[] }) => saveCreativeOrder({ [kind]: keys }), onSuccess: store });
  const failure = order.error;
  return (
    <div className="mt-6" data-testid="creative-settings">
      <h3 className="mb-1 mt-0 text-[15px]">Creative (AI campaigns)</h3>
      <p className="m-0 mb-2 text-[13px] text-muted">
        Which source &quot;Create with AI&quot; tries first for each task; the next one is used if it fails. Images use PilotSonic&apos;s OpenAI and Gemini models.
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
          {failure && <p className="text-xs text-danger">{apiErrorText(failure, FORBIDDEN)}</p>}
        </>
      )}
    </div>
  );
}

// Sound for AI videos (SPEC-FE-060): voiceover + background music for the
// OpenAI slideshow videos (SPEC-BE-094). Veo videos come with their own sound.
function VideoAudioSection() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: aiCampaignKeys.videoAudio, queryFn: fetchVideoAudio });
  const tracks = useQuery({ queryKey: mediaKeys.list("audio"), queryFn: () => fetchMedia("audio") });
  const save = useMutation({
    mutationFn: (changes: Partial<VideoAudioSave>) => {
      const cur = settings.data as VideoAudioSettings;
      return saveVideoAudio({ voiceover: cur.voiceover, voice: cur.voice, music_media_id: cur.music_media_id, music_volume: cur.music_volume, ...changes });
    },
    onSuccess: (d) => queryClient.setQueryData(aiCampaignKeys.videoAudio, d),
  });
  const upload = useMutation({
    mutationFn: async (file: File) => (await uploadMedia(file)).id,
    onSuccess: (id) => {
      void queryClient.invalidateQueries({ queryKey: mediaKeys.list("audio") });
      save.mutate({ music_media_id: id });
    },
  });
  const failure = save.error ?? upload.error;
  if (settings.isPending) return <p className="mt-6 text-[13px] text-muted">Loading sound settings…</p>;
  if (settings.isError) return <p className="mt-6 text-[13px] text-danger">{apiErrorText(settings.error, FORBIDDEN)}</p>;
  const d = settings.data;
  const others = (tracks.data?.items ?? []).filter((t) => t.id !== d.music_media_id);
  return (
    <div className="mt-6" data-testid="video-audio">
      <h3 className="mb-1 mt-0 text-[15px]">Sound for AI videos</h3>
      <p className="m-0 mb-2 text-[13px] text-muted">
        Used when OpenAI makes a slideshow video. Google Veo videos come with their own sound.
      </p>
      <div className="card grid gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={d.voiceover} disabled={save.isPending} onChange={(e) => save.mutate({ voiceover: e.target.checked })} />
            AI voiceover (the AI writes a short script; OpenAI reads it)
          </label>
          <select value={d.voice} disabled={!d.voiceover || save.isPending} onChange={(e) => save.mutate({ voice: e.target.value as TTSVoice })} aria-label="Voice">
            {TTS_VOICES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-2">
          <div className="text-[13px] font-semibold">Background music</div>
          {d.music ? (
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-[13px]">{d.music.name ?? "Your track"}</span>
              <audio controls src={d.music.url} className="h-8" />
              <button type="button" className="btn btn-secondary btn-sm" disabled={save.isPending} onClick={() => save.mutate({ music_media_id: null })}>
                Remove
              </button>
            </div>
          ) : (
            <p className="m-0 text-[13px] text-muted">No music yet. Use a track you have the rights to.</p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <label className="btn btn-secondary btn-sm cursor-pointer">
              {upload.isPending ? "Uploading…" : d.music ? "Upload another track" : "Upload music"}
              <input
                type="file"
                accept="audio/mpeg,audio/mp4,audio/x-m4a,audio/wav,.mp3,.m4a,.wav"
                className="hidden"
                disabled={upload.isPending}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload.mutate(f);
                  e.target.value = "";
                }}
              />
            </label>
            <span className="text-xs text-muted">MP3, M4A or WAV, up to 20 MB</span>
            {others.length > 0 && (
              <select value="" onChange={(e) => e.target.value && save.mutate({ music_media_id: e.target.value })} aria-label="Use an uploaded track">
                <option value="">Use an uploaded track…</option>
                {others.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name ?? t.id}
                  </option>
                ))}
              </select>
            )}
          </div>
          {d.music && (
            <label className="flex items-center gap-2 text-[13px]">
              Music volume
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                defaultValue={Math.round(d.music_volume * 100)}
                onMouseUp={(e) => save.mutate({ music_volume: Number((e.target as HTMLInputElement).value) / 100 })}
                onKeyUp={(e) => save.mutate({ music_volume: Number((e.target as HTMLInputElement).value) / 100 })}
              />
              <span className="text-muted">{Math.round(d.music_volume * 100)} %</span>
            </label>
          )}
        </div>
        {failure && <p className="m-0 text-[13px] text-danger">{apiErrorText(failure, FORBIDDEN)}</p>}
      </div>
    </div>
  );
}
