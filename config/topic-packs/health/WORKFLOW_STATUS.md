# Health workflow status

This is a safety-first implementation of the requested mainland cardiovascular
news workflow. It is not yet a complete automated fact-checker.

## Implemented and inspectable

1. Google News searches and RSS collection resolve to allowed publisher URLs.
2. Five regional publisher domains receive rotating identity x event x media
   searches plus broader cardiovascular searches, capped at ten queries per
   run. The exact queries appear
   on `/admin/health-review` and in the run log.
3. Source keyword rules and the cardiovascular topic gate run before ranking.
   A title match qualifies for automatic selection; two distinct topic signals
   only in the body create a review lead. Generic wellness does not qualify.
4. A missing publication date or a person-related death/collapse report goes
   to `review`, not the automatic digest. Ambiguous death wording is never
   converted to a cardiovascular diagnosis by the rule engine.
   Platform-contributor disclaimers, short source text, and cautionary
   clickbait wording also trigger review.
5. Previously used URLs from earlier local days are excluded. News is chosen
   from 24 hours first, then 48 and 72 hours if needed. No item is invented
   to meet a daily quota.
6. A post-summary check holds an item if the model adds an unsupported named
   diagnosis, death, age, or explicit causal claim.
7. Candidate decisions and reasons are saved independently of digest history
   and shown at `/admin/health-review`; a dry run does not publish to Feishu
   or WeCom and does not replace the latest formal digest.

## How to debug

- Sources and per-source keyword rules: `/admin/sources`.
- Candidate decision, reason, and rotating queries: `/admin/health-review`.
- Full run logs: `/api/logs/latest` (authentication required).
- Preview without publishing: `docker compose exec app condenseit run --dry-run --no-deploy`.
- Edit search terms, media domains, time windows, and topic terms in
  `config/topic-packs/health/config.yaml`, then restart the app container.
- Keep credentials only in `.env`. Do not put them in the topic pack.

## Not yet automated

- Exhaustive coverage of every province, county, hospital, radio station,
  official account, and short-video platform. New domains must be individually
  checked and added to the allowlist; social accounts are discovery-only.
- Finding the first-party notice and independent second source for every case.
- Human approval UI for held person-event leads. Held items remain unpublished.
- Structured extraction of person, age, event date, disease, source type,
  publication date versus data period, and research population.
- Event-level deduplication across different titles and URLs. Current story
  deduplication uses title similarity (and optional embeddings), not a verified
  identity + location + date + event key.
- The requested ten-dimensional scoring model and a fully audited 100-200 word
  internal evidence report. The public Feishu document still follows the
  previously requested concise format.
- Human final medical and factual review. Keyword and model-output checks can
  miss errors, so `ready` is not a truth certification.

Do not describe an unconfirmed cause of death as established or use this output
to make product-efficacy claims.
