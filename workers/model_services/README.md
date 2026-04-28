# Model Service Runtime Notes

Structura Phase 8.5 expects model services to expose small internal HTTP APIs:

- Qwen and Granite expose OpenAI-compatible `/v1/chat/completions`.
- Text and visual embedding services expose `/embed`.
- Services must be bound to Docker-internal networking or `127.0.0.1` host ports.
- Services must not fetch user-provided URLs.
- Operators must pin image references before live release gates.

The files in this directory mirror `infrastructure/models/*.env.example` for worker
operators who deploy model services separately from the main Compose stack.
