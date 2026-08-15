#!/usr/bin/env python3
import os
import sys
import argparse
import json
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

def get_embedding(text):
    payload = {"model": EMBED_MODEL, "prompt": text[:4000]}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("embedding", [])
    except Exception as e:
        print(f"⚠️ Erro ao gerar embedding: {e}", file=sys.stderr)
        return []

def add_memory(note, project_name="global"):
    embedding = get_embedding(note)
    if not embedding:
        print("❌ Não foi possível gerar embedding para a memória.", file=sys.stderr)
        return

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor()

    sql = """
        INSERT INTO document_chunks (project_name, file_path, content, embedding)
        VALUES (%s, %s, %s, %s::vector);
    """
    virtual_file = f"memory://{project_name}/agent-notes"
    cur.execute(sql, (project_name, virtual_file, f"MEMÓRIA DE PROJETO: {note}", embedding))
    conn.commit()
    cur.close()
    conn.close()

    print(f"🧠 Memória salva com sucesso no projeto '{project_name}'!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grava memória do agente no Wygor")
    parser.add_argument("note", help="Conteúdo da memória/decisão técnica")
    parser.add_argument("-p", "--project", default="global", help="Nome do projeto")

    args = parser.parse_args()
    add_memory(args.note, project_name=args.project)
