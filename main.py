import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from searchbox.auth import AuthSettings, auth_key_from_header_or_key
from searchbox.rate_limit import InMemoryRateLimiter
from searchbox.extraction import (
    PLAYWRIGHT_AVAILABLE as _PLAYWRIGHT_AVAILABLE,
    ExtractionSettings,
    extract_content,
    extract_with_playwright,
    html_to_text,
    pdf_to_text,
)
from searchbox.providers.web import (
    WebSearchOptions,
    WebSearchSettings,
    parse_brave_results,
    parse_searxng_results,
    parse_serper_results,
    search_brave as web_search_brave,
    search_provider as web_search_provider,
    search_searxng as web_search_searxng,
    search_serper as web_search_serper,
    searxng_query_url as web_searxng_query_url,
)
from searchbox.text import (
    bounded_int as _bounded_int,
    chunk_text as _chunk_text,
    model_dict as _model_dict,
    truncate_payload as _truncate_payload,
)
from searchbox.urls import (
    domain_allowed as _domain_allowed,
    favicon_for_url as _favicon_for_url,
    validate_fetch_url,
)
from searchbox.search_options import (
    resolve_brave_safesearch,
    resolve_country,
    resolve_debug,
    resolve_freshness,
    resolve_include_answer,
    resolve_include_content,
    resolve_max_chars_per_source,
    resolve_max_results,
    resolve_search_depth,
    resolve_searxng_safesearch,
    resolve_serper_tbs,
    resolve_summarize_top_n,
    resolve_timeout,
    resolve_unused_results,
    split_result_buckets,
    resolve_searxng_time_range,
)
from searchbox.scoring import score_item as _score_item

try:
    from litellm import completion as llm_completion

    _LITELLM_AVAILABLE = True
except Exception:
    llm_completion = None
    _LITELLM_AVAILABLE = False


BASE_DIR = Path(__file__).resolve().parent


def _load_env_file() -> None:
    env_file = os.environ.get("SEARCHBOX_ENV_FILE") or str(BASE_DIR / ".env")
    env_file = env_file.strip()
    if not env_file or not os.path.exists(env_file):
        return
    with open(env_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


_load_env_file()


BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "").strip()

SERPER_API_URL = os.environ.get("SERPER_API_URL", "https://google.serper.dev/search").strip()
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "").strip()

REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "20"))
USER_AGENT = os.environ.get("REQUEST_UA", "Searchbox/0.1 (+https://github.com/morganross/APICostX-Searchbox)")
SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY", "").strip()
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "true").lower() in ("1", "true", "yes", "on")
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "120"))
MAX_FETCH_CONCURRENCY = int(os.environ.get("MAX_FETCH_CONCURRENCY", "5"))
MAX_REDIRECTS = int(os.environ.get("MAX_REDIRECTS", "5"))
BLOCK_PRIVATE_FETCH_IPS = os.environ.get("BLOCK_PRIVATE_FETCH_IPS", "true").lower() in ("1", "true", "yes", "on")

SEARCH_PROVIDER = os.environ.get("SEARCH_PROVIDER", "serper").strip().lower()
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8091").strip()
SEARXNG_RESULTS_LIMIT = int(os.environ.get("SEARXNG_RESULTS_LIMIT", "50"))

ADVANCED_SEARCH_ENABLED = os.environ.get("ADVANCED_SEARCH_ENABLED", "true").lower() in ("1", "true", "yes", "on")
ADVANCED_SEARCH_DEFAULT_SOURCE = os.environ.get("ADVANCED_SEARCH_DEFAULT_SOURCE", "auto").strip().lower()
ADVANCED_SEARCH_AUTO_PROVIDER_ORDER = [
    p.strip().lower().replace("-", "_")
    for p in os.environ.get(
        "ADVANCED_SEARCH_AUTO_PROVIDER_ORDER", "sciencestack,searchapi_scholar,serpapi_scholar,agentic_data,arxiv,oanor"
    ).split(",")
    if p.strip()
]
ADVANCED_SEARCH_AUTO_MIN_PROVIDERS = int(os.environ.get("ADVANCED_SEARCH_AUTO_MIN_PROVIDERS", "2"))
ADVANCED_SEARCH_AUTO_MAX_PROVIDERS = int(os.environ.get("ADVANCED_SEARCH_AUTO_MAX_PROVIDERS", "5"))
SCIENCE_CLASSIFIER_ENABLED = os.environ.get("SCIENCE_CLASSIFIER_ENABLED", "true").lower() in ("1", "true", "yes", "on")
SCIENCE_CLASSIFIER_TIMEOUT = float(os.environ.get("SCIENCE_CLASSIFIER_TIMEOUT", "8"))
SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS = float(os.environ.get("SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS", "15"))
SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS = int(os.environ.get("SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS", "128"))
SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD = float(os.environ.get("SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD", "0.55"))
ARXIV_API_URL = os.environ.get("ARXIV_API_URL", "https://export.arxiv.org/api/query").strip()
ARXIV_USER_AGENT = os.environ.get("ARXIV_USER_AGENT", "Searchbox/0.1 (+https://github.com/searchbox/searchbox)").strip()
ARXIV_TIMEOUT = float(os.environ.get("ARXIV_TIMEOUT", "20"))
ARXIV_MAX_RESULTS = int(os.environ.get("ARXIV_MAX_RESULTS", "8"))
ARXIV_PDF_MAX_BYTES = int(os.environ.get("ARXIV_PDF_MAX_BYTES", str(25 * 1024 * 1024)))
ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS = int(os.environ.get("ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS", "5000"))
ARXIV_PAPER_SUMMARY_MAX_SOURCE_CHARS = int(os.environ.get("ARXIV_PAPER_SUMMARY_MAX_SOURCE_CHARS", "120000"))
ARXIV_MIN_INTERVAL_SECONDS = float(os.environ.get("ARXIV_MIN_INTERVAL_SECONDS", "3.2"))
ARXIV_DAILY_REQUEST_LIMIT = int(os.environ.get("ARXIV_DAILY_REQUEST_LIMIT", "28800"))
ARXIV_COOLDOWN_SECONDS = float(os.environ.get("ARXIV_COOLDOWN_SECONDS", "300"))
ARXIV_MAX_RETRY_AFTER_SECONDS = float(os.environ.get("ARXIV_MAX_RETRY_AFTER_SECONDS", "1800"))

AGENTIC_DATA_ARXIV_URL = (
    os.environ.get("AGENTIC_DATA_ARXIV_URL", "https://data.rag.ac.cn/arxiv/").strip().rstrip("/") + "/"
)
AGENTIC_DATA_API_KEY = os.environ.get("AGENTIC_DATA_API_KEY", "").strip()
AGENTIC_DATA_TIMEOUT = float(os.environ.get("AGENTIC_DATA_TIMEOUT", "30"))
AGENTIC_DATA_MAX_RESULTS = int(os.environ.get("AGENTIC_DATA_MAX_RESULTS", "8"))
AGENTIC_DATA_DAILY_REQUEST_LIMIT = int(os.environ.get("AGENTIC_DATA_DAILY_REQUEST_LIMIT", "10000"))

SCIENCESTACK_API_URL = os.environ.get("SCIENCESTACK_API_URL", "https://sciencestack.ai/api/v1").strip().rstrip("/")
SCIENCESTACK_API_KEY = os.environ.get("SCIENCESTACK_API_KEY", "").strip()
SCIENCESTACK_TIMEOUT = float(os.environ.get("SCIENCESTACK_TIMEOUT", "30"))
SCIENCESTACK_MAX_RESULTS = int(os.environ.get("SCIENCESTACK_MAX_RESULTS", "8"))
SCIENCESTACK_DAILY_REQUEST_LIMIT = int(os.environ.get("SCIENCESTACK_DAILY_REQUEST_LIMIT", "100"))

OANOR_ARXIV_API_URL = os.environ.get("OANOR_ARXIV_API_URL", "https://api.oanor.com/arxiv-api").strip().rstrip("/")
OANOR_API_KEY = os.environ.get("OANOR_API_KEY", "").strip()
OANOR_TIMEOUT = float(os.environ.get("OANOR_TIMEOUT", "30"))
OANOR_MAX_RESULTS = int(os.environ.get("OANOR_MAX_RESULTS", "8"))
OANOR_DAILY_REQUEST_LIMIT = int(os.environ.get("OANOR_DAILY_REQUEST_LIMIT", "3"))

SEARCHAPI_API_URL = os.environ.get("SEARCHAPI_API_URL", "https://www.searchapi.io/api/v1/search").strip()
SEARCHAPI_API_KEY = os.environ.get("SEARCHAPI_API_KEY", "").strip()
SEARCHAPI_TIMEOUT = float(os.environ.get("SEARCHAPI_TIMEOUT", "30"))
SEARCHAPI_MAX_RESULTS = int(os.environ.get("SEARCHAPI_MAX_RESULTS", "8"))
SEARCHAPI_DAILY_REQUEST_LIMIT = int(os.environ.get("SEARCHAPI_DAILY_REQUEST_LIMIT", "100"))

SERPAPI_API_URL = os.environ.get("SERPAPI_API_URL", "https://serpapi.com/search.json").strip()
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "").strip()
SERPAPI_TIMEOUT = float(os.environ.get("SERPAPI_TIMEOUT", "30"))
SERPAPI_MAX_RESULTS = int(os.environ.get("SERPAPI_MAX_RESULTS", "8"))
SERPAPI_DAILY_REQUEST_LIMIT = int(os.environ.get("SERPAPI_DAILY_REQUEST_LIMIT", "250"))
SERPAPI_MONTHLY_REQUEST_LIMIT = int(os.environ.get("SERPAPI_MONTHLY_REQUEST_LIMIT", "250"))

ADVANCED_PROVIDER_QUOTA_FILE = os.environ.get(
    "ADVANCED_PROVIDER_QUOTA_FILE", str(BASE_DIR / "data" / "advanced_provider_daily_usage.json")
).strip()
ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE = os.environ.get(
    "ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE", str(BASE_DIR / "data" / "advanced_provider_monthly_usage.json")
).strip()
ADVANCED_PROVIDER_COOLDOWN_FILE = os.environ.get(
    "ADVANCED_PROVIDER_COOLDOWN_FILE", str(BASE_DIR / "data" / "advanced_provider_cooldowns.json")
).strip()
ADVANCED_PROVIDER_COOLDOWN_MAX_SECONDS = int(os.environ.get("ADVANCED_PROVIDER_COOLDOWN_MAX_SECONDS", "86400"))

SEARCHBOX_LOG_DIR = os.environ.get("SEARCHBOX_LOG_DIR", str(BASE_DIR / "logs")).strip()
LLM_ATTEMPT_LOG_FILE = os.environ.get(
    "LLM_ATTEMPT_LOG_FILE", os.path.join(SEARCHBOX_LOG_DIR, "llm_attempts.jsonl")
).strip()
PROVIDER_EVENT_LOG_FILE = os.environ.get(
    "PROVIDER_EVENT_LOG_FILE", os.path.join(SEARCHBOX_LOG_DIR, "provider_events.jsonl")
).strip()
SEARCHBOX_LOG_API_MAX_LINES = int(os.environ.get("SEARCHBOX_LOG_API_MAX_LINES", "1000"))
SEARCHBOX_WEB_CONTEXT_RESULTS = int(os.environ.get("SEARCHBOX_WEB_CONTEXT_RESULTS", "5"))
SEARCHBOX_AGGREGATE_CONTENT_MAX_CHARS = int(os.environ.get("SEARCHBOX_AGGREGATE_CONTENT_MAX_CHARS", "50000"))
SEARCHBOX_AGGREGATE_RAW_CONTENT_MAX_CHARS = int(os.environ.get("SEARCHBOX_AGGREGATE_RAW_CONTENT_MAX_CHARS", "200000"))

ENRICH_USE_PLAYWRIGHT = os.environ.get("ENRICH_USE_PLAYWRIGHT", "true").lower() in ("1", "true", "yes", "on")
ENRICH_PLAYWRIGHT_TIMEOUT_MS = int(os.environ.get("ENRICH_PLAYWRIGHT_TIMEOUT_MS", "15000"))
ENRICH_PLAYWRIGHT_MAX_CHARS = int(os.environ.get("ENRICH_PLAYWRIGHT_MAX_CHARS", "60000"))
ENRICH_MIN_CONTENT_CHARS = int(os.environ.get("ENRICH_MIN_CONTENT_CHARS", "240"))
ENRICH_DEFAULT_MAX_CHARS = int(os.environ.get("ENRICH_DEFAULT_MAX_CHARS", "160000"))

SUMMARIZER_ENABLED = os.environ.get("SUMMARIZER_ENABLED", "false").lower() in ("1", "true", "yes", "on")
# Primary model: DeepSeek V4 Flash (free, 1M ctx, fast)
LLM_MODEL = os.environ.get("LLM_MODEL", "openrouter/openai/gpt-5-mini")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter").strip().lower()
LLM_QUALITY_TIER = os.environ.get("LLM_QUALITY_TIER", "balanced").strip().lower()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip() or None
OPENROUTER_API_BASE = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1").strip()
OPENROUTER_MODEL_CHEAP = os.environ.get("OPENROUTER_MODEL_CHEAP", "openrouter/qwen/qwen3-coder:free").strip()
OPENROUTER_MODEL_BALANCED = os.environ.get("OPENROUTER_MODEL_BALANCED", "openrouter/openai/gpt-5-mini").strip()
OPENROUTER_MODEL_BEST = os.environ.get("OPENROUTER_MODEL_BEST", "openrouter/openai/gpt-5-mini").strip()
# Fallback cascade: GPT-5 Mini primary, then free models as opportunistic backstops.
LLM_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "LLM_FALLBACK_MODELS",
        "openrouter/moonshotai/kimi-k2.6:free,openrouter/qwen/qwen3-coder:free",
    ).split(",")
    if m.strip()
]
LLM_MAX_ATTEMPTS = int(os.environ.get("LLM_MAX_ATTEMPTS", "4"))  # 3 free + 1 paid backstop
LLM_MAX_REPAIR_ATTEMPTS = int(os.environ.get("LLM_MAX_REPAIR_ATTEMPTS", "1"))
LLM_MAX_TOTAL_SECONDS = float(os.environ.get("LLM_MAX_TOTAL_SECONDS", "120"))  # free models can be slow
LLM_ALLOW_EXPENSIVE_FALLBACK = os.environ.get("LLM_ALLOW_EXPENSIVE_FALLBACK", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
LLM_REPAIR_MODEL = os.environ.get("LLM_REPAIR_MODEL", "").strip() or None
LLM_RESPONSE_FORMAT = os.environ.get("LLM_RESPONSE_FORMAT", "auto").strip().lower()
LLM_SYSTEM_PROMPT = os.environ.get(
    "LLM_SYSTEM_PROMPT",
    'You are a strict evidence-aware research synthesis model. Use only the provided sources. Never invent claims.\nNever use markdown, bullets, fences, or prose. Return ONLY a single valid JSON object matching the following structure:\n\n{\n  "found": true,\n  "answer": "A detailed paragraph summarizing the findings based purely on the evidence. Target 700 words.",\n  "highlights": ["Key fact 1", "Key fact 2"],\n  "follow_up_questions": ["Follow up question 1?", "Follow up question 2?"],\n  "confidence": 0.95\n}\n\nEnsure all returned JSON fields conform exactly to this structure. If no sources are usable, set found=false, confidence=0.0, and explain the lack of info in the answer field.',
)
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))
LLM_REPAIR_TIMEOUT = float(os.environ.get("LLM_REPAIR_TIMEOUT", "20"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
LLM_MIN_COMPLETION_TOKENS = int(os.environ.get("LLM_MIN_COMPLETION_TOKENS", "256"))
LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS = int(os.environ.get("LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS", "4096"))
LLM_MAX_COMPLETION_TOKENS_CAP = int(os.environ.get("LLM_MAX_COMPLETION_TOKENS_CAP", "8192"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "1"))
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "minimal").strip() or None
LLM_ALLOW_REQUEST_OPTIONS = os.environ.get("LLM_ALLOW_REQUEST_OPTIONS", "true").lower() in ("1", "true", "yes", "on")
LLM_FORCE_MODEL = os.environ.get("LLM_FORCE_MODEL", "").strip() or None
LLM_FORCE_MAX_COMPLETION_TOKENS = os.environ.get("LLM_FORCE_MAX_COMPLETION_TOKENS", "").strip() or None
LLM_FORCE_REASONING_EFFORT = os.environ.get("LLM_FORCE_REASONING_EFFORT", "").strip() or None
LLM_FORCE_TEMPERATURE = os.environ.get("LLM_FORCE_TEMPERATURE", "").strip() or None
LLM_FORCE_TIMEOUT = os.environ.get("LLM_FORCE_TIMEOUT", "").strip() or None
LLM_API_BASE = os.environ.get("LLM_API_BASE", "").strip() or None
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip() or None
LLM_PROVIDER_KEY = os.environ.get("LLM_PROVIDER_KEY", "").strip() or None


_RATE_LIMITER = InMemoryRateLimiter()
_ARXIV_REQUEST_LOCK = asyncio.Lock()
_ARXIV_LAST_REQUEST_AT = 0.0
_ARXIV_COOLDOWN_UNTIL = 0.0
_ARXIV_LAST_REFUSAL: Optional[Dict[str, Any]] = None
_STATUS = {
    "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "requests_total": 0,
    "provider_success_total": 0,
    "provider_error_total": 0,
    "extract_success_total": 0,
    "extract_error_total": 0,
    "llm_success_total": 0,
    "llm_error_total": 0,
    "last_error": None,
}


# Transitional compatibility imports stay after .env loading until config moves into searchbox.config.
from searchbox.aggregation import build_aggregate_search_result  # noqa: E402
from searchbox.usage import calculate_searchbox_usage as _calculate_searchbox_usage  # noqa: E402
from searchbox.logging_utils import (  # noqa: E402
    append_jsonl as _append_jsonl,
    summarize_events as _summarize_events,
    tail_jsonl as _tail_jsonl,
)
from searchbox.state import cooldown as cooldown_state  # noqa: E402
from searchbox.state import quota as quota_state  # noqa: E402
from searchbox.defaults import BRAVE_DEFAULT_COUNT, BRAVE_MAX_COUNT, SERPER_DEFAULT_COUNT, SERPER_MAX_COUNT  # noqa: E402
from searchbox.models import (  # noqa: E402,F401
    ImageItem,
    LLMOptions,
    SearchItem,
    SearchRequest,
    SearchResponse,
    SearchSummaryRequest,
    SearchSummaryResponse,
    SourceEvidence,
    TavilySearchResponse,
    TavilySearchResult,
)


app = FastAPI(title="Searchbox", version="0.1.0")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "provider": SEARCH_PROVIDER,
        "has_serper_key": bool(SERPER_API_KEY),
        "has_brave_key": bool(BRAVE_API_KEY),
        "has_searxng_base": bool(SEARXNG_URL),
        "playwright_available": _PLAYWRIGHT_AVAILABLE,
        "playwright_enabled": ENRICH_USE_PLAYWRIGHT,
        "summarizer_enabled": SUMMARIZER_ENABLED,
        "litellm_available": _LITELLM_AVAILABLE,
        "default_model": LLM_MODEL,
    }


@app.get("/config")
def config() -> Dict[str, Any]:
    return {
        "provider": {
            "search_provider": SEARCH_PROVIDER,
            "brave_default_count": BRAVE_DEFAULT_COUNT,
            "brave_max_count": BRAVE_MAX_COUNT,
            "serper_default_count": SERPER_DEFAULT_COUNT,
            "serper_max_count": SERPER_MAX_COUNT,
            "searxng_results_limit": SEARXNG_RESULTS_LIMIT,
            "request_timeout": REQUEST_TIMEOUT,
        },
        "advanced_search": {
            "enabled": ADVANCED_SEARCH_ENABLED,
            "default_source": ADVANCED_SEARCH_DEFAULT_SOURCE,
            "auto_provider_order": ADVANCED_SEARCH_AUTO_PROVIDER_ORDER,
            "auto_min_providers": ADVANCED_SEARCH_AUTO_MIN_PROVIDERS,
            "auto_max_providers": ADVANCED_SEARCH_AUTO_MAX_PROVIDERS,
            "science_classifier_enabled": SCIENCE_CLASSIFIER_ENABLED,
            "science_classifier_timeout": SCIENCE_CLASSIFIER_TIMEOUT,
            "science_classifier_max_total_seconds": SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS,
            "science_classifier_max_completion_tokens": SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS,
            "science_classifier_confidence_threshold": SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD,
            "sources": [
                "auto",
                "arxiv",
                "agentic_data",
                "sciencestack",
                "oanor",
                "searchapi_scholar",
                "serpapi_scholar",
            ],
            "arxiv_timeout": ARXIV_TIMEOUT,
            "arxiv_max_results": ARXIV_MAX_RESULTS,
            "arxiv_pdf_max_bytes": ARXIV_PDF_MAX_BYTES,
            "arxiv_content_summary_threshold_chars": ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS,
            "arxiv_paper_summary_max_source_chars": ARXIV_PAPER_SUMMARY_MAX_SOURCE_CHARS,
            "arxiv_min_interval_seconds": ARXIV_MIN_INTERVAL_SECONDS,
            "arxiv_daily_request_limit": ARXIV_DAILY_REQUEST_LIMIT,
            "arxiv_cooldown_seconds": ARXIV_COOLDOWN_SECONDS,
            "arxiv_max_retry_after_seconds": ARXIV_MAX_RETRY_AFTER_SECONDS,
            "arxiv_cooldown_remaining_seconds": _arxiv_cooldown_remaining_seconds(),
            "arxiv_last_refusal": _ARXIV_LAST_REFUSAL,
            "agentic_data_configured": bool(AGENTIC_DATA_API_KEY),
            "agentic_data_timeout": AGENTIC_DATA_TIMEOUT,
            "agentic_data_max_results": AGENTIC_DATA_MAX_RESULTS,
            "agentic_data_daily_request_limit": AGENTIC_DATA_DAILY_REQUEST_LIMIT,
            "sciencestack_configured": bool(SCIENCESTACK_API_KEY),
            "sciencestack_timeout": SCIENCESTACK_TIMEOUT,
            "sciencestack_max_results": SCIENCESTACK_MAX_RESULTS,
            "sciencestack_daily_request_limit": SCIENCESTACK_DAILY_REQUEST_LIMIT,
            "oanor_configured": bool(OANOR_API_KEY),
            "oanor_timeout": OANOR_TIMEOUT,
            "oanor_max_results": OANOR_MAX_RESULTS,
            "oanor_daily_request_limit": OANOR_DAILY_REQUEST_LIMIT,
            "searchapi_configured": bool(SEARCHAPI_API_KEY),
            "searchapi_timeout": SEARCHAPI_TIMEOUT,
            "searchapi_max_results": SEARCHAPI_MAX_RESULTS,
            "searchapi_daily_request_limit": SEARCHAPI_DAILY_REQUEST_LIMIT,
            "serpapi_configured": bool(SERPAPI_API_KEY),
            "serpapi_timeout": SERPAPI_TIMEOUT,
            "serpapi_max_results": SERPAPI_MAX_RESULTS,
            "serpapi_daily_request_limit": SERPAPI_DAILY_REQUEST_LIMIT,
            "serpapi_monthly_request_limit": SERPAPI_MONTHLY_REQUEST_LIMIT,
            "provider_daily_usage": _advanced_provider_quota_snapshot(),
            "provider_monthly_usage": _advanced_provider_monthly_quota_snapshot(),
            "provider_cooldowns": _advanced_provider_cooldown_snapshot(),
        },
        "enrichment": {
            "playwright_enabled": ENRICH_USE_PLAYWRIGHT,
            "playwright_available": _PLAYWRIGHT_AVAILABLE,
            "playwright_timeout_ms": ENRICH_PLAYWRIGHT_TIMEOUT_MS,
            "min_content_chars": ENRICH_MIN_CONTENT_CHARS,
            "default_max_chars": ENRICH_DEFAULT_MAX_CHARS,
        },
        "summarizer": {
            "enabled": SUMMARIZER_ENABLED,
            "litellm_available": _LITELLM_AVAILABLE,
            "default_provider": LLM_PROVIDER,
            "quality_tier_default": LLM_QUALITY_TIER,
            "default_model": LLM_MODEL,
            "openrouter_key_configured": bool(OPENROUTER_API_KEY),
            "openrouter_model_cheap": OPENROUTER_MODEL_CHEAP,
            "openrouter_model_balanced": OPENROUTER_MODEL_BALANCED,
            "openrouter_model_best": OPENROUTER_MODEL_BEST,
            "fallback_models_configured": len(LLM_FALLBACK_MODELS),
            "max_attempts_default": LLM_MAX_ATTEMPTS,
            "max_repair_attempts_default": LLM_MAX_REPAIR_ATTEMPTS,
            "max_total_seconds_default": LLM_MAX_TOTAL_SECONDS,
            "allow_expensive_fallback_default": LLM_ALLOW_EXPENSIVE_FALLBACK,
            "repair_model_configured": bool(LLM_REPAIR_MODEL),
            "response_format_default": LLM_RESPONSE_FORMAT,
            "repair_timeout_default": LLM_REPAIR_TIMEOUT,
            "request_options_enabled": LLM_ALLOW_REQUEST_OPTIONS,
            "max_tokens_default": LLM_MAX_TOKENS,
            "min_completion_tokens": LLM_MIN_COMPLETION_TOKENS,
            "reasoning_model_min_completion_tokens": LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS,
            "max_completion_tokens_cap": LLM_MAX_COMPLETION_TOKENS_CAP,
            "temperature_default": LLM_TEMPERATURE,
            "reasoning_effort_default": LLM_REASONING_EFFORT,
            "force_model_active": bool(LLM_FORCE_MODEL),
            "force_max_completion_tokens_active": bool(LLM_FORCE_MAX_COMPLETION_TOKENS),
            "force_reasoning_effort_active": bool(LLM_FORCE_REASONING_EFFORT),
            "force_temperature_active": bool(LLM_FORCE_TEMPERATURE),
            "force_timeout_active": bool(LLM_FORCE_TIMEOUT),
        },
        "security": {
            "auth_disabled": AUTH_DISABLED,
            "search_api_key_configured": bool(SEARCH_API_KEY),
            "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
            "block_private_fetch_ips": BLOCK_PRIVATE_FETCH_IPS,
            "max_fetch_concurrency": MAX_FETCH_CONCURRENCY,
            "max_redirects": MAX_REDIRECTS,
        },
    }


@app.get("/status")
def status() -> Dict[str, Any]:
    payload = dict(_STATUS)
    payload["logs"] = {
        "llm_attempt_log_file": LLM_ATTEMPT_LOG_FILE,
        "provider_event_log_file": PROVIDER_EVENT_LOG_FILE,
        "api_max_lines": SEARCHBOX_LOG_API_MAX_LINES,
    }
    return payload


@app.get("/health/monitor")
def health_monitor(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    _authorize(authorization)
    llm_events = _tail_jsonl(LLM_ATTEMPT_LOG_FILE, 500)
    provider_events = _tail_jsonl(PROVIDER_EVENT_LOG_FILE, 500)
    return {
        "status": "ok",
        "runtime": dict(_STATUS),
        "advanced_provider_daily_usage": _advanced_provider_quota_snapshot(),
        "advanced_provider_monthly_usage": _advanced_provider_monthly_quota_snapshot(),
        "advanced_provider_cooldowns": _advanced_provider_cooldown_snapshot(),
        "llm_attempts_recent": _summarize_events(llm_events, ["purpose", "provider", "model"]),
        "provider_events_recent": _summarize_events(provider_events, ["provider", "event"]),
    }


@app.get("/logs/llm-attempts")
def get_llm_attempt_logs(limit: int = 100, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    _authorize(authorization)
    safe_limit = _coerce_log_limit(limit)
    return {"log": "llm_attempts", "count": safe_limit, "events": _tail_jsonl(LLM_ATTEMPT_LOG_FILE, safe_limit)}


@app.get("/logs/provider-events")
def get_provider_event_logs(limit: int = 100, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    _authorize(authorization)
    safe_limit = _coerce_log_limit(limit)
    return {"log": "provider_events", "count": safe_limit, "events": _tail_jsonl(PROVIDER_EVENT_LOG_FILE, safe_limit)}


def _coerce_log_limit(limit: int) -> int:
    safe_limit = int(limit)
    if safe_limit < 1:
        safe_limit = 1
    return min(safe_limit, SEARCHBOX_LOG_API_MAX_LINES)


def _auth_settings() -> AuthSettings:
    return AuthSettings(auth_disabled=AUTH_DISABLED, search_api_key=SEARCH_API_KEY)


def _auth_key_from_header_or_key(authorization: Optional[str], api_key: Optional[str] = None) -> str:
    return auth_key_from_header_or_key(authorization, api_key, settings=_auth_settings())


def _check_rate_limit(bucket_key: str) -> None:
    _RATE_LIMITER.check(bucket_key, RATE_LIMIT_PER_MINUTE)


def _authorize(authorization: Optional[str], api_key: Optional[str] = None) -> None:
    _check_rate_limit(_auth_key_from_header_or_key(authorization, api_key))


def _log_llm_attempt(event: Dict[str, Any]) -> None:
    event = dict(event or {})
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    event.setdefault("event_type", "llm_attempt")
    for forbidden in ("prompt", "messages", "raw", "raw_model_output", "api_key"):
        event.pop(forbidden, None)
    _append_jsonl(LLM_ATTEMPT_LOG_FILE, event)


def _log_provider_event(event: Dict[str, Any]) -> None:
    event = dict(event or {})
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    event.setdefault("event_type", "provider_event")
    event.pop("api_key", None)
    _append_jsonl(PROVIDER_EVENT_LOG_FILE, event)


def _resolve_max_results(req: Any) -> int:
    return resolve_max_results(req=req, default_count=SERPER_DEFAULT_COUNT, max_count=SERPER_MAX_COUNT)


def _resolve_include_content(req: Any, default: bool = False) -> bool:
    return resolve_include_content(req=req, default=default)


def _resolve_include_answer(req: Any, default: bool = False) -> bool:
    return resolve_include_answer(req=req, default=default)


def _resolve_debug(req: Any) -> bool:
    return resolve_debug(req)


def _resolve_unused_results(items: List[SearchItem], max_sources: int) -> List[SearchItem]:
    return resolve_unused_results(items=items, max_sources=max_sources)


def _resolve_country(req: Any) -> Optional[str]:
    return resolve_country(req)


def _resolve_brave_safesearch(req: Any) -> str:
    return resolve_brave_safesearch(req)


def _resolve_searxng_safesearch(req: Any) -> int:
    return resolve_searxng_safesearch(req)


def _resolve_freshness(req: Any) -> Optional[str]:
    return resolve_freshness(req)


def _resolve_searxng_time_range(req: Any) -> Optional[str]:
    return resolve_searxng_time_range(req)


def _resolve_serper_tbs(req: Any) -> Optional[str]:
    return resolve_serper_tbs(req)


def _resolve_search_depth(req: Any) -> str:
    return resolve_search_depth(req)


def _resolve_summarize_top_n(req: Any, default: int = 5) -> int:
    return resolve_summarize_top_n(req=req, default=default, max_count=SERPER_MAX_COUNT)


def _resolve_max_chars_per_source(req: Any, default: int = 4000) -> int:
    return resolve_max_chars_per_source(req=req, default=default)


def _resolve_timeout(req: Any) -> float:
    return resolve_timeout(req=req, default=REQUEST_TIMEOUT)


def _split_result_buckets(items: List[SearchItem], max_sources: int) -> Dict[str, List[SearchItem]]:
    return split_result_buckets(items=items, max_sources=max_sources)


def _validate_fetch_url(url: str) -> None:
    validate_fetch_url(url, block_private_fetch_ips=BLOCK_PRIVATE_FETCH_IPS)


def _forced_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _forced_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _resolve_llm_options(options: Optional[LLMOptions]) -> Dict[str, Any]:
    request_options = options if (LLM_ALLOW_REQUEST_OPTIONS and options is not None) else None
    provider = (
        (request_options.provider if request_options and request_options.provider else LLM_PROVIDER).strip().lower()
    )
    quality_tier = (
        (request_options.quality_tier if request_options and request_options.quality_tier else LLM_QUALITY_TIER)
        .strip()
        .lower()
    )
    requested_tokens = None
    if request_options is not None:
        requested_tokens = request_options.max_completion_tokens or request_options.max_tokens
    forced_tokens = _forced_int(LLM_FORCE_MAX_COMPLETION_TOKENS)
    tier_model = None
    if provider == "openrouter":
        tier_model = {
            "cheap": OPENROUTER_MODEL_CHEAP,
            "balanced": OPENROUTER_MODEL_BALANCED,
            "best": OPENROUTER_MODEL_BEST,
        }.get(quality_tier, OPENROUTER_MODEL_BALANCED)
    model = LLM_FORCE_MODEL or (
        request_options.model if request_options and request_options.model else (tier_model or LLM_MODEL)
    )
    reasoning_effort = LLM_FORCE_REASONING_EFFORT or (
        request_options.reasoning_effort
        if request_options and request_options.reasoning_effort is not None
        else LLM_REASONING_EFFORT
    )
    token_floor = LLM_MIN_COMPLETION_TOKENS
    if (model or "").lower().startswith(("gpt-5", "openai/gpt-5", "o1", "o3", "o4")) and reasoning_effort:
        token_floor = max(token_floor, LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS)
    max_completion_tokens = forced_tokens if forced_tokens is not None else (requested_tokens or LLM_MAX_TOKENS)
    max_completion_tokens = _bounded_int(
        max_completion_tokens,
        LLM_MAX_TOKENS,
        token_floor,
        LLM_MAX_COMPLETION_TOKENS_CAP,
    )

    requested_temperature = request_options.temperature if request_options is not None else None
    forced_temperature = _forced_float(LLM_FORCE_TEMPERATURE)
    temperature = (
        forced_temperature
        if forced_temperature is not None
        else (requested_temperature if requested_temperature is not None else LLM_TEMPERATURE)
    )

    requested_timeout = request_options.timeout if request_options is not None else None
    forced_timeout = _forced_float(LLM_FORCE_TIMEOUT)
    timeout = forced_timeout if forced_timeout is not None else (requested_timeout or LLM_TIMEOUT)

    return {
        "provider": provider,
        "model": model,
        "fallback_models": (
            request_options.fallback_models
            if request_options and request_options.fallback_models is not None
            else LLM_FALLBACK_MODELS
        ),
        "quality_tier": quality_tier,
        "max_attempts": request_options.max_attempts
        if request_options and request_options.max_attempts is not None
        else LLM_MAX_ATTEMPTS,
        "max_repair_attempts": request_options.max_repair_attempts
        if request_options and request_options.max_repair_attempts is not None
        else LLM_MAX_REPAIR_ATTEMPTS,
        "max_total_seconds": request_options.max_total_seconds
        if request_options and request_options.max_total_seconds is not None
        else LLM_MAX_TOTAL_SECONDS,
        "allow_expensive_fallback": request_options.allow_expensive_fallback
        if request_options and request_options.allow_expensive_fallback is not None
        else LLM_ALLOW_EXPENSIVE_FALLBACK,
        "repair_model": request_options.repair_model
        if request_options and request_options.repair_model is not None
        else LLM_REPAIR_MODEL,
        "response_format": (
            request_options.response_format
            if request_options and request_options.response_format is not None
            else LLM_RESPONSE_FORMAT
        )
        .strip()
        .lower(),
        "max_completion_tokens": max_completion_tokens,
        "reasoning_effort": reasoning_effort,
        "temperature": temperature,
        "timeout": timeout,
        "repair_timeout": request_options.repair_timeout
        if request_options and request_options.repair_timeout is not None
        else LLM_REPAIR_TIMEOUT,
        "system_prompt": request_options.system_prompt
        if request_options and request_options.system_prompt is not None
        else LLM_SYSTEM_PROMPT,
        "request_options_enabled": LLM_ALLOW_REQUEST_OPTIONS,
    }


def _html_to_text(html: str) -> str:
    return html_to_text(html)


def _pdf_to_text(data: bytes) -> str:
    return pdf_to_text(data)


async def _normalize_search_query(req: Any) -> str:
    query = (getattr(req, "query", "") or "").strip()
    if getattr(req, "exact_match", False) and query and not (query.startswith('"') and query.endswith('"')):
        query = f'"{query}"'

    import re

    operators = re.findall(r"(?:OR\s+)?(?:site|date|filetype|ext):[^\s]+", query)

    base_query = query
    for op in operators:
        base_query = base_query.replace(op, "")

    base_query = re.sub(r"\s+", " ", base_query).strip()

    words = base_query.split()
    if len(words) <= 15:
        return query

    if SUMMARIZER_ENABLED and _LITELLM_AVAILABLE:
        try:
            resolved_llm = _resolve_llm_options(getattr(req, "llm_options", None))
            system_prompt = (
                "You are an expert Google Search query optimizer. Convert the user's verbose paragraph into an "
                "extremely dense 5-10 keyword Google Search query. Do not generalize or simplify; be extra "
                "specific, and focus heavily on the last part of the search query. Return ONLY a single JSON "
                'object with the structure: {"query": "optimized keywords"}. '
                "Do not use markdown or extra text."
            )
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": base_query}]
            for spec in _build_llm_candidate_specs(resolved_llm):
                try:
                    attempt_timeout = min(float(resolved_llm.get("timeout", 3.0)), 3.0)
                    llm_resp = await _call_litellm_model(spec, messages, resolved_llm, attempt_timeout=attempt_timeout)
                    payload = _extract_llm_response_payload(llm_resp)
                    parsed = _extract_json_from_text(payload.get("raw") or "")
                    if parsed and isinstance(parsed, dict) and parsed.get("query"):
                        opt_query = str(parsed["query"]).strip()
                        final_query = opt_query
                        if operators:
                            final_query += " " + " ".join(operators)
                        return final_query.strip()
                except Exception as inner_e:
                    import traceback

                    print("LLM QUERY MAKER INNER FAILED:", repr(inner_e))
                    traceback.print_exc()
                    continue
        except Exception as e:
            import traceback

            print("LLM QUERY MAKER FAILED:", repr(e))
            traceback.print_exc()
            pass

    base_query = " ".join(words[:20])
    base_query = re.sub(r"\s+OR$", "", base_query)
    if base_query.count('"') % 2 != 0:
        base_query += '"'
    open_p = base_query.count("(")
    close_p = base_query.count(")")
    if open_p > close_p:
        base_query += ")" * (open_p - close_p)

    final_query = base_query
    if operators:
        final_query += " " + " ".join(operators)

    return final_query.strip()


def _web_search_settings() -> WebSearchSettings:
    return WebSearchSettings(
        search_provider=SEARCH_PROVIDER,
        user_agent=USER_AGENT,
        request_timeout=REQUEST_TIMEOUT,
        brave_api_url=BRAVE_API_URL,
        brave_api_key=BRAVE_API_KEY,
        serper_api_url=SERPER_API_URL,
        serper_api_key=SERPER_API_KEY,
        searxng_url=SEARXNG_URL,
    )


async def _web_search_options(req: SearchRequest, count: int) -> WebSearchOptions:
    return WebSearchOptions(
        query=await _normalize_search_query(req),
        count=count,
        topic=(getattr(req, "topic", None) or "").strip() or None,
        country=_resolve_country(req),
        brave_safesearch=_resolve_brave_safesearch(req),
        searxng_safesearch=_resolve_searxng_safesearch(req),
        freshness=_resolve_freshness(req),
        searxng_time_range=_resolve_searxng_time_range(req),
        serper_tbs=_resolve_serper_tbs(req),
        search_depth=_resolve_search_depth(req),
        safe_search=bool(getattr(req, "safe_search", False)),
    )


def _searxng_query_url() -> str:
    return web_searxng_query_url(SEARXNG_URL)


def _parse_brave_results(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    return parse_brave_results(data, limit)


def _parse_serper_results(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    return parse_serper_results(data, limit)


def _parse_searxng_results(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    return parse_searxng_results(data, limit)


async def _search_brave(req: SearchRequest, count: int) -> Dict[str, Any]:
    return await web_search_brave(await _web_search_options(req, count), _web_search_settings())


async def _search_serper(req: SearchRequest, count: int) -> Dict[str, Any]:
    return await web_search_serper(await _web_search_options(req, count), _web_search_settings())


async def _search_searxng(req: SearchRequest, count: int) -> Dict[str, Any]:
    return await web_search_searxng(await _web_search_options(req, count), _web_search_settings())


async def _search_provider(req: SearchRequest, count: int) -> List[Dict[str, Any]]:
    try:
        results = await web_search_provider(await _web_search_options(req, count), _web_search_settings())
        _STATUS["provider_success_total"] += 1
        return results
    except HTTPException:
        _STATUS["provider_error_total"] += 1
        raise
    except Exception as exc:
        _STATUS["provider_error_total"] += 1
        _STATUS["last_error"] = f"provider:{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=502, detail=f"Provider search failed: {type(exc).__name__}: {exc}") from exc


def _extraction_settings() -> ExtractionSettings:
    return ExtractionSettings(
        user_agent=USER_AGENT,
        max_redirects=MAX_REDIRECTS,
        block_private_fetch_ips=BLOCK_PRIVATE_FETCH_IPS,
        use_playwright=ENRICH_USE_PLAYWRIGHT,
        playwright_timeout_ms=ENRICH_PLAYWRIGHT_TIMEOUT_MS,
        playwright_max_chars=ENRICH_PLAYWRIGHT_MAX_CHARS,
        min_content_chars=ENRICH_MIN_CONTENT_CHARS,
        default_max_chars=ENRICH_DEFAULT_MAX_CHARS,
    )


async def _extract_with_playwright(url: str) -> Dict[str, Any]:
    return await extract_with_playwright(
        url,
        user_agent=USER_AGENT,
        timeout_ms=ENRICH_PLAYWRIGHT_TIMEOUT_MS,
        max_chars=ENRICH_PLAYWRIGHT_MAX_CHARS,
    )


async def _extract_content(url: str, timeout_s: float) -> Dict[str, Any]:
    return await extract_content(url, timeout_s, settings=_extraction_settings())


_ARXIV_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "analysis",
    "and",
    "any",
    "are",
    "article",
    "based",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "can",
    "could",
    "deep",
    "describe",
    "does",
    "doing",
    "during",
    "each",
    "effect",
    "effects",
    "find",
    "from",
    "give",
    "have",
    "into",
    "latest",
    "like",
    "make",
    "many",
    "model",
    "models",
    "more",
    "most",
    "new",
    "paper",
    "papers",
    "please",
    "recent",
    "report",
    "research",
    "review",
    "search",
    "show",
    "study",
    "studies",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "through",
    "using",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "write",
    "your",
}
_ARXIV_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def _clean_arxiv_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _compile_arxiv_query(query: str) -> str:
    compiled = re.sub(r"\s+", " ", query or "").strip()
    if not compiled:
        raise HTTPException(status_code=400, detail="advanced arXiv search query is empty")
    return compiled


def _advanced_provider_names() -> List[str]:
    return ["arxiv", "agentic_data", "sciencestack", "oanor", "searchapi_scholar", "serpapi_scholar"]


def _advanced_provider_base_cooldown_seconds(provider: str, status_code: int) -> int:
    return cooldown_state.base_cooldown_seconds(
        provider,
        status_code,
        arxiv_cooldown_seconds=ARXIV_COOLDOWN_SECONDS,
    )


def _advanced_provider_cooldown_snapshot() -> Dict[str, Any]:
    return cooldown_state.snapshot(ADVANCED_PROVIDER_COOLDOWN_FILE, _advanced_provider_names())


def _advanced_provider_cooldown_remaining(provider: str) -> int:
    return cooldown_state.remaining(ADVANCED_PROVIDER_COOLDOWN_FILE, _advanced_provider_names(), provider)


def _raise_if_advanced_provider_cooling(provider: str) -> None:
    cooldown_state.raise_if_cooling(ADVANCED_PROVIDER_COOLDOWN_FILE, _advanced_provider_names(), provider)


def _mark_advanced_provider_success(provider: str) -> None:
    cooldown_state.mark_success(ADVANCED_PROVIDER_COOLDOWN_FILE, provider, _log_provider_event)


def _mark_advanced_provider_failure(
    provider: str, status_code: int, reason: str, retry_after: Optional[int] = None
) -> int:
    return cooldown_state.mark_failure(
        ADVANCED_PROVIDER_COOLDOWN_FILE,
        provider,
        status_code,
        reason,
        max_cooldown_seconds=ADVANCED_PROVIDER_COOLDOWN_MAX_SECONDS,
        arxiv_cooldown_seconds=ARXIV_COOLDOWN_SECONDS,
        log_event=_log_provider_event,
        retry_after=retry_after,
    )


def _advanced_provider_daily_limits() -> Dict[str, int]:
    return {
        "arxiv": ARXIV_DAILY_REQUEST_LIMIT,
        "agentic_data": AGENTIC_DATA_DAILY_REQUEST_LIMIT,
        "sciencestack": SCIENCESTACK_DAILY_REQUEST_LIMIT,
        "oanor": OANOR_DAILY_REQUEST_LIMIT,
        "searchapi_scholar": SEARCHAPI_DAILY_REQUEST_LIMIT,
        "serpapi_scholar": SERPAPI_DAILY_REQUEST_LIMIT,
    }


def _advanced_provider_quota_day() -> str:
    return quota_state.quota_day()


def _advanced_provider_monthly_limits() -> Dict[str, int]:
    return {
        "serpapi_scholar": SERPAPI_MONTHLY_REQUEST_LIMIT,
    }


def _advanced_provider_quota_month() -> str:
    return quota_state.quota_month()


def _advanced_provider_monthly_quota_paths() -> tuple[str, str]:
    return (ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE, ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE + ".lock")


def _advanced_provider_monthly_quota_snapshot() -> Dict[str, Any]:
    return quota_state.monthly_snapshot(ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE, _advanced_provider_monthly_limits())


def _reserve_advanced_provider_monthly_quota(provider: str, units: int = 1) -> None:
    quota_state.reserve_monthly(
        provider,
        ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE,
        _advanced_provider_monthly_limits(),
        units,
    )


def _advanced_provider_quota_paths() -> tuple[str, str]:
    return (ADVANCED_PROVIDER_QUOTA_FILE, ADVANCED_PROVIDER_QUOTA_FILE + ".lock")


def _advanced_provider_quota_snapshot() -> Dict[str, Any]:
    return quota_state.daily_snapshot(ADVANCED_PROVIDER_QUOTA_FILE, _advanced_provider_daily_limits())


def _reserve_advanced_provider_quota(provider: str, units: int = 1) -> None:
    quota_state.reserve_daily(
        provider,
        ADVANCED_PROVIDER_QUOTA_FILE,
        _advanced_provider_daily_limits(),
        monthly_quota_file=ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE,
        monthly_limits=_advanced_provider_monthly_limits(),
        units=units,
    )


def _arxiv_cooldown_remaining_seconds() -> int:
    return max(0, int(round(_ARXIV_COOLDOWN_UNTIL - time.monotonic())))


def _arxiv_parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    raw = value.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            return None
        return max(0.0, retry_at.timestamp() - time.time())
    except Exception:
        return None


def _arxiv_mark_refusal(
    status_code: int, response: Optional[httpx.Response] = None, *, reason: str = "upstream_refused_request"
) -> int:
    global _ARXIV_COOLDOWN_UNTIL, _ARXIV_LAST_REFUSAL
    retry_after = _arxiv_parse_retry_after(response.headers.get("retry-after") if response is not None else None)
    cooldown = retry_after if retry_after is not None else ARXIV_COOLDOWN_SECONDS
    cooldown = max(ARXIV_MIN_INTERVAL_SECONDS, min(float(cooldown), ARXIV_MAX_RETRY_AFTER_SECONDS))
    _ARXIV_COOLDOWN_UNTIL = max(_ARXIV_COOLDOWN_UNTIL, time.monotonic() + cooldown)
    retry_seconds = _arxiv_cooldown_remaining_seconds()
    _ARXIV_LAST_REFUSAL = {
        "status_code": status_code,
        "reason": reason,
        "retry_after_seconds": retry_seconds,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _STATUS["last_error"] = {
        "provider": "advanced:arxiv",
        "status_code": status_code,
        "reason": reason,
        "retry_after_seconds": retry_seconds,
    }
    return retry_seconds


def _arxiv_throttle_exception(status_code: int, retry_after_seconds: int, *, reason: str) -> HTTPException:
    detail = {
        "source": "arxiv",
        "reason": reason,
        "message": "arXiv did not accept this request right now; Searchbox is cooling down locally before trying arXiv again.",
        "retry_after_seconds": retry_after_seconds,
    }
    return HTTPException(status_code=status_code, detail=detail, headers={"Retry-After": str(retry_after_seconds)})


async def _arxiv_rate_limited_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> httpx.Response:
    global _ARXIV_LAST_REQUEST_AT
    async with _ARXIV_REQUEST_LOCK:
        cooldown_remaining = _arxiv_cooldown_remaining_seconds()
        if cooldown_remaining > 0:
            raise _arxiv_throttle_exception(429, cooldown_remaining, reason="local_arxiv_cooldown_active")
        now = time.monotonic()
        wait_seconds = max(0.0, (_ARXIV_LAST_REQUEST_AT + ARXIV_MIN_INTERVAL_SECONDS) - now)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        _reserve_advanced_provider_quota("arxiv")
        try:
            response = await client.get(url, params=params, headers=headers)
        finally:
            _ARXIV_LAST_REQUEST_AT = time.monotonic()
        if response.status_code in (429, 503):
            retry_seconds = _arxiv_mark_refusal(response.status_code, response, reason="upstream_arxiv_refused_request")
            raise _arxiv_throttle_exception(
                response.status_code, retry_seconds, reason="upstream_arxiv_refused_request"
            )
        return response


async def _fetch_arxiv_pdf_text(pdf_url: str, *, timeout: float) -> Dict[str, Any]:
    if not pdf_url:
        return {"content": "", "error": "missing_pdf_url"}
    _validate_fetch_url(pdf_url)
    headers = {"User-Agent": ARXIV_USER_AGENT or USER_AGENT, "Accept": "application/pdf"}
    t0 = datetime.now()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await _arxiv_rate_limited_get(client, pdf_url, headers=headers)
        status = resp.status_code
        content_type = resp.headers.get("content-type")
        resp.raise_for_status()
        body = resp.content
        if len(body) > ARXIV_PDF_MAX_BYTES:
            return {
                "content": "",
                "error": f"pdf_too_large:{len(body)}",
                "http_status": status,
                "content_type": content_type,
                "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
                "canonical_url": str(resp.url),
            }
        text = _pdf_to_text(body)
        return {
            "content": text,
            "error": None if text else "pdf_text_empty",
            "http_status": status,
            "content_type": content_type,
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
            "canonical_url": str(resp.url),
            "bytes": len(body),
        }
    except Exception as exc:
        return {
            "content": "",
            "error": f"{type(exc).__name__}: {exc}",
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
        }


def _arxiv_wants_pdf_text(req: SearchRequest) -> bool:
    return True


async def _summarize_paper_content(
    query: str, item: SearchItem, paper_text: str, llm_options: Optional[LLMOptions] = None
) -> str:
    if not SUMMARIZER_ENABLED:
        raise HTTPException(status_code=503, detail="paper text exceeded content limit and the summarizer is disabled")
    if not _LITELLM_AVAILABLE:
        raise HTTPException(status_code=503, detail="paper text exceeded content limit and litellm is not installed")
    source_text = _truncate_payload(paper_text, ARXIV_PAPER_SUMMARY_MAX_SOURCE_CHARS)
    resolved_llm = _resolve_llm_options(llm_options)
    resolved_llm["system_prompt"] = (
        "You summarize scientific papers from extracted PDF text. Use only the provided paper text. "
        "Do not invent claims. Return only one strict JSON object."
    )
    messages = [
        {"role": "system", "content": resolved_llm["system_prompt"]},
        {
            "role": "user",
            "content": (
                f"Original search query: {query}\n"
                f"Paper title: {item.title}\n"
                f"Paper URL: {item.url}\n\n"
                "Summarize the paper as a useful research-result content field. Include the problem, method, key findings, "
                "limitations or caveats when present, and why it matches the query. Return ONLY JSON with fields found, answer, "
                "highlights, open_questions, confidence, schema_version.\n\n"
                f"Extracted PDF text:\n{source_text}"
            ),
        },
    ]
    llm_result = await _run_llm_orchestrator(messages, resolved_llm, [item], purpose="paper_summary")
    parsed = _adjust_summary_confidence(
        llm_result["parsed"], llm_result.get("attempts") or [], [item], bool(llm_result.get("repaired"))
    )
    if llm_result.get("ok"):
        _STATUS["llm_success_total"] += 1
    else:
        _STATUS["llm_error_total"] += 1
        _STATUS["last_error"] = "arxiv_paper_summary:validation_failed"
    answer = (parsed.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=502, detail="paper summary LLM returned no answer")
    return _truncate_payload(answer, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)


def _parse_arxiv_entries(payload: bytes, *, query: str, compiled_query: str, count: int) -> List[SearchItem]:
    root = ET.fromstring(payload)
    items: List[SearchItem] = []
    for idx, entry in enumerate(root.findall("atom:entry", _ARXIV_ATOM_NS), start=1):
        if len(items) >= count:
            break
        entry_id = _clean_arxiv_text(entry.findtext("atom:id", default="", namespaces=_ARXIV_ATOM_NS))
        title = _clean_arxiv_text(entry.findtext("atom:title", default="", namespaces=_ARXIV_ATOM_NS))
        summary = _clean_arxiv_text(entry.findtext("atom:summary", default="", namespaces=_ARXIV_ATOM_NS))
        published = _clean_arxiv_text(entry.findtext("atom:published", default="", namespaces=_ARXIV_ATOM_NS)) or None
        pdf_url = ""
        for link in entry.findall("atom:link", _ARXIV_ATOM_NS):
            attrs = getattr(link, "attrib", {}) or {}
            if attrs.get("title") == "pdf" and attrs.get("href"):
                pdf_url = attrs.get("href") or ""
                break
        url = entry_id or pdf_url
        if not url:
            continue
        content = summary[:3000]
        items.append(
            SearchItem(
                rank=idx,
                title=title or url,
                url=url,
                description=summary[:3000],
                published=published,
                language="en",
                score=None,
                source="arxiv",
                engine="arxiv_export_api",
                scraped=True,
                content_chars=len(summary),
                fetch_ms=None,
                content=content,
                raw_content=summary,
                extracted_content=summary,
                usable_for_summary=bool(summary),
                summary_input_mode="arxiv_abstract",
                quality_flags=[
                    "advanced_search",
                    "scientific_source",
                    f"compiled_query:{compiled_query}",
                    f"pdf_url:{pdf_url}",
                ],
                extract_method="arxiv_atom",
                fetch_status="ok",
                http_status=200,
                content_type="application/atom+xml",
                canonical_url=url,
                provider_rank=idx,
            )
        )
    for item in items:
        item.score = _score_item(item, query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


def _resolve_advanced_source(req: SearchRequest) -> str:
    source = (
        (getattr(req, "topic", None) or ADVANCED_SEARCH_DEFAULT_SOURCE or "arxiv").strip().lower().replace("-", "_")
    )
    if source in (
        "",
        "auto",
        "advanced",
        "advanced_search",
        "general",
        "science",
        "scientific",
        "academic",
        "paper",
        "papers",
    ):
        return "auto"
    if source in ("arxiv", "arxiv_api", "arxiv_export"):
        return "arxiv"
    if source in ("rag", "rag_ac_cn", "agentic", "agentic_data", "deepxiv", "agentic_data_interface"):
        return "agentic_data"
    if source in ("sciencestack", "science_stack", "science-stack"):
        return "sciencestack"
    if source in ("oanor", "oanor_arxiv", "oanor-api", "oanor_api"):
        return "oanor"
    if source in ("searchapi", "searchapi_scholar", "searchapi_google_scholar"):
        return "searchapi_scholar"
    if source in ("serpapi", "serpapi_scholar", "serpapi_google_scholar"):
        return "serpapi_scholar"
    if source in ("google_scholar", "scholar"):
        return "searchapi_scholar"
    return source


def _agentic_data_headers() -> Dict[str, str]:
    if not AGENTIC_DATA_API_KEY:
        raise HTTPException(status_code=503, detail="agentic_data advanced_search is not configured")
    return {
        "Accept": "application/json, text/markdown;q=0.9, text/plain;q=0.8, */*;q=0.5",
        "Authorization": f"Bearer {AGENTIC_DATA_API_KEY}",
        "User-Agent": USER_AGENT,
    }


def _agentic_text_from_payload(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_agentic_text_from_payload(v) for v in value]
        return "\n\n".join([p for p in parts if p]).strip()
    if isinstance(value, dict):
        for key in ("content", "raw", "markdown", "text", "paper", "body", "preview"):
            text = _agentic_text_from_payload(value.get(key))
            if text:
                return text
        if "sections" in value:
            return _agentic_text_from_payload(value.get("sections"))
        if "section_contents" in value:
            return _agentic_text_from_payload(value.get("section_contents"))
        parts = []
        title = value.get("section_name") or value.get("title")
        if title:
            parts.append(str(title))
        for key in ("paragraphs", "contents", "children"):
            text = _agentic_text_from_payload(value.get(key))
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()
    return str(value).strip()


def _agentic_response_text(resp: httpx.Response) -> str:
    content_type = (resp.headers.get("content-type") or "").lower()
    if "json" in content_type:
        try:
            return _agentic_text_from_payload(resp.json())
        except Exception:
            return resp.text.strip()
    try:
        parsed = resp.json()
        text = _agentic_text_from_payload(parsed)
        if text:
            return text
    except Exception:
        pass
    return resp.text.strip()


async def _fetch_agentic_full_text(client: httpx.AsyncClient, arxiv_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    if not arxiv_id:
        return {"content": "", "error": "missing_arxiv_id"}
    t0 = datetime.now()
    try:
        _reserve_advanced_provider_quota("agentic_data")
        resp = await client.get(AGENTIC_DATA_ARXIV_URL, params={"type": "raw", "arxiv_id": arxiv_id}, headers=headers)
        status = resp.status_code
        content_type = resp.headers.get("content-type")
        resp.raise_for_status()
        text = _agentic_response_text(resp)
        return {
            "content": text,
            "error": None if text else "agentic_raw_empty",
            "http_status": status,
            "content_type": content_type,
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
            "canonical_url": f"https://arxiv.org/abs/{arxiv_id}",
        }
    except Exception as exc:
        return {
            "content": "",
            "error": f"{type(exc).__name__}: {exc}",
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
        }


async def _run_agentic_data_search(req: SearchRequest) -> List[SearchItem]:
    count = min(_resolve_max_results(req), max(1, AGENTIC_DATA_MAX_RESULTS))
    if count <= 0:
        return []
    timeout = min(float(getattr(req, "timeout", None) or AGENTIC_DATA_TIMEOUT), 120.0)
    headers = _agentic_data_headers()
    params = {
        "type": "retrieve",
        "query": req.query,
        "source": "arxiv",
        "top_k": str(count),
        "return_contents": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            _reserve_advanced_provider_quota("agentic_data")
            resp = await client.get(AGENTIC_DATA_ARXIV_URL, params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(status_code=429, detail="Agentic Data returned 429 Too Many Requests")
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("result") or payload.get("results") or []
            if not isinstance(rows, list):
                rows = []
            items: List[SearchItem] = []
            for idx, row in enumerate(rows[:count], start=1):
                if not isinstance(row, dict):
                    continue
                arxiv_id = str(row.get("arxiv_id") or row.get("id") or "").strip()
                url = str(row.get("url") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")).strip()
                title = _clean_arxiv_text(str(row.get("title") or url or "Untitled"))
                abstract = _clean_arxiv_text(str(row.get("abstract") or row.get("tldr") or ""))
                contents_text = _agentic_text_from_payload(row.get("contents"))
                raw_seed = contents_text or abstract
                item = SearchItem(
                    rank=idx,
                    title=title,
                    url=url,
                    description=abstract[:3000],
                    published=str(row.get("date") or row.get("publish_at") or "") or None,
                    language="en",
                    score=float(row.get("score")) if row.get("score") is not None else None,
                    source="agentic_data",
                    engine="agentic_data_retrieve",
                    scraped=True,
                    content_chars=len(raw_seed),
                    content=_truncate_payload(raw_seed, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS),
                    raw_content=raw_seed,
                    extracted_content=raw_seed,
                    usable_for_summary=bool(raw_seed),
                    summary_input_mode="agentic_data_retrieve",
                    quality_flags=["advanced_search", "scientific_source", "agentic_data", f"arxiv_id:{arxiv_id}"]
                    if arxiv_id
                    else ["advanced_search", "scientific_source", "agentic_data"],
                    extract_method="agentic_data_retrieve",
                    fetch_status="ok",
                    http_status=200,
                    content_type="application/json",
                    canonical_url=url,
                    provider_rank=idx,
                )
                full_result = await _fetch_agentic_full_text(client, arxiv_id, headers)
                full_text = (full_result.get("content") or "").strip()
                if full_text:
                    item.raw_content = full_text
                    item.extracted_content = full_text
                    item.content_chars = len(full_text)
                    item.extract_method = "agentic_data_raw_markdown"
                    item.fetch_ms = int(full_result.get("fetch_ms") or 0)
                    item.http_status = int(full_result.get("http_status") or 200)
                    item.content_type = str(full_result.get("content_type") or "text/markdown")
                    item.canonical_url = str(full_result.get("canonical_url") or url)
                    if len(full_text) > ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS:
                        item.content = await _summarize_paper_content(req.query, item, full_text, req.llm_options)
                        item.summary_input_mode = "agentic_data_llm_summary"
                        flags = list(item.quality_flags or [])
                        flags.append("content_llm_summary")
                        item.quality_flags = flags
                    else:
                        item.content = _truncate_payload(full_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)
                        item.summary_input_mode = "agentic_data_raw_markdown"
                else:
                    item.error = full_result.get("error") or item.error
                    flags = list(item.quality_flags or [])
                    flags.append("agentic_full_text_unavailable")
                    item.quality_flags = flags
                items.append(item)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Agentic Data API timed out for advanced_search") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Agentic Data API failed: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Agentic Data API transport failed: {type(exc).__name__}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Agentic Data API parse failed: {type(exc).__name__}: {exc}"
        ) from exc

    for item in items:
        item.score = item.score if item.score is not None else _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


def _sciencestack_headers() -> Dict[str, str]:
    if not SCIENCESTACK_API_KEY:
        raise HTTPException(status_code=503, detail="sciencestack advanced_search is not configured")
    return {
        "Accept": "application/json, text/markdown;q=0.9, text/plain;q=0.8, */*;q=0.5",
        "x-api-key": SCIENCESTACK_API_KEY,
        "User-Agent": USER_AGENT,
    }


def _sciencestack_payload_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _sciencestack_text_from_payload(value: Any) -> str:
    value = _sciencestack_payload_data(value)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_sciencestack_text_from_payload(v) for v in value]
        return "\n\n".join([p for p in parts if p]).strip()
    if isinstance(value, dict):
        for key in ("markdown", "content", "text", "body", "latex", "raw"):
            text = _sciencestack_text_from_payload(value.get(key))
            if text:
                return text
        parts = []
        for key in ("title", "abstract", "aiSummary", "tldr"):
            if value.get(key):
                parts.append(str(value.get(key)).strip())
        for key in ("sections", "nodes", "children"):
            text = _sciencestack_text_from_payload(value.get(key))
            if text:
                parts.append(text)
        return "\n\n".join([p for p in parts if p]).strip()
    return str(value).strip()


async def _fetch_sciencestack_content(
    client: httpx.AsyncClient, arxiv_id: str, headers: Dict[str, str]
) -> Dict[str, Any]:
    if not arxiv_id:
        return {"content": "", "error": "missing_arxiv_id"}
    t0 = datetime.now()
    try:
        _reserve_advanced_provider_quota("sciencestack")
        resp = await client.get(
            f"{SCIENCESTACK_API_URL}/papers/{arxiv_id}/content", params={"format": "markdown"}, headers=headers
        )
        status = resp.status_code
        content_type = resp.headers.get("content-type")
        if status == 429:
            raise HTTPException(status_code=429, detail="ScienceStack returned 429 Too Many Requests")
        resp.raise_for_status()
        if "json" in (content_type or "").lower():
            text = _sciencestack_text_from_payload(resp.json())
        else:
            text = resp.text.strip()
        return {
            "content": text,
            "error": None if text else "sciencestack_content_empty",
            "http_status": status,
            "content_type": content_type,
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
            "canonical_url": f"https://arxiv.org/abs/{arxiv_id}",
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {
            "content": "",
            "error": f"{type(exc).__name__}: {exc}",
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
        }


async def _run_sciencestack_search(req: SearchRequest) -> List[SearchItem]:
    count = min(_resolve_max_results(req), max(1, SCIENCESTACK_MAX_RESULTS))
    if count <= 0:
        return []
    timeout = min(float(getattr(req, "timeout", None) or SCIENCESTACK_TIMEOUT), 120.0)
    headers = _sciencestack_headers()
    params = {"q": req.query, "limit": str(count)}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            _reserve_advanced_provider_quota("sciencestack")
            resp = await client.get(f"{SCIENCESTACK_API_URL}/search", params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(status_code=429, detail="ScienceStack returned 429 Too Many Requests")
            resp.raise_for_status()
            payload = resp.json()
            rows = _sciencestack_payload_data(payload)
            if not isinstance(rows, list):
                rows = []
            items: List[SearchItem] = []
            for idx, row in enumerate(rows[:count], start=1):
                if not isinstance(row, dict):
                    continue
                arxiv_id = str(row.get("arxivId") or row.get("arxiv_id") or row.get("id") or "").strip()
                url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else str(row.get("url") or "").strip()
                title = _clean_arxiv_text(str(row.get("title") or url or "Untitled"))
                abstract = _clean_arxiv_text(str(row.get("abstract") or row.get("tldr") or row.get("aiSummary") or ""))
                seed_text = abstract or title
                item = SearchItem(
                    rank=idx,
                    title=title,
                    url=url,
                    description=abstract[:3000],
                    published=str(row.get("published") or row.get("publishedAt") or "") or None,
                    language="en",
                    score=None,
                    source="sciencestack",
                    engine="sciencestack_search",
                    scraped=True,
                    content_chars=len(seed_text),
                    content=_truncate_payload(seed_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS),
                    raw_content=seed_text,
                    extracted_content=seed_text,
                    usable_for_summary=bool(seed_text),
                    summary_input_mode="sciencestack_search",
                    quality_flags=["advanced_search", "scientific_source", "sciencestack", f"arxiv_id:{arxiv_id}"]
                    if arxiv_id
                    else ["advanced_search", "scientific_source", "sciencestack"],
                    extract_method="sciencestack_search",
                    fetch_status="ok",
                    http_status=200,
                    content_type="application/json",
                    canonical_url=url,
                    provider_rank=idx,
                )
                content_result = await _fetch_sciencestack_content(client, arxiv_id, headers)
                full_text = (content_result.get("content") or "").strip()
                if full_text:
                    item.raw_content = full_text
                    item.extracted_content = full_text
                    item.content_chars = len(full_text)
                    item.extract_method = "sciencestack_markdown"
                    item.fetch_ms = int(content_result.get("fetch_ms") or 0)
                    item.http_status = int(content_result.get("http_status") or 200)
                    item.content_type = str(content_result.get("content_type") or "text/markdown")
                    item.canonical_url = str(content_result.get("canonical_url") or url)
                    if len(full_text) > ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS:
                        item.content = await _summarize_paper_content(req.query, item, full_text, req.llm_options)
                        item.summary_input_mode = "sciencestack_llm_summary"
                        flags = list(item.quality_flags or [])
                        flags.append("content_llm_summary")
                        item.quality_flags = flags
                    else:
                        item.content = _truncate_payload(full_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)
                        item.summary_input_mode = "sciencestack_markdown"
                else:
                    item.error = content_result.get("error") or item.error
                    flags = list(item.quality_flags or [])
                    flags.append("sciencestack_content_unavailable")
                    item.quality_flags = flags
                items.append(item)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="ScienceStack API timed out for advanced_search") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"ScienceStack API failed: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ScienceStack API transport failed: {type(exc).__name__}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"ScienceStack API parse failed: {type(exc).__name__}: {exc}"
        ) from exc

    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


def _oanor_headers() -> Dict[str, str]:
    if not OANOR_API_KEY:
        raise HTTPException(status_code=503, detail="oanor advanced_search is not configured")
    return {
        "Accept": "application/json, */*;q=0.5",
        "x-oanor-key": OANOR_API_KEY,
        "User-Agent": USER_AGENT,
    }


def _oanor_data_rows(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "items", "papers"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for key in ("result", "paper"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _oanor_first(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if not value:
            return ""
        if all(isinstance(v, str) for v in value):
            return ", ".join([v.strip() for v in value if v.strip()])
        return _oanor_first(value[0])
    if isinstance(value, dict):
        for key in ("name", "title", "value", "url", "href"):
            if value.get(key):
                return _oanor_first(value.get(key))
    return str(value).strip()


def _oanor_pdf_url(row: Dict[str, Any]) -> str:
    for key in ("pdf_url", "pdfUrl", "pdf", "pdfLink"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            candidate = _oanor_first(value)
            if candidate:
                return candidate
    links = row.get("links") or row.get("link") or []
    if isinstance(links, dict):
        links = [links]
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict):
                title = str(link.get("title") or link.get("rel") or link.get("type") or "").lower()
                href = _oanor_first(link.get("href") or link.get("url"))
                if href and ("pdf" in title or href.endswith(".pdf") or "/pdf/" in href):
                    return href
            elif isinstance(link, str) and ("/pdf/" in link or link.endswith(".pdf")):
                return link.strip()
    return ""


def _oanor_arxiv_id(row: Dict[str, Any]) -> str:
    for key in ("arxiv_id", "arxivId", "id"):
        value = _oanor_first(row.get(key))
        if value:
            return value.replace("arXiv:", "").strip()
    url = _oanor_first(row.get("url") or row.get("abs_url") or row.get("absUrl"))
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", url)
    return match.group(1).replace(".pdf", "").strip() if match else ""


async def _run_oanor_search(req: SearchRequest) -> List[SearchItem]:
    count = min(_resolve_max_results(req), max(1, OANOR_MAX_RESULTS))
    if count <= 0:
        return []
    timeout = min(float(getattr(req, "timeout", None) or OANOR_TIMEOUT), 120.0)
    headers = _oanor_headers()
    params = {"q": req.query, "limit": str(count)}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            _reserve_advanced_provider_quota("oanor")
            resp = await client.get(f"{OANOR_ARXIV_API_URL}/v1/search", params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(status_code=429, detail="Oanor returned 429 Too Many Requests")
            resp.raise_for_status()
            payload = resp.json()
            rows = _oanor_data_rows(payload)
            items: List[SearchItem] = []
            for idx, row in enumerate(rows[:count], start=1):
                if not isinstance(row, dict):
                    continue
                arxiv_id = _oanor_arxiv_id(row)
                pdf_url = _oanor_pdf_url(row) or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "")
                url = _oanor_first(row.get("url") or row.get("abs_url") or row.get("absUrl")) or (
                    f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else pdf_url
                )
                title = _clean_arxiv_text(_oanor_first(row.get("title")) or url or "Untitled")
                abstract = _clean_arxiv_text(
                    _oanor_first(row.get("abstract") or row.get("summary") or row.get("description"))
                )
                authors = _oanor_first(row.get("authors") or row.get("author"))
                seed_parts = [p for p in [title, f"Authors: {authors}" if authors else "", abstract] if p]
                seed_text = "\n\n".join(seed_parts).strip()
                item = SearchItem(
                    rank=idx,
                    title=title,
                    url=url,
                    description=abstract[:3000],
                    published=_oanor_first(row.get("published") or row.get("published_at") or row.get("updated"))
                    or None,
                    language="en",
                    score=None,
                    source="oanor",
                    engine="oanor_arxiv_api",
                    scraped=True,
                    content_chars=len(seed_text),
                    content=_truncate_payload(seed_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS),
                    raw_content=seed_text,
                    extracted_content=seed_text,
                    usable_for_summary=bool(seed_text),
                    summary_input_mode="oanor_metadata",
                    quality_flags=[
                        "advanced_search",
                        "scientific_source",
                        "oanor",
                        f"arxiv_id:{arxiv_id}",
                        f"pdf_url:{pdf_url}",
                    ],
                    extract_method="oanor_arxiv_api",
                    fetch_status="ok",
                    http_status=200,
                    content_type="application/json",
                    canonical_url=url,
                    provider_rank=idx,
                )
                if pdf_url:
                    pdf_result = await _fetch_arxiv_pdf_text(pdf_url, timeout=timeout)
                    pdf_text = (pdf_result.get("content") or "").strip()
                    if pdf_text:
                        item.raw_content = pdf_text
                        item.extracted_content = pdf_text
                        item.content_chars = len(pdf_text)
                        item.extract_method = "oanor_arxiv_pdf_pypdf"
                        item.fetch_ms = int(pdf_result.get("fetch_ms") or 0)
                        item.http_status = int(pdf_result.get("http_status") or 200)
                        item.content_type = str(pdf_result.get("content_type") or "application/pdf")
                        item.canonical_url = str(pdf_result.get("canonical_url") or pdf_url or url)
                        if len(pdf_text) > ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS:
                            item.content = await _summarize_paper_content(req.query, item, pdf_text, req.llm_options)
                            item.summary_input_mode = "oanor_pdf_llm_summary"
                            flags = list(item.quality_flags or [])
                            flags.append("content_llm_summary")
                            item.quality_flags = flags
                        else:
                            item.content = _truncate_payload(pdf_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)
                            item.summary_input_mode = "oanor_pdf_text"
                    else:
                        item.error = pdf_result.get("error") or item.error
                        flags = list(item.quality_flags or [])
                        flags.append("pdf_text_unavailable")
                        item.quality_flags = flags
                items.append(item)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Oanor API timed out for advanced_search") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Oanor API failed: HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Oanor API transport failed: {type(exc).__name__}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Oanor API parse failed: {type(exc).__name__}: {exc}") from exc

    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


def _searchapi_auth_params() -> Dict[str, str]:
    if not SEARCHAPI_API_KEY:
        raise HTTPException(status_code=503, detail="searchapi_scholar advanced_search is not configured")
    return {"api_key": SEARCHAPI_API_KEY}


def _searchapi_author_names(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item.get("name")).strip())
            elif isinstance(item, str):
                names.append(item.strip())
        return ", ".join([n for n in names if n])
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _searchapi_best_url(row: Dict[str, Any]) -> str:
    resource = row.get("resource") if isinstance(row.get("resource"), dict) else {}
    resource_link = str(resource.get("link") or "").strip()
    if resource_link:
        return resource_link
    return str(row.get("link") or "").strip()


async def _run_searchapi_scholar_search(req: SearchRequest) -> List[SearchItem]:
    count = min(_resolve_max_results(req), max(1, SEARCHAPI_MAX_RESULTS))
    if count <= 0:
        return []
    timeout = min(float(getattr(req, "timeout", None) or SEARCHAPI_TIMEOUT), 120.0)
    params = {
        "engine": "google_scholar",
        "q": req.query,
        "num": str(min(count, 20)),
    }
    params.update(_searchapi_auth_params())
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            _reserve_advanced_provider_quota("searchapi_scholar")
            resp = await client.get(SEARCHAPI_API_URL, params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(status_code=429, detail="SearchAPI returned 429 Too Many Requests")
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("organic_results") or []
            if not isinstance(rows, list):
                rows = []
            items: List[SearchItem] = []
            for idx, row in enumerate(rows[:count], start=1):
                if not isinstance(row, dict):
                    continue
                url = _searchapi_best_url(row)
                if not url:
                    continue
                title = _clean_arxiv_text(str(row.get("title") or url))
                snippet = _clean_arxiv_text(str(row.get("snippet") or ""))
                publication = _clean_arxiv_text(str(row.get("publication") or ""))
                authors = _searchapi_author_names(row.get("authors"))
                seed_parts = [p for p in [title, publication, f"Authors: {authors}" if authors else "", snippet] if p]
                seed_text = "\n\n".join(seed_parts).strip()
                item = SearchItem(
                    rank=idx,
                    title=title,
                    url=url,
                    description=snippet[:3000],
                    published=None,
                    language="en",
                    score=None,
                    source="searchapi_scholar",
                    engine="searchapi_google_scholar",
                    scraped=False,
                    content_chars=len(seed_text),
                    content=_truncate_payload(seed_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS),
                    raw_content=seed_text,
                    extracted_content=seed_text,
                    usable_for_summary=bool(seed_text),
                    summary_input_mode="searchapi_scholar_metadata",
                    quality_flags=["advanced_search", "scientific_source", "searchapi_scholar"],
                    extract_method="searchapi_google_scholar",
                    fetch_status="metadata_only",
                    http_status=200,
                    content_type="application/json",
                    canonical_url=url,
                    provider_rank=int(row.get("position") or idx),
                )
                try:
                    extracted = await _extract_content(url, timeout)
                except Exception as exc:
                    extracted = {"content": "", "error": f"{type(exc).__name__}: {exc}"}
                extracted_text = (extracted.get("content") or "").strip()
                if extracted_text:
                    item.raw_content = extracted_text
                    item.extracted_content = extracted_text
                    item.content_chars = len(extracted_text)
                    item.scraped = True
                    item.fetch_ms = int(extracted.get("fetch_ms") or 0)
                    item.http_status = int(extracted.get("http_status") or 200)
                    item.content_type = str(extracted.get("content_type") or "") or item.content_type
                    item.canonical_url = str(extracted.get("canonical_url") or url)
                    item.extract_method = str(extracted.get("extract_method") or "searchapi_fetch")
                    item.fetch_status = "ok"
                    if len(extracted_text) > ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS:
                        item.content = await _summarize_paper_content(req.query, item, extracted_text, req.llm_options)
                        item.summary_input_mode = "searchapi_scholar_llm_summary"
                        flags = list(item.quality_flags or [])
                        flags.append("content_llm_summary")
                        item.quality_flags = flags
                    else:
                        item.content = _truncate_payload(extracted_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)
                        item.summary_input_mode = "searchapi_scholar_extracted_text"
                else:
                    item.error = extracted.get("error") or item.error
                    item.failure_reason = extracted.get("failure_reason") or item.failure_reason
                    flags = list(item.quality_flags or [])
                    flags.append("content_unavailable")
                    item.quality_flags = flags
                items.append(item)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="SearchAPI Google Scholar timed out for advanced_search") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"SearchAPI Google Scholar failed: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"SearchAPI Google Scholar transport failed: {type(exc).__name__}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"SearchAPI Google Scholar parse failed: {type(exc).__name__}: {exc}"
        ) from exc

    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


def _advanced_provider_failure_status(exc: HTTPException) -> int:
    status = int(exc.status_code or 500)
    detail_text = json.dumps(exc.detail) if isinstance(exc.detail, (dict, list)) else str(exc.detail or "")
    match = re.search(r"HTTP\s+(\d{3})", detail_text)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            pass
    return status


def _advanced_provider_failure_reason(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict):
        return str(exc.detail.get("reason") or exc.detail.get("message") or exc.detail)
    return str(exc.detail or type(exc).__name__)


async def _call_advanced_provider(provider: str, req: SearchRequest) -> List[SearchItem]:
    _raise_if_advanced_provider_cooling(provider)
    try:
        if provider == "agentic_data":
            items = await _run_agentic_data_search(req)
        elif provider == "sciencestack":
            items = await _run_sciencestack_search(req)
        elif provider == "oanor":
            items = await _run_oanor_search(req)
        elif provider == "searchapi_scholar":
            items = await _run_searchapi_scholar_search(req)
        elif provider == "serpapi_scholar":
            items = await _run_serpapi_scholar_search(req)
        elif provider == "arxiv":
            items = await _run_arxiv_search(req)
        else:
            raise HTTPException(status_code=400, detail=f"advanced_search source {provider!r} is not supported yet")
    except HTTPException as exc:
        status = _advanced_provider_failure_status(exc)
        if status in (402, 429, 502, 503, 504):
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            retry_after = None
            if isinstance(detail, dict) and detail.get("retry_after_seconds") is not None:
                try:
                    retry_after = int(detail.get("retry_after_seconds"))
                except Exception:
                    retry_after = None
            _mark_advanced_provider_failure(
                provider, status, _advanced_provider_failure_reason(exc), retry_after=retry_after
            )
        raise
    if items:
        _mark_advanced_provider_success(provider)
    return items


def _advanced_clone_for_provider(req: SearchRequest, per_provider_count: int) -> SearchRequest:
    clone = SearchRequest(**_model_dict(req))
    clone.topic = None
    clone.count = per_provider_count
    clone.max_results = per_provider_count
    return clone


def _normalize_science_classifier_payload(parsed: Any) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {"is_science": False, "confidence": 0.0, "reason": "classifier_returned_non_json"}
    raw_value = parsed.get("is_science")
    if raw_value is None:
        raw_value = parsed.get("science")
    if raw_value is None:
        raw_value = parsed.get("scientific")
    if isinstance(raw_value, str):
        is_science = raw_value.strip().lower() in ("1", "true", "yes", "y", "science", "scientific")
    else:
        is_science = bool(raw_value)
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
    except Exception:
        confidence = 0.0
    category = str(parsed.get("category") or "").strip().lower()
    reason = str(parsed.get("reason") or "").strip()
    return {
        "is_science": bool(is_science and confidence >= SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD),
        "raw_is_science": bool(is_science),
        "confidence": confidence,
        "category": category,
        "reason": reason,
    }


async def _classify_science_query(
    query: str, llm_options: Optional[LLMOptions] = None, request_id: Optional[str] = None
) -> Dict[str, Any]:
    if not SCIENCE_CLASSIFIER_ENABLED:
        return {"is_science": False, "confidence": 0.0, "reason": "science_classifier_disabled"}
    if not SUMMARIZER_ENABLED or not _LITELLM_AVAILABLE:
        return {"is_science": False, "confidence": 0.0, "reason": "science_classifier_llm_unavailable"}
    resolved_llm = _resolve_llm_options(llm_options)
    resolved_llm["response_format"] = "json_object"
    resolved_llm["max_completion_tokens"] = max(
        32,
        min(
            SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS,
            int(resolved_llm.get("max_completion_tokens") or SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS),
        ),
    )
    resolved_llm["timeout"] = max(
        1.0, min(SCIENCE_CLASSIFIER_TIMEOUT, float(resolved_llm.get("timeout") or SCIENCE_CLASSIFIER_TIMEOUT))
    )
    resolved_llm["max_total_seconds"] = max(
        1.0,
        min(
            SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS,
            float(resolved_llm.get("max_total_seconds") or SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS),
        ),
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Classify whether a search query should use scientific or scholarly retrieval in addition to web search. "
                "Return ONLY JSON. Do not explain outside JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "Return JSON with fields is_science boolean, confidence number 0-1, category string, reason string.\n"
                "Mark true for queries about science, engineering, medicine, biology, chemistry, physics, materials, batteries, climate, geology, math, statistics, machine learning research, papers, patents, datasets, experiments, technical mechanisms, or academic topics.\n"
                "Mark false for ordinary consumer, local, entertainment, sports, shopping, general news, or navigation searches unless they ask for scientific/technical evidence.\n\n"
                f"Query: {query}"
            ),
        },
    ]
    started = time.monotonic()
    attempts: List[Dict[str, Any]] = []
    allow_expensive = bool(resolved_llm.get("allow_expensive_fallback"))
    for spec in _build_llm_candidate_specs(resolved_llm):
        if time.monotonic() - started > float(
            resolved_llm.get("max_total_seconds") or SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS
        ):
            attempt = {
                "purpose": "science_classifier",
                "request_id": request_id,
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "classifier",
                "success": False,
                "failure_type": "budget_exhausted",
            }
            _log_llm_attempt(attempt)
            attempts.append(attempt)
            break
        if (
            not allow_expensive
            and _is_expensive_llm_spec(spec)
            and spec != {"provider": resolved_llm["provider"], "model": resolved_llm["model"]}
        ):
            attempt = {
                "purpose": "science_classifier",
                "request_id": request_id,
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "classifier",
                "success": False,
                "failure_type": "expensive_fallback_blocked",
            }
            _log_llm_attempt(attempt)
            attempts.append(attempt)
            continue
        t0 = time.monotonic()
        try:
            remaining = _remaining_llm_timeout(
                started,
                float(resolved_llm.get("max_total_seconds") or SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS),
                float(resolved_llm.get("timeout") or SCIENCE_CLASSIFIER_TIMEOUT),
            )
            if remaining <= 0:
                raise asyncio.TimeoutError("science_classifier_budget_exhausted")
            llm_resp = await _call_litellm_model(spec, messages, resolved_llm, attempt_timeout=remaining)
            payload = _extract_llm_response_payload(llm_resp)
            parsed = _extract_json_from_text(payload.get("raw") or "")
            normalized = _normalize_science_classifier_payload(parsed)
            success = isinstance(parsed, dict)
            attempt = {
                "purpose": "science_classifier",
                "request_id": request_id,
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "classifier",
                "success": success,
                "failure_type": None if success else "invalid_json",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "finish_reason": payload.get("finish_reason"),
                "classification": normalized.get("is_science"),
                "confidence": normalized.get("confidence"),
                "category": normalized.get("category"),
            }
            if payload.get("usage"):
                attempt["usage"] = payload.get("usage")
            _log_llm_attempt(attempt)
            attempts.append(attempt)
            if success:
                normalized["provider"] = spec["provider"]
                normalized["model"] = spec["model"]
                normalized["attempts"] = attempts
                return normalized
        except Exception as exc:
            attempt = {
                "purpose": "science_classifier",
                "request_id": request_id,
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "classifier",
                "success": False,
                "failure_type": type(exc).__name__,
                "error": str(exc),
                "latency_ms": int((time.monotonic() - t0) * 1000),
            }
            _log_llm_attempt(attempt)
            attempts.append(attempt)
            continue
    return {"is_science": False, "confidence": 0.0, "reason": "science_classifier_failed", "attempts": attempts}


async def _run_advanced_search_auto(req: SearchRequest) -> List[SearchItem]:
    requested = max(1, _resolve_max_results(req))
    min_successes = max(1, ADVANCED_SEARCH_AUTO_MIN_PROVIDERS)
    max_providers = max(min_successes, ADVANCED_SEARCH_AUTO_MAX_PROVIDERS)
    target_results = max(requested, min_successes)
    per_provider_count = 1
    order = []
    for raw in ADVANCED_SEARCH_AUTO_PROVIDER_ORDER:
        provider = raw.strip().lower().replace("-", "_")
        if provider in ("searchapi", "google_scholar", "scholar"):
            provider = "searchapi_scholar"
        if provider in ("serpapi", "serpapi_google_scholar"):
            provider = "serpapi_scholar"
        if provider in _advanced_provider_names() and provider not in order:
            order.append(provider)
    for provider in _advanced_provider_names():
        if provider not in order:
            order.append(provider)

    items: List[SearchItem] = []
    seen_urls = set()
    successes = 0
    failures: List[Dict[str, Any]] = []
    attempted = 0
    for provider in order:
        if attempted >= max_providers:
            break
        cooldown_remaining = _advanced_provider_cooldown_remaining(provider)
        if cooldown_remaining > 0:
            failures.append(
                {
                    "provider": provider,
                    "status_code": 429,
                    "reason": "cooldown",
                    "retry_after_seconds": cooldown_remaining,
                }
            )
            continue
        attempted += 1
        provider_req = _advanced_clone_for_provider(req, per_provider_count)
        try:
            provider_items = await _call_advanced_provider(provider, provider_req)
        except HTTPException as exc:
            failures.append({"provider": provider, "status_code": exc.status_code, "detail": exc.detail})
            continue
        if provider_items:
            successes += 1
            for item in provider_items:
                key = (item.url or item.canonical_url or item.title or "").strip().lower()
                if key and key in seen_urls:
                    continue
                if key:
                    seen_urls.add(key)
                flags = list(item.quality_flags or [])
                flags.append(f"advanced_auto_provider:{provider}")
                item.quality_flags = flags
                item.rank = len(items) + 1
                items.append(item)
        if successes >= min_successes and len(items) >= target_results:
            break

    if not items:
        raise HTTPException(
            status_code=502,
            detail={
                "source": "advanced_auto",
                "reason": "all_advanced_providers_failed",
                "provider_failures": failures,
            },
        )
    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items[:target_results]


def _serpapi_auth_params() -> Dict[str, str]:
    if not SERPAPI_API_KEY:
        raise HTTPException(status_code=503, detail="serpapi_scholar advanced_search is not configured")
    return {"api_key": SERPAPI_API_KEY}


def _serpapi_publication_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        pieces = []
        if value.get("summary"):
            pieces.append(str(value.get("summary")).strip())
        authors = value.get("authors")
        if isinstance(authors, list):
            names = []
            for author in authors:
                if isinstance(author, dict) and author.get("name"):
                    names.append(str(author.get("name")).strip())
                elif isinstance(author, str):
                    names.append(author.strip())
            if names:
                pieces.append("Authors: " + ", ".join(names))
        return "\n".join([p for p in pieces if p]).strip()
    return str(value).strip()


def _serpapi_best_url(row: Dict[str, Any]) -> str:
    resources = row.get("resources")
    if isinstance(resources, list):
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            link = str(resource.get("link") or "").strip()
            title = str(resource.get("title") or resource.get("file_format") or "").lower()
            if link and ("pdf" in title or link.lower().endswith(".pdf")):
                return link
        for resource in resources:
            if isinstance(resource, dict) and resource.get("link"):
                return str(resource.get("link")).strip()
    return str(row.get("link") or "").strip()


async def _run_serpapi_scholar_search(req: SearchRequest) -> List[SearchItem]:
    count = min(_resolve_max_results(req), max(1, SERPAPI_MAX_RESULTS))
    if count <= 0:
        return []
    timeout = min(float(getattr(req, "timeout", None) or SERPAPI_TIMEOUT), 120.0)
    params = {
        "engine": "google_scholar",
        "q": req.query,
        "num": str(min(count, 20)),
    }
    params.update(_serpapi_auth_params())
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            _reserve_advanced_provider_quota("serpapi_scholar")
            resp = await client.get(SERPAPI_API_URL, params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(status_code=429, detail="SerpApi returned 429 Too Many Requests")
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise HTTPException(status_code=502, detail=f"SerpApi error: {payload.get('error')}")
            rows = payload.get("organic_results") or []
            if not isinstance(rows, list):
                rows = []
            items: List[SearchItem] = []
            for idx, row in enumerate(rows[:count], start=1):
                if not isinstance(row, dict):
                    continue
                url = _serpapi_best_url(row)
                if not url:
                    continue
                title = _clean_arxiv_text(str(row.get("title") or url))
                snippet = _clean_arxiv_text(str(row.get("snippet") or ""))
                publication = _clean_arxiv_text(_serpapi_publication_text(row.get("publication_info")))
                seed_parts = [p for p in [title, publication, snippet] if p]
                seed_text = "\n\n".join(seed_parts).strip()
                item = SearchItem(
                    rank=idx,
                    title=title,
                    url=url,
                    description=snippet[:3000],
                    published=None,
                    language="en",
                    score=None,
                    source="serpapi_scholar",
                    engine="serpapi_google_scholar",
                    scraped=False,
                    content_chars=len(seed_text),
                    content=_truncate_payload(seed_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS),
                    raw_content=seed_text,
                    extracted_content=seed_text,
                    usable_for_summary=bool(seed_text),
                    summary_input_mode="serpapi_scholar_metadata",
                    quality_flags=["advanced_search", "scientific_source", "serpapi_scholar"],
                    extract_method="serpapi_google_scholar",
                    fetch_status="metadata_only",
                    http_status=200,
                    content_type="application/json",
                    canonical_url=url,
                    provider_rank=int(row.get("position") or idx),
                )
                try:
                    extracted = await _extract_content(url, timeout)
                except Exception as exc:
                    extracted = {"content": "", "error": f"{type(exc).__name__}: {exc}"}
                extracted_text = (extracted.get("content") or "").strip()
                if extracted_text:
                    item.raw_content = extracted_text
                    item.extracted_content = extracted_text
                    item.content_chars = len(extracted_text)
                    item.scraped = True
                    item.fetch_ms = int(extracted.get("fetch_ms") or 0)
                    item.http_status = int(extracted.get("http_status") or 200)
                    item.content_type = str(extracted.get("content_type") or "") or item.content_type
                    item.canonical_url = str(extracted.get("canonical_url") or url)
                    item.extract_method = str(extracted.get("extract_method") or "serpapi_fetch")
                    item.fetch_status = "ok"
                    if len(extracted_text) > ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS:
                        item.content = await _summarize_paper_content(req.query, item, extracted_text, req.llm_options)
                        item.summary_input_mode = "serpapi_scholar_llm_summary"
                        flags = list(item.quality_flags or [])
                        flags.append("content_llm_summary")
                        item.quality_flags = flags
                    else:
                        item.content = _truncate_payload(extracted_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)
                        item.summary_input_mode = "serpapi_scholar_extracted_text"
                else:
                    item.error = extracted.get("error") or item.error
                    item.failure_reason = extracted.get("failure_reason") or item.failure_reason
                    flags = list(item.quality_flags or [])
                    flags.append("content_unavailable")
                    item.quality_flags = flags
                items.append(item)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="SerpApi Google Scholar timed out for advanced_search") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"SerpApi Google Scholar failed: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"SerpApi Google Scholar transport failed: {type(exc).__name__}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"SerpApi Google Scholar parse failed: {type(exc).__name__}: {exc}"
        ) from exc

    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


async def _run_advanced_search(req: SearchRequest) -> List[SearchItem]:
    if not ADVANCED_SEARCH_ENABLED:
        raise HTTPException(status_code=503, detail="advanced_search is disabled")
    source = _resolve_advanced_source(req)
    if source == "auto":
        return await _run_advanced_search_auto(req)
    return await _call_advanced_provider(source, req)


async def _run_arxiv_search(req: SearchRequest) -> List[SearchItem]:
    count = min(_resolve_max_results(req), max(1, ARXIV_MAX_RESULTS))
    if count <= 0:
        return []
    compiled_query = _compile_arxiv_query(req.query)
    params = {
        "search_query": compiled_query,
        "start": "0",
        "max_results": str(count),
    }
    headers = {
        "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.5",
        "User-Agent": ARXIV_USER_AGENT or USER_AGENT,
    }
    timeout = min(float(getattr(req, "timeout", None) or ARXIV_TIMEOUT), 120.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await _arxiv_rate_limited_get(client, ARXIV_API_URL, params=params, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="arXiv export API timed out for advanced_search") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"arXiv export API transport failed: {type(exc).__name__}") from exc
    try:
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"arXiv export API failed: HTTP {resp.status_code}") from exc
    try:
        items = _parse_arxiv_entries(resp.content, query=req.query, compiled_query=compiled_query, count=count)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"arXiv Atom parse failed: {type(exc).__name__}: {exc}") from exc

    if _arxiv_wants_pdf_text(req) and items:
        for item in items:
            pdf_url = ""
            for flag in item.quality_flags or []:
                if flag.startswith("pdf_url:"):
                    pdf_url = flag.split(":", 1)[1]
                    break
            pdf_result = await _fetch_arxiv_pdf_text(pdf_url, timeout=timeout)
            pdf_text = (pdf_result.get("content") or "").strip()
            if pdf_text:
                item.raw_content = pdf_text
                item.extracted_content = pdf_text
                if len(pdf_text) > ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS:
                    item.content = await _summarize_paper_content(req.query, item, pdf_text, req.llm_options)
                    item.summary_input_mode = "arxiv_pdf_llm_summary"
                    flags = list(item.quality_flags or [])
                    flags.append("content_llm_summary")
                    item.quality_flags = flags
                else:
                    item.content = _truncate_payload(pdf_text, ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS)
                    item.summary_input_mode = "arxiv_pdf_text"
                item.content_chars = len(pdf_text)
                item.extract_method = "arxiv_pdf_pypdf"
                item.fetch_ms = int(pdf_result.get("fetch_ms") or 0)
                item.http_status = int(pdf_result.get("http_status") or 200)
                item.content_type = str(pdf_result.get("content_type") or "application/pdf")
                item.canonical_url = str(pdf_result.get("canonical_url") or pdf_url or item.canonical_url)
                flags = list(item.quality_flags or [])
                flags.append(f"pdf_bytes:{pdf_result.get('bytes') or 0}")
                item.quality_flags = flags
            else:
                item.error = pdf_result.get("error") or item.error
                item.failure_reason = pdf_result.get("error") or item.failure_reason
                flags = list(item.quality_flags or [])
                flags.append("pdf_text_unavailable")
                item.quality_flags = flags

    return items


async def _run_search(req: SearchRequest) -> List[SearchItem]:
    count = _resolve_max_results(req)
    if count <= 0:
        return []
    has_domain_filters = bool(getattr(req, "include_domains", []) or getattr(req, "exclude_domains", []))
    provider_count = SERPER_MAX_COUNT if has_domain_filters and count < SERPER_MAX_COUNT else count
    raw_results = await _search_provider(req, provider_count)
    items: List[SearchItem] = []
    seen_urls = set()

    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        url = (raw.get("url") or "").strip()
        canonical_key = url.split("#", 1)[0].rstrip("/")
        if canonical_key in seen_urls:
            continue
        seen_urls.add(canonical_key)
        if not _domain_allowed(url, getattr(req, "include_domains", []), getattr(req, "exclude_domains", [])):
            continue
        items.append(
            SearchItem(
                rank=int(raw.get("rank") or 0),
                title=(raw.get("title") or "").strip()[:512],
                url=url,
                description=(raw.get("description") or "").strip()[:3000],
                published=raw.get("published") or None,
                language=raw.get("language") or None,
                score=raw.get("score") if isinstance(raw.get("score"), (int, float)) else None,
                source=raw.get("source") or SEARCH_PROVIDER,
                engine=raw.get("engine"),
                content=(raw.get("description") or "").strip()[:3000],
                favicon=_favicon_for_url(url) if getattr(req, "include_favicon", False) else None,
                images=[ImageItem(**img) for img in (raw.get("images") or [])]
                if getattr(req, "include_images", False)
                else None,
                provider_rank=int(raw.get("rank") or 0),
            )
        )
        if len(items) >= count:
            break

    if _resolve_include_content(req) and items:
        limit = req.fetch_top_n if req.fetch_top_n else len(items)
        to_fetch = items[:limit]
        semaphore = asyncio.Semaphore(max(1, MAX_FETCH_CONCURRENCY))

        async def guarded_extract(item: SearchItem) -> Dict[str, Any]:
            if not item.url:
                return {
                    "content": None,
                    "scraped": False,
                    "content_chars": 0,
                    "fetch_ms": None,
                    "error": "empty_url",
                    "extract_method": "failed",
                    "fetch_status": "failed",
                    "failure_reason": "empty_url",
                }
            async with semaphore:
                return await _extract_content(item.url, timeout_s=_resolve_timeout(req))

        tasks = [guarded_extract(item) for item in to_fetch]
        scraped_data = await asyncio.gather(*tasks)
        for item, scraped in zip(to_fetch, scraped_data):
            item.scraped = bool(scraped.get("scraped"))
            item.content_chars = int(scraped.get("content_chars") or 0)
            item.fetch_ms = int(scraped.get("fetch_ms") or 0)
            item.error = scraped.get("error")
            item.extract_method = scraped.get("extract_method")
            item.fetch_status = scraped.get("fetch_status")
            item.http_status = scraped.get("http_status")
            item.content_type = scraped.get("content_type")
            item.failure_reason = scraped.get("failure_reason")
            item.canonical_url = scraped.get("canonical_url") or item.url
            if not item.error:
                full_content = scraped.get("content") or ""
                item.extracted_content = full_content
                item.content = (
                    _chunk_text(full_content, req.chunks_per_source)
                    if _resolve_search_depth(req) == "advanced" or req.chunks_per_source
                    else _truncate_payload(full_content, 1000)
                )
                if getattr(req, "include_raw_content", None) is not None:
                    item.raw_content = full_content
                _STATUS["extract_success_total"] += 1
            else:
                _STATUS["extract_error_total"] += 1

    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


_NAV_JUNK_PATTERNS = [
    "skip to main content",
    "toggle menu",
    "sign in",
    "subscribe",
    "newsletters",
    "follow us",
    "my account",
    "privacy policy",
    "terms of use",
    "cookie policy",
    "advertise",
    "all newsletters",
    "facebook",
    "instagram",
    "linkedin",
    "cartoons",
    "podcasts",
    "live events",
    "log in",
]
_CURRENT_EVENT_TERMS = {
    "new",
    "latest",
    "current",
    "today",
    "recent",
    "now",
    "replacement",
    "successor",
    "fire",
    "fired",
    "ouster",
    "ousted",
    "planning",
    "approved",
}


def _word_list(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{1,}", (text or "").lower())


def _summary_terms(query: str, item: SearchItem) -> List[str]:
    raw_terms = _word_list(" ".join([query or "", item.title or "", item.description or ""]))
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "about",
        "what",
        "who",
        "has",
        "have",
        "was",
        "were",
        "are",
        "been",
        "will",
        "his",
        "her",
        "its",
    }
    terms: List[str] = []
    for term in raw_terms:
        if len(term) >= 3 and term not in stop and term not in terms:
            terms.append(term)
    return terms[:40]


def _split_passages(text: str) -> List[str]:
    normalized = re.sub(r"\r\n?", "\n", text or "")
    parts = re.split(r'\n{2,}|(?<=[.!?])\s+(?=[A-Z0-9""])', normalized)
    passages: List[str] = []
    for part in parts:
        clean = re.sub(r"\s+", " ", part).strip()
        if len(clean) >= 40:
            passages.append(clean)
    return passages


def _is_domain_only_text(text: str, url: str) -> bool:
    compact = re.sub(r"\s+", "", (text or "").lower())
    host = (urlparse(url or "").netloc or "").lower().removeprefix("www.")
    return bool(compact) and (
        compact == host or compact == host.replace(".", "") or compact in {"wsj.com", "politico.com"}
    )


def _passage_score(passage: str, terms: List[str], position: int, current_event: bool) -> float:
    lower = passage.lower()
    score = 0.0
    for term in terms:
        if term in lower:
            score += 2.0 if term in _CURRENT_EVENT_TERMS else 1.0
    if any(
        marker in lower
        for marker in (
            "confirmed",
            "approved",
            "planning",
            "fire",
            "fired",
            "ouster",
            "successor",
            "replacement",
            "white house",
            "according to",
        )
    ):
        score += 3.0 if current_event else 1.0
    if any(marker in lower for marker in _NAV_JUNK_PATTERNS):
        score -= 4.0
    words = len(_word_list(passage))
    if words < 12:
        score -= 2.0
    if words > 35:
        score += 0.5
    score -= min(position, 20) * 0.03
    return score


def _select_source_passages(item: SearchItem, query: str, max_chars: int) -> Dict[str, Any]:
    body = (item.extracted_content or item.raw_content or item.content or "").strip()
    description = (item.description or "").strip()
    title = (item.title or "").strip()
    terms = _summary_terms(query, item)
    current_event = any(term in _CURRENT_EVENT_TERMS for term in _word_list(query or ""))
    flags: List[str] = []
    mode = "body_passages"

    body_words = len(_word_list(body))
    if not body or body_words < 30:
        flags.append("too_short_body")
    if _is_domain_only_text(body, item.url):
        flags.append("domain_only_body")
    nav_hits = sum(1 for marker in _NAV_JUNK_PATTERNS if marker in body.lower())
    if nav_hits >= 4:
        flags.append("nav_heavy_body")
    if item.http_status in (401, 402, 403):
        flags.append(f"http_{item.http_status}")

    passages = _split_passages(body)
    scored = [(_passage_score(p, terms, idx, current_event), idx, p) for idx, p in enumerate(passages)]
    scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
    selected: List[str] = []
    used_chars = 0
    for score, _, passage in scored:
        if score <= 0 and selected:
            continue
        if score <= -1:
            continue
        addition = passage if len(passage) <= 1200 else passage[:1200].rstrip()
        if used_chars + len(addition) > max_chars and selected:
            continue
        selected.append(addition)
        used_chars += len(addition)
        if used_chars >= max_chars or len(selected) >= 6:
            break

    overlap_text = " ".join(selected).lower()
    if terms and selected and sum(1 for term in terms[:12] if term in overlap_text) < 2:
        flags.append("low_query_overlap")

    if not selected or "domain_only_body" in flags:
        mode = "snippet_only"
        selected = []
        snippet_parts: List[str] = []
        if title:
            snippet_parts.append(f"Title: {title}")
        if description:
            snippet_parts.append(f"Search snippet: {description}")
        if item.published:
            snippet_parts.append(f"Published: {item.published}")
        selected_text = "\n".join(snippet_parts).strip()
        if selected_text:
            selected = [selected_text]
        else:
            mode = "excluded"
            flags.append("no_usable_text")

    usable = bool(selected) and mode != "excluded"
    if mode == "snippet_only":
        flags.append("snippet_only")
    return {"usable": usable, "mode": mode, "flags": sorted(set(flags)), "passages": selected}


def _normalize_for_summarizer(items: List[SearchItem], max_chars_per_source: int, query: str = "") -> str:
    chunks: List[str] = []
    for i, item in enumerate(items, start=1):
        selection = _select_source_passages(item, query, max_chars=max_chars_per_source)
        item.usable_for_summary = bool(selection["usable"])
        item.summary_input_mode = selection["mode"]
        item.quality_flags = selection["flags"]
        item.selected_passages = selection["passages"]
        if not selection["usable"]:
            continue
        source_block = [
            f"[{i}] {item.title or 'Untitled'}",
            f"URL: {item.url}",
            f"Published: {item.published or 'unknown'}",
            f"Description: {item.description or ''}",
            f"Status: scraped={item.scraped}, chars={item.content_chars}, method={item.extract_method}, input_mode={item.summary_input_mode}, quality_flags={','.join(item.quality_flags or [])}",
            "Selected evidence:",
            _truncate_payload("\n".join(selection["passages"]).strip(), max_chars_per_source),
        ]
        chunks.append("\n".join(source_block))
    return "\n\n".join(chunks)


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    for candidate in [text.strip(), *re.findall(r"```json\n(.*?)```", text, flags=re.S)]:
        try:
            return json.loads(candidate.strip())
        except Exception:
            continue
    return None


def _litellm_api_key_for_model(model: str, provider: Optional[str] = None) -> Optional[str]:
    normalized = (model or "").lower()
    if (provider or "").lower() == "openrouter" or normalized.startswith("openrouter/"):
        return OPENROUTER_API_KEY or LLM_PROVIDER_KEY
    if LLM_PROVIDER_KEY:
        return LLM_PROVIDER_KEY
    if LLM_API_KEY:
        return LLM_API_KEY
    if normalized.startswith("gpt-") or normalized.startswith("openai/"):
        return os.environ.get("OPENAI_API_KEY")
    if "gemini" in normalized or normalized.startswith("gemini/"):
        return os.environ.get("GEMINI_API_KEY")
    if "claude" in normalized or normalized.startswith("anthropic/"):
        return os.environ.get("ANTHROPIC_API_KEY")
    if "bedrock" in normalized:
        return os.environ.get("AWS_ACCESS_KEY_ID")
    if "llama" in normalized and normalized.startswith("ollama/"):
        return os.environ.get("OLLAMA_API_KEY")
    return None


def _litellm_api_base_for_provider(provider: Optional[str]) -> Optional[str]:
    if (provider or "").lower() == "openrouter":
        return OPENROUTER_API_BASE
    return LLM_API_BASE


def _split_provider_model(value: str, default_provider: str) -> Dict[str, str]:
    raw = (value or "").strip()
    lowered = raw.lower()
    if lowered.startswith("openrouter/") or lowered.endswith(":free"):
        return {"provider": "openrouter", "model": raw}
    if ":" in raw:
        provider, model = raw.split(":", 1)
        return {"provider": provider.strip().lower(), "model": model.strip()}
    return {"provider": default_provider, "model": raw}


def _build_llm_candidate_specs(resolved_llm: Dict[str, Any]) -> List[Dict[str, str]]:
    specs = [{"provider": resolved_llm["provider"], "model": resolved_llm["model"]}]
    for fallback in resolved_llm.get("fallback_models") or []:
        spec = _split_provider_model(str(fallback), LLM_PROVIDER)
        if spec not in specs:
            specs.append(spec)
    return specs[: max(1, int(resolved_llm.get("max_attempts") or LLM_MAX_ATTEMPTS))]


def _is_expensive_llm_spec(spec: Dict[str, str]) -> bool:
    provider = (spec.get("provider") or "").lower()
    model = (spec.get("model") or "").lower()
    if provider in ("openai", "anthropic"):
        return True
    return any(marker in model for marker in ("gpt-5", "gpt-4", "claude-3", "o1", "o3", "o4"))


def _extract_llm_response_payload(llm_resp: Any) -> Dict[str, Any]:
    raw = None
    finish_reason = None
    usage_payload = None
    try:
        choice = llm_resp.choices[0]
        raw = choice.message.content
        finish_reason = getattr(choice, "finish_reason", None)
    except Exception:
        pass
    try:
        usage = getattr(llm_resp, "usage", None)
        if hasattr(usage, "model_dump"):
            usage_payload = usage.model_dump()
        elif isinstance(usage, dict):
            usage_payload = usage
    except Exception:
        usage_payload = None
    return {"raw": raw, "finish_reason": finish_reason, "usage": usage_payload}


def _normalize_summary_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(parsed or {})
    normalized["found"] = bool(normalized.get("found", bool(str(normalized.get("answer") or "").strip())))
    normalized["answer"] = str(normalized.get("answer") or "").strip()

    # Map follow_up_questions / open_questions robustly
    fups = normalized.get("follow_up_questions") or normalized.get("open_questions")
    if not isinstance(fups, list):
        fups = [] if fups is None else [str(fups)]
    fups = [str(f).strip() for f in fups if str(f).strip()]
    normalized["follow_up_questions"] = fups
    normalized["open_questions"] = fups

    for key in ("highlights",):
        value = normalized.get(key)
        if not isinstance(value, list):
            value = [] if value is None else [str(value)]
        normalized[key] = [str(v).strip() for v in value if str(v).strip()]
    try:
        normalized["confidence"] = max(0.0, min(1.0, float(normalized.get("confidence", 0.0))))
    except Exception:
        normalized["confidence"] = 0.0
    normalized.setdefault("schema_version", "search-answer-v1")
    return normalized


def _validate_summary_payload(parsed: Any, candidate_items: List[SearchItem]) -> Dict[str, Any]:
    reasons: List[str] = []
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "failure_type": "invalid_json",
            "reasons": ["response was not a JSON object"],
            "payload": None,
        }
    normalized = _normalize_summary_payload(parsed)
    if candidate_items and not normalized["answer"]:
        reasons.append("answer is empty")
    if not isinstance(normalized.get("highlights"), list):
        reasons.append("highlights must be a list")
    if not isinstance(normalized.get("open_questions"), list):
        reasons.append("open_questions must be a list")
    if normalized["answer"].startswith("```"):
        reasons.append("answer contains markdown fence")
    terminal_chars = set([".", "!", "?", '"', "'", ")"])
    if normalized["answer"] and normalized["answer"][-1] not in terminal_chars:
        reasons.append("answer appears incomplete")
    failure_type = "quality_invalid" if reasons else None
    return {"ok": not reasons, "failure_type": failure_type, "reasons": reasons, "payload": normalized}


def _adjust_summary_confidence(
    parsed: Dict[str, Any], attempts: List[Dict[str, Any]], candidate_items: List[SearchItem], repaired: bool
) -> Dict[str, Any]:
    confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
    reasons: List[str] = []
    if len(candidate_items) <= 1:
        confidence -= 0.10
        reasons.append("single_source")
    if repaired:
        confidence -= 0.10
        reasons.append("json_repair_used")
    failed_attempts = len([a for a in attempts if not a.get("success")])
    if failed_attempts:
        confidence -= min(0.20, failed_attempts * 0.05)
        reasons.append("model_retries")
    if not parsed.get("highlights"):
        confidence -= 0.05
        reasons.append("no_highlights")
    parsed["confidence"] = round(max(0.0, min(1.0, confidence)), 2)
    if reasons:
        parsed["confidence_reasons"] = reasons
    return parsed


def _summary_json_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "answer": {"type": "string"},
            "highlights": {"type": "array", "items": {"type": "string"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
            "schema_version": {"type": "string"},
        },
        "required": ["found", "answer", "highlights", "open_questions", "confidence", "schema_version"],
        "additionalProperties": True,
    }


def _resolve_response_format(candidate_provider: str, resolved_llm: Dict[str, Any]) -> Dict[str, Any]:
    mode = (resolved_llm.get("response_format") or "auto").strip().lower()
    if mode in ("none", "off", "disabled"):
        return {}
    if mode == "json_object":
        return {"response_format": {"type": "json_object"}}
    if mode == "json_schema" or (mode == "auto" and candidate_provider == "openrouter"):
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "search_answer",
                    "strict": True,
                    "schema": _summary_json_schema(),
                },
            }
        }
    return {"response_format": {"type": "json_object"}}


async def _call_litellm_model(
    spec: Dict[str, str],
    messages: List[Dict[str, str]],
    resolved_llm: Dict[str, Any],
    attempt_timeout: Optional[float] = None,
) -> Any:
    candidate_provider = spec["provider"]
    candidate_model = spec["model"]
    api_key = _litellm_api_key_for_model(candidate_model, candidate_provider)
    if not api_key:
        raise RuntimeError("missing_api_key")
    kwargs = {
        "model": candidate_model,
        "messages": messages,
        "temperature": resolved_llm["temperature"],
        "max_completion_tokens": resolved_llm["max_completion_tokens"],
        "api_key": api_key,
        "api_base": _litellm_api_base_for_provider(candidate_provider),
        "timeout": resolved_llm["timeout"],
    }
    kwargs.update(_resolve_response_format(candidate_provider, resolved_llm))
    if resolved_llm.get("reasoning_effort") and candidate_provider != "openrouter":
        kwargs["reasoning_effort"] = resolved_llm["reasoning_effort"]
    timeout_s = max(1.0, float(attempt_timeout or resolved_llm["timeout"]))
    return await asyncio.wait_for(asyncio.to_thread(lambda: llm_completion(**kwargs)), timeout=timeout_s)


async def _repair_summary_payload(
    raw: str, spec: Dict[str, str], resolved_llm: Dict[str, Any], attempt_timeout: Optional[float] = None
) -> Dict[str, Any]:
    repair_value = resolved_llm.get("repair_model")
    repair_spec = _split_provider_model(repair_value, spec["provider"]) if repair_value else spec
    repair_messages = [
        {
            "role": "system",
            "content": "You repair malformed model output into strict JSON. Do not add facts. Return only JSON.",
        },
        {
            "role": "user",
            "content": (
                "Convert this attempted search answer into one strict JSON object with fields "
                "found, answer, highlights, follow_up_questions, open_questions, confidence, schema_version. "
                "Use empty strings or arrays when the source text is missing.\n\n"
                f"Attempted output:\n{_truncate_payload(raw or '', 6000)}"
            ),
        },
    ]
    repair_resp = await _call_litellm_model(repair_spec, repair_messages, resolved_llm, attempt_timeout=attempt_timeout)
    payload = _extract_llm_response_payload(repair_resp)
    return {"spec": repair_spec, "response": payload, "parsed": _extract_json_from_text(payload.get("raw") or "")}


def _remaining_llm_timeout(started: float, total_budget: float, per_call_timeout: float) -> float:
    remaining = total_budget - (time.monotonic() - started)
    if remaining <= 0:
        return 0.0
    return max(1.0, min(float(per_call_timeout), remaining))


async def _run_llm_orchestrator(
    messages: List[Dict[str, str]],
    resolved_llm: Dict[str, Any],
    candidate_items: List[SearchItem],
    purpose: str = "search_summary",
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.monotonic()
    attempts: List[Dict[str, Any]] = []
    last_payload: Dict[str, Any] = {}
    repair_limit = int(resolved_llm.get("max_repair_attempts") or 0)
    total_budget = float(resolved_llm.get("max_total_seconds") or LLM_MAX_TOTAL_SECONDS)
    allow_expensive = bool(resolved_llm.get("allow_expensive_fallback"))

    for spec in _build_llm_candidate_specs(resolved_llm):
        if time.monotonic() - started > total_budget:
            attempt = {
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "answer",
                "success": False,
                "failure_type": "budget_exhausted",
            }
            attempts.append(attempt)
            _log_llm_attempt({**attempt, "purpose": purpose, "request_id": request_id})
            break
        if (
            not allow_expensive
            and _is_expensive_llm_spec(spec)
            and spec != {"provider": resolved_llm["provider"], "model": resolved_llm["model"]}
        ):
            attempt = {
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "answer",
                "success": False,
                "failure_type": "expensive_fallback_blocked",
            }
            attempts.append(attempt)
            _log_llm_attempt({**attempt, "purpose": purpose, "request_id": request_id})
            continue
        t0 = time.monotonic()
        try:
            attempt_timeout = _remaining_llm_timeout(started, total_budget, resolved_llm["timeout"])
            if attempt_timeout <= 0:
                raise asyncio.TimeoutError("llm_total_budget_exhausted")
            llm_resp = await _call_litellm_model(spec, messages, resolved_llm, attempt_timeout=attempt_timeout)
            payload = _extract_llm_response_payload(llm_resp)
            last_payload = payload
            parsed = _extract_json_from_text(payload.get("raw") or "")
            validation = _validate_summary_payload(parsed, candidate_items)
            attempt = {
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "answer",
                "success": bool(validation["ok"]),
                "failure_type": validation.get("failure_type"),
                "reasons": validation.get("reasons") or [],
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "finish_reason": payload.get("finish_reason"),
            }
            if payload.get("usage"):
                attempt["usage"] = payload.get("usage")
            attempts.append(attempt)
            _log_llm_attempt({**attempt, "purpose": purpose, "request_id": request_id})
            if validation["ok"]:
                return {
                    "ok": True,
                    "parsed": validation["payload"],
                    "raw": payload.get("raw"),
                    "finish_reason": payload.get("finish_reason"),
                    "usage": payload.get("usage"),
                    "provider": spec["provider"],
                    "model": spec["model"],
                    "attempts": attempts,
                    "repaired": False,
                }
            for repair_index in range(repair_limit):
                rt0 = time.monotonic()
                try:
                    repair_timeout = _remaining_llm_timeout(
                        started, total_budget, resolved_llm.get("repair_timeout") or resolved_llm["timeout"]
                    )
                    if repair_timeout <= 0:
                        raise asyncio.TimeoutError("llm_total_budget_exhausted")
                    repair_result = await _repair_summary_payload(
                        payload.get("raw") or "", spec, resolved_llm, attempt_timeout=repair_timeout
                    )
                    repair_validation = _validate_summary_payload(repair_result.get("parsed"), candidate_items)
                    repair_spec = repair_result.get("spec") or spec
                    repair_payload = repair_result.get("response") or {}
                    repair_attempt = {
                        "provider": repair_spec["provider"],
                        "model": repair_spec["model"],
                        "role": "repair",
                        "success": bool(repair_validation["ok"]),
                        "failure_type": repair_validation.get("failure_type"),
                        "reasons": repair_validation.get("reasons") or [],
                        "latency_ms": int((time.monotonic() - rt0) * 1000),
                        "finish_reason": repair_payload.get("finish_reason"),
                    }
                    attempts.append(repair_attempt)
                    _log_llm_attempt({**repair_attempt, "purpose": purpose, "request_id": request_id})
                    if repair_validation["ok"]:
                        return {
                            "ok": True,
                            "parsed": repair_validation["payload"],
                            "raw": repair_payload.get("raw"),
                            "finish_reason": repair_payload.get("finish_reason"),
                            "usage": repair_payload.get("usage"),
                            "provider": repair_spec["provider"],
                            "model": repair_spec["model"],
                            "attempts": attempts,
                            "repaired": True,
                        }
                except Exception as repair_exc:
                    repair_attempt = {
                        "provider": spec["provider"],
                        "model": spec["model"],
                        "role": "repair",
                        "success": False,
                        "failure_type": type(repair_exc).__name__,
                        "error": str(repair_exc),
                        "latency_ms": int((time.monotonic() - rt0) * 1000),
                    }
                    attempts.append(repair_attempt)
                    _log_llm_attempt({**repair_attempt, "purpose": purpose, "request_id": request_id})
        except Exception as exc:
            attempt = {
                "provider": spec["provider"],
                "model": spec["model"],
                "role": "answer",
                "success": False,
                "failure_type": type(exc).__name__,
                "error": str(exc),
                "latency_ms": int((time.monotonic() - t0) * 1000),
            }
            attempts.append(attempt)
            _log_llm_attempt({**attempt, "purpose": purpose, "request_id": request_id})

    return {
        "ok": False,
        "parsed": {
            "found": bool(candidate_items),
            "answer": "Relevant sources were found, but answer generation failed validation.",
            "highlights": [],
            "open_questions": ["Try a stronger model, fewer sources, or enable a fallback model."],
            "confidence": 0.0,
            "schema_version": "search-answer-v1",
            "llm_failed": True,
        },
        "raw": last_payload.get("raw"),
        "finish_reason": last_payload.get("finish_reason"),
        "usage": last_payload.get("usage"),
        "provider": resolved_llm["provider"],
        "model": resolved_llm["model"],
        "attempts": attempts,
        "repaired": False,
    }


async def _summarize_query(
    query: str,
    items: List[SearchItem],
    max_sources: int,
    max_chars_per_source: int,
    llm_options: Optional[LLMOptions] = None,
    debug: bool = False,
    include_usage: bool = False,
) -> Dict[str, Any]:
    if not SUMMARIZER_ENABLED:
        raise HTTPException(status_code=400, detail="Summarizer is disabled. Set SUMMARIZER_ENABLED=true")
    if not _LITELLM_AVAILABLE:
        raise HTTPException(status_code=500, detail="litellm package not installed")

    candidate_items = [i for i in items if i.url and (i.scraped or i.description or i.title)] if items else []
    candidate_items = candidate_items[:max_sources]

    if not candidate_items:
        return {
            "found": False,
            "answer": "No usable source content was available for this query.",
            "highlights": [],
            "sources": [],
            "excluded_results": [i.url for i in items if i.url and not i.scraped],
            "confidence": 0.00,
            "open_questions": ["Could you provide a higher fetch_top_n or different query?"],
            "raw_model_error": None,
        }

    resolved_llm = _resolve_llm_options(llm_options)
    corpus = _normalize_for_summarizer(candidate_items, max_chars_per_source=max_chars_per_source, query=query)
    candidate_items = [i for i in candidate_items if i.usable_for_summary]
    if not candidate_items or not corpus.strip():
        return {
            "found": False,
            "answer": "No usable source content was available for this query.",
            "highlights": [],
            "sources": [],
            "excluded_results": [i.url for i in items if i.url],
            "confidence": 0.0,
            "open_questions": ["All fetched sources were blocked, too short, or low quality."],
        }
    system_prompt = resolved_llm["system_prompt"]
    user_prompt = (
        f"Query: {query}\n\n"
        f"Sources to use:\n{corpus}\n\n"
        f"Return ONLY a strict JSON object matching the following structure:\n\n"
        f"{{\n"
        f'  "found": true,\n'
        f'  "answer": "A detailed paragraph summarizing the findings based purely on the evidence. Target 700 words.",\n'
        f'  "highlights": ["Key fact 1", "Key fact 2"],\n'
        f'  "follow_up_questions": ["Follow up question 1?", "Follow up question 2?"],\n'
        f'  "confidence": 0.95\n'
        f"}}\n\n"
        f"Include only facts supported by the provided source text. Avoid sensational wording.\n"
        f"Use the selected evidence from every source; do not answer from only the first source when later sources conflict.\n"
        f"Do not include raw source excerpts unless needed for a short highlight."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    llm_result = await _run_llm_orchestrator(messages, resolved_llm, candidate_items, purpose="search_summary")
    parsed = _adjust_summary_confidence(
        llm_result["parsed"], llm_result.get("attempts") or [], candidate_items, bool(llm_result.get("repaired"))
    )
    if llm_result.get("ok"):
        _STATUS["llm_success_total"] += 1
    else:
        _STATUS["llm_error_total"] += 1
        _STATUS["last_error"] = "llm:validation_failed"

    candidate_source_urls = [i.url for i in candidate_items if i.url]
    model_sources = parsed.get("sources")
    if not isinstance(model_sources, list):
        model_sources = []
    normalized_sources = []
    for source in [*model_sources, *candidate_source_urls]:
        if isinstance(source, str):
            url = source.strip()
        elif isinstance(source, dict):
            url = str(source.get("url") or source.get("link") or "").strip()
        else:
            url = ""
        if url and url not in normalized_sources:
            normalized_sources.append(url)
    parsed["sources"] = normalized_sources

    parsed["source_evidence"] = [
        {
            "rank": idx,
            "title": i.title,
            "url": i.url,
            "content_chars": i.content_chars,
            "extract_method": i.extract_method,
            "used_in_summary": True,
        }
        for idx, i in enumerate(candidate_items, start=1)
        if i.url
    ]

    parsed.setdefault("excluded_results", [])
    parsed.setdefault("highlights", [])
    parsed.setdefault("open_questions", [])
    parsed.setdefault("answer", "")
    parsed.setdefault("confidence", 0.0)

    if debug:
        parsed["raw_model_output"] = llm_result.get("raw")
        parsed["llm_attempts"] = llm_result.get("attempts") or []
        parsed["model_finish_reason"] = llm_result.get("finish_reason")
        parsed["llm_options"] = {
            "model": llm_result.get("model"),
            "provider": llm_result.get("provider"),
            "quality_tier": resolved_llm["quality_tier"],
            "fallback_models": resolved_llm.get("fallback_models") or [],
            "max_attempts": resolved_llm.get("max_attempts"),
            "max_repair_attempts": resolved_llm.get("max_repair_attempts"),
            "max_total_seconds": resolved_llm.get("max_total_seconds"),
            "allow_expensive_fallback": resolved_llm.get("allow_expensive_fallback"),
            "repair_model": resolved_llm.get("repair_model"),
            "response_format": resolved_llm.get("response_format"),
            "max_completion_tokens": resolved_llm["max_completion_tokens"],
            "reasoning_effort": resolved_llm["reasoning_effort"],
            "temperature": resolved_llm["temperature"],
            "timeout": resolved_llm["timeout"],
            "repair_timeout": resolved_llm.get("repair_timeout"),
            "request_options_enabled": resolved_llm["request_options_enabled"],
        }
    else:
        parsed.pop("raw_model_output", None)
        parsed.pop("llm_attempts", None)
        parsed.pop("model_finish_reason", None)
        parsed.pop("llm_options", None)

    usage_payload = llm_result.get("usage")
    if usage_payload and (include_usage or debug):
        parsed.setdefault("model_usage", usage_payload)
    elif debug:
        parsed.setdefault("model_usage", usage_payload)
    else:
        parsed.pop("model_usage", None)

    return parsed


def _build_aggregate_search_result(
    *,
    query: str,
    request_id: str,
    web_results: List[SearchItem],
    science_results: List[SearchItem],
    classifier_result: Dict[str, Any],
    use_science: bool,
    summary_payload: Optional[Dict[str, Any]] = None,
) -> TavilySearchResult:
    return build_aggregate_search_result(
        query=query,
        request_id=request_id,
        web_results=web_results,
        science_results=science_results,
        classifier_result=classifier_result,
        use_science=use_science,
        summary_payload=summary_payload,
        content_max_chars=SEARCHBOX_AGGREGATE_CONTENT_MAX_CHARS,
        raw_content_max_chars=SEARCHBOX_AGGREGATE_RAW_CONTENT_MAX_CHARS,
    )


@app.post("/search", response_model=TavilySearchResponse)
async def search(req: SearchRequest, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization, req.api_key)
    _STATUS["requests_total"] += 1
    request_id = str(uuid.uuid4())

    requested_results = req.max_results or req.count or 1
    web_context_count = min(SERPER_MAX_COUNT, max(SEARCHBOX_WEB_CONTEXT_RESULTS, int(requested_results or 1)))
    search_req = SearchRequest(**_model_dict(req))
    search_req.count = web_context_count
    search_req.max_results = web_context_count
    # advanced_search=true is retained as a compatibility force-science override.
    # advanced_search=false/no field no longer disables science detection.
    forced_science = bool(search_req.advanced_search is True)

    # Searchbox always returns one complete research context. Engine-native
    # request knobs are accepted for compatibility, but content extraction and
    # summarization are non-configurable for ACM callers.
    search_req.include_content = True
    search_req.include_raw_content = True
    if search_req.fetch_top_n is None:
        search_req.fetch_top_n = web_context_count

    web_req = SearchRequest(**_model_dict(search_req))
    web_req.advanced_search = False
    web_req.topic = req.topic
    web_req.include_content = True
    web_req.fetch_top_n = web_context_count
    web_req.count = web_context_count
    web_req.max_results = web_context_count
    web_results = await _run_search(web_req)
    classifier_result = (
        {"is_science": True, "confidence": 1.0, "reason": "advanced_search_force_override"}
        if forced_science
        else await _classify_science_query(req.query, req.llm_options, request_id=request_id)
    )
    use_science = bool(classifier_result.get("is_science"))
    if use_science:
        science_req = SearchRequest(**_model_dict(search_req))
        science_req.advanced_search = True
        science_req.topic = "auto"
        science_count = max(ADVANCED_SEARCH_AUTO_MIN_PROVIDERS, 2)
        science_req.count = science_count
        science_req.max_results = science_count
        try:
            advanced_results = await _run_advanced_search(science_req)
        except HTTPException as exc:
            advanced_results = []
            classifier_result = dict(classifier_result or {})
            classifier_result["science_retrieval_error"] = {
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
            _STATUS["last_error"] = {
                "stage": "science_retrieval",
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
    else:
        advanced_results = []
    search_req.advanced_search = use_science
    results = web_results + advanced_results

    summary_payload = await _summarize_query(
        query=req.query,
        items=results,
        max_sources=max(1, len(results)),
        max_chars_per_source=_resolve_max_chars_per_source(req),
        llm_options=req.llm_options,
        debug=_resolve_debug(req),
        include_usage=True,
    )
    answer = summary_payload.get("answer") if isinstance(summary_payload, dict) else None

    scrapes_http = len(
        [
            r
            for r in results
            if r.scraped
            and r.extract_method != "playwright_fallback"
            and r.source
            not in {"arxiv", "agentic_data", "sciencestack", "oanor", "searchapi_scholar", "serpapi_scholar"}
        ]
    )
    scrapes_pw = len([r for r in results if r.scraped and r.extract_method == "playwright_fallback"])
    llm_usage = summary_payload.get("model_usage") if summary_payload else None
    usage_provider = f"web+advanced:{_resolve_advanced_source(search_req)}" if use_science else SEARCH_PROVIDER
    usage = _calculate_searchbox_usage(
        provider=usage_provider,
        search_queries=(1 + (1 if use_science else 0)) if results else 0,
        scrapes_http=scrapes_http,
        scrapes_playwright=scrapes_pw,
        llm_usage=llm_usage,
    )

    aggregate_result = _build_aggregate_search_result(
        query=req.query,
        request_id=request_id,
        web_results=web_results,
        science_results=advanced_results,
        classifier_result=classifier_result,
        use_science=use_science,
        summary_payload=summary_payload,
    )
    tavily_results = [aggregate_result]

    global_images: List[Dict[str, Any]] = []
    if req.include_images:
        for item in results:
            for img in item.images or []:
                if img.url and all(existing["url"] != img.url for existing in global_images):
                    global_images.append({"url": img.url, "description": img.description or ""})

    response_data = TavilySearchResponse(
        query=req.query,
        follow_up_questions=summary_payload.get("follow_up_questions") if summary_payload else None,
        answer=answer,
        images=global_images if req.include_images else None,
        results=tavily_results,
        usage=usage if (req.include_usage or getattr(req, "caller", None) == "aiq") else None,
        _searchbox_usage=usage,
    )

    headers = {
        "X-Searchbox-Usage-Total-Cost": str(usage.get("total_cost_usd", 0.0)),
        "X-Searchbox-Usage-Search-Cost": str(usage.get("search_cost_usd", 0.0)),
        "X-Searchbox-Usage-Scrape-Cost": str(usage.get("scrape_cost_usd", 0.0)),
        "X-Searchbox-Usage-LLM-Cost": str(usage.get("llm_cost_usd", 0.0)),
        "X-Searchbox-Usage-Search-Requests": str(usage.get("search_requests", 0)),
        "X-Searchbox-Usage-Scrape-Fetches": str(usage.get("scrape_fetches", 0)),
    }

    dumped = response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict()
    # Filter out follow_up_questions/images/answer if None to match Tavily behavior
    if dumped.get("follow_up_questions") is None:
        dumped.pop("follow_up_questions", None)
    if dumped.get("answer") is None:
        dumped.pop("answer", None)
    if dumped.get("images") is None:
        dumped.pop("images", None)
    if dumped.get("usage") is None:
        dumped.pop("usage", None)

    return JSONResponse(content=dumped, headers=headers)


@app.get("/search")
async def search_get(
    q: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    include_answer: bool = False,
    include_images: bool = False,
    include_raw_content: bool = False,
    advanced_search: bool = False,
    include_domains: Optional[str] = None,
    exclude_domains: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    inc_domains = [d.strip() for d in include_domains.split(",") if d.strip()] if include_domains else []
    exc_domains = [d.strip() for d in exclude_domains.split(",") if d.strip()] if exclude_domains else []

    req = SearchRequest(
        query=q,
        max_results=max_results,
        count=max_results,
        search_depth=search_depth,
        topic=topic,
        include_answer=include_answer,
        include_images=include_images,
        include_raw_content=include_raw_content,
        advanced_search=advanced_search,
        include_domains=inc_domains,
        exclude_domains=exc_domains,
    )
    return await search(req, authorization=authorization)


@app.get("/search-raw")
async def search_raw(q: str, count: int = SERPER_DEFAULT_COUNT, authorization: Optional[str] = Header(default=None)):
    requested_count = min(max(1, int(count or SERPER_DEFAULT_COUNT)), SERPER_MAX_COUNT)
    req = SearchRequest(
        query=q,
        count=requested_count,
        max_results=requested_count,
        include_content=True,
        include_raw_content=True,
        include_answer=True,
        include_usage=True,
    )
    return await search(req, authorization=authorization)


@app.post("/search-summary", response_model=SearchSummaryResponse)
async def search_summary(req: SearchSummaryRequest, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    _STATUS["requests_total"] += 1
    req_search = SearchRequest(
        query=req.query,
        count=req.count,
        max_results=req.max_results,
        include_content=req.include_content,
        include_raw_content=req.include_raw_content,
        include_answer=req.include_answer,
        fetch_top_n=req.fetch_top_n,
        summarize_top_n=req.summarize_top_n,
        max_chars_per_source=req.max_chars_per_source,
        chunks_per_source=req.chunks_per_source,
        search_depth=req.search_depth,
        topic=req.topic,
        time_range=req.time_range,
        start_date=req.start_date,
        end_date=req.end_date,
        days=req.days,
        include_domains=req.include_domains,
        exclude_domains=req.exclude_domains,
        country=req.country,
        auto_parameters=req.auto_parameters,
        exact_match=req.exact_match,
        include_usage=req.include_usage,
        include_images=req.include_images,
        include_image_descriptions=req.include_image_descriptions,
        include_favicon=req.include_favicon,
        safe_search=req.safe_search,
        debug=req.debug,
        response_mode=req.response_mode,
        llm_options=req.llm_options,
        advanced_search=req.advanced_search,
    )
    classifier_result: Dict[str, Any] = {}
    if req_search.advanced_search:
        web_req = SearchRequest(**_model_dict(req_search))
        web_req.advanced_search = False
        web_req.topic = req.topic
        web_results = await _run_search(web_req)
        science_req = SearchRequest(**_model_dict(req_search))
        science_req.advanced_search = True
        science_req.topic = "auto"
        classifier_result = {"is_science": True, "confidence": 1.0, "reason": "advanced_search_force_override"}
        try:
            results = web_results + await _run_advanced_search(science_req)
        except HTTPException as exc:
            results = web_results
            classifier_result["science_retrieval_error"] = {
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
            _STATUS["last_error"] = {
                "stage": "science_retrieval",
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
    else:
        web_results = await _run_search(req_search)
        classifier_result = await _classify_science_query(req.query, req.llm_options, request_id=str(uuid.uuid4()))
        if classifier_result.get("is_science"):
            science_req = SearchRequest(**_model_dict(req_search))
            science_req.advanced_search = True
            science_req.topic = "auto"
            try:
                results = web_results + await _run_advanced_search(science_req)
            except HTTPException as exc:
                results = web_results
                classifier_result = dict(classifier_result or {})
                classifier_result["science_retrieval_error"] = {
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
                _STATUS["last_error"] = {
                    "stage": "science_retrieval",
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            req_search.advanced_search = True
        else:
            results = web_results
    max_sources = _resolve_summarize_top_n(req)

    if _resolve_include_answer(req, default=True):
        summary_payload = await _summarize_query(
            query=req.query,
            items=results,
            max_sources=max_sources,
            max_chars_per_source=_resolve_max_chars_per_source(req),
            llm_options=req.llm_options,
            debug=_resolve_debug(req),
            include_usage=req.include_usage,
        )
    else:
        summary_payload = {
            "answer": "",
            "highlights": [],
            "sources": [],
            "excluded_results": [],
            "confidence": 0.0,
            "open_questions": [],
            "notes": "include_answer=false",
        }
    if isinstance(classifier_result, dict) and classifier_result.get("science_retrieval_error"):
        summary_payload.setdefault("retrieval_notes", []).append(
            {
                "type": "science_retrieval_error",
                "detail": classifier_result.get("science_retrieval_error"),
            }
        )
    buckets = _split_result_buckets(results, max_sources)
    unused_results = [*buckets["not_summarized"], *buckets["excluded_results"]]
    global_images: List[ImageItem] = []
    if req.include_images:
        for item in results:
            for img in item.images or []:
                if img.url and all(existing.url != img.url for existing in global_images):
                    global_images.append(img)

    return SearchSummaryResponse(
        provider=(
            f"web+advanced:{_resolve_advanced_source(req_search)}" if req_search.advanced_search else SEARCH_PROVIDER
        ),
        request_id=str(uuid.uuid4()),
        query=req.query,
        results_count=len(results),
        included_sources=min(max_sources, len([r for r in results if r.scraped and r.content])),
        unused_results_count=len(unused_results),
        unused_results=unused_results if _resolve_debug(req) else None,
        not_summarized=buckets["not_summarized"] if _resolve_debug(req) else None,
        excluded_results=buckets["excluded_results"] if _resolve_debug(req) else None,
        images=global_images if req.include_images else None,
        summary=summary_payload,
    )
