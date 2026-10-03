# Contributing

Daily Health News is a configurable fork of
[CondenseIt](https://github.com/wildlifechorus/condenseit). Contributions to the
news workflow, documentation, and topic packs are welcome.

## Before opening a pull request

- Keep changes focused and add tests for changed behavior.
- Do not commit `.env`, API credentials, database files, downloaded news,
  generated briefings, logs, or backups.
- Keep source and filtering rules in a topic pack when possible. The health
  example lives in `config/topic-packs/health/`.
- Distinguish verified source facts from generated summaries. Health content
  must not be presented as individual medical advice.

## Local checks

Use Python 3.11+ and Node.js 20+:

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest tests/
cd frontend
npm ci
npm run build
```

For a full local run, copy `.env.example` to `.env`, supply your own credentials,
and use `docker compose up -d --build`.

Report security-sensitive issues privately as described in `SECURITY.md`.
