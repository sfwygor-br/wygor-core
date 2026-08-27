# Mapeamento de Conhecimento - Projeto: wygor-core
Agente: system_knowledge_agent | Atualizado em: 2026-08-17T20:51:12.880859

---

#### **Gatilho do Cron - Projeto: wygor-core - 2026-08-17 20:44:26**

---

#### **Rotina de Varredura do Ecossistema**

Este cronograma realiza uma varredura completa do projeto `wygor-core` para identificar e atualizar as rotinas e utilitários atuais. A varredura inclui a inspeção das skills, scripts e tabelas SQL relacionadas ao projeto.

---

#### **Estrutura de Arquivos e Manifestos**

A estrutura de arquivos do projeto `wygor-core` é organizada conforme abaixo:

1. **Arquivos de Scripts:**
   - `auto_exec.py`
   - `chat.py`
   - `db_migrate.py`
   - `deepseek_agent.py`
   - `auto_diag.py`
   - `ssh_manager.py`
   - `session_manager.py`
   - `model_manager.py`
   - `telemetry_collector.py`
   - `telemetry_classify.py`
   - `native_workflow.py`
   - `cron_agent.py`

2. **Manifestos de Skills:**
   - `SKILL_MANIFEST.json` (contém detalhes sobre cada skill)

---

#### **Contratos de Execução e Parâmetros**

A varredura identificou os seguintes contratos de execução e parâmetros:

- **Skill: auto_exec.py**
  - Intenção: `auto_exec`
  - Descrição: Executa comandos Bash e scripts no sistema operacional / terminal de forma segura.

- **Skill: chat.py**
  - Intenção: `chat`
  - Parâmetro: `-p PROJETO` (projeto ativo)

- **Skill: db_migrate.py**
  - Intenção: `db_migrate`
  - Descrição: Gerencia e executa migrações no banco de dados PostgreSQL. Aplica schema.sql base e arquivos incrementais em migrations/*.sql rastreando versões.

- **Skill: deepseek_agent.py**
  - Intenção: `deepseek_task`
  - Descrição: Delega tarefas de alta complexidade ou refatorações densas para o DeepSeek.

- **Skill: auto_diag.py**
  - Intenção: `auto_diag`
  - Descrição: Executa autodiagnóstico de hardware, latência de IA e status do ambiente local, salvando a telemetria na base vetorial.

- **Skill: ssh_manager.py**
  - Intenção: `ssh_manager`
  - Parâmetro: `-p PROJETO` (projeto ativo)
  - Descrição: Gerencia perfis de conexão SSH no banco de dados (CRUD). Permite cadastrar, listar, remover e testar conexões de servidores.

- **Skill: session_manager.py**
  - Intenção: `session_manager`
  - Descrição: Gerencia e recupera sessões de chat e contextos anteriores armazenados no banco de dados.

- **Skill: model_manager.py**
  - Intenção: `model_config`
  - Parâmetro: `-p PROJETO` (projeto ativo)
  - Descrição: Gerencia e altera os modelos LLM (Ollama) atribuídos a diferentes tarefas (router, complex, intermediate).

- **Skill: telemetry_collector.py**
  - Intenção: `telemetry_collector`
  - Descrição: Coleta logs e estados do sistema (PIDs, stdout/stderr, journalctl e /var/log) de forma não-invasiva, extraindo assinaturas de erros e exceções.

- **Skill: telemetry_classify.py**
  - Intenção: `telemetry_classify`
  - Descrição: Classifica os logs de erro coletados pela telemetria e os vetoriza na tabela document_chunks sob o escopo system_telemetry para busca semântica (RAG).

- **Skill: native_workflow.py**
  - Intenção: `native_workflow`
  - Descrição: Gera e executa pipelines de comandos Bash nativos (ssh, journalctl, ps, top, curl, tar, rsync) com ciclo de auto-healing, reexecução e analise de fallbacks.

- **Skill: cron_agent.py**
  - Intenção: `cron_agent`
  - Parâmetro: `-p PROJETO` (projeto ativo)
  - Descrição: Executa rotinas de agentes autônomos por projeto (-p) com sessão fixa e re-indexação RAG.

---

#### **Tabelas SQL Atreladas**

A varredura identificou as seguintes tabelas SQL relacionadas ao projeto:

- `hosts` (gerenciamento de perfis SSH)
- `sessions` (gerenciamento de sessões de chat)
- `models` (gerenciamento de modelos LLM)
- `document_chunks` (telemetria classificada)

---

#### **Atualização do Documento de Arquitetura**

A varredura atualizou o documento de arquitetura conforme abaixo:

---

### Estrutura de Arquivos e Manifestos

1. **Arquivos de Scripts:**
   - `auto_exec.py`
   - `chat.py`
   - `db_migrate.py`
   - `deepseek_agent.py`
   - `auto_diag.py`
   - `ssh_manager.py`
   - `session_manager.py`
   - `model_manager.py`
   - `telemetry_collector.py`
   - `telemetry_classify.py`
   - `native_workflow.py`
   - `cron_agent.py`

2. **Manifestos de Skills:**
   - `SKILL_MANIFEST.json` (contém detalhes sobre cada skill)

---

#### Contratos de Execução e Parâmetros

- **Skill: auto_exec.py**
  - Intenção: `auto_exec`
  - Descrição: Executa comandos Bash e scripts no sistema operacional / terminal de forma segura.

- **Skill: chat.py**
  - Intenção: `chat`
  - Parâmetro: `-p PROJETO` (projeto ativo)

- **Skill: db_migrate.py**
  - Intenção: `db_migrate`
  - Descrição: Gerencia e executa migrações no banco de dados PostgreSQL. Aplica schema.sql base e arquivos incrementais em migrations/*.sql rastreando versões.

- **Skill: deepseek_agent.py**
  - Intenção: `deepseek_task`
  - Descrição: Delega tarefas de alta complexidade ou refatorações densas para o DeepSeek.

- **Skill: auto_diag.py**
  - Intenção: `auto_diag`
  - Descrição: Executa autodiagnóstico de hardware, latência de IA e status do ambiente local, salvando a telemetria na base vetorial.

- **Skill: