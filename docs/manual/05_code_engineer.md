# Wygor Core - Manual de Engenharia de Código

## 🛠️ Manipulação de Código por Agente
A skill `skills/code_engineer.py` dá ao Wygor a capacidade de criar novos arquivos, aplicar alterações pontuais (patches) e buscar contexto existente no repositório.

### Funcionalidades:
- **`code write`**: Cria arquivos ou sobrescreve o conteúdo total de um arquivo existente.
- **`code patch`**: Altera apenas um bloco/trecho específico sem sobrescrever o restante do arquivo.
- **`code context`**: Executa a busca híbrida para que o agente entenda como declarar funções, interfaces ou tipos no padrão do projeto.
- **Auto-Commit**: Se passado o parâmetro `-m / --message` e o `-repo / --repository`, o Wygor registra as mudanças automaticamente via `git_guard`.
