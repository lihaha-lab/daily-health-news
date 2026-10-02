"""Ollama-backed summarization."""

import logging
from typing import Any

import ollama

from condenseit.digest.format import build_digest_markdown
from condenseit.providers.base import (
    ArticleSummary,
    SummarizerProvider,
    build_chat_system_prompt,
    build_chat_user_prompt,
    parse_summary_response,
    resolve_digest_language,
)

logger = logging.getLogger(__name__)


def _build_summary_prompt(
    title: str,
    content: str,
    max_key_takeaways: int = 5,
    max_summary_paragraphs: int = 5,
    language: str = "English",
    audience: str = "general readers",
    editorial_guidance: list[str] | None = None,
) -> str:
    """Build the per-article summarization prompt with configurable output size.

    ``language`` is a human-readable language name such as ``"English"`` or
    ``"French"``.
    """
    system = build_chat_system_prompt(language, audience, editorial_guidance)
    user = build_chat_user_prompt(
        title,
        content,
        max_key_takeaways,
        max_summary_paragraphs,
        language,
    )
    return f"{system}\n\n{user}\n\nJSON:"


class OllamaSummarizer(SummarizerProvider):
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        max_key_takeaways: int = 5,
        max_summary_paragraphs: int = 5,
        digest_language: str = "en",
        briefing_title: str = "CondenseIt Digest",
        briefing_audience: str = "general readers",
        editorial_guidance: list[str] | None = None,
        briefing_disclaimer: str = "",
    ) -> None:
        self.model = model
        self.client = ollama.Client(host=host)
        self.max_key_takeaways = max_key_takeaways
        self.max_summary_paragraphs = max_summary_paragraphs
        self.digest_language = digest_language
        self.briefing_title = briefing_title
        self.briefing_audience = briefing_audience
        self.editorial_guidance = editorial_guidance or []
        self.briefing_disclaimer = briefing_disclaimer

    @property
    def model_name(self) -> str:
        return self.model

    def summarize_article(
        self,
        article: dict[str, Any],
    ) -> ArticleSummary:
        content = (article.get("content") or "")[:4000]
        title = article.get("title", "Untitled")
        language = resolve_digest_language(self.digest_language, content)
        prompt = _build_summary_prompt(
            title,
            content,
            self.max_key_takeaways,
            self.max_summary_paragraphs,
            language=language,
            audience=self.briefing_audience,
            editorial_guidance=self.editorial_guidance,
        )
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            think=False,
            options={"temperature": 0.3, "num_predict": 1400},
        )
        if response.get("done_reason") == "length":
            logger.warning(
                "Ollama response truncated (done_reason=length) for model=%s; "
                "consider raising num_predict",
                self.model,
            )
        return parse_summary_response(response["response"], language=language)

    def generate_digest(
        self,
        categorized: dict[str, list[dict[str, Any]]],
        changes: list[dict[str, str]] | None = None,
        videos: list[dict[str, Any]] | None = None,
    ) -> str:
        return build_digest_markdown(
            categorized,
            changes,
            videos,
            title=self.briefing_title,
            disclaimer=self.briefing_disclaimer,
        )
