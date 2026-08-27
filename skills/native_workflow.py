#!/usr/bin/env python3
"""Executor Nativo de Sistema (Spec 002) - Wygor Core.

Skill que permite ao agente utilizar utilitarios nativos da maquina (ssh,
journalctl, ps, top, curl, tar, rsync) via pipelines de comandos Bash nativos,
em malha fechada com ciclo de auto-healing, reexecucao e analise de fallbacks.

Etapas:
  1. Mapear executaveis disponiveis no ambiente local (which <binary>).
  2. Executar o pipeline Bash nativo.
  3. Analisar saida/saida de erro e reexecutar corrigindo (auto-healing).
  4. Registrar o historico na tabela native_execution_logs.
"""

import os
import sys
import json
import shutil
import subprocess
import argparse
import re
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from utils.db_service import get_model_for_role

SKILL_MANIFEST = {
    "intent": "native_workflow",
    "description": "Gera e executa pipelines de comandos Bash nativos (ssh, journalctl, ps, top, curl, tar, rsync) com ciclo de auto-healing, reexecucao e analise de fallbacks.",
    "keywords": ["executar comando nativo", "pipelines bash", "auto healing", "usa ssh", "executar bash", "ferramentas nativas", "executar curl", "executar comando"],
    "allowed_actions": ["run", "check", "history"],
    "script": "skills/native_workflow.py"
}

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

MAX_RETRIES = 3

# Binarios nativos tipicos que a skill sabe mapear
USEFUL_BINARIES = [
    "ssh", "scp", "rsync", "tar", "curl", "journalctl", "ps", "top", "htop",
    "systemctl", "pgrep", "kill", "ping", "ss", "df", "free", "grep", "awk", "sed"
]


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    except Exception as e:
        print(f"ERRO conexao: {e}", file=sys.stderr)
        return None


def map_binaries():
    """Mapeia executaveis disponiveis no ambiente local via `which`/shutil.which."""
    available = {}
    missing = []
    for binary in USEFUL_BINARIES:
        path = shutil.which(binary)
        if path:
            available[binary] = path
        else:
            missing.append(binary)
    return available, missing


def run_pipeline(command):
    """Executa um pipeline Bash nativo com pipefail e captura saida/erro/tempo."""
    full = f"set -o pipefail; {command}"
    start = datetime.now()
    try:
        res = subprocess.run(
            full, shell=True, executable="/bin/bash",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return 124, "(timeout)", "(comando excedeu 60s)", round((datetime.now() - start).total_seconds() * 1000)
    except Exception as e:
        return 1, "", f"(falha ao executar: {e})", 0
    duration = round((datetime.now() - start).total_seconds() * 1000)
    return res.returncode, res.stdout, res.stderr, duration


def log_execution(pipeline, exit_code, duration_ms, attempts, output, error, status):
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO native_execution_logs
            (pipeline, exit_code, duration_ms, attempts, output, error, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (pipeline, exit_code, duration_ms, attempts, output[:2000], error[:2000], status))
        conn.commit()
    except Exception as e:
        if "UndefinedTable" in str(e) or "does not exist" in str(e):
            print("ERR_MISSING_TABLE: Tabela 'native_execution_logs' ausente.", file=sys.stderr)
        else:
            print(f"ERRO log execucao: {e}", file=sys.stderr)
    finally:
        cur.close(); conn.close()


def analyze_fallback(command, exit_code, stderr):
    """Sugere fallbacks comuns com base no erro e binario ausente."""
    hints = []
    low = (stderr or "").lower()
    if "command not found" in low or "no such file" in low:
        hints.append("Possivel binario ausente: verifique com `which` ou instale o pacote.")
    if "permission denied" in low or "denied" in low:
        hints.append("Possivel problema de permissao/autenticacao. Verifique usuario e chaves SSH.")
    if "ssh" in command and exit_code != 0:
        hints.append("Falha de SSH: verifique hostname, porta, usuario e chave. Tente `ssh -vvv` para diagnosticar.")
    if "tar" in command and exit_code != 0:
        hints.append("Falha em tar: verifique flags e caminhos, ou use `--exclude` para contornar.")
    if "curl" in command and exit_code != 0:
        hints.append("Falha em curl: use `-L` (seguir redirects), `-k` (TLS) ou especifique `--retry`.")
    return hints


def check(project="default", raw=False):
    """Mapeia executaveis nativos disponiveis no ambiente."""
    available, missing = map_binaries()
    if raw:
        print(json.dumps({"available": available, "missing": missing}, ensure_ascii=False))
        return True
    print(f"\nNATIVAS DISPONIVEIS [{project}]:")
    for name, path in available.items():
        print(f"  ✓ {name} -> {path}")
    if missing:
        print("AUSENTES:", ", ".join(missing))
    return True


def history(limit=20, raw=False):
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, executed_at, pipeline, exit_code, attempts, status FROM native_execution_logs ORDER BY executed_at DESC LIMIT %s;", (limit,))
        rows = cur.fetchall()
    except Exception as e:
        print(f"ERRO historico: {e}", file=sys.stderr); return
    finally:
        cur.close(); conn.close()

    for r in rows:
        if raw:
            print(json.dumps({"id": r[0], "pipeline": r[2], "exit": r[3], "attempts": r[4], "status": r[5]}, ensure_ascii=False))
        else:
            print(f"[#{r[0]}] {r[1]} status={r[5]} exit={r[3]} tentativas={r[4]}")


def run(command, project="default", raw=False):
    """Executa um pipeline Bash nativo com ciclo de auto-healing e fallback."""
    if not command or not command.strip():
        print("Informe um comando Bash nativo.", file=sys.stderr)
        return False

    print(f"[[ Executor Nativo ]] comando: {command}")

    exit_code, stdout, stderr, duration = run_pipeline(command)
    attempts = 1
    final_status = "success"

    # Loop de auto-healing / reexecucao
    while exit_code != 0 and attempts < MAX_RETRIES:
        attempts += 1
        print(f"tentativa {attempts}/{MAX_RETRIES} - reexecutando com fallback...")
        # Aplica small adjustments comuns (seguir redirects no curl)
        adjusted = command
        if "curl " in adjusted and "-L" not in adjusted:
            adjusted = adjusted.replace("curl ", "curl -L ")
        if "ssh " in adjusted and "-o BatchMode=yes" not in adjusted:
            adjusted = adjusted.replace("ssh ", "ssh -o BatchMode=yes ")
        adjusted = adjusted.replace("curl ", "curl --retry 2 ")
        exit_code, stdout, stderr, duration = run_pipeline(adjusted)
        command = adjusted
        final_status = "healed" if exit_code == 0 else "failed"

    log_execution(command, exit_code, duration, attempts, stdout, stderr, final_status)

    if raw:
        print(json.dumps({"exit": exit_code, "stdout": stdout, "stderr": stderr, "attempts": attempts, "status": final_status}, ensure_ascii=False))
        return exit_code == 0

    print(f"status={final_status} exit={exit_code} tentativas={attempts} duracao={duration}ms")
    if stdout:
        print("--- STDOUT ---"); print(stdout)
    if stderr:
        print("--- STDERR ---"); print(stderr)
    if exit_code != 0:
        for hint in analyze_fallback(command, exit_code, stderr):
            print(f"  fallback: {hint}")
    return exit_code == 0


OLLAMA_GENERATE_URL = f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/generate"
NATIVE_MODEL = get_model_for_role("intermediate", default="qwen2.5-coder:3b", env_var="OLLAMA_LLM_MODEL")


def _load_native_prompt(available_binaries_text, instruction):
    """Carrega o template de prompt do executor nativo via prompt_loader."""
    try:
        import importlib.util
        proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if proj_root not in sys.path:
            sys.path.insert(0, proj_root)
        from utils.prompt_loader import load_prompt
        return load_prompt(
            "native_workflow_system.txt",
            available_binaries=available_binaries_text,
            user_instruction=instruction
        )
    except (FileNotFoundError, ImportError):
        # fallback direto caso o template nao exista
        return (
            "Traduza a instrucao em um pipeline bash nativo (ssh, curl, tar, journalctl, ps, top). "
            "Binarios disponiveis: %s\nInstrucao: %s\nResponda apenas com o comando bash."
        ) % (available_binaries_text, instruction)


def _extract_command_from_llm(raw_response):
    """Extrai o campo `command` do JSON retornado pelo LLM.

    Tolerante a: code fences markdown (```json/```bash), texto antes/depois do
    JSON e respostas que já vêm como comando puro (fallback).
    """
    text = raw_response.strip()
    # Remove code fences markdown (ex.: ```json ... ``` ou ```bash ... ```)
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"```$", "", text).strip()
    # Tenta parsear o texto inteiro como JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("command"), data
    except json.JSONDecodeError:
        pass
    # Procura o primeiro bloco {...} (JSON embutido em texto)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data.get("command"), data
        except json.JSONDecodeError:
            pass
    # Fallback: resposta não-JSON é tratada como o próprio comando
    return text, None


def generate_command(instruction, project="default"):
    """Gera um pipeline Bash nativo a partir de uma instrucao usando a LLM local."""
    available, _missing = map_binaries()
    avail_text = ", ".join(f"{n}->{p}" for n, p in available.items()) or "(nenhum binario mapeado)"
    prompt = _load_native_prompt(avail_text, instruction)

    payload = {"model": NATIVE_MODEL, "prompt": prompt, "stream": False,
               "options": {"temperature": 0.1}}
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            cmd, data = _extract_command_from_llm(res.get("response", ""))
            if data and data.get("status") == "FAILED":
                print(f"LLM reportou FAILED: {data.get('reasoning', '')}", file=sys.stderr)
                return None
            return cmd if cmd else None
    except Exception as e:
        print(f"ERRO gerar comando via LLM: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executor Nativo de Sistema Wygor Core")
    parser.add_argument("action", nargs="?", default="run", choices=["run", "check", "history"])
    parser.add_argument("-c", "--command", default=None, help="Pipeline Bash nativo a executar")
    parser.add_argument("--instruction", default=None, help="Instrucao em linguagem natural para gerar o comando via LLM")
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args()

    if args.action == "run":
        if args.instruction:
            cmd = generate_command(args.instruction, project=args.project)
            if not cmd:
                print("Nao foi possivel gerar comando via instrucao.", file=sys.stderr)
                sys.exit(1)
            print(f"Comando gerado pela LLM: {cmd}")
            run(cmd, project=args.project, raw=args.raw)
        elif args.command:
            run(args.command, project=args.project, raw=args.raw)
        else:
            print("Informe --command <comando bash> ou --instruction <instrucao>.", file=sys.stderr)
            sys.exit(1)
    elif args.action == "check":
        check(args.project, raw=args.raw)
    elif args.action == "history":
        history(limit=args.limit, raw=args.raw)
