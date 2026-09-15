#!/usr/bin/env python3
import os
import sys
import json
import time
import re
import shutil
import subprocess
import urllib.request
import psycopg2
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.model_manager import get_model_for_role

SKILL_MANIFEST: Dict[str, Any] = {
    "intent": "auto_exec",
    "description": "Executa comandos bash no terminal Linux com auto-healing estruturado.",
    "allowed_actions": ["execute"],
    "keywords": ["bash", "comando", "sistema", "hardware", "terminal", "arquivos", "nome do computador", "ip"],
    "script": "skills/auto_exec.py"
}

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL: str = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_EMBED_URL: str = f"{OLLAMA_BASE_URL}/api/embeddings"
MODEL_LLM: str = get_model_for_role("complex", default="qwen2.5-coder:3b", env_var="OLLAMA_LLM_MODEL")
MODEL_EMBED: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_NAME: str = os.getenv("DB_NAME", "postgres")
DB_USER: str = os.getenv("DB_USER", "postgres")
DB_PASS: str = os.getenv("DB_PASS", "root")

MAX_RETRIES: int = 3
DEFAULT_TIMEOUT_SECONDS: int = 200
LOG_DIR: str = os.path.join(PROJECT_ROOT, "memory")
LOG_FILE: str = os.path.join(LOG_DIR, "execution_trace.jsonl")
TROUBLESHOOTING_FILE: str = os.path.join(LOG_DIR, "troubleshooting.md")

SOUND_PATH: str = "/usr/share/sounds/freedesktop/stereo/service-logout.oga"

# Estilização ANSI
C_GREEN: str = "\033[1;32m"
C_CYAN: str = "\033[1;36m"
C_YELLOW: str = "\033[1;33m"
C_RED: str = "\033[1;31m"
C_RESET: str = "\033[0m"


def play_completion_sound(sound_path: str = SOUND_PATH) -> None:
    """Dispara efeito sonoro em background sem bloquear o runtime."""
    if shutil.which("paplay"):
        cmd = ["paplay", sound_path]
    elif shutil.which("canberra-gtk-play"):
        cmd = ["canberra-gtk-play", "-f", sound_path]
    elif shutil.which("ffplay"):
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", sound_path]
    else:
        return

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def get_embedding(text: str) -> List[float]:
    """Gera embeddings via Ollama API."""
    payload = {"model": MODEL_EMBED, "prompt": text[:4000]}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("embedding", [])
    except Exception:
        return []


def retrieve_rag_context(query: str, limit: int = 3) -> str:
    """Recupera contexto episódico da base vetorial PostgreSQL."""
    embedding = get_embedding(query)
    if not embedding:
        return ""

    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cur = conn.cursor()
        sql = """
            SELECT file_path, content, 1 - (embedding <=> %s::vector) AS similarity
            FROM document_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        cur.execute(sql, (str(embedding), str(embedding), limit))
        results = cur.fetchall()
        cur.close()
        conn.close()

        context_blocks = []
        for file_path, content, score in results:
            if score >= 0.5:
                context_blocks.append(f"--- Fonte: {file_path} (Relevância: {score:.2f}) ---\n{content}")
        return "\n\n".join(context_blocks)
    except Exception as e:
        print(f"{C_YELLOW}[!] Alerta RAG: {e}. Prosseguindo sem contexto.{C_RESET}")
        return ""


def save_learned_fix(task: str, failed_attempt: Dict[str, Any], successful_command: str) -> None:
    """Registra soluções aprendidas no histórico de troubleshooting."""
    os.makedirs(LOG_DIR, exist_ok=True)
    entry = f"""
## Resolução de Problema - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Tarefa**: {task}
- **Comando que Falhou**: `{failed_attempt.get('generated_command', '')}`
- **Erro (STDERR)**: {str(failed_attempt.get('stderr', '')).strip()}
- **Solução Validada**: `{successful_command}`

---
"""
    with open(TROUBLESHOOTING_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

    try:
        ingest_script = os.path.join(PROJECT_ROOT, "skills", "ingest_docs.py")
        if os.path.exists(ingest_script):
            subprocess.run([sys.executable, ingest_script, LOG_DIR], check=True, stdout=subprocess.DEVNULL)
            print(f"{C_GREEN}[✓] Aprendizado gravado e re-indexado na memória episódica.{C_RESET}")
    except Exception as e:
        print(f"{C_YELLOW}[!] Falha ao re-indexar aprendizado: {e}{C_RESET}")


def call_qwen(prompt: str) -> Dict[str, Any]:
    """Chama o modelo Ollama configurado."""
    payload = {
        "model": MODEL_LLM,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192}
    }
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            res = json.loads(response.read().decode("utf-8"))
            return {
                "response": res.get("response", "").strip(),
                "prompt_tokens": res.get("prompt_eval_count", 0),
                "completion_tokens": res.get("eval_count", 0),
                "total_duration_ms": round((res.get("total_duration", 0) or 0) / 1e6, 2)
            }
    except Exception as e:
        print(f"{C_RED}[✗] Erro na requisição ao Ollama ({OLLAMA_GENERATE_URL}): {e}{C_RESET}")
        sys.exit(1)


def parse_llm_json(response_text: str) -> Dict[str, Any]:
    """Parse resiliente de JSON para respostas de modelos pequenos."""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Fallback de emergência caso venha bash bruto
        clean_cmd = response_text.replace("```bash", "").replace("```json", "").replace("```", "").strip()
        return {
            "analysis": "Execução direta gerada via fallback de parse.",
            "command": clean_cmd,
            "status": "EXECUTE"
        }


def run_command(command: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Tuple[int, str, str]:
    """Executa um comando Bash no sistema com isolamento e timeout."""
    start_t = time.time()
    print(f"\n{C_CYAN}┌─── [ BASH EXECUTION ] ──────────────────────────────────────────────┐{C_RESET}")
    print(f"{C_CYAN}│ $ {command}{C_RESET}")
    print(f"{C_CYAN}└─────────────────────────────────────────────────────────────────────┘{C_RESET}")

    full_cmd = f"set -o pipefail; {command}"

    try:
        process = subprocess.Popen(
            full_cmd,
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(timeout=timeout)
        elapsed = round(time.time() - start_t, 2)
        print(f"{C_GREEN}[✓] Executado em {elapsed}s (Exit Code: {process.returncode}){C_RESET}")
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        err_msg = (stderr or "") + f"\n⚠️ [TIMEOUT] Processo interrompido após exceder {timeout}s."
        return 124, stdout or "", err_msg


def log_trace(trace_data: Dict[str, Any]) -> None:
    """Grava o log de execução no arquivo de trace."""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace_data, ensure_ascii=False) + "\n")


def print_metrics(trace: Dict[str, Any]) -> None:
    """Exibe painel ANSI formatado com resumo da execução."""
    total_tokens = trace["total_prompt_tokens"] + trace["total_completion_tokens"]
    
    if trace['status'] == "SUCCESS":
        status_icon = "✓ SUCCESS"
        status_color = C_GREEN
    elif trace['status'] == "NEED_HUMAN":
        status_icon = "⚠ NEED_HUMAN"
        status_color = C_YELLOW
    else:
        status_icon = "✗ FAILED"
        status_color = C_RED

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


def auto_heal(task_description: str) -> Tuple[bool, Dict[str, Any]]:
    """Loop principal de auto-healing e execução atômica."""
    print(f"{C_GREEN}[+] Auto-Exec ativado para a meta: '{task_description}'{C_RESET}")
    rag_context = retrieve_rag_context(task_description)

    trace: Dict[str, Any] = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "task": task_description,
        "model": MODEL_LLM,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "attempts": [],
        "status": "IN_PROGRESS"
    }

    system_rules = f"""Você é o Agente de Auto-Healing e Execução Linux do Wygor Core.
Analise a tarefa ou o erro recebido e responda EXCLUSIVAMENTE em JSON CRU (sem marcações markdown).

[REGRAS DE EXECUÇÃO]
- NÍVEL 1 (Inspeção): Comando Bash direto e atômico.
- NÍVEL 2 (Lógica/Parsing): Script Python em '/tmp/script_wygor.py' executado via Bash (`cat << 'EOF' > /tmp/script_wygor.py ... EOF && python3 /tmp/script_wygor.py`).
- NÍVEL 3 (Intervenção Necessária): Se o erro exigir decisão do usuário, credenciais indisponíveis ou refatoração profunda de projeto, defina status como "NEED_HUMAN".
- PostgreSQL: Use 'PGPASSWORD={DB_PASS}' especificando '-h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME}'.

[SAÍDA OBRIGATÓRIA - ESTRUTURA JSON]
{{
  "analysis": "Diagnóstico em 1 frase concisa",
  "command": "comando_bash_executavel",
  "status": "EXECUTE" | "NEED_HUMAN"
}}"""

    context_prompt = f"\n\nCONTEXTO DO PROJETO RECUPERADO (RAG):\n{rag_context}" if rag_context else ""
    prompt = f"{system_rules}{context_prompt}\n\nTAREFA: {task_description}"

    for attempt_num in range(1, MAX_RETRIES + 1):
        if attempt_num > 1:
            print(f"{C_YELLOW}[!] Tentativa {attempt_num}/{MAX_RETRIES}...{C_RESET}")

        qwen_res = call_qwen(prompt)
        payload = parse_llm_json(qwen_res["response"])

        analysis: str = payload.get("analysis", "Analisando instrução...")
        command: str = payload.get("command", "").strip()
        status: str = payload.get("status", "EXECUTE")

        trace["total_prompt_tokens"] += qwen_res["prompt_tokens"]
        trace["total_completion_tokens"] += qwen_res["completion_tokens"]

        print(f"\n{C_YELLOW}[DIAGNÓSTICO]: {analysis}{C_RESET}")

        # Interrupção graciosa se o modelo solicitar ação humana
        if status == "NEED_HUMAN" or not command:
            print(f"{C_RED}[!] Interrupção: Intervenção manual solicitada pelo motor de execução.{C_RESET}")
            trace["status"] = "NEED_HUMAN"
            attempt_record = {
                "attempt": attempt_num,
                "analysis": analysis,
                "generated_command": command,
                "returncode": -1,
                "stdout": "",
                "stderr": "HUMAN_INTERVENTION_REQUESTED",
                "tokens": {"prompt": qwen_res["prompt_tokens"], "completion": qwen_res["completion_tokens"]},
                "duration_ms": qwen_res["total_duration_ms"]
            }
            trace["attempts"].append(attempt_record)
            log_trace(trace)
            print_metrics(trace)
            return False, trace

        returncode, stdout, stderr = run_command(command)

        attempt_record = {
            "attempt": attempt_num,
            "analysis": analysis,
            "generated_command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "tokens": {"prompt": qwen_res["prompt_tokens"], "completion": qwen_res["completion_tokens"]},
            "duration_ms": qwen_res["total_duration_ms"]
        }
        trace["attempts"].append(attempt_record)

        if stdout:
            print(f"{C_GREEN}[STDOUT]:\n{stdout}{C_RESET}")

        if returncode == 0 and "FATAL:" not in stderr and "ERROR:" not in stderr:
            trace["status"] = "SUCCESS"
            if attempt_num > 1:
                save_learned_fix(task_description, trace["attempts"][0], command)

            log_trace(trace)
            print_metrics(trace)
            play_completion_sound()
            return True, trace
        else:
            if stderr:
                print(f"{C_RED}[STDERR]:\n{stderr}{C_RESET}")

            prompt = f"""{system_rules}{context_prompt}

O comando abaixo FALHOU ao ser executado:
Comando Anterior: {command}
Código de Saída: {returncode}
Erro / STDERR:
{stderr}
Saída / STDOUT:
{stdout}

Forneça um novo JSON com a análise atualizada do erro e o comando corrigido."""

    trace["status"] = "FAILED"
    log_trace(trace)
    print_metrics(trace)
    return False, trace


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 skills/auto_exec.py 'descrição da tarefa'")
        sys.exit(1)

    task_input = " ".join(sys.argv[1:])
    auto_heal(task_input)