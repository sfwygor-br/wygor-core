#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import psycopg2
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WYGOR_CORE_DIR = os.path.dirname(SCRIPT_DIR)

# Configurações do Banco e Ollama
OLLAMA_EMBED_URL = f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/embeddings"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

def fetch_context(query, project_name, limit=3):
    """Busca trechos do projeto via RAG para contexto de engenharia."""
    try:
        query_knowledge_script = os.path.join(SCRIPT_DIR, "query_knowledge.py")
        res = subprocess.run(
            [sys.executable, query_knowledge_script, query, "-p", project_name, "-l", str(limit), "--raw"],
            capture_output=True,
            text=True
        )
        return res.stdout.strip()
    except Exception as e:
        print(f"⚠️ Erro ao recuperar contexto: {e}", file=sys.stderr)
        return ""

def write_file(target_path, content, overwrite=False):
    """Cria ou substitui o conteúdo de um arquivo."""
    abs_path = os.path.abspath(target_path)
    dir_name = os.path.dirname(abs_path)
    
    if not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        print(f"📁 Diretório criado: {dir_name}")

    if os.path.exists(abs_path) and not overwrite:
        print(f"⚠️ O arquivo '{target_path}' já existe. Use --overwrite para sobrescrever.")
        return False

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Arquivo salvo com sucesso: {target_path}")
    return True

def replace_in_file(target_path, old_text, new_text):
    """Substitui um trecho exato de texto dentro de um arquivo existente."""
    abs_path = os.path.abspath(target_path)
    if not os.path.exists(abs_path):
        print(f"❌ Arquivo não encontrado: {target_path}", file=sys.stderr)
        return False

    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()

    if old_text not in content:
        print(f"⚠️ O trecho a ser substituído não foi encontrado em '{target_path}'.", file=sys.stderr)
        return False

    updated_content = content.replace(old_text, new_text)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"📝 Trecho atualizado com sucesso em: {target_path}")
    return True

def auto_commit(repo_path, commit_message):
    """Chama a skill git_guard para registrar o commit local."""
    try:
        git_guard_script = os.path.join(SCRIPT_DIR, "git_guard.py")
        subprocess.run(
            [sys.executable, git_guard_script, "commit", repo_path, "-m", commit_message],
            check=True
        )
    except Exception as e:
        print(f"⚠️ Não foi possível registrar o commit automaticamente: {e}", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill de Engenharia e Edição de Código do Wygor Core")
    subparsers = parser.add_subparsers(dest="action", help="Ação de engenharia")

    # Ação: write (criar/sobrescrever)
    write_parser = subparsers.add_parser("write", help="Cria ou sobrescreve um arquivo de código")
    write_parser.add_argument("file", help="Caminho do arquivo de destino")
    write_parser.add_argument("--content", required=True, help="Conteúdo do arquivo")
    write_parser.add_argument("--overwrite", action="store_true", help="Permite sobrescrever se existir")
    write_parser.add_argument("-repo", "--repository", default=".", help="Caminho do repositório para o commit")
    write_parser.add_argument("-m", "--message", help="Mensagem do commit após a escrita")

    # Ação: patch (substituir trecho)
    patch_parser = subparsers.add_parser("patch", help="Substitui um trecho de código específico")
    patch_parser.add_argument("file", help="Caminho do arquivo")
    patch_parser.add_argument("--old", required=True, help="Texto/Bloco antigo a ser substituído")
    patch_parser.add_argument("--new", required=True, help="Novo texto/bloco")
    patch_parser.add_argument("-repo", "--repository", default=".", help="Caminho do repositório para o commit")
    patch_parser.add_argument("-m", "--message", help="Mensagem do commit após a alteração")

    # Ação: context (consulta contexto para a tarefa)
    ctx_parser = subparsers.add_parser("context", help="Busca o contexto de código existente via RAG")
    ctx_parser.add_argument("query", help="Descrição da tarefa/função")
    ctx_parser.add_argument("-p", "--project", required=True, help="Nome do projeto no pgvector")

    args = parser.parse_args()

    if args.action == "write":
        success = write_file(args.file, args.content, overwrite=args.overwrite)
        if success and args.message:
            auto_commit(args.repository, args.message)
    elif args.action == "patch":
        success = replace_in_file(args.file, args.old, args.new)
        if success and args.message:
            auto_commit(args.repository, args.message)
    elif args.action == "context":
        ctx = fetch_context(args.query, args.project)
        print("🔍 Contexto RelevanteEncontrado:\n")
        print(ctx)
    else:
        parser.print_help()
