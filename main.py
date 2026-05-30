import asyncio
import ipaddress
import json
import os
import re
import socket
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import trafilatura

try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    async_playwright = None
    _PLAYWRIGHT_AVAILABLE = False

try:
    from litellm import completion as llm_completion
    _LITELLM_AVAILABLE = True
except Exception:
    llm_completion = None
    _LITELLM_AVAILABLE = False

try:
    from pypdf import PdfReader
    _PDF_AVAILABLE = True
except Exception:
    PdfReader = None
    _PDF_AVAILABLE = False


def _load_env_file() -> None:
    env_file = os.environ.get('SEARCH_MVP_ENV_FILE', '/home/ubuntu/acm-oss/search-stack-playground/.env').strip()
    if not env_file or not os.path.exists(env_file):
        return
    with open(env_file, encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


_load_env_file()


BRAVE_API_URL = 'https://api.search.brave.com/res/v1/web/search'
BRAVE_API_KEY = os.environ.get('BRAVE_API_KEY', '').strip()
BRAVE_DEFAULT_COUNT = int(os.environ.get('BRAVE_DEFAULT_COUNT', '10'))
BRAVE_MAX_COUNT = int(os.environ.get('BRAVE_MAX_COUNT', '20'))

SERPER_API_URL = os.environ.get('SERPER_API_URL', 'https://google.serper.dev/search').strip()
SERPER_API_KEY = os.environ.get('SERPER_API_KEY', '').strip()
SERPER_DEFAULT_COUNT = int(os.environ.get('SERPER_DEFAULT_COUNT', str(BRAVE_DEFAULT_COUNT)))
SERPER_MAX_COUNT = int(os.environ.get('SERPER_MAX_COUNT', '20'))

REQUEST_TIMEOUT = float(os.environ.get('REQUEST_TIMEOUT', '20'))
USER_AGENT = os.environ.get('REQUEST_UA', 'Mozilla/5.0 apicostx-mvp-search/1.0')
SEARCH_API_KEY = os.environ.get('SEARCH_API_KEY', '').strip()
AUTH_DISABLED = os.environ.get('AUTH_DISABLED', 'true').lower() in ('1', 'true', 'yes', 'on')
RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', '120'))
MAX_FETCH_CONCURRENCY = int(os.environ.get('MAX_FETCH_CONCURRENCY', '5'))
MAX_REDIRECTS = int(os.environ.get('MAX_REDIRECTS', '5'))
BLOCK_PRIVATE_FETCH_IPS = os.environ.get('BLOCK_PRIVATE_FETCH_IPS', 'true').lower() in ('1', 'true', 'yes', 'on')

SEARCH_PROVIDER = os.environ.get('SEARCH_PROVIDER', 'serper').strip().lower()
SEARXNG_URL = os.environ.get('SEARXNG_URL', 'http://127.0.0.1:8091').strip()
SEARXNG_RESULTS_LIMIT = int(os.environ.get('SEARXNG_RESULTS_LIMIT', '50'))

ENRICH_USE_PLAYWRIGHT = os.environ.get('ENRICH_USE_PLAYWRIGHT', 'true').lower() in ('1', 'true', 'yes', 'on')
ENRICH_PLAYWRIGHT_TIMEOUT_MS = int(os.environ.get('ENRICH_PLAYWRIGHT_TIMEOUT_MS', '15000'))
ENRICH_PLAYWRIGHT_MAX_CHARS = int(os.environ.get('ENRICH_PLAYWRIGHT_MAX_CHARS', '60000'))
ENRICH_MIN_CONTENT_CHARS = int(os.environ.get('ENRICH_MIN_CONTENT_CHARS', '240'))
ENRICH_DEFAULT_MAX_CHARS = int(os.environ.get('ENRICH_DEFAULT_MAX_CHARS', '160000'))

SUMMARIZER_ENABLED = os.environ.get('SUMMARIZER_ENABLED', 'false').lower() in ('1', 'true', 'yes', 'on')
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai').strip().lower()
LLM_QUALITY_TIER = os.environ.get('LLM_QUALITY_TIER', 'balanced').strip().lower()
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '').strip() or None
OPENROUTER_API_BASE = os.environ.get('OPENROUTER_API_BASE', 'https://openrouter.ai/api/v1').strip()
OPENROUTER_MODEL_CHEAP = os.environ.get('OPENROUTER_MODEL_CHEAP', 'openrouter/openai/gpt-oss-120b:free').strip()
OPENROUTER_MODEL_BALANCED = os.environ.get('OPENROUTER_MODEL_BALANCED', 'openrouter/openai/gpt-oss-120b:free').strip()
OPENROUTER_MODEL_BEST = os.environ.get('OPENROUTER_MODEL_BEST', 'openrouter/anthropic/claude-3.5-sonnet').strip()
LLM_FALLBACK_MODELS = [m.strip() for m in os.environ.get('LLM_FALLBACK_MODELS', 'openrouter/nvidia/nemotron-3-super-120b-a12b:free').split(',') if m.strip()]
LLM_MAX_ATTEMPTS = int(os.environ.get('LLM_MAX_ATTEMPTS', '3'))
LLM_MAX_REPAIR_ATTEMPTS = int(os.environ.get('LLM_MAX_REPAIR_ATTEMPTS', '1'))
LLM_MAX_TOTAL_SECONDS = float(os.environ.get('LLM_MAX_TOTAL_SECONDS', '45'))
LLM_ALLOW_EXPENSIVE_FALLBACK = os.environ.get('LLM_ALLOW_EXPENSIVE_FALLBACK', 'true').lower() in ('1', 'true', 'yes', 'on')
LLM_REPAIR_MODEL = os.environ.get('LLM_REPAIR_MODEL', '').strip() or None
LLM_RESPONSE_FORMAT = os.environ.get('LLM_RESPONSE_FORMAT', 'auto').strip().lower()
LLM_SYSTEM_PROMPT = os.environ.get('LLM_SYSTEM_PROMPT', 'You are a strict evidence-aware research synthesis model. Use only the provided sources. Never invent claims.\nNever use markdown, bullets, fences, or prose. Return ONLY a single valid JSON object and nothing else.\n\nRequired JSON fields at minimum: query, found, message, matched_sources, available_related_info, source_evidence, excluded_results, highlights, open_questions, answer, confidence, schema_version.\nIf source evidence is missing, set found=false and explain the limitation in message/answer. Do not hallucinate. Do not add explanations outside JSON.')
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '30'))
LLM_REPAIR_TIMEOUT = float(os.environ.get('LLM_REPAIR_TIMEOUT', '20'))
LLM_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '4096'))
LLM_MIN_COMPLETION_TOKENS = int(os.environ.get('LLM_MIN_COMPLETION_TOKENS', '256'))
LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS = int(os.environ.get('LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS', '4096'))
LLM_MAX_COMPLETION_TOKENS_CAP = int(os.environ.get('LLM_MAX_COMPLETION_TOKENS_CAP', '8192'))
LLM_TEMPERATURE = float(os.environ.get('LLM_TEMPERATURE', '1'))
LLM_REASONING_EFFORT = os.environ.get('LLM_REASONING_EFFORT', 'minimal').strip() or None
LLM_ALLOW_REQUEST_OPTIONS = os.environ.get('LLM_ALLOW_REQUEST_OPTIONS', 'true').lower() in ('1', 'true', 'yes', 'on')
LLM_FORCE_MODEL = os.environ.get('LLM_FORCE_MODEL', '').strip() or None
LLM_FORCE_MAX_COMPLETION_TOKENS = os.environ.get('LLM_FORCE_MAX_COMPLETION_TOKENS', '').strip() or None
LLM_FORCE_REASONING_EFFORT = os.environ.get('LLM_FORCE_REASONING_EFFORT', '').strip() or None
LLM_FORCE_TEMPERATURE = os.environ.get('LLM_FORCE_TEMPERATURE', '').strip() or None
LLM_FORCE_TIMEOUT = os.environ.get('LLM_FORCE_TIMEOUT', '').strip() or None
LLM_API_BASE = os.environ.get('LLM_API_BASE', '').strip() or None
LLM_API_KEY = os.environ.get('LLM_API_KEY', '').strip() or None
LLM_PROVIDER_KEY = os.environ.get('LLM_PROVIDER_KEY', '').strip() or None


_RATE_BUCKETS: Dict[str, deque] = defaultdict(deque)
_STATUS = {
    'started_at': datetime.utcnow().isoformat() + 'Z',
    'requests_total': 0,
    'provider_success_total': 0,
    'provider_error_total': 0,
    'extract_success_total': 0,
    'extract_error_total': 0,
    'llm_success_total': 0,
    'llm_error_total': 0,
    'last_error': None,
}


class LLMOptions(BaseModel):
    provider: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=128)
    quality_tier: Optional[str] = Field(default=None, max_length=32)
    fallback_models: Optional[List[str]] = Field(default=None)
    max_attempts: Optional[int] = Field(default=None, ge=1, le=10)
    max_repair_attempts: Optional[int] = Field(default=None, ge=0, le=3)
    max_total_seconds: Optional[float] = Field(default=None, ge=1, le=180)
    allow_expensive_fallback: Optional[bool] = Field(default=None)
    repair_model: Optional[str] = Field(default=None, max_length=128)
    response_format: Optional[str] = Field(default=None, max_length=32)
    max_completion_tokens: Optional[int] = Field(default=None, ge=1, le=65536)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=65536)
    reasoning_effort: Optional[str] = Field(default=None, max_length=32)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    timeout: Optional[float] = Field(default=None, ge=1, le=300)
    repair_timeout: Optional[float] = Field(default=None, ge=1, le=120)
    system_prompt: Optional[str] = Field(default=None, max_length=8000)


class ImageItem(BaseModel):
    url: str
    description: Optional[str] = None


class SourceEvidence(BaseModel):
    rank: int
    title: str
    url: str
    content_chars: int = 0
    extract_method: Optional[str] = None
    used_in_summary: bool = True


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    count: int = Field(default=SERPER_DEFAULT_COUNT, ge=1, le=SERPER_MAX_COUNT)
    max_results: Optional[int] = Field(default=None, ge=0, le=SERPER_MAX_COUNT)
    include_content: bool = Field(default=False)
    include_raw_content: Optional[Union[bool, str]] = Field(default=None)
    include_answer: Optional[Union[bool, str]] = Field(default=None)
    fetch_top_n: Optional[int] = Field(default=None, ge=1, le=SERPER_MAX_COUNT)
    summarize_top_n: Optional[int] = Field(default=None, ge=1, le=SERPER_MAX_COUNT)
    max_chars_per_source: Optional[int] = Field(default=None, ge=500, le=16000)
    chunks_per_source: Optional[int] = Field(default=None, ge=1, le=5)
    search_depth: Optional[str] = Field(default=None, max_length=32)
    topic: Optional[str] = Field(default=None, max_length=32)
    time_range: Optional[str] = Field(default=None, max_length=16)
    start_date: Optional[str] = Field(default=None, max_length=32)
    end_date: Optional[str] = Field(default=None, max_length=32)
    days: Optional[int] = Field(default=None, ge=1, le=3650)
    include_domains: List[str] = Field(default_factory=list)
    exclude_domains: List[str] = Field(default_factory=list)
    country: Optional[str] = Field(default=None, max_length=64)
    auto_parameters: bool = Field(default=False)
    exact_match: bool = Field(default=False)
    include_usage: bool = Field(default=False)
    include_images: bool = Field(default=False)
    include_image_descriptions: bool = Field(default=False)
    include_favicon: bool = Field(default=False)
    safe_search: bool = Field(default=False)
    debug: bool = Field(default=False)
    response_mode: Optional[str] = Field(default=None, max_length=32)
    timeout: Optional[float] = Field(default=None, ge=1, le=120)
    llm_options: Optional[LLMOptions] = Field(default=None)


class SearchItem(BaseModel):
    rank: int
    title: str
    url: str
    description: Optional[str] = None
    published: Optional[str] = None
    language: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None
    engine: Optional[str] = None
    scraped: bool = False
    content_chars: int = 0
    fetch_ms: Optional[int] = None
    content: Optional[str] = None
    raw_content: Optional[str] = None
    extracted_content: Optional[str] = Field(default=None, exclude=True)
    usable_for_summary: Optional[bool] = None
    summary_input_mode: Optional[str] = None
    quality_flags: Optional[List[str]] = None
    selected_passages: Optional[List[str]] = None
    error: Optional[str] = None
    extract_method: Optional[str] = None
    fetch_status: Optional[str] = None
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    failure_reason: Optional[str] = None
    canonical_url: Optional[str] = None
    favicon: Optional[str] = None
    images: Optional[List[ImageItem]] = None
    provider_rank: Optional[int] = None


class SearchResponse(BaseModel):
    provider: str
    query: str
    results_count: int
    request_id: str
    results: List[SearchItem]
    images: Optional[List[ImageItem]] = None
    answer: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    unused_results: Optional[List[SearchItem]] = None
    not_summarized: Optional[List[SearchItem]] = None
    excluded_results: Optional[List[SearchItem]] = None
    response_time: Optional[float] = None
    auto_parameters: Optional[Dict[str, Any]] = None


class SearchSummaryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    count: int = Field(default=SERPER_DEFAULT_COUNT, ge=1, le=SERPER_MAX_COUNT)
    max_results: Optional[int] = Field(default=None, ge=0, le=SERPER_MAX_COUNT)
    include_content: bool = Field(default=True)
    include_raw_content: Optional[Union[bool, str]] = Field(default=None)
    include_answer: Optional[Union[bool, str]] = Field(default=True)
    fetch_top_n: int = Field(default=5, ge=1, le=SERPER_MAX_COUNT)
    summarize_top_n: int = Field(default=5, ge=1, le=SERPER_MAX_COUNT)
    max_chars_per_source: Optional[int] = Field(default=None, ge=500, le=16000)
    chunks_per_source: Optional[int] = Field(default=None, ge=1, le=5)
    search_depth: Optional[str] = Field(default=None, max_length=32)
    topic: Optional[str] = Field(default=None, max_length=32)
    time_range: Optional[str] = Field(default=None, max_length=16)
    start_date: Optional[str] = Field(default=None, max_length=32)
    end_date: Optional[str] = Field(default=None, max_length=32)
    days: Optional[int] = Field(default=None, ge=1, le=3650)
    include_domains: List[str] = Field(default_factory=list)
    exclude_domains: List[str] = Field(default_factory=list)
    country: Optional[str] = Field(default=None, max_length=64)
    auto_parameters: bool = Field(default=False)
    exact_match: bool = Field(default=False)
    include_usage: bool = Field(default=False)
    include_images: bool = Field(default=False)
    include_image_descriptions: bool = Field(default=False)
    include_favicon: bool = Field(default=False)
    safe_search: bool = Field(default=False)
    debug: bool = Field(default=False)
    response_mode: Optional[str] = Field(default=None, max_length=32)
    timeout: Optional[float] = Field(default=None, ge=1, le=120)
    llm_options: Optional[LLMOptions] = Field(default=None)


class SearchSummaryResponse(BaseModel):
    provider: str
    request_id: str
    query: str
    results_count: int
    included_sources: int
    unused_results_count: int = 0
    unused_results: Optional[List[SearchItem]] = None
    not_summarized: Optional[List[SearchItem]] = None
    excluded_results: Optional[List[SearchItem]] = None
    images: Optional[List[ImageItem]] = None
    summary: Dict[str, Any]


app = FastAPI(title='APICOSTX OSS Search MVP', version='0.2.0')


@app.get('/health')
def health() -> Dict[str, Any]:
    return {
        'status': 'ok',
        'provider': SEARCH_PROVIDER,
        'has_serper_key': bool(SERPER_API_KEY),
        'has_brave_key': bool(BRAVE_API_KEY),
        'has_searxng_base': bool(SEARXNG_URL),
        'playwright_available': _PLAYWRIGHT_AVAILABLE,
        'playwright_enabled': ENRICH_USE_PLAYWRIGHT,
        'summarizer_enabled': SUMMARIZER_ENABLED,
        'litellm_available': _LITELLM_AVAILABLE,
        'default_model': LLM_MODEL,
    }


@app.get('/config')
def config() -> Dict[str, Any]:
    return {
        'provider': {
            'search_provider': SEARCH_PROVIDER,
            'brave_default_count': BRAVE_DEFAULT_COUNT,
            'brave_max_count': BRAVE_MAX_COUNT,
            'serper_default_count': SERPER_DEFAULT_COUNT,
            'serper_max_count': SERPER_MAX_COUNT,
            'searxng_results_limit': SEARXNG_RESULTS_LIMIT,
            'request_timeout': REQUEST_TIMEOUT,
        },
        'enrichment': {
            'playwright_enabled': ENRICH_USE_PLAYWRIGHT,
            'playwright_available': _PLAYWRIGHT_AVAILABLE,
            'playwright_timeout_ms': ENRICH_PLAYWRIGHT_TIMEOUT_MS,
            'min_content_chars': ENRICH_MIN_CONTENT_CHARS,
            'default_max_chars': ENRICH_DEFAULT_MAX_CHARS,
        },
        'summarizer': {
            'enabled': SUMMARIZER_ENABLED,
            'litellm_available': _LITELLM_AVAILABLE,
            'default_provider': LLM_PROVIDER,
            'quality_tier_default': LLM_QUALITY_TIER,
            'default_model': LLM_MODEL,
            'openrouter_key_configured': bool(OPENROUTER_API_KEY),
            'openrouter_model_cheap': OPENROUTER_MODEL_CHEAP,
            'openrouter_model_balanced': OPENROUTER_MODEL_BALANCED,
            'openrouter_model_best': OPENROUTER_MODEL_BEST,
            'fallback_models_configured': len(LLM_FALLBACK_MODELS),
            'max_attempts_default': LLM_MAX_ATTEMPTS,
            'max_repair_attempts_default': LLM_MAX_REPAIR_ATTEMPTS,
            'max_total_seconds_default': LLM_MAX_TOTAL_SECONDS,
            'allow_expensive_fallback_default': LLM_ALLOW_EXPENSIVE_FALLBACK,
            'repair_model_configured': bool(LLM_REPAIR_MODEL),
            'response_format_default': LLM_RESPONSE_FORMAT,
            'repair_timeout_default': LLM_REPAIR_TIMEOUT,
            'request_options_enabled': LLM_ALLOW_REQUEST_OPTIONS,
            'max_tokens_default': LLM_MAX_TOKENS,
            'min_completion_tokens': LLM_MIN_COMPLETION_TOKENS,
            'reasoning_model_min_completion_tokens': LLM_REASONING_MODEL_MIN_COMPLETION_TOKENS,
            'max_completion_tokens_cap': LLM_MAX_COMPLETION_TOKENS_CAP,
            'temperature_default': LLM_TEMPERATURE,
            'reasoning_effort_default': LLM_REASONING_EFFORT,
            'force_model_active': bool(LLM_FORCE_MODEL),
            'force_max_completion_tokens_active': bool(LLM_FORCE_MAX_COMPLETION_TOKENS),
            'force_reasoning_effort_active': bool(LLM_FORCE_REASONING_EFFORT),
            'force_temperature_active': bool(LLM_FORCE_TEMPERATURE),
            'force_timeout_active': bool(LLM_FORCE_TIMEOUT),
        },
        'security': {
            'auth_disabled': AUTH_DISABLED,
            'search_api_key_configured': bool(SEARCH_API_KEY),
            'rate_limit_per_minute': RATE_LIMIT_PER_MINUTE,
            'block_private_fetch_ips': BLOCK_PRIVATE_FETCH_IPS,
            'max_fetch_concurrency': MAX_FETCH_CONCURRENCY,
            'max_redirects': MAX_REDIRECTS,
        },
    }


@app.get('/status')
def status() -> Dict[str, Any]:
    return dict(_STATUS)


def _auth_key_from_header(authorization: Optional[str]) -> str:
    if AUTH_DISABLED:
        return 'anonymous'
    if not SEARCH_API_KEY:
        raise HTTPException(status_code=503, detail='SEARCH_API_KEY is not configured')
    prefix = 'Bearer '
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail='Missing bearer token')
    token = authorization[len(prefix):].strip()
    if token != SEARCH_API_KEY:
        raise HTTPException(status_code=403, detail='Invalid bearer token')
    return 'authorized'


def _check_rate_limit(bucket_key: str) -> None:
    if RATE_LIMIT_PER_MINUTE <= 0:
        return
    now = time.time()
    bucket = _RATE_BUCKETS[bucket_key]
    while bucket and bucket[0] <= now - 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail='Rate limit exceeded')
    bucket.append(now)


def _authorize(authorization: Optional[str]) -> None:
    _check_rate_limit(_auth_key_from_header(authorization))


def _shorten(text: str, max_chars: int) -> str:
    return (text or '')[:max_chars]


def _boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ('', '0', 'false', 'no', 'off', 'none')
    return bool(value)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _model_dict(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump() if hasattr(model, 'model_dump') else model.dict()


def _resolve_max_results(req: Any) -> int:
    value = getattr(req, 'max_results', None)
    if value is None:
        value = getattr(req, 'count', SERPER_DEFAULT_COUNT)
    return _bounded_int(value, SERPER_DEFAULT_COUNT, 0, SERPER_MAX_COUNT)


def _resolve_include_content(req: Any, default: bool = False) -> bool:
    mode = (getattr(req, 'response_mode', None) or '').strip().lower()
    if mode in ('search_with_content', 'search_with_answer', 'answer', 'debug'):
        return True
    if bool(getattr(req, 'include_content', default)):
        return True
    include_raw = getattr(req, 'include_raw_content', None)
    if include_raw is not None:
        return _boolish(include_raw, default=False)
    return False


def _resolve_include_answer(req: Any, default: bool = False) -> bool:
    mode = (getattr(req, 'response_mode', None) or '').strip().lower()
    if mode in ('search_only', 'search_with_content'):
        return False
    if mode in ('search_with_answer', 'answer', 'debug'):
        return True
    return _boolish(getattr(req, 'include_answer', None), default=default)


def _resolve_debug(req: Any) -> bool:
    mode = (getattr(req, 'response_mode', None) or '').strip().lower()
    return bool(getattr(req, 'debug', False) or mode == 'debug')


def _resolve_unused_results(items: List[SearchItem], max_sources: int) -> List[SearchItem]:
    usable_seen = 0
    unused: List[SearchItem] = []
    for item in items:
        if item.url and item.scraped and item.content and usable_seen < max_sources:
            usable_seen += 1
            continue
        unused.append(item)
    return unused


def _split_result_buckets(items: List[SearchItem], max_sources: int) -> Dict[str, List[SearchItem]]:
    used = 0
    not_summarized: List[SearchItem] = []
    excluded: List[SearchItem] = []
    for item in items:
        usable = bool(item.url and item.scraped and item.content)
        if usable and used < max_sources:
            used += 1
        elif usable:
            not_summarized.append(item)
        else:
            excluded.append(item)
    return {'not_summarized': not_summarized, 'excluded_results': excluded}


def _normalize_search_query(req: Any) -> str:
    query = (getattr(req, 'query', '') or '').strip()
    if getattr(req, 'exact_match', False) and query and not (query.startswith('"') and query.endswith('"')):
        return f'"{query}"'
    return query


def _resolve_country(req: Any) -> Optional[str]:
    country = (getattr(req, 'country', None) or '').strip()
    if not country:
        return None
    return country[:2].upper()


def _resolve_brave_safesearch(req: Any) -> str:
    return 'strict' if getattr(req, 'safe_search', False) else 'moderate'


def _resolve_searxng_safesearch(req: Any) -> int:
    return 1 if getattr(req, 'safe_search', False) else 0


def _resolve_freshness(req: Any) -> Optional[str]:
    start_date = (getattr(req, 'start_date', None) or '').strip()
    end_date = (getattr(req, 'end_date', None) or '').strip()
    if start_date and end_date:
        return f'{start_date}to{end_date}'

    value = (getattr(req, 'time_range', None) or '').strip().lower()
    mapping = {
        'day': 'pd',
        'd': 'pd',
        '24h': 'pd',
        'week': 'pw',
        'w': 'pw',
        '7d': 'pw',
        'month': 'pm',
        'm': 'pm',
        '31d': 'pm',
        'year': 'py',
        'y': 'py',
        '365d': 'py',
    }
    return mapping.get(value)


def _resolve_searxng_time_range(req: Any) -> Optional[str]:
    value = (getattr(req, 'time_range', None) or '').strip().lower()
    mapping = {
        'day': 'day',
        'd': 'day',
        '24h': 'day',
        'month': 'month',
        'm': 'month',
        '31d': 'month',
        'year': 'year',
        'y': 'year',
        '365d': 'year',
    }
    return mapping.get(value)


def _resolve_serper_tbs(req: Any) -> Optional[str]:
    days = getattr(req, 'days', None)
    if days:
        return f'qdr:d{int(days)}'
    start_date = (getattr(req, 'start_date', None) or '').strip()
    end_date = (getattr(req, 'end_date', None) or '').strip()
    if start_date and end_date:
        return f'cdr:1,cd_min:{start_date},cd_max:{end_date}'

    value = (getattr(req, 'time_range', None) or '').strip().lower()
    mapping = {
        'day': 'qdr:d',
        'd': 'qdr:d',
        '24h': 'qdr:d',
        'week': 'qdr:w',
        'w': 'qdr:w',
        '7d': 'qdr:w',
        'month': 'qdr:m',
        'm': 'qdr:m',
        '31d': 'qdr:m',
        'year': 'qdr:y',
        'y': 'qdr:y',
        '365d': 'qdr:y',
    }
    return mapping.get(value)


def _resolve_search_depth(req: Any) -> str:
    depth = (getattr(req, 'search_depth', None) or 'basic').strip().lower()
    return depth if depth else 'basic'


def _resolve_summarize_top_n(req: Any, default: int = 5) -> int:
    return _bounded_int(getattr(req, 'summarize_top_n', None), default, 1, SERPER_MAX_COUNT)


def _resolve_max_chars_per_source(req: Any, default: int = 4000) -> int:
    explicit = getattr(req, 'max_chars_per_source', None)
    if explicit is not None:
        return _bounded_int(explicit, default, 500, 16000)
    chunks = getattr(req, 'chunks_per_source', None)
    if chunks is not None:
        return _bounded_int(chunks, 3, 1, 5) * 500
    return default


def _resolve_timeout(req: Any) -> float:
    return float(getattr(req, 'timeout', None) or REQUEST_TIMEOUT)


def _favicon_for_url(url: str) -> Optional[str]:
    host = (urlparse(url or '').netloc or '').lower()
    if not host:
        return None
    return f'https://www.google.com/s2/favicons?domain={host}&sz=64'


def _chunk_text(text: str, chunks_per_source: Optional[int]) -> str:
    if not text:
        return ''
    count = _bounded_int(chunks_per_source, 3, 1, 5) if chunks_per_source else 1
    chunks = []
    cleaned = re.sub(r'\s+', ' ', text).strip()
    for idx in range(count):
        start = idx * 500
        chunk = cleaned[start:start + 500].strip()
        if not chunk:
            break
        chunks.append(f'<chunk {idx + 1}> {chunk}')
    return ' [...] '.join(chunks)


def _score_item(item: SearchItem, query: str) -> float:
    score = max(0.0, 1.0 - ((max(item.rank, 1) - 1) * 0.05))
    haystack = f'{item.title} {item.description} {item.content or ""}'.lower()
    terms = [t for t in re.findall(r'[a-z0-9]+', query.lower()) if len(t) > 2]
    if terms:
        score += min(0.3, sum(1 for t in terms if t in haystack) / len(terms) * 0.3)
    if item.scraped:
        score += 0.2
    if item.content_chars:
        score += min(0.2, item.content_chars / 10000 * 0.2)
    if item.published:
        score += 0.05
    return round(min(score, 1.0), 4)


def _is_private_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved


def _validate_fetch_url(url: str) -> None:
    parsed = urlparse(url or '')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise HTTPException(status_code=400, detail=f'Unsafe URL scheme or host: {url}')
    if not BLOCK_PRIVATE_FETCH_IPS:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f'Could not resolve URL host: {parsed.hostname}') from exc
    for info in infos:
        if _is_private_ip(info[4][0]):
            raise HTTPException(status_code=400, detail=f'Blocked private or unsafe fetch host: {parsed.hostname}')


def _domain_allowed(url: str, include_domains: List[str], exclude_domains: List[str]) -> bool:
    host = (urlparse(url or '').netloc or '').lower()
    host = host[4:] if host.startswith('www.') else host
    includes = [d.lower().removeprefix('www.') for d in include_domains or [] if d]
    excludes = [d.lower().removeprefix('www.') for d in exclude_domains or [] if d]
    if includes and not any(host == d or host.endswith('.' + d) for d in includes):
        return False
    if excludes and any(host == d or host.endswith('.' + d) for d in excludes):
        return False
    return True


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
    provider = (request_options.provider if request_options and request_options.provider else LLM_PROVIDER).strip().lower()
    quality_tier = (request_options.quality_tier if request_options and request_options.quality_tier else LLM_QUALITY_TIER).strip().lower()
    requested_tokens = None
    if request_options is not None:
        requested_tokens = request_options.max_completion_tokens or request_options.max_tokens
    forced_tokens = _forced_int(LLM_FORCE_MAX_COMPLETION_TOKENS)
    tier_model = None
    if provider == 'openrouter':
        tier_model = {
            'cheap': OPENROUTER_MODEL_CHEAP,
            'balanced': OPENROUTER_MODEL_BALANCED,
            'best': OPENROUTER_MODEL_BEST,
        }.get(quality_tier, OPENROUTER_MODEL_BALANCED)
    model = LLM_FORCE_MODEL or (request_options.model if request_options and request_options.model else (tier_model or LLM_MODEL))
    reasoning_effort = LLM_FORCE_REASONING_EFFORT or (request_options.reasoning_effort if request_options and request_options.reasoning_effort is not None else LLM_REASONING_EFFORT)
    token_floor = LLM_MIN_COMPLETION_TOKENS
    if (model or '').lower().startswith(('gpt-5', 'openai/gpt-5', 'o1', 'o3', 'o4')) and reasoning_effort:
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
    temperature = forced_temperature if forced_temperature is not None else (
        requested_temperature if requested_temperature is not None else LLM_TEMPERATURE
    )

    requested_timeout = request_options.timeout if request_options is not None else None
    forced_timeout = _forced_float(LLM_FORCE_TIMEOUT)
    timeout = forced_timeout if forced_timeout is not None else (requested_timeout or LLM_TIMEOUT)

    return {
        'provider': provider,
        'model': model,
        'fallback_models': (request_options.fallback_models if request_options and request_options.fallback_models is not None else LLM_FALLBACK_MODELS),
        'quality_tier': quality_tier,
        'max_attempts': request_options.max_attempts if request_options and request_options.max_attempts is not None else LLM_MAX_ATTEMPTS,
        'max_repair_attempts': request_options.max_repair_attempts if request_options and request_options.max_repair_attempts is not None else LLM_MAX_REPAIR_ATTEMPTS,
        'max_total_seconds': request_options.max_total_seconds if request_options and request_options.max_total_seconds is not None else LLM_MAX_TOTAL_SECONDS,
        'allow_expensive_fallback': request_options.allow_expensive_fallback if request_options and request_options.allow_expensive_fallback is not None else LLM_ALLOW_EXPENSIVE_FALLBACK,
        'repair_model': request_options.repair_model if request_options and request_options.repair_model is not None else LLM_REPAIR_MODEL,
        'response_format': (request_options.response_format if request_options and request_options.response_format is not None else LLM_RESPONSE_FORMAT).strip().lower(),
        'max_completion_tokens': max_completion_tokens,
        'reasoning_effort': reasoning_effort,
        'temperature': temperature,
        'timeout': timeout,
        'repair_timeout': request_options.repair_timeout if request_options and request_options.repair_timeout is not None else LLM_REPAIR_TIMEOUT,
        'system_prompt': request_options.system_prompt if request_options and request_options.system_prompt is not None else LLM_SYSTEM_PROMPT,
        'request_options_enabled': LLM_ALLOW_REQUEST_OPTIONS,
    }


def _truncate_payload(text: str, max_chars: int) -> str:
    if not text:
        return ''
    return text if len(text) <= max_chars else text[:max_chars].rstrip()


def _html_to_text(html: str) -> str:
    if not html:
        return ''
    soup = BeautifulSoup(html, 'lxml')
    for tag in soup(['script', 'style', 'noscript', 'svg', 'canvas', 'iframe']):
        tag.decompose()
    text = soup.get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', text).strip()


def _pdf_to_text(data: bytes) -> str:
    if not _PDF_AVAILABLE or PdfReader is None:
        return ''
    try:
        import io
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages[:10]:
            parts.append(page.extract_text() or '')
        return re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    except Exception:
        return ''


def _searxng_query_url() -> str:
    return SEARXNG_URL.rstrip('/') + '/search'


def _parse_brave_results(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    raw_results = data.get('web', {}).get('results', []) if isinstance(data, dict) else []
    parsed: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_results or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(parsed) >= limit:
            break
        parsed.append({
            'rank': idx,
            'title': (item.get('title') or '').strip(),
            'url': (item.get('url') or '').strip(),
            'description': (item.get('description') or '').strip()[:3000],
            'published': item.get('published') or None,
            'language': item.get('language') or None,
            'score': item.get('score') if isinstance(item.get('score'), (int, float)) else None,
            'source': 'brave',
            'engine': 'brave',
        })
    return parsed


def _parse_serper_results(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    raw_results = data.get('organic', []) if isinstance(data, dict) else []
    parsed: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_results or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(parsed) >= limit:
            break
        parsed.append({
            'rank': int(item.get('position') or idx),
            'title': (item.get('title') or '').strip(),
            'url': (item.get('link') or '').strip(),
            'description': (item.get('snippet') or '').strip()[:3000],
            'published': item.get('date') or None,
            'language': None,
            'score': None,
            'source': 'serper',
            'engine': 'google',
            'images': [
                {'url': img.get('imageUrl') or img.get('thumbnailUrl') or img.get('link') or '', 'description': img.get('title') or img.get('source')}
                for img in (item.get('images') or [])
                if isinstance(img, dict) and (img.get('imageUrl') or img.get('thumbnailUrl') or img.get('link'))
            ],
        })
    return parsed


def _parse_searxng_results(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    raw_results = data.get('results', []) if isinstance(data, dict) else []
    parsed: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_results or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(parsed) >= limit:
            break
        parsed.append({
            'rank': idx,
            'title': (item.get('title') or '').strip(),
            'url': (item.get('url') or '').strip(),
            'description': (item.get('content') or '').strip()[:3000],
            'published': item.get('publishedDate') or item.get('published') or None,
            'language': item.get('language') or None,
            'score': item.get('score') if isinstance(item.get('score'), (int, float)) else None,
            'source': 'searxng',
            'engine': item.get('engine') if isinstance(item.get('engine'), str) else None,
        })
    return parsed


async def _search_brave(req: SearchRequest, count: int) -> Dict[str, Any]:
    if not BRAVE_API_KEY:
        raise HTTPException(status_code=500, detail='BRAVE_API_KEY is not configured')

    payload: Dict[str, Any] = {
        'count': count,
        'q': _normalize_search_query(req),
        'search_lang': 'en',
        'safesearch': _resolve_brave_safesearch(req),
        'operators': True,
    }
    country = _resolve_country(req)
    if country:
        payload['country'] = country
    freshness = _resolve_freshness(req)
    if freshness:
        payload['freshness'] = freshness
    if _resolve_search_depth(req) == 'advanced':
        payload['extra_snippets'] = True
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': BRAVE_API_KEY,
        'User-Agent': USER_AGENT,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(BRAVE_API_URL, params=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _search_serper(req: SearchRequest, count: int) -> Dict[str, Any]:
    if not SERPER_API_KEY:
        raise HTTPException(status_code=500, detail='SERPER_API_KEY is not configured')

    if SERPER_API_KEY.lower() == 'mock':
        return {
            'organic': [
                {
                    'title': 'Mock Result 1',
                    'link': 'https://example.com/mock1',
                    'snippet': 'This is a mock search result snippet for testing the native searchbox pipeline.',
                }
            ]
        }

    endpoint = SERPER_API_URL
    if (getattr(req, 'topic', None) or '').strip().lower() == 'news':
        endpoint = SERPER_API_URL.rsplit('/', 1)[0] + '/news'
    payload: Dict[str, Any] = {
        'q': _normalize_search_query(req),
        'num': count,
        'hl': 'en',
    }
    country = _resolve_country(req)
    if country:
        payload['gl'] = country.lower()
    tbs = _resolve_serper_tbs(req)
    if tbs:
        payload['tbs'] = tbs
    if getattr(req, 'safe_search', False):
        payload['safe'] = 'active'

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-API-KEY': SERPER_API_KEY,
        'User-Agent': USER_AGENT,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        _STATUS['provider_success_total'] += 1
        return resp.json()


async def _search_searxng(req: SearchRequest, count: int) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        'q': _normalize_search_query(req),
        'format': 'json',
        'language': 'en',
        'safesearch': _resolve_searxng_safesearch(req),
        'categories': 'general',
    }
    time_range = _resolve_searxng_time_range(req)
    if time_range:
        params['time_range'] = time_range
    headers = {'User-Agent': USER_AGENT}
    async with httpx.AsyncClient(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(_searxng_query_url(), params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    parsed = _parse_searxng_results(data, count)
    return {'web': {'results': parsed}}


async def _search_provider(req: SearchRequest, count: int) -> List[Dict[str, Any]]:
    try:
        if SEARCH_PROVIDER == 'serper':
            data = await _search_serper(req, count)
            return _parse_serper_results(data, count)
        if SEARCH_PROVIDER == 'brave':
            data = await _search_brave(req, count)
            _STATUS['provider_success_total'] += 1
            return _parse_brave_results(data, count)
        if SEARCH_PROVIDER == 'searxng':
            data = await _search_searxng(req, count)
            _STATUS['provider_success_total'] += 1
            return data.get('web', {}).get('results', [])
        raise HTTPException(status_code=400, detail=f'Unknown SEARCH_PROVIDER {SEARCH_PROVIDER!r}')
    except HTTPException:
        _STATUS['provider_error_total'] += 1
        raise
    except Exception as exc:
        _STATUS['provider_error_total'] += 1
        _STATUS['last_error'] = f'provider:{type(exc).__name__}: {exc}'
        raise HTTPException(status_code=502, detail=f'Provider search failed: {type(exc).__name__}: {exc}') from exc


async def _extract_with_playwright(url: str) -> Dict[str, Any]:
    if async_playwright is None:
        return {
            'method': 'playwright_unavailable',
            'content': None,
            'error': 'playwright_import_missing',
        }

    t0 = datetime.now()
    html = None
    page = None
    browser = None
    context = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded', timeout=ENRICH_PLAYWRIGHT_TIMEOUT_MS)
            try:
                await page.wait_for_load_state('networkidle', timeout=3000)
            except Exception:
                pass
            html = await page.content()
    except Exception as exc:
        return {
            'method': 'playwright_fallback',
            'content': None,
            'error': f'{type(exc).__name__}: {exc}',
            'fetch_ms': int((datetime.now() - t0).total_seconds() * 1000),
        }
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

    text = _html_to_text(html)
    text = _shorten(text, ENRICH_PLAYWRIGHT_MAX_CHARS)

    return {
        'method': 'playwright_fallback',
        'content': text if text else None,
        'error': None if text else 'playwright_content_empty',
        'fetch_ms': int((datetime.now() - t0).total_seconds() * 1000),
    }


async def _extract_content(url: str, timeout_s: float) -> Dict[str, Any]:
    _validate_fetch_url(url)
    headers = {'User-Agent': USER_AGENT}
    t0 = datetime.now()

    html = None
    body = b''
    fetch_error = None
    method = 'failed'
    fetch_ms = 0
    http_status = None
    content_type = None
    canonical_url = url

    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout_s) as client:
        current_url = url
        for attempt in range(2):
            try:
                for _ in range(MAX_REDIRECTS + 1):
                    _validate_fetch_url(current_url)
                    response = await client.get(current_url, headers=headers)
                    http_status = response.status_code
                    canonical_url = str(response.url)
                    content_type = response.headers.get('content-type')
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get('location'):
                        current_url = urljoin(current_url, response.headers['location'])
                        continue
                    response.raise_for_status()
                    body = response.content
                    html = response.text if 'text' in (content_type or '') or 'html' in (content_type or '') else None
                    fetch_ms = int((datetime.now() - t0).total_seconds() * 1000)
                    break
                break
            except Exception as exc:
                fetch_ms = int((datetime.now() - t0).total_seconds() * 1000)
                fetch_error = f'{type(exc).__name__}: {exc}'
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue

    text = None
    if (content_type or '').lower().split(';', 1)[0] == 'application/pdf' or canonical_url.lower().endswith('.pdf'):
        text = _pdf_to_text(body)
        method = 'pdf_pypdf' if text else 'pdf_unavailable_or_empty'

    if not text and html:
        text = trafilatura.extract(html)
        method = 'trafilatura' if text else 'trafilatura_empty'

    if not text:
        text = _html_to_text(html)
        method = 'bs4_fallback' if text else 'bs4_fallback'

    if (not text or len(text) < ENRICH_MIN_CONTENT_CHARS) and ENRICH_USE_PLAYWRIGHT and _PLAYWRIGHT_AVAILABLE:
        playwright_result = await _extract_with_playwright(url)
        pw_method = playwright_result.get('method')
        if playwright_result.get('content') and len(playwright_result['content']) > len(text or ''):
            text = playwright_result.get('content')
            method = pw_method
        if playwright_result.get('error') and (not text):
            fetch_error = (fetch_error + ' | ' if fetch_error else '') + playwright_result.get('error')
        elif not fetch_error:
            fetch_error = None
        fetch_ms = max(fetch_ms, int(playwright_result.get('fetch_ms') or 0))

    text = _shorten((text or '').strip(), ENRICH_DEFAULT_MAX_CHARS)

    return {
        'content': text if text else None,
        'scraped': bool(text),
        'content_chars': len(text or ''),
        'fetch_ms': int(fetch_ms),
        'error': None if text else (fetch_error or 'no_content_extracted'),
        'extract_method': method if text else 'failed',
        'fetch_status': 'ok' if text else 'failed',
        'http_status': http_status,
        'content_type': content_type,
        'failure_reason': None if text else (fetch_error or method or 'no_content_extracted'),
        'canonical_url': canonical_url,
    }


async def _run_search(req: SearchRequest) -> List[SearchItem]:
    count = _resolve_max_results(req)
    if count <= 0:
        return []
    has_domain_filters = bool(getattr(req, 'include_domains', []) or getattr(req, 'exclude_domains', []))
    provider_count = SERPER_MAX_COUNT if has_domain_filters and count < SERPER_MAX_COUNT else count
    raw_results = await _search_provider(req, provider_count)
    items: List[SearchItem] = []
    seen_urls = set()

    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        url = (raw.get('url') or '').strip()
        canonical_key = url.split('#', 1)[0].rstrip('/')
        if canonical_key in seen_urls:
            continue
        seen_urls.add(canonical_key)
        if not _domain_allowed(url, getattr(req, 'include_domains', []), getattr(req, 'exclude_domains', [])):
            continue
        items.append(SearchItem(
            rank=int(raw.get('rank') or 0),
            title=(raw.get('title') or '').strip()[:512],
            url=url,
            description=(raw.get('description') or '').strip()[:3000],
            published=raw.get('published') or None,
            language=raw.get('language') or None,
            score=raw.get('score') if isinstance(raw.get('score'), (int, float)) else None,
            source=raw.get('source') or SEARCH_PROVIDER,
            engine=raw.get('engine'),
            content=(raw.get('description') or '').strip()[:3000],
            favicon=_favicon_for_url(url) if getattr(req, 'include_favicon', False) else None,
            images=[ImageItem(**img) for img in (raw.get('images') or [])] if getattr(req, 'include_images', False) else None,
            provider_rank=int(raw.get('rank') or 0),
        ))
        if len(items) >= count:
            break

    if _resolve_include_content(req) and items:
        limit = req.fetch_top_n if req.fetch_top_n else len(items)
        to_fetch = items[:limit]
        semaphore = asyncio.Semaphore(max(1, MAX_FETCH_CONCURRENCY))
        async def guarded_extract(item: SearchItem) -> Dict[str, Any]:
            if not item.url:
                return {
                    'content': None,
                    'scraped': False,
                    'content_chars': 0,
                    'fetch_ms': None,
                    'error': 'empty_url',
                    'extract_method': 'failed',
                    'fetch_status': 'failed',
                    'failure_reason': 'empty_url',
                }
            async with semaphore:
                return await _extract_content(item.url, timeout_s=_resolve_timeout(req))

        tasks = [
            guarded_extract(item)
            for item in to_fetch
        ]
        scraped_data = await asyncio.gather(*tasks)
        for item, scraped in zip(to_fetch, scraped_data):
            item.scraped = bool(scraped.get('scraped'))
            item.content_chars = int(scraped.get('content_chars') or 0)
            item.fetch_ms = int(scraped.get('fetch_ms') or 0)
            item.error = scraped.get('error')
            item.extract_method = scraped.get('extract_method')
            item.fetch_status = scraped.get('fetch_status')
            item.http_status = scraped.get('http_status')
            item.content_type = scraped.get('content_type')
            item.failure_reason = scraped.get('failure_reason')
            item.canonical_url = scraped.get('canonical_url') or item.url
            if not item.error:
                full_content = scraped.get('content') or ''
                item.extracted_content = full_content
                item.content = _chunk_text(full_content, req.chunks_per_source) if _resolve_search_depth(req) == 'advanced' or req.chunks_per_source else _truncate_payload(full_content, 1000)
                if getattr(req, 'include_raw_content', None) is not None:
                    item.raw_content = full_content
                _STATUS['extract_success_total'] += 1
            else:
                _STATUS['extract_error_total'] += 1

    for item in items:
        item.score = _score_item(item, req.query)
    items.sort(key=lambda i: (i.score or 0, -i.rank), reverse=True)
    return items


_NAV_JUNK_PATTERNS = [
    'skip to main content', 'toggle menu', 'sign in', 'subscribe', 'newsletters', 'follow us',
    'my account', 'privacy policy', 'terms of use', 'cookie policy', 'advertise', 'all newsletters',
    'facebook', 'instagram', 'linkedin', 'cartoons', 'podcasts', 'live events', 'log in',
]
_CURRENT_EVENT_TERMS = {'new', 'latest', 'current', 'today', 'recent', 'now', 'replacement', 'successor', 'fire', 'fired', 'ouster', 'ousted', 'planning', 'approved'}


def _word_list(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{1,}", (text or '').lower())


def _summary_terms(query: str, item: SearchItem) -> List[str]:
    raw_terms = _word_list(' '.join([query or '', item.title or '', item.description or '']))
    stop = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'about', 'what', 'who', 'has', 'have', 'was', 'were', 'are', 'been', 'will', 'his', 'her', 'its'}
    terms: List[str] = []
    for term in raw_terms:
        if len(term) >= 3 and term not in stop and term not in terms:
            terms.append(term)
    return terms[:40]


def _split_passages(text: str) -> List[str]:
    normalized = re.sub(r'\r\n?', '\n', text or '')
    parts = re.split(r'\n{2,}|(?<=[.!?])\s+(?=[A-Z0-9""])', normalized)
    passages: List[str] = []
    for part in parts:
        clean = re.sub(r'\s+', ' ', part).strip()
        if len(clean) >= 40:
            passages.append(clean)
    return passages


def _is_domain_only_text(text: str, url: str) -> bool:
    compact = re.sub(r'\s+', '', (text or '').lower())
    host = (urlparse(url or '').netloc or '').lower().removeprefix('www.')
    return bool(compact) and (compact == host or compact == host.replace('.', '') or compact in {'wsj.com', 'politico.com'})


def _passage_score(passage: str, terms: List[str], position: int, current_event: bool) -> float:
    lower = passage.lower()
    score = 0.0
    for term in terms:
        if term in lower:
            score += 2.0 if term in _CURRENT_EVENT_TERMS else 1.0
    if any(marker in lower for marker in ('confirmed', 'approved', 'planning', 'fire', 'fired', 'ouster', 'successor', 'replacement', 'white house', 'according to')):
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
    body = (item.extracted_content or item.raw_content or item.content or '').strip()
    description = (item.description or '').strip()
    title = (item.title or '').strip()
    terms = _summary_terms(query, item)
    current_event = any(term in _CURRENT_EVENT_TERMS for term in _word_list(query or ''))
    flags: List[str] = []
    mode = 'body_passages'

    body_words = len(_word_list(body))
    if not body or body_words < 30:
        flags.append('too_short_body')
    if _is_domain_only_text(body, item.url):
        flags.append('domain_only_body')
    nav_hits = sum(1 for marker in _NAV_JUNK_PATTERNS if marker in body.lower())
    if nav_hits >= 4:
        flags.append('nav_heavy_body')
    if item.http_status in (401, 402, 403):
        flags.append(f'http_{item.http_status}')

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

    overlap_text = ' '.join(selected).lower()
    if terms and selected and sum(1 for term in terms[:12] if term in overlap_text) < 2:
        flags.append('low_query_overlap')

    if not selected or 'domain_only_body' in flags:
        mode = 'snippet_only'
        selected = []
        snippet_parts: List[str] = []
        if title:
            snippet_parts.append(f'Title: {title}')
        if description:
            snippet_parts.append(f'Search snippet: {description}')
        if item.published:
            snippet_parts.append(f'Published: {item.published}')
        selected_text = '\n'.join(snippet_parts).strip()
        if selected_text:
            selected = [selected_text]
        else:
            mode = 'excluded'
            flags.append('no_usable_text')

    usable = bool(selected) and mode != 'excluded'
    if mode == 'snippet_only':
        flags.append('snippet_only')
    return {'usable': usable, 'mode': mode, 'flags': sorted(set(flags)), 'passages': selected}


def _current_event_instruction(query: str) -> str:
    terms = set(_word_list(query or ''))
    if not terms.intersection(_CURRENT_EVENT_TERMS):
        return ''
    return (
        "Current-event handling: this query appears to ask about a new/current/recent status. "
        "Prefer newer dated reports for current status, but mention older official/profile pages when they conflict. "
        "If sources disagree, explain the disagreement. If no replacement or successor is confirmed, say that clearly.\n"
    )


def _normalize_for_summarizer(items: List[SearchItem], max_chars_per_source: int, query: str = '') -> str:
    chunks: List[str] = []
    for i, item in enumerate(items, start=1):
        selection = _select_source_passages(item, query, max_chars=max_chars_per_source)
        item.usable_for_summary = bool(selection['usable'])
        item.summary_input_mode = selection['mode']
        item.quality_flags = selection['flags']
        item.selected_passages = selection['passages']
        if not selection['usable']:
            continue
        source_block = [
            f"[{i}] {item.title or 'Untitled'}",
            f"URL: {item.url}",
            f"Published: {item.published or 'unknown'}",
            f"Description: {item.description or ''}",
            f"Status: scraped={item.scraped}, chars={item.content_chars}, method={item.extract_method}, input_mode={item.summary_input_mode}, quality_flags={','.join(item.quality_flags or [])}",
            "Selected evidence:",
            _truncate_payload('\n'.join(selection['passages']).strip(), max_chars_per_source),
        ]
        chunks.append('\n'.join(source_block))
    return '\n\n'.join(chunks)
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
    normalized = (model or '').lower()
    if (provider or '').lower() == 'openrouter' or normalized.startswith('openrouter/'):
        return OPENROUTER_API_KEY or LLM_PROVIDER_KEY
    if LLM_PROVIDER_KEY:
        return LLM_PROVIDER_KEY
    if LLM_API_KEY:
        return LLM_API_KEY
    if normalized.startswith('gpt-') or normalized.startswith('openai/'):
        return os.environ.get('OPENAI_API_KEY')
    if 'gemini' in normalized or normalized.startswith('gemini/'):
        return os.environ.get('GEMINI_API_KEY')
    if 'claude' in normalized or normalized.startswith('anthropic/'):
        return os.environ.get('ANTHROPIC_API_KEY')
    if 'bedrock' in normalized:
        return os.environ.get('AWS_ACCESS_KEY_ID')
    if 'llama' in normalized and normalized.startswith('ollama/'):
        return os.environ.get('OLLAMA_API_KEY') or 'dummy'
    return None


def _litellm_api_base_for_provider(provider: Optional[str]) -> Optional[str]:
    if (provider or '').lower() == 'openrouter':
        return OPENROUTER_API_BASE
    return LLM_API_BASE


def _split_provider_model(value: str, default_provider: str) -> Dict[str, str]:
    raw = (value or '').strip()
    lowered = raw.lower()
    if lowered.startswith('openrouter/') or lowered.endswith(':free'):
        return {'provider': 'openrouter', 'model': raw}
    if ':' in raw:
        provider, model = raw.split(':', 1)
        return {'provider': provider.strip().lower(), 'model': model.strip()}
    return {'provider': default_provider, 'model': raw}


def _build_llm_candidate_specs(resolved_llm: Dict[str, Any]) -> List[Dict[str, str]]:
    specs = [{'provider': resolved_llm['provider'], 'model': resolved_llm['model']}]
    for fallback in resolved_llm.get('fallback_models') or []:
        spec = _split_provider_model(str(fallback), LLM_PROVIDER)
        if spec not in specs:
            specs.append(spec)
    return specs[:max(1, int(resolved_llm.get('max_attempts') or LLM_MAX_ATTEMPTS))]


def _is_expensive_llm_spec(spec: Dict[str, str]) -> bool:
    provider = (spec.get('provider') or '').lower()
    model = (spec.get('model') or '').lower()
    if provider in ('openai', 'anthropic'):
        return True
    return any(marker in model for marker in ('gpt-5', 'gpt-4', 'claude-3', 'o1', 'o3', 'o4'))


def _extract_llm_response_payload(llm_resp: Any) -> Dict[str, Any]:
    raw = None
    finish_reason = None
    usage_payload = None
    try:
        choice = llm_resp.choices[0]
        raw = choice.message.content
        finish_reason = getattr(choice, 'finish_reason', None)
    except Exception:
        pass
    try:
        usage = getattr(llm_resp, 'usage', None)
        if hasattr(usage, 'model_dump'):
            usage_payload = usage.model_dump()
        elif isinstance(usage, dict):
            usage_payload = usage
    except Exception:
        usage_payload = None
    return {'raw': raw, 'finish_reason': finish_reason, 'usage': usage_payload}


def _normalize_summary_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(parsed or {})
    normalized['found'] = bool(normalized.get('found', bool(str(normalized.get('answer') or '').strip())))
    normalized['answer'] = str(normalized.get('answer') or '').strip()
    for key in ('highlights', 'open_questions'):
        value = normalized.get(key)
        if not isinstance(value, list):
            value = [] if value is None else [str(value)]
        normalized[key] = [str(v).strip() for v in value if str(v).strip()]
    try:
        normalized['confidence'] = max(0.0, min(1.0, float(normalized.get('confidence', 0.0))))
    except Exception:
        normalized['confidence'] = 0.0
    normalized.setdefault('schema_version', 'search-answer-v1')
    return normalized


def _validate_summary_payload(parsed: Any, candidate_items: List[SearchItem]) -> Dict[str, Any]:
    reasons: List[str] = []
    if not isinstance(parsed, dict):
        return {'ok': False, 'failure_type': 'invalid_json', 'reasons': ['response was not a JSON object'], 'payload': None}
    normalized = _normalize_summary_payload(parsed)
    if candidate_items and not normalized['answer']:
        reasons.append('answer is empty')
    if not isinstance(normalized.get('highlights'), list):
        reasons.append('highlights must be a list')
    if not isinstance(normalized.get('open_questions'), list):
        reasons.append('open_questions must be a list')
    if normalized['answer'].startswith('```'):
        reasons.append('answer contains markdown fence')
    terminal_chars = set(['.', '!', '?', '"', "'", ')'])
    if normalized['answer'] and normalized['answer'][-1] not in terminal_chars:
        reasons.append('answer appears incomplete')
    failure_type = 'quality_invalid' if reasons else None
    return {'ok': not reasons, 'failure_type': failure_type, 'reasons': reasons, 'payload': normalized}


def _adjust_summary_confidence(parsed: Dict[str, Any], attempts: List[Dict[str, Any]], candidate_items: List[SearchItem], repaired: bool) -> Dict[str, Any]:
    confidence = max(0.0, min(1.0, float(parsed.get('confidence') or 0.0)))
    reasons: List[str] = []
    if len(candidate_items) <= 1:
        confidence -= 0.10
        reasons.append('single_source')
    if repaired:
        confidence -= 0.10
        reasons.append('json_repair_used')
    failed_attempts = len([a for a in attempts if not a.get('success')])
    if failed_attempts:
        confidence -= min(0.20, failed_attempts * 0.05)
        reasons.append('model_retries')
    if not parsed.get('highlights'):
        confidence -= 0.05
        reasons.append('no_highlights')
    parsed['confidence'] = round(max(0.0, min(1.0, confidence)), 2)
    if reasons:
        parsed['confidence_reasons'] = reasons
    return parsed


def _summary_json_schema() -> Dict[str, Any]:
    return {
        'type': 'object',
        'properties': {
            'found': {'type': 'boolean'},
            'answer': {'type': 'string'},
            'highlights': {'type': 'array', 'items': {'type': 'string'}},
            'open_questions': {'type': 'array', 'items': {'type': 'string'}},
            'confidence': {'type': 'number'},
            'schema_version': {'type': 'string'},
        },
        'required': ['found', 'answer', 'highlights', 'open_questions', 'confidence', 'schema_version'],
        'additionalProperties': True,
    }


def _resolve_response_format(candidate_provider: str, resolved_llm: Dict[str, Any]) -> Dict[str, Any]:
    mode = (resolved_llm.get('response_format') or 'auto').strip().lower()
    if mode in ('none', 'off', 'disabled'):
        return {}
    if mode == 'json_object':
        return {'response_format': {'type': 'json_object'}}
    if mode == 'json_schema' or (mode == 'auto' and candidate_provider == 'openrouter'):
        return {'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'search_answer',
                'strict': True,
                'schema': _summary_json_schema(),
            },
        }}
    return {'response_format': {'type': 'json_object'}}

async def _call_litellm_model(spec: Dict[str, str], messages: List[Dict[str, str]], resolved_llm: Dict[str, Any], attempt_timeout: Optional[float] = None) -> Any:
    candidate_provider = spec['provider']
    candidate_model = spec['model']
    api_key = _litellm_api_key_for_model(candidate_model, candidate_provider)
    if not api_key:
        raise RuntimeError('missing_api_key')
    kwargs = {
        'model': candidate_model,
        'messages': messages,
        'temperature': resolved_llm['temperature'],
        'max_completion_tokens': resolved_llm['max_completion_tokens'],
        'api_key': api_key,
        'api_base': _litellm_api_base_for_provider(candidate_provider),
        'timeout': resolved_llm['timeout'],
    }
    kwargs.update(_resolve_response_format(candidate_provider, resolved_llm))
    if resolved_llm.get('reasoning_effort') and candidate_provider != 'openrouter':
        kwargs['reasoning_effort'] = resolved_llm['reasoning_effort']
    timeout_s = max(1.0, float(attempt_timeout or resolved_llm['timeout']))
    return await asyncio.wait_for(asyncio.to_thread(lambda: llm_completion(**kwargs)), timeout=timeout_s)


async def _repair_summary_payload(raw: str, spec: Dict[str, str], resolved_llm: Dict[str, Any], attempt_timeout: Optional[float] = None) -> Dict[str, Any]:
    repair_value = resolved_llm.get('repair_model')
    repair_spec = _split_provider_model(repair_value, spec['provider']) if repair_value else spec
    repair_messages = [
        {'role': 'system', 'content': 'You repair malformed model output into strict JSON. Do not add facts. Return only JSON.'},
        {'role': 'user', 'content': (
            'Convert this attempted search answer into one strict JSON object with fields '
            'found, answer, highlights, open_questions, confidence, schema_version. '
            'Use empty strings or arrays when the source text is missing.\n\n'
            f'Attempted output:\n{_truncate_payload(raw or "", 6000)}'
        )},
    ]
    repair_resp = await _call_litellm_model(repair_spec, repair_messages, resolved_llm, attempt_timeout=attempt_timeout)
    payload = _extract_llm_response_payload(repair_resp)
    return {'spec': repair_spec, 'response': payload, 'parsed': _extract_json_from_text(payload.get('raw') or '')}


def _remaining_llm_timeout(started: float, total_budget: float, per_call_timeout: float) -> float:
    remaining = total_budget - (time.monotonic() - started)
    if remaining <= 0:
        return 0.0
    return max(1.0, min(float(per_call_timeout), remaining))

async def _run_llm_orchestrator(messages: List[Dict[str, str]], resolved_llm: Dict[str, Any], candidate_items: List[SearchItem]) -> Dict[str, Any]:
    started = time.monotonic()
    attempts: List[Dict[str, Any]] = []
    last_payload: Dict[str, Any] = {}
    repair_limit = int(resolved_llm.get('max_repair_attempts') or 0)
    total_budget = float(resolved_llm.get('max_total_seconds') or LLM_MAX_TOTAL_SECONDS)
    allow_expensive = bool(resolved_llm.get('allow_expensive_fallback'))

    for spec in _build_llm_candidate_specs(resolved_llm):
        if time.monotonic() - started > total_budget:
            attempts.append({'provider': spec['provider'], 'model': spec['model'], 'success': False, 'failure_type': 'budget_exhausted'})
            break
        if not allow_expensive and _is_expensive_llm_spec(spec) and spec != {'provider': resolved_llm['provider'], 'model': resolved_llm['model']}:
            attempts.append({'provider': spec['provider'], 'model': spec['model'], 'success': False, 'failure_type': 'expensive_fallback_blocked'})
            continue
        t0 = time.monotonic()
        try:
            attempt_timeout = _remaining_llm_timeout(started, total_budget, resolved_llm['timeout'])
            if attempt_timeout <= 0:
                raise asyncio.TimeoutError('llm_total_budget_exhausted')
            llm_resp = await _call_litellm_model(spec, messages, resolved_llm, attempt_timeout=attempt_timeout)
            payload = _extract_llm_response_payload(llm_resp)
            last_payload = payload
            parsed = _extract_json_from_text(payload.get('raw') or '')
            validation = _validate_summary_payload(parsed, candidate_items)
            attempt = {
                'provider': spec['provider'],
                'model': spec['model'],
                'role': 'answer',
                'success': bool(validation['ok']),
                'failure_type': validation.get('failure_type'),
                'reasons': validation.get('reasons') or [],
                'latency_ms': int((time.monotonic() - t0) * 1000),
                'finish_reason': payload.get('finish_reason'),
            }
            if payload.get('usage'):
                attempt['usage'] = payload.get('usage')
            attempts.append(attempt)
            if validation['ok']:
                return {'ok': True, 'parsed': validation['payload'], 'raw': payload.get('raw'), 'finish_reason': payload.get('finish_reason'), 'usage': payload.get('usage'), 'provider': spec['provider'], 'model': spec['model'], 'attempts': attempts, 'repaired': False}
            for repair_index in range(repair_limit):
                rt0 = time.monotonic()
                try:
                    repair_timeout = _remaining_llm_timeout(started, total_budget, resolved_llm.get('repair_timeout') or resolved_llm['timeout'])
                    if repair_timeout <= 0:
                        raise asyncio.TimeoutError('llm_total_budget_exhausted')
                    repair_result = await _repair_summary_payload(payload.get('raw') or '', spec, resolved_llm, attempt_timeout=repair_timeout)
                    repair_validation = _validate_summary_payload(repair_result.get('parsed'), candidate_items)
                    repair_spec = repair_result.get('spec') or spec
                    repair_payload = repair_result.get('response') or {}
                    attempts.append({
                        'provider': repair_spec['provider'],
                        'model': repair_spec['model'],
                        'role': 'repair',
                        'success': bool(repair_validation['ok']),
                        'failure_type': repair_validation.get('failure_type'),
                        'reasons': repair_validation.get('reasons') or [],
                        'latency_ms': int((time.monotonic() - rt0) * 1000),
                        'finish_reason': repair_payload.get('finish_reason'),
                    })
                    if repair_validation['ok']:
                        return {'ok': True, 'parsed': repair_validation['payload'], 'raw': repair_payload.get('raw'), 'finish_reason': repair_payload.get('finish_reason'), 'usage': repair_payload.get('usage'), 'provider': repair_spec['provider'], 'model': repair_spec['model'], 'attempts': attempts, 'repaired': True}
                except Exception as repair_exc:
                    attempts.append({'provider': spec['provider'], 'model': spec['model'], 'role': 'repair', 'success': False, 'failure_type': type(repair_exc).__name__, 'error': str(repair_exc), 'latency_ms': int((time.monotonic() - rt0) * 1000)})
        except Exception as exc:
            attempts.append({'provider': spec['provider'], 'model': spec['model'], 'role': 'answer', 'success': False, 'failure_type': type(exc).__name__, 'error': str(exc), 'latency_ms': int((time.monotonic() - t0) * 1000)})

    return {'ok': False, 'parsed': {
        'found': bool(candidate_items),
        'answer': 'Relevant sources were found, but answer generation failed validation.',
        'highlights': [],
        'open_questions': ['Try a stronger model, fewer sources, or enable a fallback model.'],
        'confidence': 0.0,
        'schema_version': 'search-answer-v1',
        'llm_failed': True,
    }, 'raw': last_payload.get('raw'), 'finish_reason': last_payload.get('finish_reason'), 'usage': last_payload.get('usage'), 'provider': resolved_llm['provider'], 'model': resolved_llm['model'], 'attempts': attempts, 'repaired': False}


async def _summarize_query(query: str, items: List[SearchItem], max_sources: int, max_chars_per_source: int, llm_options: Optional[LLMOptions] = None, debug: bool = False, include_usage: bool = False) -> Dict[str, Any]:
    if not SUMMARIZER_ENABLED:
        raise HTTPException(status_code=400, detail='Summarizer is disabled. Set SUMMARIZER_ENABLED=true')
    if not _LITELLM_AVAILABLE:
        raise HTTPException(status_code=500, detail='litellm package not installed')

    candidate_items = [i for i in items if i.url and (i.scraped or i.description or i.title)] if items else []
    candidate_items = candidate_items[:max_sources]

    if not candidate_items:
        return {
            'found': False,
            'answer': 'No usable source content was available for this query.',
            'highlights': [],
            'sources': [],
            'excluded_results': [i.url for i in items if i.url and not i.scraped],
            'confidence': 0.00,
            'open_questions': ['Could you provide a higher fetch_top_n or different query?'],
            'raw_model_error': None,
        }

    resolved_llm = _resolve_llm_options(llm_options)
    corpus = _normalize_for_summarizer(candidate_items, max_chars_per_source=max_chars_per_source, query=query)
    candidate_items = [i for i in candidate_items if i.usable_for_summary]
    if not candidate_items or not corpus.strip():
        return {
            'found': False,
            'answer': 'No usable source content was available for this query.',
            'highlights': [],
            'sources': [],
            'excluded_results': [i.url for i in items if i.url],
            'confidence': 0.0,
            'open_questions': ['All fetched sources were blocked, too short, or low quality.'],
        }
    system_prompt = resolved_llm['system_prompt']
    user_prompt = (
        f"Query: {query}\n\n"
        f"Sources to use:\n{corpus}\n\n"
        f"{_current_event_instruction(query)}"
        f"Return ONLY a strict JSON object and nothing else.\n"
        f"No markdown, no fences, no prose, no prefatory text.\n"
        f"Write a detailed search-API answer. Target 700 words.\n"
        f"Include only facts supported by the provided source text. Avoid sensational wording.\n"
        f"Use the selected evidence from every source; do not answer from only the first source when later sources conflict.\n"
        f"Return fields: found, answer, highlights, open_questions, confidence, schema_version.\n"
        f"If fields are missing, use safe defaults: found=false, answer empty, confidence=0.0, arrays empty.\n"
        f"Do not include raw source excerpts unless needed for a short highlight."
    )

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]

    llm_result = await _run_llm_orchestrator(messages, resolved_llm, candidate_items)
    parsed = _adjust_summary_confidence(llm_result['parsed'], llm_result.get('attempts') or [], candidate_items, bool(llm_result.get('repaired')))
    if llm_result.get('ok'):
        _STATUS['llm_success_total'] += 1
    else:
        _STATUS['llm_error_total'] += 1
        _STATUS['last_error'] = 'llm:validation_failed'

    candidate_source_urls = [i.url for i in candidate_items if i.url]
    model_sources = parsed.get('sources')
    if not isinstance(model_sources, list):
        model_sources = []
    normalized_sources = []
    for source in [*model_sources, *candidate_source_urls]:
        if isinstance(source, str):
            url = source.strip()
        elif isinstance(source, dict):
            url = str(source.get('url') or source.get('link') or '').strip()
        else:
            url = ''
        if url and url not in normalized_sources:
            normalized_sources.append(url)
    parsed['sources'] = normalized_sources

    parsed['source_evidence'] = [
        {
            'rank': idx,
            'title': i.title,
            'url': i.url,
            'content_chars': i.content_chars,
            'extract_method': i.extract_method,
            'used_in_summary': True,
        }
        for idx, i in enumerate(candidate_items, start=1)
        if i.url
    ]

    parsed.setdefault('excluded_results', [])
    parsed.setdefault('highlights', [])
    parsed.setdefault('open_questions', [])
    parsed.setdefault('answer', '')
    parsed.setdefault('confidence', 0.0)

    if debug:
        parsed['raw_model_output'] = llm_result.get('raw')
        parsed['llm_attempts'] = llm_result.get('attempts') or []
        parsed['model_finish_reason'] = llm_result.get('finish_reason')
        parsed['llm_options'] = {
            'model': llm_result.get('model'),
            'provider': llm_result.get('provider'),
            'quality_tier': resolved_llm['quality_tier'],
            'fallback_models': resolved_llm.get('fallback_models') or [],
            'max_attempts': resolved_llm.get('max_attempts'),
            'max_repair_attempts': resolved_llm.get('max_repair_attempts'),
            'max_total_seconds': resolved_llm.get('max_total_seconds'),
            'allow_expensive_fallback': resolved_llm.get('allow_expensive_fallback'),
            'repair_model': resolved_llm.get('repair_model'),
            'response_format': resolved_llm.get('response_format'),
            'max_completion_tokens': resolved_llm['max_completion_tokens'],
            'reasoning_effort': resolved_llm['reasoning_effort'],
            'temperature': resolved_llm['temperature'],
            'timeout': resolved_llm['timeout'],
            'repair_timeout': resolved_llm.get('repair_timeout'),
            'request_options_enabled': resolved_llm['request_options_enabled'],
        }
    else:
        parsed.pop('raw_model_output', None)
        parsed.pop('llm_attempts', None)
        parsed.pop('model_finish_reason', None)
        parsed.pop('llm_options', None)

    usage_payload = llm_result.get('usage')
    if usage_payload and (include_usage or debug):
        parsed.setdefault('model_usage', usage_payload)
    elif debug:
        parsed.setdefault('model_usage', usage_payload)
    else:
        parsed.pop('model_usage', None)

    return parsed

class GPTRRetrieverRequest(BaseModel):
    query: Optional[str] = Field(default=None, min_length=1, max_length=512)
    q: Optional[str] = Field(default=None, min_length=1, max_length=512)
    question: Optional[str] = Field(default=None, min_length=1, max_length=512)
    max_results: Optional[int] = Field(default=None, ge=1, le=SERPER_MAX_COUNT)
    count: Optional[int] = Field(default=None, ge=1, le=SERPER_MAX_COUNT)
    include_domains: List[str] = Field(default_factory=list)
    exclude_domains: List[str] = Field(default_factory=list)
    time_range: Optional[str] = Field(default=None, max_length=16)
    days: Optional[int] = Field(default=None, ge=1, le=3650)
    country: Optional[str] = Field(default=None, max_length=64)
    safe_search: bool = Field(default=False)
    timeout: Optional[float] = Field(default=None, ge=1, le=120)
    debug: bool = Field(default=False)

def _resolve_gptr_query(req: GPTRRetrieverRequest) -> str:
    query = (req.query or req.q or req.question or '').strip()
    if not query:
        raise HTTPException(status_code=422, detail='GPTR retriever requires query, q, or question')
    return query


def _gptr_raw_content(item: SearchItem) -> str:
    body = (item.extracted_content or item.raw_content or item.content or '').strip()
    if item.selected_passages:
        body = '\n\n'.join(item.selected_passages).strip()
    if not body or _is_domain_only_text(body, item.url):
        parts = []
        if item.title:
            parts.append(f"Title: {item.title}")
        if item.description:
            parts.append(f"Search snippet: {item.description}")
        if item.published:
            parts.append(f"Published: {item.published}")
        body = '\n'.join(parts).strip()
    return body



def _calculate_searchbox_usage(
    provider: str,
    search_queries: int = 0,
    scrapes_http: int = 0,
    scrapes_playwright: int = 0,
    llm_usage: dict | None = None
) -> dict:
    search_cost = search_queries * 0.001
    scrape_cost = (scrapes_http * 0.0) + (scrapes_playwright * 0.005)
    
    # Compute LLM costs using standard gpt-4o-mini rates if present
    llm_cost = 0.0
    if llm_usage:
        prompt_tokens = llm_usage.get("prompt_tokens") or llm_usage.get("input_tokens") or 0
        completion_tokens = llm_usage.get("completion_tokens") or llm_usage.get("output_tokens") or 0
        # gpt-4o-mini rates: $0.150 / 1M input, $0.600 / 1M output
        llm_cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.0000006)
        
    total_cost = search_cost + scrape_cost + llm_cost
    
    return {
        "cost_schema_version": "searchbox-cost-v1",
        "search_provider": provider,
        "total_cost_usd": round(total_cost, 6),
        "search_cost_usd": round(search_cost, 6),
        "scrape_cost_usd": round(scrape_cost, 6),
        "llm_cost_usd": round(llm_cost, 6),
        "search_requests": search_queries,
        "scrape_fetches": scrapes_http + scrapes_playwright,
        "cost_confidence": "estimated"
    }


@app.post('/gptr-retriever')
async def gptr_retriever(req: GPTRRetrieverRequest, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    query = _resolve_gptr_query(req)
    max_results = req.max_results or req.count or SERPER_DEFAULT_COUNT
    search_req = SearchRequest(
        query=query,
        count=max_results,
        max_results=max_results,
        include_content=True,
        include_raw_content=False,
        include_answer=False,
        fetch_top_n=max_results,
        summarize_top_n=max_results,
        include_domains=req.include_domains,
        exclude_domains=req.exclude_domains,
        time_range=req.time_range,
        days=req.days,
        country=req.country,
        safe_search=req.safe_search,
        timeout=req.timeout,
        debug=req.debug,
    )
    results = await _run_search(search_req)
    _normalize_for_summarizer(results[:max_results], max_chars_per_source=_resolve_max_chars_per_source(search_req), query=query)
    
    # Calculate scrapes cost metrics
    scrapes_http = len([r for r in results[:max_results] if r.scraped and r.extract_method != "playwright_fallback"])
    scrapes_pw = len([r for r in results[:max_results] if r.scraped and r.extract_method == "playwright_fallback"])
    
    usage_block = _calculate_searchbox_usage(
        provider=SEARCH_PROVIDER,
        search_queries=1 if results else 0,
        scrapes_http=scrapes_http,
        scrapes_playwright=scrapes_pw
    )
    
    payload = []
    for idx, item in enumerate(results[:max_results]):
        raw_content = _gptr_raw_content(item)
        if not item.url or not raw_content:
            continue
        row = {'url': item.url, 'raw_content': raw_content}
        if idx == 0:
            row['_searchbox_usage'] = usage_block
        if req.debug:
            row.update({
                'title': item.title,
                'published': item.published,
                'summary_input_mode': item.summary_input_mode,
                'quality_flags': item.quality_flags or [],
                'scraped': item.scraped,
                'http_status': item.http_status,
                'extract_method': item.extract_method,
            })
        payload.append(row)
    return payload


@app.get('/gptr-retriever')
async def gptr_retriever_get(query: Optional[str] = None, q: Optional[str] = None, question: Optional[str] = None, max_results: Optional[int] = None, count: Optional[int] = None, authorization: Optional[str] = Header(default=None)):
    req = GPTRRetrieverRequest(query=query, q=q, question=question, max_results=max_results, count=count)
    return await gptr_retriever(req, authorization=authorization)

@app.post('/search', response_model=SearchResponse)
async def search(req: SearchRequest, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    _STATUS['requests_total'] += 1
    t0 = datetime.now()
    request_id = str(uuid.uuid4())
    answer_requested = _resolve_include_answer(req, default=False)
    search_req = SearchRequest(**_model_dict(req))
    if answer_requested:
        search_req.include_content = True
        if search_req.fetch_top_n is None:
            search_req.fetch_top_n = min(_resolve_max_results(req) or SERPER_DEFAULT_COUNT, _resolve_summarize_top_n(req))
    results = await _run_search(search_req)
    summary_payload = None
    answer = None
    usage = None
    if answer_requested:
        summary_payload = await _summarize_query(
            query=req.query,
            items=results,
            max_sources=_resolve_summarize_top_n(req),
            max_chars_per_source=_resolve_max_chars_per_source(req),
            llm_options=req.llm_options,
            debug=_resolve_debug(req),
            include_usage=req.include_usage,
        )
        answer = summary_payload.get('answer') if isinstance(summary_payload, dict) else None
        
    # Calculate scrapes cost metrics
    scrapes_http = len([r for r in results if r.scraped and r.extract_method != "playwright_fallback"])
    scrapes_pw = len([r for r in results if r.scraped and r.extract_method == "playwright_fallback"])
    llm_usage = summary_payload.get('model_usage') if summary_payload else None
    
    usage = _calculate_searchbox_usage(
        provider=SEARCH_PROVIDER,
        search_queries=1 if results else 0,
        scrapes_http=scrapes_http,
        scrapes_playwright=scrapes_pw,
        llm_usage=llm_usage
    )
    buckets = _split_result_buckets(results, _resolve_summarize_top_n(req)) if answer_requested else {'not_summarized': [], 'excluded_results': []}
    global_images: List[ImageItem] = []
    if req.include_images:
        for item in results:
            for img in item.images or []:
                if img.url and all(existing.url != img.url for existing in global_images):
                    global_images.append(img)
    return SearchResponse(
        provider=SEARCH_PROVIDER,
        query=req.query,
        results_count=len(results),
        request_id=request_id,
        results=results,
        images=global_images if req.include_images else None,
        answer=answer,
        summary=summary_payload,
        usage=usage,
        unused_results=[*buckets['not_summarized'], *buckets['excluded_results']] if _resolve_debug(req) and answer_requested else None,
        not_summarized=buckets['not_summarized'] if _resolve_debug(req) and answer_requested else None,
        excluded_results=buckets['excluded_results'] if _resolve_debug(req) and answer_requested else None,
        response_time=round((datetime.now() - t0).total_seconds(), 3),
        auto_parameters={'search_depth': req.search_depth or 'basic'} if req.auto_parameters else None,
    )


@app.get('/search')
async def search_get(q: str, count: int = SERPER_DEFAULT_COUNT, include_content: bool = False, fetch_top_n: Optional[int] = None, authorization: Optional[str] = Header(default=None)):
    req = SearchRequest(query=q, count=count, include_content=include_content, fetch_top_n=fetch_top_n)
    return await search(req, authorization=authorization)


@app.get('/search-raw')
def search_raw(q: str, count: int = SERPER_DEFAULT_COUNT, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    if SEARCH_PROVIDER == 'serper':
        if not SERPER_API_KEY:
            raise HTTPException(status_code=500, detail='SERPER_API_KEY is not configured')
        payload = {'q': q, 'num': min(int(count), SERPER_MAX_COUNT), 'hl': 'en'}
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-API-KEY': SERPER_API_KEY,
            'User-Agent': USER_AGENT,
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.post(SERPER_API_URL, json=payload, headers=headers)
            r.raise_for_status()
            return JSONResponse(content=r.json())
    if SEARCH_PROVIDER == 'brave':
        if not BRAVE_API_KEY:
            raise HTTPException(status_code=500, detail='BRAVE_API_KEY is not configured')
        payload = {'count': str(min(int(count), BRAVE_MAX_COUNT)), 'q': q, 'search_lang': 'en'}
        headers = {
            'Accept': 'application/json',
            'X-Subscription-Token': BRAVE_API_KEY,
            'User-Agent': USER_AGENT,
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(BRAVE_API_URL, params=payload, headers=headers)
            r.raise_for_status()
            return JSONResponse(content=r.json())
    if SEARCH_PROVIDER == 'searxng':
        payload = {
            'q': q,
            'format': 'json',
            'language': 'en',
            'safesearch': 0,
            'categories': 'general',
        }
        params_count = min(int(count), SEARXNG_RESULTS_LIMIT)
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(_searxng_query_url(), params=payload, headers={'User-Agent': USER_AGENT})
            r.raise_for_status()
            data = r.json()
        return JSONResponse(content={'provider': 'searxng', 'requested_count': params_count, 'results': (data.get('results', []) or [])[:params_count]})
    raise HTTPException(status_code=400, detail=f'Unknown SEARCH_PROVIDER {SEARCH_PROVIDER!r}')


@app.post('/search-summary', response_model=SearchSummaryResponse)
async def search_summary(req: SearchSummaryRequest, authorization: Optional[str] = Header(default=None)):
    _authorize(authorization)
    _STATUS['requests_total'] += 1
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
    )
    results = await _run_search(req_search)
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
            'answer': '',
            'highlights': [],
            'sources': [],
            'excluded_results': [],
            'confidence': 0.0,
            'open_questions': [],
            'notes': 'include_answer=false',
        }
    buckets = _split_result_buckets(results, max_sources)
    unused_results = [*buckets['not_summarized'], *buckets['excluded_results']]
    global_images: List[ImageItem] = []
    if req.include_images:
        for item in results:
            for img in item.images or []:
                if img.url and all(existing.url != img.url for existing in global_images):
                    global_images.append(img)

    return SearchSummaryResponse(
        provider=SEARCH_PROVIDER,
        request_id=str(uuid.uuid4()),
        query=req.query,
        results_count=len(results),
        included_sources=min(max_sources, len([r for r in results if r.scraped and r.content])),
        unused_results_count=len(unused_results),
        unused_results=unused_results if _resolve_debug(req) else None,
        not_summarized=buckets['not_summarized'] if _resolve_debug(req) else None,
        excluded_results=buckets['excluded_results'] if _resolve_debug(req) else None,
        images=global_images if req.include_images else None,
        summary=summary_payload,
    )
