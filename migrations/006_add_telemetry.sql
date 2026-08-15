-- 006: Suporte à Observabilidade Externa não-invasiva (Spec 002)
-- Aplicado de forma idempotente pelo skills/db_migrate.py

-- 1. Eventos de Telemetria Coletados pelo serviço de coleta (Cron/Daemon)
CREATE TABLE IF NOT EXISTS system_telemetry_events (
    id SERIAL PRIMARY KEY,
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT 'system',          -- 'pid', 'journal', 'stdout', 'varlog', 'process'
    process_name TEXT,
    pid INT,
    scope TEXT NOT NULL DEFAULT 'system_telemetry', -- escopo vetorial no document_chunks
    severity TEXT,                                  -- 'error', 'warning', 'info', 'exception'
    signature TEXT,                                 -- assinatura extraída do erro
    raw_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_collected_at ON system_telemetry_events(collected_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_scope ON system_telemetry_events(scope);
CREATE INDEX IF NOT EXISTS idx_telemetry_signature ON system_telemetry_events(signature);

-- 2. Histórico de execuções do Executor Nativo de Sistema (Spec 002)
CREATE TABLE IF NOT EXISTS native_execution_logs (
    id SERIAL PRIMARY KEY,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    pipeline TEXT NOT NULL,                          -- comando bash nativo executado
    exit_code INT,
    duration_ms INT,
    attempts INT DEFAULT 1,                          -- tentativas até sucesso (1 = sem healing)
    output TEXT,
    error TEXT,
    status TEXT DEFAULT 'success'                    -- 'success' | 'failed' | 'healed'
);

CREATE INDEX IF NOT EXISTS idx_native_exec_logs_executed_at ON native_execution_logs(executed_at);
CREATE INDEX IF NOT EXISTS idx_native_exec_logs_status ON native_execution_logs(status);
