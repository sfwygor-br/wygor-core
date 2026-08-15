-- 1. Habilita a extensão pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Tabela de chunks de documentos (RAG)
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT 'default',
    file_path TEXT NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    embedding VECTOR(768), -- 768d para nomic-embed-text
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices da tabela de chunks
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
ON document_chunks 
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_document_chunks_project 
ON document_chunks (project_name);

-- 3. Tabela de Perfis e Servidores SSH
CREATE TABLE IF NOT EXISTS ssh_hosts (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INT NOT NULL DEFAULT 22,
    username TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'key_path', -- 'key_path', 'key_content' ou 'password'
    key_path TEXT,
    secret_data TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_host_per_project UNIQUE (project_name, name)
);

CREATE INDEX IF NOT EXISTS idx_ssh_hosts_project ON ssh_hosts(project_name);

-- 4. Tabela de Histórico de Execuções SSH / Deploy
CREATE TABLE IF NOT EXISTS ssh_execution_logs (
    id SERIAL PRIMARY KEY,
    host_id INT REFERENCES ssh_hosts(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    command TEXT NOT NULL,
    exit_code INT,
    output TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ssh_logs_project ON ssh_execution_logs(project_name);