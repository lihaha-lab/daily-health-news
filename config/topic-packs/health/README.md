# Health topic pack

This directory contains the versioned, non-secret configuration for the health
news edition. The application core stays domain-neutral; another edition can be
created by copying this directory and changing its sources, categories,
keywords, prompts, and scoring rules.

Sources carry four domain-neutral quality fields: publisher, region,
trust_tier, and publication_mode. Official first-party feeds use `primary` and
`direct`. Aggregators and search feeds use `discovery` and `discovery_only`.
This keeps collection, verification, ranking, and publishing independently
debuggable, and lets another edition reuse the same policy vocabulary.

The health pack includes WHO RSS and Chinese and international Google News
searches. Search results are resolved to allowlisted publisher domains before
they can become direct-source candidates. WeChat account results are
discovery-only and never automatically published. A Google News redirect URL
must not be treated as the original source link.

`required_topic_keywords` is a final topic gate before ranking and AI
summarization. It checks the original title or source snippet, including
articles already in the local cache. `required_title_keywords` only checks
the original headline, so a passing mention of blood pressure in a general
food or exercise story does not qualify it. Broad terms such as "health" and
"exercise" do not qualify on their own. If nothing qualifies, the run should
produce fewer stories rather than fill the digest with unrelated news.
Other topic packs may leave both lists empty or replace them with their own.

The health edition also enables `health_review` and a bounded `search_matrix`.
Matrix searches rotate identity, event, and allowlisted regional publisher
domains each day. The 24/48/72-hour selection prefers fresh news. The review
log records why each candidate was ready, held, or excluded; it is visible at
`/admin/health-review`. "Ready" means the automatic rules passed, **not** that
a human or medical professional verified every claim. Personal death and
collapse reports stay on hold until the original attribution and cause have
been checked separately.

See `WORKFLOW_STATUS.md` for debugging steps and remaining gaps before treating
this as a fully verified news service.

See `BRIEFING.md` for the public-facing section structure, evidence rules,
required fields, and prohibited editorial patterns.

## Activation

Set the following value in the project-level `.env` file:

```dotenv
TOPIC_PACK=health
```

Do not store API keys or publishing credentials in this directory.
