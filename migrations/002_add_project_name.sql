ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS project_name TEXT DEFAULT 'wygor-core';
CREATE INDEX IF NOT EXISTS idx_chunks_project ON document_chunks(project_name);
