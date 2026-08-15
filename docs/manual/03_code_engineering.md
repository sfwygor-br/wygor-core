# Wygor Core - Protocolo de Engenharia de Código Autônoma

## 🛡️ Regra de Ouro: Git Isolado
Toda e qualquer modificação de código proposta pelo Wygor DEVE ser realizada em uma branch separada (`feat/wygor-*` ou `fix/wygor-*`).

## 🔄 Fluxo de Desenvolvimento
1. **Workspace Check**: Verificar se o repositório está limpo (`git_guard.py`).
2. **Branch Creation**: Mudar para a branch da tarefa.
3. **Context Gathering**: Buscar no pgvector os arquivos afetados e suas dependências.
4. **Code Modification**: Escrever ou alterar arquivos (`code_engineer.py`).
5. **Validation Loop**: Rodar linters/testes (`code_checker.py`).
6. **Commit & Summary**: Gerar commit com relatório de alterações.
