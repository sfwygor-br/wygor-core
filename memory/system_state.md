# System State - wygor-core

## Status Atual
- **Fase**: Fase 3 - Ingestão e Indexação Interna do wygor-core (+ Spec 002)
- **Data**: 2026-08-14
- **Engine Local**: Ollama + aichat (v0.30.0)

## Especificação 002 - Observabilidade & Executor Nativo
- **`skills/telemetry_collector.py`**: Coleta de telemetria não-invasiva (PIDs, journalctl, /var/log) em `system_telemetry_events`.
- **`skills/telemetry_classify.py`**: Classifica e vetoriza logs em `document_chunks` sob escopo `system_telemetry`.
- **`skills/native_workflow.py`**: Executor nativo com auto-healing e fallback; registra em `native_execution_logs`.
- **Tabelas**: `system_telemetry_events`, `native_execution_logs` (migração `006_add_telemetry.sql`).
- **Prompts**: `native_workflow_system.txt`, `telemetry_classify_system.txt`.

## Mapeamento do Hardware & Modelos
- **Placa de Vídeo**: Intel Iris Xe Graphics
- **Modelo CLI Principal**: qwen2.5-coder:3b
- **Modelo Ultra-Leve**: qwen2.5-coder:1.5b
- **Modelo de Embeddings**: nomic-embed-text:latest (768d)

## Infraestrutura & Ferramentas
- **Banco de Dados**: PostgreSQL Local (`localhost:5432`, `user: postgres`, `pass: root`)
- **Extensões**: `pgvector` ativa
- **Tabela Vetorial**: `document_chunks`
- **Executor Autônomo**: `skills/auto_exec.py` (com auto-healing, pipefail fix e tracing em `memory/execution_trace.jsonl`)

## Próximos Passos Imediatos
1. Criar `skills/ingest_docs.py` para ler e indexar a estrutura do `wygor-core` (`specs/`, `tasks/`, `memory/`, `skills/`).
2. Gerar embeddings via Ollama (`nomic-embed-text`) e salvar na tabela `document_chunks`.
3. Criar a skill de busca vetorial interna `skills/query_knowledge.py`.

## Dependências Python
- **Gerenciador**: `requirements.txt`
- **Pacotes**: `psycopg2-binary`
