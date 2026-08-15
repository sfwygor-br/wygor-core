-- Adiciona colunas ausentes em document_chunks caso o banco já exista
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS project_name TEXT DEFAULT 'default';
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS chunk_index INT DEFAULT 0;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS file_hash TEXT;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_chunks_project ON document_chunks(project_name);
CREATE INDEX IF NOT EXISTS idx_chunks_file_hash ON document_chunks(file_hash);

-- Criação garantida das novas tabelas
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

CREATE TABLE IF NOT EXISTS ssh_execution_logs (
    id SERIAL PRIMARY KEY,
    host_id INT REFERENCES ssh_hosts(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    command TEXT NOT NULL,
    exit_code INT,
    output TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT 'default',
    title TEXT NOT NULL DEFAULT 'Nova Sessão',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);