#!/usr/bin/env python3
import os
import sys
import argparse
import json
import hashlib
import urllib.request
import psycopg2
from dotenv import load_dotenv

load_dotenv()

OLLAMA_EMBED_URL = f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/embeddings"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

IGNORED_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", "dist", "build", 
    ".idea", ".vscode", ".next", "out", "coverage", ".turbo"
}

IGNORED_FILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    "cargo.lock", "composer.lock"
}

ALLOWED_EXTENSIONS = {
    ".py", ".md", ".json", ".js", ".ts", ".tsx", ".jsx", 
    ".txt", ".sh", ".sql", ".yaml", ".yml", ".env.example"
}


def calculate_file_hash(filepath):
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
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
    except Exception as e:
        print(f"  ⚠️ Erro no embedding do Ollama: {e}")
        return []


def chunk_text(text, max_chars=1200, overlap_chars=200):
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + max_chars
        if end < text_len:
            last_newline = text.rfind('\n', start, end)
            if last_newline > start + (max_chars // 2):
                end = last_newline + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap_chars if end < text_len else text_len

    return chunks


def run_ingestion(target_path, project_name, clean_reindex=False):
    target_path = os.path.abspath(target_path)
    if not os.path.exists(target_path):
        print(f"❌ Caminho não encontrado: {target_path}")
        return 0

    print(f"⚡ Sincronização iniciada para o projeto [{project_name}] em: {target_path}")

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor()

    if clean_reindex:
        print(f"🧹 Forçando re-indexação limpa do projeto [{project_name}]...")
        cur.execute("DELETE FROM document_chunks WHERE project_name = %s;", (project_name,))
        conn.commit()

    cur.execute(
        "SELECT file_path, file_hash FROM document_chunks WHERE project_name = %s GROUP BY file_path, file_hash;",
        (project_name,)
    )
    db_file_hashes = {row[0]: row[1] for row in cur.fetchall()}

    disk_files = set()
    added_count = 0
    updated_count = 0
    skipped_count = 0

    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for file in files:
            if file in IGNORED_FILES:
                continue

            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, target_path)
                disk_files.add(rel_path)

                file_hash = calculate_file_hash(file_path)
                if not file_hash:
                    continue

                if rel_path in db_file_hashes and db_file_hashes[rel_path] == file_hash:
                    skipped_count += 1
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    if not content.strip():
                        continue

                    if rel_path in db_file_hashes:
                        cur.execute(
                            "DELETE FROM document_chunks WHERE project_name = %s AND file_path = %s;",
                            (project_name, rel_path)
                        )
                        conn.commit()
                        updated_count += 1
                    else:
                        added_count += 1

                    chunks = chunk_text(content)
                    file_inserted = 0

                    for idx, chunk in enumerate(chunks):
                        vector = get_embedding(chunk)
                        if vector:
                            try:
                                sql = """
                                    INSERT INTO document_chunks 
                                    (file_path, content, embedding, project_name, chunk_index, file_hash)
                                    VALUES (%s, %s, %s::vector, %s, %s, %s);
                                """
                                cur.execute(sql, (rel_path, chunk, vector, project_name, idx, file_hash))
                                conn.commit()
                                file_inserted += 1
                            except Exception as db_err:
                                conn.rollback()
                                print(f"  ⚠️ Erro no Postgres ({rel_path} - chunk {idx}): {db_err}")

                    if file_inserted > 0:
                        status_label = "Modificado" if rel_path in db_file_hashes else "Novo"
                        print(f"  ✓ [{status_label}] {rel_path} ({file_inserted} chunks)")

                except Exception as e:
                    print(f"  ⚠️ Erro ao ler arquivo {file_path}: {e}")

    deleted_files = set(db_file_hashes.keys()) - disk_files
    deleted_count = len(deleted_files)

    for rel_path in deleted_files:
        cur.execute(
            "DELETE FROM document_chunks WHERE project_name = %s AND file_path = %s;",
            (project_name, rel_path)
        )
        print(f"  🗑️ [Removido] {rel_path} não existe mais no disco.")

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print(f"📊 Resumo da Sincronização [{project_name}]:")
    print(f"  • Ignorados (Inalterados): {skipped_count}")
    print(f"  • Novos Adicionados:      {added_count}")
    print(f"  • Modificados Atualizados: {updated_count}")
    print(f"  • Deletados do Banco:     {deleted_count}")
    print("=" * 60)

    return added_count + updated_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingestão Incremental no Wygor Core")
    parser.add_argument("path", nargs="?", default=".", help="Caminho da pasta")
    parser.add_argument("-p", "--project", default="", help="Nome do projeto")
    parser.add_argument("--clean", action="store_true", help="Força re-indexação limpa do projeto")

    args = parser.parse_args()

    path = os.path.abspath(args.path)
    project = args.project if args.project else os.path.basename(path)

    run_ingestion(path, project, clean_reindex=args.clean)