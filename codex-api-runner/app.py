import json
import os
import secrets
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP = FastAPI(title="CodexExecAPI", version="1.0")
BASE = Path(os.getenv("CODEX_RUNNER_DATA_DIR", "/home/ubuntu/codex-api-runner/data"))
JOBS = BASE / "jobs"
DB = BASE / "jobs.sqlite"
CODEX_BIN = os.getenv("CODEX_RUNNER_CODEX_BIN", "/home/ubuntu/.local/bin/codex")
AUTH_JSON = os.getenv("CODEX_RUNNER_AUTH_JSON", "/home/ubuntu/.codex/auth.json")
DEFAULT_WORKSPACE = os.getenv("CODEX_RUNNER_DEFAULT_WORKSPACE", "/home/ubuntu")
ALLOWED_WORKSPACES = [p for p in os.getenv("CODEX_RUNNER_ALLOWED_WORKSPACES", "/home/ubuntu").split(os.pathsep) if p]
TOKEN = os.getenv("CODEX_RUNNER_TOKEN", "")
MAX_PROMPT_CHARS = int(os.getenv("CODEX_RUNNER_MAX_PROMPT_CHARS", "200000"))
MAX_CONCURRENT = int(os.getenv("CODEX_RUNNER_MAX_CONCURRENT", "1"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("CODEX_RUNNER_REQUEST_TIMEOUT_SECONDS", "3600"))
ALLOWED_MODELS = [
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex-spark",
]
APICOSTX_REASONING_EFFORTS = {"low", "medium", "high"}
CODEX_REASONING_EFFORT_MAP = {"low": "low", "medium": "medium", "high": "xhigh"}
ALLOWED_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}
DANGER_ALLOWED = os.getenv("ALLOW_DANGER_FULL_ACCESS", "false").lower() == "true"

JOBS.mkdir(parents=True, exist_ok=True)
_sem = threading.Semaphore(MAX_CONCURRENT)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def auth(value: str | None) -> None:
    if not TOKEN:
        raise HTTPException(status_code=500, detail="CODEX_RUNNER_TOKEN is not configured")
    if not value or not value.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    supplied = value.split(" ", 1)[1]
    if not secrets.compare_digest(supplied, TOKEN):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def init_db() -> None:
    with sqlite3.connect(DB) as con:
        con.execute("""
        create table if not exists jobs(
          job_id text primary key,
          status text not null,
          model text,
          created_at text not null,
          started_at text,
          finished_at text,
          exit_code integer,
          error text,
          input_tokens integer default 0,
          output_tokens integer default 0,
          reasoning_tokens integer default 0,
          cached_tokens integer default 0
        )
        """)


def job_dir(job_id: str) -> Path:
    return JOBS / job_id


def workspace_ok(path: str) -> str:
    resolved = str(Path(path or DEFAULT_WORKSPACE).resolve())
    for allowed in ALLOWED_WORKSPACES:
        ar = str(Path(allowed).resolve())
        if resolved == ar or resolved.startswith(ar.rstrip("/") + "/"):
            return resolved
    raise HTTPException(status_code=400, detail="Workspace is not allowlisted")


def resolve_reasoning_effort(value: str | None) -> str:
    if value is None or not str(value).strip():
        return CODEX_REASONING_EFFORT_MAP["medium"]
    normalized = str(value).strip().lower()
    if normalized not in APICOSTX_REASONING_EFFORTS:
        allowed = ", ".join(sorted(APICOSTX_REASONING_EFFORTS))
        raise ValueError(f"Unsupported reasoning_effort '{value}'. Supported values: {allowed}")
    return CODEX_REASONING_EFFORT_MAP[normalized]


def messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(str(part.get("text", "")))
                    elif "text" in part:
                        parts.append(str(part.get("text", "")))
                else:
                    parts.append(str(part))
            content = "\n".join(parts)
        chunks.append(f"[{role}]\n{content}")
    return "\n\n".join(chunks).strip()


def latest_usage(stdout: Path) -> dict[str, int]:
    usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}
    if not stdout.exists():
        return usage
    for line in stdout.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if any(k in cur for k in ("input_tokens", "output_tokens", "reasoning_output_tokens", "cached_input_tokens")):
                    usage["input_tokens"] = int(cur.get("input_tokens") or usage["input_tokens"] or 0)
                    usage["output_tokens"] = int(cur.get("output_tokens") or usage["output_tokens"] or 0)
                    usage["reasoning_tokens"] = int(cur.get("reasoning_output_tokens") or cur.get("reasoning_tokens") or usage["reasoning_tokens"] or 0)
                    usage["cached_tokens"] = int(cur.get("cached_input_tokens") or cur.get("cached_tokens") or usage["cached_tokens"] or 0)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    return usage


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    keys = list(fields)
    with sqlite3.connect(DB) as con:
        con.execute(
            f"update jobs set {', '.join(k + '=?' for k in keys)} where job_id=?",
            [fields[k] for k in keys] + [job_id],
        )


def build_codex_args(
    *,
    model: str,
    workspace: str,
    sandbox: str,
    ephemeral: bool,
    reasoning_effort: str | None,
    final_path: Path,
    output_schema: str | None = None,
) -> list[str]:
    args = [CODEX_BIN, "exec", "--json", "--sandbox", sandbox, "--skip-git-repo-check", "--cd", workspace, "-m", model, "-o", str(final_path)]
    if ephemeral:
        args.append("--ephemeral")
    resolved_effort = resolve_reasoning_effort(reasoning_effort)
    args += ["-c", f'model_reasoning_effort="{resolved_effort}"']
    if output_schema:
        args += ["--output-schema", output_schema]
    args.append("-")
    return args


def run_codex(job_id: str, *, model: str, prompt: str, workspace: str, sandbox: str, ephemeral: bool, reasoning_effort: str | None, output_schema: str | None = None) -> None:
    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    prompt_path = jd / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    stdout_path = jd / "stdout.jsonl"
    stderr_path = jd / "stderr.log"
    final_path = jd / "final.txt"
    args = build_codex_args(
        model=model,
        workspace=workspace,
        sandbox=sandbox,
        ephemeral=ephemeral,
        reasoning_effort=reasoning_effort,
        final_path=final_path,
        output_schema=output_schema,
    )
    with _sem:
        update_job(job_id, status="running", started_at=now())
        try:
            with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
                proc = subprocess.run(args, input=prompt, text=True, stdout=out, stderr=err, timeout=REQUEST_TIMEOUT_SECONDS)
            usage = latest_usage(stdout_path)
            status = "succeeded" if proc.returncode == 0 else "failed"
            error = None if proc.returncode == 0 else stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            update_job(job_id, status=status, finished_at=now(), exit_code=proc.returncode, error=error, **usage)
        except subprocess.TimeoutExpired:
            update_job(job_id, status="failed", finished_at=now(), exit_code=124, error=f"codex exec timed out after {REQUEST_TIMEOUT_SECONDS}s")
        except Exception as exc:
            update_job(job_id, status="failed", finished_at=now(), exit_code=1, error=str(exc))


def create_job_row(job_id: str, model: str) -> None:
    with sqlite3.connect(DB) as con:
        con.execute("insert into jobs(job_id,status,model,created_at) values(?,?,?,?)", (job_id, "queued", model, now()))


def get_job(job_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None


class ChatRequest(BaseModel):
    model: str = Field(default="gpt-5.4-mini")
    messages: list[dict[str, Any]] = Field(default_factory=list)
    prompt: str | None = None
    workspace: str | None = None
    sandbox: str = "workspace-write"
    ephemeral: bool = True
    reasoning_effort: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False


@APP.on_event("startup")
def startup() -> None:
    init_db()


@APP.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "codex_bin_exists": Path(CODEX_BIN).exists(),
        "auth_json_exists": Path(AUTH_JSON).exists(),
        "token_configured": bool(TOKEN),
        "models": ALLOWED_MODELS,
        "reasoning_efforts": sorted(APICOSTX_REASONING_EFFORTS),
        "reasoning_effort_mapping": CODEX_REASONING_EFFORT_MAP,
        "max_concurrent": MAX_CONCURRENT,
    }


@APP.get("/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    auth(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "owned_by": "codexexecapi",
                "supported_reasoning_efforts": sorted(APICOSTX_REASONING_EFFORTS),
                "reasoning_effort_mapping": CODEX_REASONING_EFFORT_MAP,
            }
            for model in ALLOWED_MODELS
        ],
    }


@APP.post("/v1/chat/completions")
def chat(req: ChatRequest, authorization: str | None = Header(default=None)) -> JSONResponse:
    auth(authorization)
    if req.stream:
        raise HTTPException(status_code=400, detail="stream=true is not supported")
    model = req.model
    if model.startswith("codexexecapi:"):
        model = model.split(":", 1)[1]
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail="Unsupported model")
    sandbox = req.sandbox or "workspace-write"
    if sandbox not in ALLOWED_SANDBOXES:
        raise HTTPException(status_code=400, detail="Unsupported sandbox")
    if sandbox == "danger-full-access" and not DANGER_ALLOWED:
        raise HTTPException(status_code=400, detail="danger-full-access is disabled")
    try:
        resolve_reasoning_effort(req.reasoning_effort)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workspace = workspace_ok(req.workspace or DEFAULT_WORKSPACE)
    prompt = (req.prompt or messages_to_prompt(req.messages)).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(status_code=400, detail="Prompt is too large")
    job_id = str(uuid4())
    create_job_row(job_id, model)
    run_codex(job_id, model=model, prompt=prompt, workspace=workspace, sandbox=sandbox, ephemeral=req.ephemeral, reasoning_effort=req.reasoning_effort)
    row = get_job(job_id) or {}
    final = (job_dir(job_id) / "final.txt").read_text(encoding="utf-8", errors="replace") if (job_dir(job_id) / "final.txt").exists() else ""
    usage = {
        "prompt_tokens": int(row.get("input_tokens") or 0),
        "completion_tokens": int(row.get("output_tokens") or 0),
        "total_tokens": int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0),
        "prompt_tokens_details": {"cached_tokens": int(row.get("cached_tokens") or 0)},
        "completion_tokens_details": {"reasoning_tokens": int(row.get("reasoning_tokens") or 0)},
    }
    if row.get("status") != "succeeded":
        raise HTTPException(status_code=502, detail={"job_id": job_id, "status": row.get("status"), "error": row.get("error")})
    return JSONResponse({
        "id": f"chatcmpl-{job_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": f"codexexecapi:{model}",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": final}, "finish_reason": "stop"}],
        "usage": usage,
    })


@APP.get("/jobs/{job_id}")
def job_status(job_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    auth(authorization)
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return row
