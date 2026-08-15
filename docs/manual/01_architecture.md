# Wygor Core - Arquitetura & Diretrizes de Engenharia

## 🏗️ Filosofia do Sistema
O Wygor Core é um motor contextual e executivo projetado para servir como cérebro de código e assistente autonômo.
Ele opera sob a premissa de **Zero Hallucination via RAG Híbrido** e **Extensibilidade por Skills**.

## 🧩 Componentes do Core
1. **CLI Central (`wygor.py`)**: Ponto de entrada unificado para comandos e utilitários.
2. **Camada de Dados (`pgvector` / PostgreSQL)**:
   - `document_chunks`: Armazena trechos de código, documentação e memórias técnicas.
   - **RAG Híbrido**: Combina Vector Search (distância de cosseno `<=>`) com Full-Text Search (`tsvector`/`tsquery`) via RRF (Reciprocal Rank Fusion).
3. **Módulo de Skills (`skills/`)**:
   - Scripts autocontidos e executáveis.
   - Padrão Unix: Recebem argumentos de linha de comando (`argparse`) e retornam status/saída estruturada.
