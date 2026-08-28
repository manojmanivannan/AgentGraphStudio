# 8. In-app LLM provider configuration

## Status

Accepted

## Context

The LLM provider (base URL, API key, chat model, mem0 chat/embedding models and
embedding dimension) was configured exclusively through `.env`. Changing
provider meant editing a file on the host and restarting the stack, which is
not viable for a self-contained desktop runtime and makes it hard to tell
whether a misconfiguration is in the URL, the key, or the model name.

## Decision

Provider configuration moves into the app, backed by a **single global
`provider_settings` row**, edited from a dedicated `/settings` page.

- **Env is seed/fallback only.** `canvas_server.provider_config` resolves the
  active `ProviderConfig` from the database row when one exists, otherwise from
  `.env`. All runtime consumers (`runner.py`, `memory_config.py`,
  `rag_helper.py`) read `get_provider_config()` rather than `settings.llm_*`.
- **Reads are synchronous, refreshes are explicit.** Consumers sit deep inside
  DSPy construction and cannot await, so the resolved config lives in a
  process-local cache. It is refreshed in the API lifespan, after every `PUT`,
  and — because the execution worker is a separate process — at the start of
  every claimed durable run. Worst-case propagation lag is one run.
- **The API key is never returned.** `GET /api/settings/provider` reports only
  `api_key_set`. `PUT` treats a `null` key as "keep the stored one" and `""` as
  "clear it".
- **A `Test connection` probe** (`POST /api/settings/provider/test`) validates
  the *unsaved* form values with two independent probes (chat completion and
  embedding, the latter also asserting the returned vector width). Provider
  failures are reported as `ok: false` results, never as HTTP errors.
- **Embedding dimension changes are gated.** Changing the dimension invalidates
  every stored RAG chunk and mem0 vector, so `PUT` returns 409 unless
  `confirm_reindex` is set; with confirmation the backend deletes all
  `agent_document_chunks` and drops the local Qdrant store.
- `models/canvas.py` still sizes the `SafeVector` column from `.env`, because
  that is a schema-time constant. The purge above is what keeps stored data
  consistent when the runtime dimension changes.

## Consequences

- Switching providers no longer requires a restart or host file access, and
  misconfiguration is diagnosable from the UI before a run is attempted.
- The API key is stored in plaintext, at the same trust level as the `.env`
  file it replaces. Encrypting it at rest is deliberate follow-up work.
- Configuration is app-wide: there are no per-user or per-canvas overrides.
- Infrastructure settings (Postgres, MLflow, sandbox limits, LLM timeouts)
  remain `.env`-only.
