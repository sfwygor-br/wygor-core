-- Tabela de Agentes com suporte a múltiplos projetos e sessão vinculada
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(64) NOT NULL,
    project_name VARCHAR(64) NOT NULL DEFAULT 'igor_core',
    description TEXT,
    prompt_file VARCHAR(255) NOT NULL,
    session_id INT UNIQUE REFERENCES chat_sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_agent_per_project UNIQUE (agent_name, project_name)
);

-- Tabela para rastreabilidade de requisições brutas (Telemetria LLM)
CREATE TABLE IF NOT EXISTS llm_raw_logs (
    id SERIAL PRIMARY KEY,
    project_name VARCHAR(64) DEFAULT 'igor_core',
    session_id INT REFERENCES chat_sessions(id) ON DELETE SET NULL,
    caller VARCHAR(128) NOT NULL,
    endpoint VARCHAR(64) NOT NULL,
    request_payload JSONB NOT NULL,
    response_payload JSONB,
    status_code INT,
    error_message TEXT,
    duration_ms FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);