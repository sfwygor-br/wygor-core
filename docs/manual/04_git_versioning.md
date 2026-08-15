# Wygor Core - Manual de Versionamento Git Local

## 🛡️ Gestão de Workspace
O Wygor opera com isolamento local para garantir a integridade dos seus projetos.

### Fluxo Operacional:
1. **Inicialização Automática**: Se a pasta de destino não for um repositório Git, o Wygor executa `git init` e injeta um `.gitignore` padrão.
2. **Branches de Tarefa**: Toda alteração é feita sob uma branch dedicada (`feat/wygor-<task>` ou `fix/wygor-<task>`).
3. **Commits Locais**: Após concluir a alteração ou criar arquivos, os commits são registrados mantendo o histórico rastreável.
4. **Push Remoto (Futuro)**: O push só ocorrerá sob demanda explicita se um repositório remoto estiver configurado.
