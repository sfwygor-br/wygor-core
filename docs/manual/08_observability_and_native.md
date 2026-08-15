# Wygor Core - Observabilidade Externa & Executor Nativo (Spec 002)

Este manual descreve as duas novas capacidades introduzidas pela
`specs/002-telemetry-and-native-execution.md`:

1. **Observabilidade Externa Não-Invasiva** (`telemetry_collector` + `telemetry_classify`)
2. **Executor Nativo de Sistema** (`native_workflow`)

---

## 1. Observabilidade Externa Não-Invasiva

### Filosofia
Coleta logs e estados do sistema **sem injetar ou alterar bibliotecas de
logging** nos projetos monitorados. O acesso é exclusivamente de leitura
(`ps`, `journalctl`, arquivos em `/var/log`), garantindo isolamento total.

### Coletor (`telemetry collect`)
Serviço leve, executável manualmente ou por Cron/Daemon, que:
- Mapeia PIDs de processos ativos relevantes (`ps`).
- Lê saídas do `journalctl` (sistema ou unidade systemd específica).
- Lê arquivos de log em `/var/log/` (syslog, dmesg, kern.log).
- Extrai assinaturas de erro/exceção e persiste em `system_telemetry_events`
  sob o escopo `system_telemetry`.

```bash
# Coleta padrão (últimos 30 min)
wygor telemetry collect

# Coleta para unidade systemd específica / janela customizada
wygor telemetry collect --unit nginx --minutes 60

# Lista eventos coletados
wygor telemetry list

# Limpa eventos
wygor telemetry clear
```

### Classificador & Vetorização (`wygor telclassify`)
Job secundário que aciona o Wygor Core (via LLM local) para classificar os
erros coletados (severidade + assinatura) e os **vetoriza** na tabela
`document_chunks` sob o escopo `system_telemetry`, habilitando busca semântica
(RAG) sobre logs de sistema.

```bash
wygor telclassify            # classifica eventos das últimas 24h
wygor telclassify --window-hours 48
```

---

## 2. Executor Nativo de Sistema (`wygor native`)

### Filosofia
Em vez de reescrever lógica em Python para cada protocolo (SSH, tar/rsync,
HTTP via curl), a skill gera e executa **pipelines de comandos Bash nativos**,
reaproveitando utilitários já presentes no SO.

### Mapeamento de binários (`wygor native check`)
Antes de executar, a skill verifica quais utilitários estão disponíveis no
ambiente (`which` / `shutil.which`).

```bash
wygor native check
```

### Ciclo Executivo com Auto-Healing (`wygor native run`)
O executor roda em malha fechada (Loop de Execução):
1. Gera/aceita o pipeline Bash.
2. Executa com `set -o pipefail`.
3. Se falhar, analisa a saída de erro e **re-executa com fallback** (até 3 tentativas).
4. Registra o histórico em `native_execution_logs` (status `success`/`healed`/`failed`).

```bash
# Executa um pipeline nativo direto
wygor native run -c "ps aux | grep -i postgres | grep -v grep"

# Gera o comando via LLM a partir de uma instrução natural
wygor native run --instruction "listar os 10 maiores arquivos em /var/log"

# Histórico de execuções
wygor native history
```

---

## 3. Tabelas Novas (Spec 002)

- `system_telemetry_events`: eventos de telemetria coletados.
- `native_execution_logs`: histórico de execução do executor nativo.

Migradas automaticamente por `wygor migrate` via `migrations/006_add_telemetry.sql`.

---

## 4. Prompts - Spec 002

- `prompts/native_workflow_system.txt`: geração de pipelines Bash nativos.
- `prompts/telemetry_classify_system.txt`: triagem/classificação de logs.
