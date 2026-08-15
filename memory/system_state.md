# System State - wygor-core

## Status Atual
- **Fase**: Fase 3 - Ingestão e Indexação Interna do wygor-core
- **Data**: 2026-08-14
- **Engine Local**: Ollama + aichat (v0.30.0)

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
