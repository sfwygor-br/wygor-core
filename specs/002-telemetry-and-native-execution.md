# Spec 002: Observabilidade Externa por Cron e Executor Nativo de Sistema

## 1. Visão Geral e Objetivos
Esta especificação define a arquitetura para duas novas capacidades do **Wygor Core**:
1. **Observabilidade Externa Não-Invasiva**: Coleta de logs e estados do sistema via processos em segundo plano (Cron/Daemon) sem a necessidade de modificar os códigos-fonte existentes no computador.
2. **Skill de Invocação de Ferramentas Nativas do SO**: Permite ao agente utilizar utilitários nativos da máquina (ex: `ssh`, `journalctl`, `ps`, `top`, `curl`) através de uma rotina sequencial de instruções com ciclo de auto-healing, reexecução e análise de fallbacks.

---

## 2. Requisitos de Observabilidade Externa (Logs & Processos)

### 2.1 Coleta de Logs e PIDs em Tempo Real
- **Isolamento**: O sistema não deve injetar nem alterar bibliotecas de logging nos projetos monitorados.
- **Serviço de Coleta (Cron/Daemon)**: Um script leve rodará periodicamente (ex: a cada 10 minutos) para:
  - Mapear PIDs de processos ativos relevantes.
  - Ler arquivos de saída padrão (`stdout`/`stderr`), logs do systemd (`journalctl`) ou arquivos em `/var/log/`.
  - Extrair assinaturas de erros e exceções.
- **Agente de Leitura e Triagem**:
  - Um job secundário acionará o Wygor Core para classificar os erros coletados.
  - Vetorização dos logs de erro na tabela `document_chunks` sob o escopo `system_telemetry`.

---

## 3. Requisitos da Skill de Execução Nativa (Native Workflow)

### 3.1 Utilização de Ferramentas Nativas do SO
- Em vez de reescrever lógica em Python para cada protocolo (ex: conexões SSH, manipulação de arquivos com `tar`/`rsync`), a skill gerará pipelines de comandos Bash nativos.
- Mapeamento prévio dos executáveis disponíveis no ambiente local (`which <binary>`).

### 3.2 Ciclo Executivo com Auto-Healing e Fallback
O executor nativo deve rodar em malha fechada (Loop de Execução):