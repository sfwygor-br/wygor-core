#!/usr/bin/env python3
"""
Skill Dinâmica do Wygor Core: Gerenciador e Migrador de Banco de Dados PostgreSQL
Unifica a execução incremental de arquivos em migrations/*.sql com rastreamento por versão
e a aplicação idempotente do schema.sql base.
"""

import os
import sys
import glob
import argparse
from dotenv import load_dotenv

load_dotenv()

SKILL_MANIFEST = {
    "intent": "db_migrate",
    "description": "Gerencia e executa migrações no banco de dados PostgreSQL. Aplica schema.sql base e arquivos incrementais em migrations/*.sql rastreando versões.",
    "keywords": ["migracao", "migrate", "schema", "banco de dados", "criar tabelas", "verificar banco", "db status", "migrar banco"],
    "script": "skills/db_migrate.py"
}

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "schema.sql")
MIGRATIONS_DIR = os.path.join(PROJECT_ROOT, "migrations")

REQUIRED_TABLES = [
    "document_chunks", 
    "ssh_hosts", 
    "ssh_execution_logs", 
    "chat_sessions", 
    "chat_messages", 
    "schema_migrations",
    "system_telemetry_events",
    "native_execution_logs"
]


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
    except Exception as e:
        print(f"❌ Erro ao conectar ao PostgreSQL ({DB_HOST}:{DB_PORT}): {e}", file=sys.stderr)
        sys.exit(1)


def check_status():
    """Verifica quais tabelas obrigatórias existem no banco de dados."""
    conn = get_connection()
    cur = conn.cursor()
    
    status = {}
    for table in REQUIRED_TABLES:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = %s
            );
        """, (table,))
        status[table] = cur.fetchone()[0]
        
    cur.close()
    conn.close()
    
    print("\n📊 --- STATUS DO BANCO DE DADOS POSTGRESQL ---")
    all_ok = True
    for table, exists in status.items():
        st_icon = "✅ OK" if exists else "❌ AUSENTE"
        if not exists:
            all_ok = False
        print(f"  • Tabela '{table}': {st_icon}")
    print("----------------------------------------------\n")
    
    return all_ok, status


def apply_base_schema(conn):
    """Aplica o schema.sql base se o arquivo existir."""
    if not os.path.exists(SCHEMA_PATH):
        return True

    print(f"⚙️  Aplicando DDL base de '{os.path.basename(SCHEMA_PATH)}'...")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        sql_script = f.read()

    cur = conn.cursor()
    try:
        cur.execute(sql_script)
        conn.commit()
        print("✅ DDL base (schema.sql) aplicado com sucesso.")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao aplicar schema.sql base: {e}", file=sys.stderr)
        return False
    finally:
        cur.close()


def run_migrations():
    """Executa a aplicação do schema base e migrações incrementais."""
    print("🔄 [DB Migrate] Verificando e aplicando estrutura do banco de dados...")

    conn = get_connection()
    try:
        if not apply_base_schema(conn):
            print("❌ Falha ao aplicar schema.sql base.", file=sys.stderr)
            return False

        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        migration_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
        applied_count = 0
        for filepath in migration_files:
            filename = os.path.basename(filepath)
            cur.execute("SELECT version FROM schema_migrations WHERE version = %s;", (filename,))
            if cur.fetchone():
                continue

            print(f"  ⚡ Aplicando migração incremental: {filename}...")
            with open(filepath, "r", encoding="utf-8") as f:
                sql_script = f.read()

            cur.execute(sql_script)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s);", (filename,))
            conn.commit()
            applied_count += 1

        cur.close()

        all_ok, status = check_status()
        if not all_ok:
            missing = [tbl for tbl, exists in status.items() if not exists]
            print(f"❌ [DB Migrate] Erro: As seguintes tabelas ainda estão ausentes: {missing}", file=sys.stderr)
            return False

        print(f"✨ [DB Migrate] Banco de dados totalmente sincronizado! ({applied_count} novas migrações).")
        return True

    except Exception as e:
        print(f"❌ [DB Migrate] Erro durante a migração: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill de Migração e Gestão de BD Wygor Core")
    parser.add_argument("action", nargs="?", default="apply", choices=["apply", "status", "check"],
                        help="Ação: 'apply' (executa migrações), 'status' ou 'check' (verifica integridade)")
    parser.add_argument("-p", "--project", default="default", help="Nome do projeto")
    parser.add_argument("--status", action="store_true", help="Atalho para checar status do banco")

    args = parser.parse_args()

    if args.status or args.action in ["status", "check"]:
        all_ok, _ = check_status()
        if not all_ok:
            sys.exit(2)
    else:
        success = run_migrations()
        if not success:
            sys.exit(1)