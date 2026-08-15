#!/usr/bin/env python3
import sys
import subprocess
import json
import urllib.request
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configurações Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embeddings"
MODEL_LLM = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:3b")
MODEL_EMBED = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Configurações Postgres
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

MAX_RETRIES = 3
LOG_DIR = "memory"
LOG_FILE = os.path.join(LOG_DIR, "execution_trace.jsonl")
TROUBLESHOOTING_FILE = os.path.join(LOG_DIR, "troubleshooting.md")

def get_embedding(text):
    payload = {"model": MODEL_EMBED, "prompt": text}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("embedding", [])
    except Exception:
        return []

def retrieve_rag_context(query, limit=3):
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
        cur.execute(sql, (embedding, embedding, limit))
        results = cur.fetchall()
        cur.close()
        conn.close()

        context_blocks = []
        for file_path, content, score in results:
            if score >= 0.5:
                context_blocks.append(f"--- Fonte: {file_path} (Relevância: {score:.2f}) ---\n{content}")
        
        return "\n\n".join(context_blocks)
    except Exception as e:
        print(f"⚠️ Alerta: Não foi possível consultar o RAG ({e}). Prosseguindo sem contexto.")
        return ""

def save_learned_fix(task, failed_attempt, successful_command):
    """Registra o erro corrigido na memória e dispara a re-ingestão no RAG."""
    print("\n🧠 [Auto-Learning] Registrando solução na memória evolutiva...")
    
    entry = f"""
## Resolução de Problema - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Tarefa**: {task}
- **Comando que Falhou**: `{failed_attempt['generated_command']}`
- **Erro (STDERR)**: {failed_attempt['stderr'].strip()}
- **Solução Validada**: `{successful_command}`

---
"""
    # Grava no arquivo de memória
    with open(TROUBLESHOOTING_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
        
    print(f"📝 Aprendizado salvo em `{TROUBLESHOOTING_FILE}`.")
    
    # Dispara a re-ingestão para sincronizar o banco vetorial
    try:
        print("⚡ Re-indexando base vetorial com o novo aprendizado...")
        subprocess.run([sys.executable, "skills/ingest_docs.py"], check=True, stdout=subprocess.DEVNULL)
        print("✅ Novo aprendizado memorizado no RAG com sucesso!")
    except Exception as e:
        print(f"⚠️ Falha ao re-indexar aprendizado: {e}")

def call_qwen(prompt):
    payload = {
        "model": MODEL_LLM,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1}
    }
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return {
                "response": res.get("response", "").strip(),
                "prompt_tokens": res.get("prompt_eval_count", 0),
                "completion_tokens": res.get("eval_count", 0),
                "total_duration_ms": round(res.get("total_duration", 0) / 1e6, 2)
            }
    except Exception as e:
        print(f"❌ Erro ao conectar ao Ollama ({OLLAMA_GENERATE_URL}): {e}")
        sys.exit(1)

def run_command(command):
    print(f"\n⚙️ Executando: {command}\n" + "-"*40)
    full_cmd = f"set -o pipefail; {command}"
    process = subprocess.Popen(
        full_cmd,
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr

def log_trace(trace_data):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace_data, ensure_ascii=False) + "\n")

def auto_heal(task_description):
    print(f"🚀 Iniciando Auto-Exec [RAG & Self-Learning] para: {task_description}")
    
    print("🧠 Consultando base vetorial de conhecimento (RAG)...")
    rag_context = retrieve_rag_context(task_description)
    if rag_context:
        print("✅ Contexto do projeto e memórias incorporados!")
    else:
        print("ℹ️ Nenhum contexto vetorial relevante encontrado.")

    trace = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "task": task_description,
        "model": MODEL_LLM,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "attempts": [],
        "status": "IN_PROGRESS"
    }

    system_rules = f"""Você é um assistente de automação Linux no Parrot OS.
REGRAS OBRIGATÓRIAS:
1. Responda APENAS com o comando Bash puro de linha única (ou encadeado com &&), sem markdown (```bash).
2. Para PostgreSQL:
   - NUNCA use o flag interativo -W.
   - SEMPRE adicione 'PGPASSWORD={DB_PASS}' antes do comando quando for se conectar.
   - SEMPRE especifique host, porta, usuário e banco explicitamente: '-h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME}'.
3. Evite placeholders genéricos (como 'table_name'). Use subqueries reais como: (SELECT tablename FROM pg_tables WHERE schemaname='public')."""

    context_prompt = f"\n\nCONTEXTO DO PROJETO RECUPERADO (RAG):\n{rag_context}" if rag_context else ""
    prompt = f"{system_rules}{context_prompt}\n\nTAREFA: {task_description}"

    for attempt_num in range(1, MAX_RETRIES + 1):
        print(f"\n🔄 Tentativa {attempt_num}/{MAX_RETRIES}...")
        
        qwen_res = call_qwen(prompt)
        command = qwen_res["response"].replace("```bash", "").replace("```", "").strip()
        
        trace["total_prompt_tokens"] += qwen_res["prompt_tokens"]
        trace["total_completion_tokens"] += qwen_res["completion_tokens"]
        
        returncode, stdout, stderr = run_command(command)
        
        attempt_record = {
            "attempt": attempt_num,
            "generated_command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "tokens": {
                "prompt": qwen_res["prompt_tokens"],
                "completion": qwen_res["completion_tokens"]
            },
            "duration_ms": qwen_res["total_duration_ms"]
        }
        trace["attempts"].append(attempt_record)

        if stdout:
            print(f"📄 STDOUT:\n{stdout}")

        if returncode == 0 and "FATAL:" not in stderr and "ERROR:" not in stderr:
            print("✅ Sucesso absoluto e validado na execução!")
            trace["status"] = "SUCCESS"
            
            # Se precisou de autocorreção (tentativa > 1), aciona o Self-Learning
            if attempt_num > 1:
                failed_attempt = trace["attempts"][0]
                save_learned_fix(task_description, failed_attempt, command)

            log_trace(trace)
            print_metrics(trace)
            return True, trace
        else:
            print(f"⚠️ Falha ou erro mascarado detectado (Código {returncode})!")
            if stderr:
                print(f"❌ STDERR:\n{stderr}")
            print("\n🩹 Re-injetando o erro detalhado para o Qwen corrigir...")
            
            prompt = f"""{system_rules}{context_prompt}

O comando abaixo FALHOU ao ser executado:
Comando: {command}
Código de Saída: {returncode}
Erro / STDERR:
{stderr}
Saída / STDOUT:
{stdout}

Reescreva o comando corrigindo os erros."""

    print("\n❌ Limite de tentativas atingido sem sucesso.")
    trace["status"] = "FAILED"
    log_trace(trace)
    print_metrics(trace)
    return False, trace

def print_metrics(trace):
    total_tokens = trace["total_prompt_tokens"] + trace["total_completion_tokens"]
    print("\n" + "="*50)
    print("📊 MÉTRICAS DE EXECUÇÃO E RASTREABILIDADE")
    print("="*50)
    print(f"🆔 Trace ID: {trace['id']}")
    print(f"📌 Status Final: {trace['status']}")
    print(f"🔄 Tentativas Realizadas: {len(trace['attempts'])}")
    print(f"🔤 Tokens Consumidos: {total_tokens}")
    print(f"📁 Log de Auditoria: {LOG_FILE}")
    print("="*50)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 skills/auto_exec.py 'descrição da tarefa'")
        sys.exit(1)
        
    task = " ".join(sys.argv[1:])
    auto_heal(task)
