#!/usr/bin/env python3
"""
Skill Dinâmica do Wygor Core: Gerenciador de Sessões e Histórico do Chat
Permite listar, carregar, renomear e excluir contextos de conversas anteriores.
"""

import os
import sys
import json
import argparse
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv()

SKILL_MANIFEST = {
    "intent": "session_manager",
    "description": "Gerencia e recupera sessões de chat e contextos anteriores armazenados no banco de dados.",
    "keywords": ["sessoes", "historico chat", "contextos anteriores", "retomar chat", "listar conversas", "sessao de chat"],
    "script": "skills/session_manager.py"
}

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
    except Exception as e:
        print(f"❌ Erro ao conectar ao PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

def list_sessions(project, raw=False):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT s.id, s.title, s.updated_at, COUNT(m.id) as total_msgs
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.id = m.session_id
            WHERE s.project_name = %s
            GROUP BY s.id
            ORDER BY s.updated_at DESC;
        """, (project,))
        rows = cur.fetchall()
    except Exception as e:
        if "UndefinedTable" in str(e) or "does not exist" in str(e):
            print("ERR_MISSING_TABLE: Tabela 'chat_sessions' ausente.", file=sys.stderr)
        else:
            print(f"❌ Erro ao consultar sessões: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

    sessions = [{"id": r[0], "title": r[1], "updated_at": str(r[2]), "messages": r[3]} for r in rows]

    if raw:
        print(json.dumps(sessions, ensure_ascii=False))
        return

    print(f"\n📜 --- HISTÓRICO DE SESSÕES [{project.upper()}] ---")
    if not sessions:
        print("Nenhuma sessão de chat encontrada para este projeto.")
        print("---------------------------------------------------\n")
        return

    for s in sessions:
        print(f"  • ID [{s['id']}] - {s['title']} ({s['messages']} msgs) | Última atividade: {s['updated_at']}")
    print("---------------------------------------------------\n")

def get_last_session(project):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM chat_sessions WHERE project_name = %s ORDER BY updated_at DESC LIMIT 1;", (project,))
        row = cur.fetchone()
        if row:
            print(row[0])
    except Exception as e:
        if "UndefinedTable" in str(e) or "does not exist" in str(e):
            print("ERR_MISSING_TABLE: Tabela 'chat_sessions' ausente.", file=sys.stderr)
        else:
            print(f"❌ Erro ao buscar última sessão: {e}", file=sys.stderr)
    finally:
        cur.close()
        conn.close()

def rename_session(session_id, new_title):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE chat_sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (new_title, session_id))
        conn.commit()
        print(f"✅ Sessão #{session_id} renomeada para '{new_title}'.")
    except Exception as e:
        if "UndefinedTable" in str(e) or "does not exist" in str(e):
            print("ERR_MISSING_TABLE: Tabela 'chat_sessions' ausente.", file=sys.stderr)
        else:
            print(f"❌ Erro ao renomear sessão: {e}", file=sys.stderr)
    finally:
        cur.close()
        conn.close()

def delete_session(session_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM chat_sessions WHERE id = %s;", (session_id,))
        conn.commit()
        print(f"🗑️ Sessão #{session_id} e suas mensagens foram excluídas.")
    except Exception as e:
        if "UndefinedTable" in str(e) or "does not exist" in str(e):
            print("ERR_MISSING_TABLE: Tabela 'chat_sessions' ausente.", file=sys.stderr)
        else:
            print(f"❌ Erro ao deletar sessão: {e}", file=sys.stderr)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill de Gestão de Sessões de Chat")
    parser.add_argument("action", nargs="?", default="list", choices=["list", "get-last", "rename", "delete"])
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("--id", type=int, help="ID da sessão")
    parser.add_argument("--title", help="Novo título para a sessão")
    parser.add_argument("--raw", action="store_true", help="Retorna saída JSON puro")

    args = parser.parse_args()

    if args.action == "list":
        list_sessions(args.project, raw=args.raw)
        
    elif args.action == "get-last":
        get_last_session(args.project)

    elif args.action == "rename":
        if not args.id or not args.title:
            print("❌ '--id' e '--title' são obrigatórios.", file=sys.stderr)
            sys.exit(1)
        rename_session(args.id, args.title)

    elif args.action == "delete":
        if not args.id:
            print("❌ '--id' é obrigatório.", file=sys.stderr)
            sys.exit(1)
        delete_session(args.id)