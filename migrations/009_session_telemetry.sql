-- 009_session_telemetry.sql
-- Adiciona métricas de consumo de tokens em chat_sessions e chat_messages

ALTER TABLE chat_sessions 
ADD COLUMN IF NOT EXISTS total_prompt_tokens INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_completion_tokens INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_tokens INT DEFAULT 0;

ALTER TABLE chat_messages 
ADD COLUMN IF NOT EXISTS prompt_tokens INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS completion_tokens INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_tokens INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS model_name TEXT;
