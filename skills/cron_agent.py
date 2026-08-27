#!/usr/bin/env python3
SKILL_MANIFEST = {
    "intent": "cron_agent",
    "description": "Executa rotinas de agentes autônomos por projeto (-p) com sessão fixa e re-indexação RAG.",
    "allowed_actions": ["run"],
    "keywords": ["agente", "cron", "autonomo", "conhecimento", "devops"],
    "script": "cron_agent.py"
}

import os
import sys
import json
import fcntl
import glob
import argparse
import subprocess
from datetime import datetime
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.db_service import execute_query
from utils.llm_client import call_llm
from skills.model_manager import get_model_for_role

load_dotenv()
MODEL_AGENT = get_model_for_role("intermediate", default="qwen2.5-coder:3b")

def acquire_lock(agent_name, project_name):
    """Impede execuções concorrentes do mesmo agente no mesmo projeto."""
    lock_file = f"/tmp/wygor_agent_{agent_name}_{project_name}.lock"
    fp = open(lock_file, "w")
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fp
    except IOError:
        print(f"⚠️ [LOCK] Agente '{agent_name}' já está em execução para o projeto '{project_name}'. Abortando.")
        sys.exit(0)

def get_or_create_agent_session(agent_name, project_name, prompt_file, description=""):
    """Garante que o agente acesse a mesma sessão persistente vinculada ao projeto."""
    sql_check = "SELECT session_id FROM agents WHERE agent_name = %s AND project_name = %s;"
    row = execute_query(sql_check, (agent_name, project_name), commit=False, fetch="one")

    if row:
        session_id = row[0]
        print(f"🤖 Agente '{agent_name}' localizado | Projeto: [{project_name}] | Sessão Fixa: #{session_id}")
        return session_id

    # Cria sessão exclusiva para o agente dentro do projeto informado
    sql_session = "INSERT INTO chat_sessions (project_name, title) VALUES (%s, %s) RETURNING id;"
    sess_row = execute_query(sql_session, (project_name, f"Agente Autônomo: {agent_name}"), fetch="one")
    session_id = sess_row[0]

    sql_agent = "INSERT INTO agents (agent_name, project_name, description, prompt_file, session_id) VALUES (%s, %s, %s, %s, %s);"
    execute_query(sql_agent, (agent_name, project_name, description, prompt_file, session_id))

    print(f"✨ Novo Agente '{agent_name}' registrado para [{project_name}] | Sessão #{session_id}")
    return session_id

def load_history(session_id):
    sql = "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY id ASC;"
    rows = execute_query(sql, (session_id,), commit=False, fetch="all") or []
    return [{"role": r[0], "content": r[1]} for r in rows]

def save_message(session_id, role, content):
    execute_query("INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s);", (session_id, role, content))
    execute_query("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (session_id,))

def scan_project_codebase():
    """Mapeia apenas o manifesto das skills para economizar tokens de contexto."""
    summary = ["=== RESUMO DAS SKILLS E ARQUITETURA ==="]
    skills_files = glob.glob(os.path.join(PROJECT_ROOT, "skills", "*.py"))
    
    for s_file in skills_files:
        try:
            with open(s_file, "r", encoding="utf-8") as f:
                content = f.read()
                if "SKILL_MANIFEST" in content:
                    summary.append(f"\n--- Skill: {os.path.basename(s_file)} ---")
                    manifest_lines = [line for line in content.splitlines() if '"intent"' in line or '"description"' in line]
                    summary.extend(manifest_lines[:5])
        except Exception:
            continue
    return "\n".join(summary)

def run_agent_cycle(agent_identifier, project_name="igor_core", custom_task=None):
    if os.path.exists(agent_identifier):
        config_path = agent_identifier
    else:
        config_path = os.path.join(PROJECT_ROOT, "prompts", "agents", f"{agent_identifier}.json")

    if not os.path.exists(config_path):
        print(f"❌ Configuração do agente não encontrada: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        agent_config = json.load(f)

    agent_name = agent_config["agent_name"]
    acquire_lock(agent_name, project_name)

    session_id = get_or_create_agent_session(
        agent_name=agent_name,
        project_name=project_name,
        prompt_file=config_path,
        description=agent_config.get("description", "")
    )

    history = load_history(session_id)
    codebase_state = scan_project_codebase()

    system_prompt = (
        f"{agent_config['system_prompt']}\n\n"
        f"PROJETO ALVO ATIVO: [{project_name}]\n"
        f"SESSÃO PERSISTENTE: #{session_id}\n\n"
        f"ESTADO DO CÓDIGO FONTE LOCAL:\n{codebase_state}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    task_input = custom_task or agent_config.get("default_task", "Execute sua inspeção e mapeamento de rotina.")
    cycle_user_prompt = f"[Gatilho do Cron - Projeto: {project_name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]:\n{task_input}"

    messages.append({"role": "user", "content": cycle_user_prompt})

    payload = {
        "model": MODEL_AGENT,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_predict": 1500
        }
    }

    print(f"📡 Executando LLM Client para o projeto [{project_name}] (Sessão #{session_id})...")
    ok, res, err = call_llm(
        endpoint="/api/chat",
        payload=payload,
        caller=f"cron_agent:{agent_name}",
        session_id=session_id,
        project_name=project_name
    )

    if not ok:
        print(f"❌ Erro na chamada da LLM: {err}")
        return

    # Gravação no banco realizada APENAS após confirmação de sucesso da requisição HTTP
    save_message(session_id, "user", cycle_user_prompt)
    content = res.get("message", {}).get("content", "").strip()
    save_message(session_id, "assistant", content)

    # Gravação e Ingestão do conhecimento com o escopo do projeto
    kb_dir = os.path.join(PROJECT_ROOT, "memory", "knowledge_base", project_name)
    os.makedirs(kb_dir, exist_ok=True)
    kb_file = os.path.join(kb_dir, f"{agent_name}_capabilities.md")

    with open(kb_file, "w", encoding="utf-8") as f:
        f.write(f"# Mapeamento de Conhecimento - Projeto: {project_name}\n")
        f.write(f"Agente: {agent_name} | Atualizado em: {datetime.now().isoformat()}\n\n")
        f.write(content)

    print(f"📝 Conhecimento gravado em `{kb_file}`.")

    # Ingestão para o banco de dados vetorial apontando para o parâmetro -p
    try:
        subprocess.run([
            sys.executable,
            os.path.join(PROJECT_ROOT, "skills", "ingest_docs.py"),
            PROJECT_ROOT,  
            "-p", project_name
        ], check=True)
        print(f"🚀 Base vetorial `document_chunks` atualizada com sucesso para o projeto [{project_name}]!")
    except Exception as e:
        print(f"⚠️ Falha na re-indexação vetorial: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill do Agente Autônomo com suporte a Projetos")
    parser.add_argument("agent", nargs="?", default="system_knowledge_agent", help="Nome do agente ou caminho para o JSON")
    parser.add_argument("-p", "--project", default="igor_core", help="Nome do projeto (Padrão: igor_core)")
    parser.add_argument("-t", "--task", default=None, help="Tarefa customizada")

    args = parser.parse_args()
    run_agent_cycle(args.agent, project_name=args.project, custom_task=args.task)