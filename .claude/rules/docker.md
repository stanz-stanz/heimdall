---
paths:
  - "Dockerfile*"
  - "docker-compose*"
  - "infra/docker/**"
  - "**/Dockerfile"
---

# Docker rules

## Volume mounts — verify read vs write before `:ro`

Before mounting any volume as `:ro`, verify the service NEVER writes to that path. Check for:
- `conn.commit()` calls (SQLite/database writes)
- `init_db()` or schema-creation logic (creates the DB file)
- File creation, log writes, cache writes

When in doubt, mount `:rw` and add a comment explaining why.

**Why:** Delivery container was mounted client-data as `:ro`, but the bot writes to `delivery_log` in `clients.db` and `init_db()` creates the DB file. Caused a crash loop on Pi5.

## Delegation

All Docker work is delegated to the `docker-expert` agent (per memory `feedback_docker_to_expert`). Do not write or modify Dockerfiles / compose / docker-related shell directly without dispatching docker-expert first.
