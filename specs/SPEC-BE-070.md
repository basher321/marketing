# SPEC-BE-070: Creative providers — text, image and MCP generators behind one interface

Status: IMPLEMENTED (2026-10-02). Decisions made by the user on 2026-10-02: OpenAI + Gemini + product photos; MCP outbound only. Verified in a rolled-back transaction with mocked HTTP (14/14 checks): OpenAI failing → Gemini; both failing → a named error; a wrong aspect ratio or a non-image is refused; an MCP tool returns a 9:16 image over an SSE answer (session id + bearer checked); Test names a missing tool; the token is encrypted and masked; https is required; delete also removes the tool from the order.

Deviations:
- **No crop.** No image library is installed, and none was added: each provider is asked for its nearest native ratio, the real size is read from the PNG/JPEG/WebP header, and anything more than 15 % off is refused, so the next provider is tried.
- The model names are constants (`gpt-image-1`, `gemini-2.5-flash-image`).
- The image cost (4 US cents) is an estimate, used only for the company's daily AI limit. Used by SPEC-BE-069.

## Purpose
The Autopilot must work with Claude and other LLMs, purpose-built ad-creative generators and suitable MCP servers. New sources must plug in without changing the pipeline.

## The interface (`ai/creative_providers.py`)
```python
class CreativeProvider(Protocol):
    key: str                         # "llm", "openai_image", "gemini_image", "mcp:<id>"
    kinds: set[str]                  # {"plan", "copy", "review"} | {"image"} | any subset
    def available(self, db, tenant_id) -> bool
    def generate(self, db, tenant_id, request: CreativeRequest) -> CreativeResult
```
- `CreativeRequest` = `{kind, schema_name, instructions, context, constraints: {limits, aspect_ratio, count}}`.
- `CreativeResult` = `{data | images[{bytes|url, mime, width, height}], provider, model, usage: {input_tokens, output_tokens, images, cost_cents}}`.
- A **registry** lists providers, and per-company settings choose an order per kind. The pipeline asks for "a provider for kind X". The registry tries them in order and falls back on errors. That's the only place providers are chosen.

## Built-in providers
| Provider | Kinds | How | Why it fits |
|---|---|---|---|
| **LLM chain** (`llm`) | plan, copy, review | The existing `llm_client.complete_with_usage(db=, tenant_id=)`, i.e. the company's own Claude → GPT → Gemini → Groq order (SPEC-BE-053), with JSON-schema output | Already in place, per-company keys, fallback. Claude is the recommended first choice for planning and policy review: strongest instruction-following on strict JSON and long brand rules |
| **OpenAI images** (`openai_image`) | image | `POST /v1/images/generations` with the company's saved OpenAI key; sizes mapped to the aspect ratio | A widely used, mature image API. Reuses the key in AI Models |
| **Gemini images** (`gemini_image`) | image | Gemini image generation with the company's saved Gemini key (OpenAI-compatible or native endpoint, confirmed in the plan step) | A second, independent image source as fallback |
| **Product images** (`catalog`) | image | The product's own images (no generation) | Zero cost, always on-brand; the default when products are featured |

The model names live in one constant per provider (as in `ai/providers.py`).

## MCP providers (purpose-built generators)
- An MCP server that exposes a creative tool (for example a text-to-image or ad-copy service with an MCP endpoint) can be added per company in **Integrations › AI Models › Creative tools**, with these fields:
  - server URL (https, SSRF guard);
  - bearer token (Fernet-encrypted, as other keys);
  - the tool name for each kind (e.g. `image` → `generate_image`);
  - a JSON argument template with placeholders (`{prompt}`, `{aspect_ratio}`, `{width}`, `{height}`).
- Transport: MCP Streamable HTTP, JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`), in a small `httpx` client (`integrations/mcp_client.py`, no new dependency). "Test" runs `initialize` + `tools/list` and checks that the mapped tools exist.
- Results: `content[]` items of type `image` (base64) or `text` (JSON, parsed against the stage's schema), or a `resource_link` to an https image (downloaded with size/type checks).
- **Boundary:** an MCP provider only *generates* content. It never receives platform tokens and never calls ad platform APIs. All platform writes stay on the direct-API path, with approvals and caps (the user's integration decision of 2026-10-01).

## Validation of outputs (all providers)
- Text: parsed into the stage's Pydantic schema, with every platform limit checked. Unknown keys are dropped.
- Images:
  - magic-byte type check (PNG/JPEG/WebP);
  - size ≤ 30 MB;
  - the aspect ratio within 2 % of the request, otherwise center-cropped when the difference is under 15 % (Pillow, already used? confirmed in the plan step; otherwise the image is rejected);
  - the provider's safety flags respected (a refused image → the next provider).
- Every result records the provider, model and usage. The cost is added to the run and checked against the company's daily AI limit.

## Settings and API
- `GET/PUT /ai-models/creative` (manager+): the order per kind (`plan`, `copy`, `review`, `image`) and the enabled image providers.
- `GET/PUT/DELETE /ai-models/mcp/{id}` and `POST …/test`: the MCP creative tools.

## Acceptance criteria
1. With the OpenAI image provider failing (mocked 500) → Gemini answers. Both failing → the catalog image when products are featured, otherwise the stage fails.
2. An MCP mock server (MockTransport) answering `tools/call` with a base64 PNG → an image result. A tool missing from `tools/list` → Test fails with that tool's name.
3. A wrong aspect ratio is cropped or rejected by the rules above. A non-image is rejected.
4. MCP tokens are encrypted and masked, and never logged.

## Target files
- New: `ai/creative_providers.py`, `integrations/mcp_client.py`.
- Changed: `ai/providers.py` (the image call helpers), `services/ai_model_service.py` and `api/v1/ai_models.py` (creative settings + MCP tools), `schemas/ai_model.py`.

## Amendment (2026-10-02): image models are chosen by the company

Status: APPROVED (2026-10-02), part of the SPEC-BE-053 amendment of the same date. `OPENAI_IMAGE_MODEL` / `GEMINI_IMAGE_MODEL` are removed. The OpenAI and Gemini image providers use the `image_model` saved on that provider in AI Models (picked from the live list). Without a saved key **and** image model, the provider isn't available, and the Create with AI readiness says "choose an image model in Integrations › AI Models".
