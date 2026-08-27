#!/usr/bin/env python3
import os
import sys
import json
import time
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_LOG_DIR = os.path.join(PROJECT_ROOT, "memory")
TRACE_LOG_FILE = os.path.join(TRACE_LOG_DIR, "llm_raw_traces.jsonl")
DEFAULT_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))

def _write_trace(trace_entry):
    """Grava o histórico bruto de requisições e respostas JSON em arquivo local."""
    if not os.path.exists(TRACE_LOG_DIR):
        os.makedirs(TRACE_LOG_DIR, exist_ok=True)
    with open(TRACE_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")

def call_llm(endpoint, payload, caller="unknown", session_id=None, project_name="igor_core", timeout=DEFAULT_TIMEOUT):
    """
    Wrapper HTTP centralizado do Ollama com interceptação total do tráfego (LLM Tracer).
    """
    # Força modo não-stream para evitar erro de parse JSON múltiplo
    if "stream" not in payload:
        payload["stream"] = False

    url = f"{OLLAMA_BASE_URL}{endpoint}"
    start_time = time.time()

    trace_record = {
        "timestamp": datetime.now().isoformat(),
        "project_name": project_name,
        "session_id": session_id,
        "caller": caller,
        "endpoint": endpoint,
        "url": url,
        "request_payload": payload,
        "raw_response": None,
        "duration_ms": 0,
        "status": "PENDING",
        "error": None
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            trace_record["raw_response"] = res_json
            trace_record["duration_ms"] = duration_ms
            trace_record["status"] = "SUCCESS"

            _write_trace(trace_record)
            return True, res_json, None

    except Exception as e:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        err_msg = str(e)
        trace_record["duration_ms"] = duration_ms
        trace_record["status"] = "ERROR"
        trace_record["error"] = err_msg

        _write_trace(trace_record)
        return False, None, err_msg