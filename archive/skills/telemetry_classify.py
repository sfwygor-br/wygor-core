#!/usr/bin/env python3
"""Classificador de Telemetria (Spec 002) - Wygor Core.

Job secundario que aciona o Wygor Core para classificar os erros coletados pelo
coletor de telemetria e os vetoriza na tabela document_chunks sob o escopo
system_telemetry, permitindo busca semantica (RAG) sobre logs de sistema.
"""

import os
import sys
import json
import argparse
import urllib.request
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from utils.db_service import get_model_for_role

SKILL_MANIFEST = {
    "intent": "telemetry_classify",
    "description": "Classifica os logs de erro coletados pela telemetria e os vetoriza na tabela document_chunks sob o escopo system_telemetry para busca semantica (RAG).",
    "keywords": ["classificar erros", "triagem de logs", "vetorizar logs", "analisar telemetria", "classificar telemetria"],
    "script": "skills/telemetry_classify.py"
}

OLLAMA_EMBED_URL = f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/embeddings"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

OLLAMA_GENERATE_URL = f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/generate"
CLASSIFY_MODEL = get_model_for_role("router", default="qwen2.5-coder:3b", env_var="OLLAMA_LLM_MODEL")


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    except Exception as e:
        print(f"ERRO conexao: {e}", file=sys.stderr)
        return None

def get_embedding(text):
    payload = {"model": EMBED_MODEL, "prompt": text[:4000]}
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

def fetch_unvectorized(window_hours):
    conn = get_connection()
    if not conn:
        return []
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, severity, signature, raw_message
            FROM system_telemetry_events
            WHERE scope='system_telemetry'
              AND collected_at >= CURRENT_TIMESTAMP - (%s::int * interval '1 hour')
            ORDER BY collected_at DESC
            LIMIT 100;
        """, (window_hours,))
        return cur.fetchall()
    except Exception as e:
        print(f"ERRO buscar eventos: {e}", file=sys.stderr)
        return []
    finally:
        cur.close(); conn.close()

def classify(project="default", window_hours=24, raw=False):
    """Le eventos de telemetria recentes, classifica e vetoriza no RAG (system_telemetry)."""
    rows = fetch_unvectorized(window_hours)
    if not rows:
        print("Nenhum evento de telemetria encontrado no escopo system_telemetry para classificar.")
        return True

    classified = 0

    for event_id, severity, signature, raw_message in rows:
        # 1. Processamento pesado da LLM/Embedding e feito FORA de qualquer transacao de banco
        llm = llm_classify(raw_message or "", signature or "")
        llm_sev = (llm.get("severity") or severity).lower()
        llm_sig = llm.get("signature") or signature or ""
        content = f"TELEMETRIA [{llm_sev}] {llm_sig}\n{raw_message or ''}"

        vector = get_embedding(content)
        if not vector:
            continue

        file_path = f"system_telemetry://{project}/event-{event_id}"

        # 2. Abre a conexao, insere e faz COMMIT IMEDIATO por item
        conn = get_connection()
        if not conn:
            continue

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO document_chunks (project_name, file_path, chunk_index, content, embedding, file_hash, updated_at)
                        SELECT 'system_telemetry', %s, 0, %s, %s::vector,
                               md5(%s), CURRENT_TIMESTAMP
                        WHERE NOT EXISTS (
                            SELECT 1 FROM document_chunks
                            WHERE project_name='system_telemetry' AND file_path=%s AND content=%s
                        );
                    """, (file_path, content, vector, content, file_path, content))
            classified += 1
        except Exception as e:
            if "UndefinedTable" in str(e) or "does not exist" in str(e):
                print("ERR_MISSING_TABLE: Tabela 'document_chunks' ausente.", file=sys.stderr)
                conn.close()
                sys.exit(1)
            print(f"ERRO vetorizar evento {event_id}: {e}", file=sys.stderr)
        finally:
            conn.close()

    print(f"Telemetria classificada e vetorizada em system_telemetry: {classified} eventos.")
    return True


def _load_classify_prompt(log_content):
    """Carrega o template de classificacao de telemetria via prompt_loader."""
    try:
        import importlib.util
        proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if proj_root not in sys.path:
            sys.path.insert(0, proj_root)
        from utils.prompt_loader import load_prompt
        return load_prompt("telemetry_classify_system.txt", log_content=log_content)
    except (FileNotFoundError, ImportError):
        return (
            "Classifique o log de sistema abaixo em severidade (info/warning/error/critical) "
            "e extraia a assinatura de erro. Responda apenas JSON "
            "{'severity': '...', 'signature': '...', 'process': '...'}.\nLOG:\n%s"
        ) % log_content


def llm_classify(raw_message, signature=""):
    """Chama a LLM local para classificar um log de telemetria."""
    log_content = f"{signature}\n{raw_message}"[:1500]
    prompt = _load_classify_prompt(log_content)
    payload = {"model": CLASSIFY_MODEL, "prompt": prompt, "stream": False, "format": "json",
               "options": {"temperature": 0.0}}
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            res = json.loads(response.read().decode("utf-8"))
            return json.loads(res.get("response", "{}"))
    except Exception:
        return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classificador de Telemetria Wygor Core")
    parser.add_argument("action", nargs="?", default="classify", choices=["classify", "status"])
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args()

    if args.action == "classify":
        classify(args.project, window_hours=args.window_hours, raw=args.raw)
    elif args.action == "status":
        conn = get_connection()
        if conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM system_telemetry_events WHERE scope='system_telemetry';")
                n = cur.fetchone()[0]
                print(f"Eventos de telemetria coletados: {n}")
            except Exception as e:
                print(f"ERRO status: {e}", file=sys.stderr)
            finally:
                cur.close(); conn.close()