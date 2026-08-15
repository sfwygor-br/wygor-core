-- Garante que chunk_index exista e seja opcional/padrão 0
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS chunk_index INT DEFAULT 0;
ALTER TABLE document_chunks ALTER COLUMN chunk_index DROP NOT NULL;
