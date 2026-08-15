# 001 - Especificação do Core wygor-core

## 1. Objetivo do Sistema
Construção de uma base de conhecimento local persistente, com suporte a busca vetorial (RAG) utilizando PostgreSQL + pgvector. O sistema foi projetado para permitir a indexação de documentos, notas e códigos gerados localmente no Parrot OS, servindo como fonte de dados confiável tanto para LLMs locais quanto para agentes/APIs externos.

## 2. Estrutura SDD (Spec-Driven Development)
A arquitetura do projeto segue a metodologia orientada por especificações e memória evolutiva:
- **specs/**: Documentos de especificação técnica e arquitetura de componentes.
- **tasks/**: Listas de tarefas executáveis e roadmaps passo a passo.
- **skills/**: Scripts, conectores e rotinas em Python/Bash reutilizáveis.
- **memory/**: Estado evolutivo do ecossistema, contexto persistente e logs de execução.
- **changelogs/**: Histórico estruturado de mudanças por versão.

## 3. Arquitetura Híbrida & Modelos
O ecossistema otimiza a alocação de LLMs de acordo com as restrições de hardware:
- **Qwen 2.5 Coder 3B / 1.5B**: Automação via CLI (`aichat`), geração de scripts e manipulação do ambiente local.
- **Nomic Embed Text**: Modelo especializado em gerar embeddings de 768 dimensões para indexação vetorial no PostgreSQL.
- **APIs Externas (Claude, OpenAI, Gemini)**: Consultas e análises de altíssima complexidade sobre a base gerada localmente.

## 4. Hardware e Restrições
- **OS**: Parrot OS 7.3
- **CPU / iGPU**: Intel Iris Xe Graphics (Memória VRAM compartilhada)
- **RAM**: 16 GB DDR4/DDR5
- **Estratégia**: Limitar modelos locais ao teto de ~3B-4B parâmetros para manter o consumo sob 3-4 GB de RAM, garantindo responsividade da GPU e integridade do sistema.
