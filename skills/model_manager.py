#!/usr/bin/env python3
import os
import sys
import json
import argparse
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Manifesto para inclusão dinâmica no Wygor Chat
SKILL_MANIFEST = {
    "name": "model_manager",
    "description": "Gerencia e altera os modelos LLM (Ollama) atribuídos a diferentes tarefas (router, complex, intermediate).",
    "intent": "model_config",
    "keywords": ["modelo", "modelos", "alterar modelo", "mudar modelo", "configurar llm", "qwen"],
    "script": "model_manager.py"
}

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

def get_db_connection():
    try:
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
    except Exception as e:
        print(f"❌ Erro ao conectar ao PostgreSQL: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_configs (
                id SERIAL PRIMARY KEY,
                task_role VARCHAR(50) UNIQUE NOT NULL,
                model_name VARCHAR(100) NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO model_configs (task_role, model_name, description)
            VALUES
                ('router', 'qwen2.5-coder:1.5b', 'Modelo leve para roteamento e classificação de intenções'),
                ('intermediate', 'qwen2.5-coder:3b', 'Modelo intermediário para tarefas rápidas'),
                ('complex', 'qwen2.5-coder:14b', 'Modelo principal para raciocínio e tarefas complexas')
            ON CONFLICT (task_role) DO NOTHING;
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tabela 'model_configs' inicializada com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro na migração/seed: {e}")
        return False

def list_models():
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT task_role, model_name, description, updated_at FROM model_configs ORDER BY id ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        configs = []
        print("\n⚙️  CONFIGURAÇÃO ATUAL DOS MODELOS LLM")
        print("=" * 65)
        for role, model, desc, updated in rows:
            print(f"• Papel: [{role}] -> Modelo: {model}")
            print(f"  Descrição: {desc or 'N/A'}")
            print(f"  Atualizado em: {updated}\n")
            configs.append({"role": role, "model": model, "description": desc})
        return configs
    except Exception as e:
        print(f"❌ Erro ao listar configurações: {e}")
        return []

def get_model_for_role(role, default="qwen2.5-coder:14b"):
    conn = get_db_connection()
    if not conn:
        return default
    try:
        cur = conn.cursor()
        cur.execute("SELECT model_name FROM model_configs WHERE task_role = %s;", (role,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default

def set_model_for_role(role, model, description=None):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO model_configs (task_role, model_name, description, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (task_role) 
            DO UPDATE SET model_name = EXCLUDED.model_name,
                          description = COALESCE(EXCLUDED.description, model_configs.description),
                          updated_at = CURRENT_TIMESTAMP;
        """, (role, model, description))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Modelo para o papel '{role}' alterado com sucesso para '{model}'!")
        return True
    except Exception as e:
        print(f"❌ Erro ao atualizar modelo: {e}")
        return False

if __name__ == "__main__":
    init_db()  # Garante schema resiliente antes de qualquer operação
    
    parser = argparse.ArgumentParser(description="Skill de Gerenciamento de Modelos LLM")
    parser.add_argument("action", choices=["list", "set", "get", "init"], nargs="?", default="list", help="Ação a executar")
    parser.add_argument("-r", "--role", help="Papel da tarefa (ex: router, complex, intermediate)")
    parser.add_argument("-m", "--model", help="Nome do modelo (ex: qwen2.5-coder:1.5b, qwen2.5-coder:3b)")
    parser.add_argument("-d", "--description", help="Descrição opcional do uso do papel")
    parser.add_argument("-p", "--project", default="default", help="Projeto (compatibilidade)")

    args = parser.parse_args()

    if args.action == "init":
        init_db()
    elif args.action == "list":
        list_models()
    elif args.action == "get":
        if not args.role:
            print("⚠️ Informe a role com --role <nome>")
            sys.exit(1)
        m = get_model_for_role(args.role)
        print(m)
    elif args.action == "set":
        if not args.role or not args.model:
            print("⚠️ Uso correto: --role <papel> --model <nome_do_modelo>")
            sys.exit(1)
        set_model_for_role(args.role, args.model, args.description)