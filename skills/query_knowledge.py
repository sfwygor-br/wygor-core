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

def search_documents(query_text, project_name=None, limit=5, raw_mode=False):
    query_vector = get_embedding(query_text)
    if not query_vector:
        print("❌ Falha ao gerar embedding de busca.", file=sys.stderr)
        return

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor()

    sql = """
    WITH vector_search AS (
        SELECT id, file_path, content,
               ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector ASC) as vec_rank,
               (embedding <=> %s::vector) as distance
        FROM document_chunks
        WHERE (%s::text IS NULL OR project_name = %s)
        ORDER BY vec_rank
        LIMIT 20
    ),
    text_search AS (
        SELECT id, file_path, content,
               ROW_NUMBER() OVER (ORDER BY ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', %s)) DESC) as text_rank
        FROM document_chunks
        WHERE (%s::text IS NULL OR project_name = %s)
          AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
        ORDER BY text_rank
        LIMIT 20
    )
    SELECT 
        COALESCE(v.file_path, t.file_path) as file_path,
        COALESCE(v.content, t.content) as content,
        (COALESCE(1.0 / (60 + v.vec_rank), 0.0) + COALESCE(1.0 / (60 + t.text_rank), 0.0)) as rrf_score
    FROM vector_search v
    FULL OUTER JOIN text_search t ON v.id = t.id
    ORDER BY rrf_score DESC
    LIMIT %s;
    """

    cur.execute(sql, (
        query_vector, query_vector, project_name, project_name,
        query_text, project_name, project_name, query_text,
        limit
    ))

    results = cur.fetchall()
    cur.close()
    conn.close()

    if not results:
        print("⚠️ Nenhum trecho encontrado no banco.", file=sys.stderr)
        return

    if raw_mode:
        for row in results:
            print(f"--- [Arquivo: {row[0]}] ---")
            print(row[1])
            print()
    else:
        print(f"🔍 Busca Híbrida (RRF) para: '{query_text}' (Projeto: {project_name or 'TODOS'}):\n")
        for idx, row in enumerate(results, 1):
            print(f"[{idx}] 📁 {row[0]} (Relevância RRF: {row[2]:.4f})")
            print(f"    {row[1][:300]}...\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consulta RAG Híbrida no Wygor")
    parser.add_argument("query", help="Texto de busca")
    parser.add_argument("-p", "--project", default=None, help="Nome do projeto")
    parser.add_argument("-l", "--limit", type=int, default=5, help="Quantidade de resultados")
    parser.add_argument("--raw", action="store_true", help="Retorna conteúdo limpo")

    args = parser.parse_args()
    search_documents(args.query, project_name=args.project, limit=args.limit, raw_mode=args.raw)
