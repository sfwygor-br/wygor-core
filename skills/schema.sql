-- 1. Habilita a extensão pgvector[cite: 16, 17]
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Tabela de controle de migrações
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabela de chunks de documentos (RAG) com suporte a hash e versão[cite: 16, 17, 18, 19, 20]
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT 'default',[cite: 16, 18]
    file_path TEXT NOT NULL,[cite: 16, 17]
    chunk_index INT DEFAULT 0,[cite: 16, 19]
    content TEXT NOT NULL,[cite: 16, 17]
    embedding VECTOR(768),[cite: 16, 17]
    file_hash TEXT,[cite: 20]
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,[cite: 16, 17]
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP[cite: 20]
);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
ON document_chunks USING hnsw (embedding vector_cosine_ops);[cite: 16]

CREATE INDEX IF NOT EXISTS idx_document_chunks_project 
ON document_chunks (project_name);[cite: 16, 18]

CREATE INDEX IF NOT EXISTS idx_chunks_file_hash 
ON document_chunks (file_hash);[cite: 20]

-- 4. Tabela de Perfis e Servidores SSH[cite: 16]
CREATE TABLE IF NOT EXISTS ssh_hosts (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INT NOT NULL DEFAULT 22,
    username TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'key_path',
    key_path TEXT,
    secret_data TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_host_per_project UNIQUE (project_name, name)
);

CREATE INDEX IF NOT EXISTS idx_ssh_hosts_project ON ssh_hosts(project_name);[cite: 16]

-- 5. Tabela de Histórico de Execuções SSH / Deploy[cite: 16]
CREATE TABLE IF NOT EXISTS ssh_execution_logs (
    id SERIAL PRIMARY KEY,
    host_id INT REFERENCES ssh_hosts(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    command TEXT NOT NULL,
    exit_code INT,
    output TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ssh_logs_project ON ssh_execution_logs(project_name);[cite: 16]

-- 6. Tabela de Sessões de Chat[cite: 16]
CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT 'default',
    title TEXT NOT NULL DEFAULT 'Nova Sessão',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_project ON chat_sessions(project_name);[cite: 16]

-- 7. Tabela de Mensagens do Chat[cite: 16]
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

CREATE TABLE IF NOT EXISTS model_configs (
    id SERIAL PRIMARY KEY,
    task_role VARCHAR(50) UNIQUE NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Tabela de Eventos de Telemetria (Spec 002 - Observabilidade Externa)
CREATE TABLE IF NOT EXISTS system_telemetry_events (
    id SERIAL PRIMARY KEY,
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT 'system',
    process_name TEXT,
    pid INT,
    scope TEXT NOT NULL DEFAULT 'system_telemetry',
    severity TEXT,
    signature TEXT,
    raw_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_collected_at ON system_telemetry_events(collected_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_scope ON system_telemetry_events(scope);
CREATE INDEX IF NOT EXISTS idx_telemetry_signature ON system_telemetry_events(signature);

-- 9. Tabela de Histórico do Executor Nativo de Sistema (Spec 002)
CREATE TABLE IF NOT EXISTS native_execution_logs (
    id SERIAL PRIMARY KEY,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    pipeline TEXT NOT NULL,
    exit_code INT,
    duration_ms INT,
    attempts INT DEFAULT 1,
    output TEXT,
    error TEXT,
    status TEXT DEFAULT 'success'
);

CREATE INDEX IF NOT EXISTS idx_native_exec_logs_executed_at ON native_execution_logs(executed_at);
CREATE INDEX IF NOT EXISTS idx_native_exec_logs_status ON native_execution_logs(status);

-- Inserts pré-existentes para inicialização do sistema
INSERT INTO model_configs (task_role, model_name, description)
VALUES
    ('router', 'qwen2.5-coder:1.5b', 'Modelo leve para roteamento e classificação de intenções'),
    ('intermediate', 'qwen2.5-coder:3b', 'Modelo intermediário para tarefas simples de código e respostas rápidas'),
    ('complex', 'qwen2.5-coder:14b', 'Modelo principal para raciocínio complexo, agentes de código e auto-healing')
ON CONFLICT (task_role) DO NOTHING;