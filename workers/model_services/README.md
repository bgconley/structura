# Model Service Runtime Notes

Structura Phase 8.5 expects model services to expose small internal HTTP APIs:

- Qwen Smart Parse semantic annotation and the E4 Qwen vision fallback expose
  OpenAI-compatible `/v1/chat/completions`. Separate Qwen high-quality/rescue
  services are not part of the active runtime.
- Granite is no longer part of the default required live runtime. Operators may
  start the explicit `granite-live` profile only for rollback or comparison
  gates.
- Text and visual embedding services should expose OpenAI-compatible
  `/v1/embeddings`; Structura also supports the older internal `/embed` adapter
  shape for fixture and custom gateway deployments.
- Services must be bound to Docker-internal networking or `127.0.0.1` host ports.
- Services must not fetch user-provided URLs.
- Operators must pin image references before live release gates.

The files in this directory mirror `infrastructure/models/*.env.example` for worker
operators who deploy model services separately from the main Compose stack.
