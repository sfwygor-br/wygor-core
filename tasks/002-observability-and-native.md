# Task 002: Observabilidade Externa & Executor Nativo (Spec 002)

## Status: 🟡 Em Progresso
**Responsável**: wfelipe + IA Assistente

---

## Checklist de Execução

### Fase 1: Observabilidade Externa Não-Invasiva
- [x] Criar `skills/telemetry_collector.py` (mapeia PIDs, lê journalctl e /var/log, extrai assinaturas).
- [x] Persistir eventos em `system_telemetry_events` (escopo `system_telemetry`).
- [x] Criar `skills/telemetry_classify.py` (classifica via LLM e vetoriza em `document_chunks`).

### Fase 2: Executor Nativo de Sistema
- [x] Criar `skills/native_workflow.py` (pipelines Bash nativos, mapeamento `which`, auto-healing e fallback).
- [x] Registrar histórico em `native_execution_logs`.

### Fase 3: Prompts
- [x] `prompts/native_workflow_system.txt` (geração de pipelines nativos).
- [x] `prompts/telemetry_classify_system.txt` (triagem/classificação de logs).

### Fase 4: Banco de Dados
- [x] `migrations/006_add_telemetry.sql` (tabelas `system_telemetry_events` e `native_execution_logs`).
- [x] Atualizar `skills/schema.sql` e obrigatórias em `skills/db_migrate.py`.

### Fase 5: Integração CLI & Docs
- [x] Comandos `telemetry`, `telclassify` e `native` em `wygor.py`.
- [x] `docs/manual/08_observability_and_native.md`.
- [x] `CHANGELOG.md` e `memory/system_state.md`.

### ⏳ Pendências Futuras
- [ ] Configurar job Cron/Daemon para execução periódica do coletor (a cada 10 min).
- [ ] Ampliar padrões de assinatura de erro para mais linguagens.
