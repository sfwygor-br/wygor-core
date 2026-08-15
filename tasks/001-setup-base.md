# Task 001: Infraestrutura Base, Auto-Healing & Ingestão do Core

## Status: 🟡 Em Progresso
**Responsável**: wfelipe + IA Assistente
**Data de Criação**: 2026-08-14

---

## Checklist de Execução

### Fase 1: Documentação e Estrutura SDD
- [x] Criar estrutura de diretórios (`specs`, `tasks`, `skills`, `memory`)
- [x] Criar especificação técnica (`specs/001-core-system.md`)
- [x] Criar estado inicial do sistema (`memory/system_state.md`)

### Fase 2: Banco de Dados Vetorial (PostgreSQL + pgvector)
- [x] Mapear credenciais do PostgreSQL local (`127.0.0.1:5432`, `user: postgres`, `pass: root`)
- [x] Ativar a extensão `pgvector` no banco local
- [x] Criar a estrutura das tabelas em `skills/schema.sql`

### Fase 2.5: Ferramental de Controle & Automação (Adicionado)
- [x] Criar `skills/auto_exec.py` com loop de autocorreção
- [x] Adicionar suporte a `pipefail` e chamadas não-interativas ao PostgreSQL
- [x] Implementar rastreabilidade/telemetria em `memory/execution_trace.jsonl`

### Fase 3: Ingestão do Próprio Wygor Core (Self-Index)
- [ ] Criar script `skills/ingest_docs.py` para varrer apenas a raiz do `wygor-core`
- [ ] Gerar embeddings usando Ollama (`nomic-embed-text`)
- [ ] Salvar chunks e vetores de 768d na tabela `document_chunks`

### Fase 4: Busca Semântica do Próprio Sistema
- [ ] Criar script `skills/query_knowledge.py` para consultar a documentação local do projeto
