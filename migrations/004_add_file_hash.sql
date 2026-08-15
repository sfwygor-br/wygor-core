-- Adiciona suporte a controle de versão e hash de arquivos
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS file_hash TEXT;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_chunks_file_hash ON document_chunks(file_hash);
