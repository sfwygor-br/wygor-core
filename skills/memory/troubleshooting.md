
## Resolução de Problema - 2026-08-16 18:33:37
- **Tarefa**: o sistema saas-agente usa ia para auxiliar no atendimento de conversas de whatsapp e no sistema SDD1 que chamamos de mensageria ja tem um super sistema de gerenciamento de sessoes whatsapp e com suporte a integração por chave api ke. sera que podemos integrar os dois sistemas e substituir o evolution do saas-agente pelo mensageria?
- **Comando que Falhou**: `PGPASSWORD=root psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "ALTER TABLE sessions ADD COLUMN api_key VARCHAR(255);"`
- **Erro (STDERR)**: ERROR:  relation "sessions" does not exist
- **Solução Validada**: `psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "CREATE TABLE IF NOT EXISTS sessions (id SERIAL PRIMARY KEY, api_key VARCHAR(255));"`

---
