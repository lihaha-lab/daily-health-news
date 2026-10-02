# Daily Health News operations

## Pipeline

1. Collect RSS and allowlisted Google News publisher pages.
2. Apply per-source and global keyword, age, and language rules.
3. Rank and summarize candidates with the configured LLM.
4. Save the digest and attempt each configured delivery independently.

The health topic pack is in `config/topic-packs/health/config.yaml`; its
editorial policy is in `BRIEFING.md` beside it. Other topics can use a separate
directory under `config/topic-packs/` and set `TOPIC_PACK` accordingly.

## Local setup

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data, storage, logs, backups
docker compose up -d --build
docker compose ps
```

Open `http://localhost:8899`. Set a non-empty `CONDENSEIT_AUTH_PASSWORD` and
`DIGEST_PWA_SESSION_SECRET` in `.env` before exposing the service outside your
computer. Never commit `.env` or paste credentials into issues or chat.

The versioned health pack defaults to 11:00 `Pacific/Auckland`; changes made
in the Schedule page are stored in the local SQLite database and take precedence.
The computer and Docker engine must be running at the scheduled time. The
current scheduler does not automatically backfill a missed run.

## Feishu delivery

Configure `FEISHU_APP_ID` and `FEISHU_APP_SECRET`. To append each day to one
reverse-chronological document, set both `FEISHU_DIGEST_DOCUMENT_ID` and
`FEISHU_DIGEST_DOCUMENT_URL`. Give the app edit access to that document in
Feishu. Without a fixed document ID, the legacy fallback creates a separate
document each month. `FEISHU_FOLDER_TOKEN` only affects newly created monthly
documents. Link-sharing permissions are managed in Feishu and are not changed
by the fixed-document publisher.

For traceable news rows, set `FEISHU_BITABLE_APP_TOKEN` and
`FEISHU_BITABLE_TABLE_ID`. The app writes date, headline, source, source URL,
and a short summary to that table. Document and table writes report separate
results; one destination succeeding does not mean the other succeeded.

WeCom group-bot and member-app delivery are optional and currently require
their respective credentials. They do not send to a personal WeChat account.

## Debugging

Use the web pages for Sources, Digest settings, Model settings, Schedule, and
Run logs. The current `Run digest` button runs the entire pipeline and may
publish to live destinations; it is not a preview button. The API exposes a
dry-run mode, but the web UI does not yet provide per-stage preview and
approval controls. Disable the schedule while experimenting and make one
configuration change at a time.

## Persistence and migration

`data/`, `storage/`, `logs/`, and `backups/` are local bind mounts and are
intentionally outside Git. Back up these directories and `.env` securely when
migrating. Copying only the Git repository does not migrate past digests,
Feishu delivery registries, edited source settings, or schedule overrides.
