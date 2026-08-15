# Wygor Core - Especificação para Criação de Skills

## 📐 Padrão de Engenharia de Skills
Toda nova habilidade adicionada ao `skills/` deve seguir estas regras:

1. **Shebang e Execução**: Deve começar com `#!/usr/bin/env python3` e possuir permissão `+x`.
2. **Carregamento de Ambiente**: Deve ler configurações do `.env` usando `python-dotenv`.
3. **Interface CLI**: Utilizar `argparse` para suporte a parâmetros formais.
4. **Isolamento por Projeto**: Suportar a flag `-p / --project` para permitir multi-tenancy/multi-projetos.
5. **Comunicação com o CLI Central (`wygor.py`)**:
   - Cadastrar o comando no menu `main()` do `wygor.py`.
