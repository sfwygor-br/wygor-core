# Wygor Core - Manual de Validação e Testes (Self-Healing)

## 🧪 Validação Automatizada de Código
A skill `skills/code_checker.py` atua como o portão de validação antes da conclusão de qualquer tarefa de engenharia.

### Recursos:
- **Detecção Automática**: Identifica automaticamente suítes como `pytest`, `npm test`, `cargo test`, `go test` ou `make test`.
- **Comandos Customizados**: Permite passar `-c / --cmd` para executar linters específicos (ex: `flake8`, `eslint`, `mypy`).
- **Loop de Feedback**: Em caso de falha, captura o `stderr`/`stdout` para que o agente de código ajuste a solução antes do commit final.
