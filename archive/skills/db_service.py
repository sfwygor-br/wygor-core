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
    """
    Executa queries SQL com tratamento de erro e fechamento automático de conexão.
    
    :param query: String SQL a ser executada.
    :param params: Tupla/Lista de parâmetros.
    :param commit: Se True, efetua commit após execução.
    :param fetch: 'one' para fetchone(), 'all' para fetchall(), 'rowcount' para linhas afetadas, None se nada.
    """
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
    """Verifica quais tabelas da lista estão presentes no schema 'public'."""
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