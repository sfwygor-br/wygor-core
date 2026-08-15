-- ============================================================
-- WYGOR CORE - DATABASE SCHEMA (pgvector)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela principal de chunks de documentos
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768),
    project_name TEXT DEFAULT 'wygor-core',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices para otimização de busca vetorial e filtro por projeto
CREATE INDEX IF NOT EXISTS idx_chunks_project ON document_chunks(project_name);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops);
