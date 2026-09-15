#!/usr/bin/env python3
"""
Wygor Core :: Skill de Execução Autônoma (auto_exec)
====================================================

Executa comandos Bash no sistema operacional com loop de auto-healing
estruturado, recuperação de contexto episódico via pgvector e persistência
de soluções aprendidas.

Arquitetura:
    NL → LLM → JSON → Bash → SO → Trace → (sucesso | re-prompt com erro)

Compatibilidade: Python 3.10+ (uso de TypedDict com NotRequired e Literal).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from typing import Any, Final, Literal, TypedDict

import psycopg2
from dotenv import load_dotenv

try:
    from typing import NotRequired
except ImportError:  # pragma: no cover - Python < 3.11
    from typing_extensions import NotRequired  # type: ignore[assignment]

load_dotenv()

PROJECT_ROOT: Final[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.model_manager import get_model_for_role  # noqa: E402


# --------------------------------------------------------------------------- #
# CONTRATOS (TypedDict)                                                        #
# --------------------------------------------------------------------------- #

ExecutionStatus = Literal["IN_PROGRESS", "SUCCESS", "FAILED", "NEED_HUMAN"]
LLMDecisionStatus = Literal["EXECUTE", "NEED_HUMAN"]


class TokenUsage(TypedDict):
    """Contabilização de tokens consumidos em uma chamada ao LLM."""

    prompt: int
    completion: int


class LLMPayload(TypedDict):
    """Estrutura retornada pelo parse da resposta do LLM."""

    analysis: str
    command: str
    status: LLMDecisionStatus


class LLMResponse(TypedDict):
    """Resposta estruturada do cliente HTTP do Ollama."""

    response: str
    prompt_tokens: int
    completion_tokens: int
    total_duration_ms: float
    ok: bool
    error: NotRequired[str]


class AttemptRecord(TypedDict):
    """Registro atômico de uma tentativa de execução."""

    attempt: int
    analysis: str
    generated_command: str
    returncode: int
    stdout: str
    stderr: str
    tokens: TokenUsage
    duration_ms: float


class ExecutionTrace(TypedDict):
    """Trace completo de uma execução do auto_heal."""

    id: str
    timestamp: str
    task: str
    model: str
    total_prompt_tokens: int
    total_completion_tokens: int
    attempts: list[AttemptRecord]
    status: ExecutionStatus


class SkillManifest(TypedDict):
    """Contrato de registro da skill no catálogo do Wygor Core."""

    intent: str
    description: str
    allowed_actions: list[str]
    keywords: list[str]
    script: str


# --------------------------------------------------------------------------- #
# CONFIGURAÇÃO                                                                 #
# --------------------------------------------------------------------------- #

SKILL_MANIFEST: Final[SkillManifest] = {
    "intent": "auto_exec",
    "description": "Executa comandos bash no terminal Linux com auto-healing estruturado.",
    "allowed_actions": ["execute"],
    "keywords": [
        "bash", "comando", "sistema", "hardware", "terminal",
        "arquivos", "nome do computador", "ip",
    ],
    "script": "skills/auto_exec.py",
}

OLLAMA_BASE_URL: Final[str] = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL: Final[str] = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_EMBED_URL: Final[str] = f"{OLLAMA_BASE_URL}/api/embeddings"

MODEL_LLM: Final[str] = get_model_for_role(
    "complex", default="qwen2.5-coder:3b", env_var="OLLAMA_LLM_MODEL"
)
MODEL_EMBED: Final[str] = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

DB_HOST: Final[str] = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT: Final[str] = os.getenv("DB_PORT", "5432")
DB_NAME: Final[str] = os.getenv("DB_NAME", "postgres")
DB_USER: Final[str] = os.getenv("DB_USER", "postgres")
DB_PASS: Final[str] = os.getenv("DB_PASS", "root")

MAX_RETRIES: Final[int] = 3
DEFAULT_TIMEOUT_SECONDS: Final[int] = 200
LOG_DIR: Final[str] = os.path.join(PROJECT_ROOT, "memory")
LOG_FILE: Final[str] = os.path.join(LOG_DIR, "execution_trace.jsonl")
TROUBLESHOOTING_FILE: Final[str] = os.path.join(LOG_DIR, "troubleshooting.md")
LOG_ROTATION_MAX_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
LOG_ROTATION_BACKUPS: Final[int] = 5

SOUND_PATH: Final[str] = "/usr/share/sounds/freedesktop/stereo/service-logout.oga"

# Estilização ANSI
C_GREEN: Final[str] = "\033[1;32m"
C_CYAN: Final[str] = "\033[1;36m"
C_YELLOW: Final[str] = "\033[1;33m"
C_RED: Final[str] = "\033[1;31m"
C_RESET: Final[str] = "\033[0m"

# Whitelist de segurança: padrões destrutivos bloqueados antes de chegar ao shell.
DANGEROUS_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|/\*|~|\$HOME)(\s|$)"),
    re.compile(r"\bmkfs(\.\w+)?\b"),
    re.compile(r"\bdd\s+.*of=/dev/(sd|nvme|hd)"),
    re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"),           # fork bomb
    re.compile(r">\s*/dev/(sd|nvme|hd)\w+"),
    re.compile(r"\bchmod\s+-R\s+777\s+/\b"),
    re.compile(r"\bcurl\s+[^\|]*\|\s*(bash|sh)\b"),
    re.compile(r"\bwget\s+[^\|]*\|\s*(bash|sh)\b"),
)


# --------------------------------------------------------------------------- #
# UTILITÁRIOS                                                                  #
# --------------------------------------------------------------------------- #

def play_completion_sound(sound_path: str = SOUND_PATH) -> None:
    """Dispara efeito sonoro em background sem bloquear o runtime."""
    if shutil.which("paplay"):
        cmd: list[str] = ["paplay", sound_path]
    elif shutil.which("canberra-gtk-play"):
        cmd = ["canberra-gtk-play", "-f", sound_path]
    elif shutil.which("ffplay"):
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", sound_path]
    else:
        return

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _ensure_log_dir() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)


def _rotate_log_if_needed() -> None:
    """Rotaciona execution_trace.jsonl mantendo N backups comprimidos por sufixo."""
    if not os.path.exists(LOG_FILE):
        return
    if os.path.getsize(LOG_FILE) < LOG_ROTATION_MAX_BYTES:
        return

    for idx in range(LOG_ROTATION_BACKUPS - 1, 0, -1):
        src = f"{LOG_FILE}.{idx}"
        dst = f"{LOG_FILE}.{idx + 1}"
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)

    oldest = f"{LOG_FILE}.1"
    if os.path.exists(oldest):
        os.remove(oldest)
    os.rename(LOG_FILE, oldest)


def _is_dangerous(command: str) -> tuple[bool, str]:
    """Verifica se um comando dispara um padrão destrutivo conhecido."""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True, pattern.pattern
    return False, ""


# --------------------------------------------------------------------------- #
# RAG / MEMÓRIA EPISÓDICA                                                      #
# --------------------------------------------------------------------------- #

def get_embedding(text: str) -> list[float]:
    """Gera embeddings via Ollama API. Retorna lista vazia em caso de falha."""
    payload: dict[str, Any] = {"model": MODEL_EMBED, "prompt": text[:4000]}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            embedding = res.get("embedding", [])
            return list(embedding) if isinstance(embedding, list) else []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []


def retrieve_rag_context(query: str, limit: int = 3) -> str:
    """Recupera contexto episódico da base vetorial PostgreSQL/pgvector."""
    embedding = get_embedding(query)
    if not embedding:
        return ""

    vector_literal = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"

    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASS,
        )
        try:
            cur = conn.cursor()
            sql = """
                SELECT file_path, content, 1 - (embedding <=> %s::vector) AS similarity
                FROM document_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            cur.execute(sql, (vector_literal, vector_literal, limit))
            results: list[tuple[str, str, float]] = cur.fetchall()
            cur.close()
        finally:
            conn.close()

        blocks: list[str] = [
            f"--- Fonte: {file_path} (Relevância: {score:.2f}) ---\n{content}"
            for file_path, content, score in results
            if score >= 0.5
        ]
        return "\n\n".join(blocks)
    except psycopg2.Error as exc:
        print(f"{C_YELLOW}[!] Alerta RAG (DB): {exc}. Prosseguindo sem contexto.{C_RESET}")
        return ""


def save_learned_fix(
    task: str,
    failed_attempt: AttemptRecord,
    successful_command: str,
) -> None:
    """Registra soluções aprendidas no histórico de troubleshooting e re-indexa."""
    _ensure_log_dir()
    entry = f"""
## Resolução de Problema - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Tarefa**: {task}
- **Comando que Falhou**: `{failed_attempt.get('generated_command', '')}`
- **Erro (STDERR)**: {str(failed_attempt.get('stderr', '')).strip()}
- **Solução Validada**: `{successful_command}`

---
"""
    with open(TROUBLESHOOTING_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry)

    try:
        ingest_script = os.path.join(PROJECT_ROOT, "skills", "ingest_docs.py")
        if os.path.exists(ingest_script):
            subprocess.run(
                [sys.executable, ingest_script, LOG_DIR],
                check=True, stdout=subprocess.DEVNULL,
            )
            print(f"{C_GREEN}[✓] Aprendizado gravado e re-indexado.{C_RESET}")
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"{C_YELLOW}[!] Falha ao re-indexar aprendizado: {exc}{C_RESET}")


# --------------------------------------------------------------------------- #
# INFERÊNCIA LLM                                                               #
# --------------------------------------------------------------------------- #

def call_qwen(prompt: str) -> LLMResponse:
    """Chama o modelo Ollama. Retorna estrutura com flag `ok` em vez de matar o processo."""
    payload: dict[str, Any] = {
        "model": MODEL_LLM,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            res: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return LLMResponse(
            response=str(res.get("response", "")).strip(),
            prompt_tokens=int(res.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(res.get("eval_count", 0) or 0),
            total_duration_ms=round(float(res.get("total_duration", 0) or 0) / 1e6, 2),
            ok=True,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"{C_RED}[✗] Erro na requisição ao Ollama ({OLLAMA_GENERATE_URL}): {exc}{C_RESET}")
        return LLMResponse(
            response="", prompt_tokens=0, completion_tokens=0,
            total_duration_ms=0.0, ok=False, error=str(exc),
        )


def parse_llm_json(response_text: str) -> LLMPayload:
    """Parse resiliente de JSON para respostas de modelos pequenos (3 camadas)."""
    # Camada 1: JSON estrito
    try:
        data = json.loads(response_text)
        if isinstance(data, dict) and "command" in data:
            return LLMPayload(
                analysis=str(data.get("analysis", "")),
                command=str(data.get("command", "")),
                status=_normalize_status(data.get("status", "EXECUTE")),
            )
    except json.JSONDecodeError:
        pass

    # Camada 2: extração por regex não-guloso
    match = re.search(r"\{.*?\}", response_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return LLMPayload(
                    analysis=str(data.get("analysis", "Análise extraída via regex.")),
                    command=str(data.get("command", "")),
                    status=_normalize_status(data.get("status", "EXECUTE")),
                )
        except json.JSONDecodeError:
            pass

    # Camada 3: fallback de bash cru (limpa cercas markdown)
    clean_cmd = (
        response_text
        .replace("```bash", "").replace("```json", "").replace("```", "")
        .strip()
    )
    return LLMPayload(
        analysis="Execução direta via fallback de parse.",
        command=clean_cmd,
        status="EXECUTE",
    )


def _normalize_status(value: Any) -> LLMDecisionStatus:
    """Normaliza o campo `status` para o literal esperado."""
    if isinstance(value, str) and value.strip().upper() == "NEED_HUMAN":
        return "NEED_HUMAN"
    return "EXECUTE"


# --------------------------------------------------------------------------- #
# EXECUÇÃO DE COMANDOS                                                         #
# --------------------------------------------------------------------------- #

def run_command(
    command: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, str, str]:
    """Executa um comando Bash com isolamento, whitelist e timeout."""
    blocked, pattern = _is_dangerous(command)
    if blocked:
        err = f"[BLOCKED] Comando bloqueado por whitelist de segurança (padrão: {pattern})"
        print(f"{C_RED}{err}{C_RESET}")
        return 126, "", err

    start_t = time.time()
    print(f"\n{C_CYAN}┌─── [ BASH EXECUTION ] ──────────────────────────────────────────────┐{C_RESET}")
    print(f"{C_CYAN}│ $ {command}{C_RESET}")
    print(f"{C_CYAN}└─────────────────────────────────────────────────────────────────────┘{C_RESET}")

    full_cmd = f"set -o pipefail; {command}"
    process = subprocess.Popen(
        full_cmd,
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        stderr = (stderr or "") + f"\n⚠ [TIMEOUT] Processo interrompido após {timeout}s."
        returncode = 124
    else:
        returncode = process.returncode

    elapsed = round(time.time() - start_t, 2)
    print(f"{C_GREEN}[✓] Executado em {elapsed}s (Exit Code: {returncode}){C_RESET}")
    return returncode, stdout or "", stderr or ""


# --------------------------------------------------------------------------- #
# LOGGING / MÉTRICAS                                                           #
# --------------------------------------------------------------------------- #

def log_trace(trace_data: ExecutionTrace) -> None:
    """Grava o log de execução com rotação automática."""
    _ensure_log_dir()
    _rotate_log_if_needed()
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(trace_data, ensure_ascii=False) + "\n")


def print_metrics(trace: ExecutionTrace) -> None:
    """Exibe painel ANSI formatado com resumo da execução."""
    total_tokens = trace["total_prompt_tokens"] + trace["total_completion_tokens"]

    status_map: dict[ExecutionStatus, tuple[str, str]] = {
        "SUCCESS":    ("✓ SUCCESS", C_GREEN),
        "NEED_HUMAN": ("⚠ NEED_HUMAN", C_YELLOW),
        "FAILED":     ("✗ FAILED", C_RED),
        "IN_PROGRESS": ("… RUNNING", C_CYAN),
    }
    status_icon, status_color = status_map.get(trace["status"], ("? UNKNOWN", C_RESET))

    border = "─" * 63
    print(f"\n{status_color}┌{border}┐{C_RESET}")
    print(f"{status_color}│ ░▒▓ WYGOR CORE ENGINE :: RUNTIME TRACE [{trace['id']}] ▓▒░ │{C_RESET}")
    print(f"{status_color}├{border}┤{C_RESET}")
    print(f"{status_color}│{C_RESET}  STATUS       : [ {status_color}{status_icon:<12}{C_RESET} ]                              │")
    print(f"{status_color}│{C_RESET}  MODEL        : {trace['model']:<44} │")
    print(f"{status_color}│{C_RESET}  ATTEMPTS     : {len(trace['attempts']):<44} │")
    print(f"{status_color}│{C_RESET}  TOTAL TOKENS : {total_tokens:<44} │")
    print(f"{status_color}│{C_RESET}  LOG FILE     : memory/execution_trace.jsonl                         │")
    print(f"{status_color}└{border}┘{C_RESET}\n")


# --------------------------------------------------------------------------- #
# NÚCLEO: AUTO-HEAL                                                            #
# --------------------------------------------------------------------------- #

def _build_system_rules() -> str:
    """Constrói o bloco de regras fixas (fora do loop para evitar inflação de prompt)."""
    return f"""Você é o Agente de Auto-Healing e Execução Linux do Wygor Core.
Analise a tarefa ou o erro recebido e responda EXCLUSIVAMENTE em JSON CRU (sem marcações markdown).

[REGRAS DE EXECUÇÃO]
- NÍVEL 1 (Inspeção): Comando Bash direto e atômico.
- NÍVEL 2 (Lógica/Parsing): Script Python em '/tmp/script_wygor.py' executado via Bash
  (`cat << 'EOF' > /tmp/script_wygor.py ... EOF && python3 /tmp/script_wygor.py`).
- NÍVEL 3 (Intervenção Necessária): Se o erro exigir decisão do usuário, credenciais
  indisponíveis ou refatoração profunda, defina status como "NEED_HUMAN".
- PostgreSQL: Use 'PGPASSWORD={shlex.quote(DB_PASS)}' especificando
  '-h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME}'.
- NUNCA emita comandos destrutivos (rm -rf /, mkfs, dd of=/dev/*, shutdown, reboot).

[SAÍDA OBRIGATÓRIA - ESTRUTURA JSON]
{{
  "analysis": "Diagnóstico em 1 frase concisa",
  "command": "comando_bash_executavel",
  "status": "EXECUTE" | "NEED_HUMAN"
}}"""


def _new_trace(task_description: str) -> ExecutionTrace:
    return ExecutionTrace(
        id=datetime.now().strftime("%Y%m%d_%H%M%S"),
        timestamp=datetime.now().isoformat(),
        task=task_description,
        model=MODEL_LLM,
        total_prompt_tokens=0,
        total_completion_tokens=0,
        attempts=[],
        status="IN_PROGRESS",
    )


def _record_attempt(
    trace: ExecutionTrace,
    attempt_num: int,
    analysis: str,
    command: str,
    returncode: int,
    stdout: str,
    stderr: str,
    tokens: TokenUsage,
    duration_ms: float,
) -> AttemptRecord:
    record = AttemptRecord(
        attempt=attempt_num,
        analysis=analysis,
        generated_command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        tokens=tokens,
        duration_ms=duration_ms,
    )
    trace["attempts"].append(record)
    return record


def auto_heal(task_description: str) -> tuple[bool, ExecutionTrace]:
    """Loop principal de auto-healing e execução atômica."""
    print(f"{C_GREEN}[+] Auto-Exec ativado para a meta: '{task_description}'{C_RESET}")
    rag_context = retrieve_rag_context(task_description)

    trace = _new_trace(task_description)
    system_rules = _build_system_rules()  # Construído UMA vez, fora do loop
    context_suffix = f"\n\nCONTEXTO DO PROJETO RECUPERADO (RAG):\n{rag_context}" if rag_context else ""

    dynamic_block = f"\n\nTAREFA: {task_description}"

    for attempt_num in range(1, MAX_RETRIES + 1):
        if attempt_num > 1:
            print(f"{C_YELLOW}[!] Tentativa {attempt_num}/{MAX_RETRIES}...{C_RESET}")

        prompt = f"{system_rules}{context_suffix}{dynamic_block}"
        qwen_res = call_qwen(prompt)

        if not qwen_res["ok"]:
            trace["status"] = "FAILED"
            _record_attempt(
                trace, attempt_num, qwen_res.get("error", "LLM indisponível"),
                "", -1, "", qwen_res.get("error", ""),
                TokenUsage(prompt=0, completion=0), 0.0,
            )
            log_trace(trace)
            print_metrics(trace)
            return False, trace

        payload = parse_llm_json(qwen_res["response"])
        analysis: str = payload["analysis"] or "Analisando instrução..."
        command: str = payload["command"].strip()
        status: LLMDecisionStatus = payload["status"]

        tokens = TokenUsage(
            prompt=qwen_res["prompt_tokens"],
            completion=qwen_res["completion_tokens"],
        )
        trace["total_prompt_tokens"] += tokens["prompt"]
        trace["total_completion_tokens"] += tokens["completion"]

        print(f"\n{C_YELLOW}[DIAGNÓSTICO]: {analysis}{C_RESET}")

        if status == "NEED_HUMAN":
            print(f"{C_RED}[!] Interrupção: Intervenção manual solicitada.{C_RESET}")
            trace["status"] = "NEED_HUMAN"
            _record_attempt(
                trace, attempt_num, analysis, command, -1, "",
                "HUMAN_INTERVENTION_REQUESTED", tokens,
                qwen_res["total_duration_ms"],
            )
            log_trace(trace)
            print_metrics(trace)
            return False, trace

        if not command:
            # Command vazio sem NEED_HUMAN explícito: força re-prompt em vez de abortar.
            print(f"{C_YELLOW}[!] LLM retornou comando vazio. Re-prompt forçado.{C_RESET}")
            _record_attempt(
                trace, attempt_num, analysis, "", -1, "",
                "EMPTY_COMMAND", tokens, qwen_res["total_duration_ms"],
            )
            dynamic_block = (
                f"\n\nTAREFA: {task_description}"
                "\n\nAVISO: Sua resposta anterior não continha o campo 'command'. "
                "Responda APENAS com o JSON no formato exigido, sem texto adicional."
            )
            continue

        returncode, stdout, stderr = run_command(command)
        _record_attempt(
            trace, attempt_num, analysis, command, returncode,
            stdout, stderr, tokens, qwen_res["total_duration_ms"],
        )

        if stdout:
            print(f"{C_GREEN}[STDOUT]:\n{stdout}{C_RESET}")

        if returncode == 0 and "FATAL:" not in stderr and "ERROR:" not in stderr:
            trace["status"] = "SUCCESS"
            if attempt_num > 1 and len(trace["attempts"]) >= 2:
                save_learned_fix(task_description, trace["attempts"][-2], command)
            log_trace(trace)
            print_metrics(trace)
            play_completion_sound()
            return True, trace

        if stderr:
            print(f"{C_RED}[STDERR]:\n{stderr}{C_RESET}")

        dynamic_block = (
            f"\n\nTAREFA ORIGINAL: {task_description}"
            f"\n\nO comando abaixo FALHOU ao ser executado:"
            f"\nComando Anterior: {command}"
            f"\nCódigo de Saída: {returncode}"
            f"\nErro / STDERR:\n{stderr}"
            f"\nSaída / STDOUT:\n{stdout}"
            "\n\nForneça um novo JSON com a análise atualizada do erro e o comando corrigido."
        )

    trace["status"] = "FAILED"
    log_trace(trace)
    print_metrics(trace)
    return False, trace


# --------------------------------------------------------------------------- #
# ENTRYPOINT                                                                   #
# --------------------------------------------------------------------------- #

def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python3 skills/auto_exec.py 'descrição da tarefa'")
        return 1
    task_input = " ".join(argv[1:])
    success, _ = auto_heal(task_input)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))