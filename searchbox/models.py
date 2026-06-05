"""Pydantic models for Searchbox requests, responses, and normalized results."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from .defaults import SERPER_DEFAULT_COUNT, SERPER_MAX_COUNT


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
    api_key: Optional[str] = Field(default=None, max_length=256)
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
    caller: Optional[str] = Field(default=None, max_length=64)
    user_uuid: Optional[str] = Field(default=None, max_length=64)
    run_id: Optional[str] = Field(default=None, max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=64)
    aiq_job_id: Optional[str] = Field(default=None, max_length=64)
    report_index: Optional[int] = Field(default=None)
    report_count: Optional[int] = Field(default=None)
    advanced_search: Optional[bool] = Field(default=None)
    max_content_length: Optional[int] = Field(default=None)


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
    caller: Optional[str] = Field(default=None, max_length=64)
    user_uuid: Optional[str] = Field(default=None, max_length=64)
    run_id: Optional[str] = Field(default=None, max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=64)
    aiq_job_id: Optional[str] = Field(default=None, max_length=64)
    report_index: Optional[int] = Field(default=None)
    report_count: Optional[int] = Field(default=None)
    advanced_search: Optional[bool] = Field(default=None)
    max_content_length: Optional[int] = Field(default=None)


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


class TavilySearchResult(BaseModel):
    title: str
    url: str
    content: str
    raw_content: Optional[str] = None
    score: float


class TavilySearchResponse(BaseModel):
    query: str
    follow_up_questions: Optional[List[str]] = None
    answer: Optional[str] = None
    images: Optional[List[Dict[str, Any]]] = None
    results: List[TavilySearchResult]
    usage: Optional[Dict[str, Any]] = None
    _searchbox_usage: Optional[Dict[str, Any]] = None
