-- 008_chat_episodic_memories.sql
-- Tabela para armazenamento de resumos de sessões e memória episódica vetorial (Fase 3)

CREATE TABLE IF NOT EXISTS chat_episodic_memories (
	id SERIAL PRIMARY KEY,
	session_id INT REFERENCES chat_sessions(id) ON DELETE CASCADE,
												   project_name TEXT NOT NULL DEFAULT 'default',
												   summary TEXT NOT NULL,
												   embedding VECTOR(768),
												   created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_episodic_memories_project ON chat_episodic_memories(project_name);
CREATE INDEX IF NOT EXISTS idx_chat_episodic_memories_session ON chat_episodic_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_episodic_memories_embedding ON chat_episodic_memories USING hnsw (embedding vector_cosine_ops);
