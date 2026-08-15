#!/usr/bin/env python3
import os
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

def run_migrations():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    migrations_dir = os.path.join(project_root, "migrations")

    print("🔄 [DB Migrate] Verificando estado do banco de dados...")

    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cur = conn.cursor()

        # Tabela de controle de versão das migrações
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # Lê os arquivos da pasta migrations/ ordenados por nome (001, 002...)
        migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

        applied_count = 0
        for filepath in migration_files:
            filename = os.path.basename(filepath)

            cur.execute("SELECT version FROM schema_migrations WHERE version = %s;", (filename,))
            if cur.fetchone():
                continue  # Já foi aplicada

            print(f"  ⚡ Aplicando migração: {filename}...")
            with open(filepath, "r", encoding="utf-8") as f:
                sql_script = f.read()

            cur.execute(sql_script)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s);", (filename,))
            conn.commit()
            applied_count += 1

        cur.close()
        conn.close()

        if applied_count > 0:
            print(f"✅ [DB Migrate] {applied_count} migração(ões) aplicada(s) com sucesso!")
        else:
            print("✨ [DB Migrate] Banco de dados já está na versão mais recente.")

    except Exception as e:
        print(f"❌ [DB Migrate] Erro ao aplicar migrações: {e}")

if __name__ == "__main__":
    run_migrations()
