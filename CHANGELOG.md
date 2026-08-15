# CHANGELOG - Wygor Core

## [1.2.0] - 2026-08-15 (Spec 002)

### 📡 Observabilidade Externa Não-Invasiva
* **`skills/telemetry_collector.py`**: Coleta PIDs, logs `journalctl` e `/var/log`
  (leitura), extrai assinaturas de erro e persiste em `system_telemetry_events`
  no escopo `system_telemetry`, sem alterar bibliotecas dos projetos monitorados.
* **`skills/telemetry_classify.py`**: Job secundário que classifica os erros via LLM
  (prompt `telemetry_classify_system.txt`) e os vetoriza em `document_chunks` no
  escopo `system_telemetry` (RAG).

### 🖥️ Executor Nativo de Sistema
* **`skills/native_workflow.py`**: Gera e executa pipelines Bash nativos
  (ssh, curl, tar, rsync, journalctl, ps, top) com mapeamento de binários
  (`which`), ciclo de auto-healing, reexecução e análise de fallbacks.
* **`prompts/native_workflow_system.txt`**: Template de geração de pipelines nativos.

### 📦 Banco de Dados & CLI
* **`migrations/006_add_telemetry.sql`**: Tabelas `system_telemetry_events` e
  `native_execution_logs`.
* **`skills/db_migrate.py`**: Novas tabelas adicionadas às obrigatórias.
* **`wygor.py`**: Novos comandos `telemetry`, `telclassify` e `native`.
* **`docs/manual/08_observability_and_native.md`**: Manual das novas capacidades.

---

## [1.1.0] - 2026-08-15

### 🛠️ Alterações na Interface CLI (`wygor.py`)
* **Roteador por Subcomandos**: Entrada unificada para invocar as skills sem choque de flags do `argparse`[cite: 18, 19].
* **Correção do `wygor migrate`**: Mapeamento direto para `skills/db_migrate.py` sem argumentos positional inválidos.
* **Correção do `wygor chat`**: Despacho para `skills/chat.py` para gerenciamento de sessões e workflows.

### 🧩 Mapeamento da CLI & Skills
* **`wygor agent "<instrução>"`**: Execução autônoma de engenharia de código.
* **`wygor migrate`**: Aplicação de migrações no PostgreSQL.
* **`wygor search "<query>"`**: Consulta ao motor de RAG Híbrido[cite: 18].
* **`wygor ingest <caminho>`**: Indexação incremental de código e documentação[cite: 18].
* **`wygor watch <caminho>`**: Monitoramento e reindexação em tempo real[cite: 18].
* **`wygor memory "<nota>"`**: Registro de memórias técnicas no banco de dados[cite: 18].
* **`wygor git prepare/commit`**: Isolamento de tarefas em branches dedicadas (`feat/wygor-*`)[cite: 20, 21].
* **`wygor code write/patch`**: Edição precisa e criação de arquivos[cite: 22].
* **`wygor check <path>`**: Execução de linters e testes (`pytest`, `npm test`)[cite: 23].
* **`wygor manual [seção]`**: Exibição da documentação presente em `docs/manual/`[cite: 18].
* **`wygor chat`**: Interface do chat orquestrador[cite: 24].

### 📖 Estrutura de Documentação (`docs/manual/`)
* **`01_arquitetura.md`**: Conceitos do RAG Híbrido e motor executivo[cite: 18].
* **`02_skills_standard.md`**: Padrão de construção de skills e interoperabilidade[cite: 19].
* **`03_git_protocol.md` & `04_git_manual.md`**: Protocolo de isolamento local Git[cite: 20, 21].
* **`05_code_engineer.md`**: Instruções do manipulador de código[cite: 22].
* **`06_code_checker.md`**: Validação e auto-healing[cite: 23].
* **`07_chat_orchestrator.md`**: Protocolo de chat e atalhos de fluxo[cite: 24].
