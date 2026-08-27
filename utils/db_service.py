#!/usr/bin/env python3
"""
Serviço centralizado de conexões e operações CRUD no PostgreSQL para o Wygor Core.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

def get_connection():
    """Retorna uma nova conexão psycopg2 ao PostgreSQL."""
    try:
        import psycopg2
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
    except Exception as e:
        print(f"❌ Erro de Conexão com o PostgreSQL ({DB_HOST}:{DB_PORT}): {e}", file=sys.stderr)
        return None

def execute_query(query, params=None, commit=True, fetch=None):
    conn = get_connection()
    if not conn:
        raise ConnectionError("Não foi possível conectar ao banco de dados PostgreSQL.")

    try:
        cur = conn.cursor()
        cur.execute(query, params or ())

        result = None
        if fetch == "one":
            result = cur.fetchone()
        elif fetch == "all":
            result = cur.fetchall()
        elif fetch == "rowcount":
            result = cur.rowcount

        if commit:
            conn.commit()

        cur.close()
        return result
    except Exception as e:
        if commit and conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def check_tables_status(required_tables):
    status = {}
    conn = get_connection()
    if not conn:
        return {table: False for table in required_tables}

    try:
        cur = conn.cursor()
        for table in required_tables:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = %s
                );
            """, (table,))
            status[table] = cur.fetchone()[0]
        cur.close()
    finally:
        conn.close()

    return status

def get_model_for_role(role, default=None, env_var=None):
    """
    Fonte de verdade única para modelos LLM (Ollama).

    Resolução hierárquica:
      1. Banco de dados (tabela `model_configs`) — fonte de verdade.
      2. Variável de ambiente (`env_var`, se informada) — fallback.
      3. Default `qwen2.5-coder:3b` — último recurso.

    Ex.: get_model_for_role("complex", default="qwen2.5-coder:3b", env_var="OLLAMA_CHAT_MODEL")
    """
    if default is None:
        default = "qwen2.5-coder:3b"
    try:
        row = execute_query(
            "SELECT model_name FROM model_configs WHERE task_role = %s;",
            params=(role,),
            fetch="one",
        )
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    if env_var:
        env_value = os.getenv(env_var)
        if env_value:
            return env_value
    return default
