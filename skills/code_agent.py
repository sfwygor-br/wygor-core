#!/usr/bin/env python3
import os
import sys
import argparse
from typing import List, Dict, Any
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.model_manager import get_model_for_role
from utils.agent_engine import ReActEngine, run_skill_script

load_dotenv()

FAST_MODEL: str = get_model_for_role("router", default="qwen2.5-coder:3b")
COMPLEX_MODEL: str = get_model_for_role("complex", default="qwen2.5-coder:7b")


def run_agent_task(
    prompt_task: str, 
    project_path: str = ".", 
    project_name: str = "default", 
    max_retries: int = 3, 
    no_tests: bool = False, 
    verbose: bool = False
) -> bool:
    print(f"\n🤖 [WYGOR CODE AGENT] Iniciando tarefa: '{prompt_task}'\n")

    # 1. Isolamento via Git Guard
    task_slug = prompt_task[:25].lower().replace(" ", "-")
    print("1️⃣ [Git Guard] Isolando workspace...")
    run_skill_script("git_guard.py", ["prepare", project_path, "-t", task_slug])

    # 2. Inicialização do ReAct Engine
    engine = ReActEngine(
        fast_model=FAST_MODEL,
        complex_model=COMPLEX_MODEL,
        project_name=project_name,
        max_steps=max_retries,
        verbose=verbose
    )

    # 3. Formatação da Instrução para o ReAct Engine
    test_instruction = "Sem testes. Validação direta via execução." if no_tests else "Escreva testes e garanta aprovação no code_checker."
    agent_prompt = f"""
Você é o Agente de Código ReAct do Wygor Core.
Sua missão é concluir a seguinte tarefa de engenharia no repositório '{project_path}':

OBJETIVO:
{prompt_task}

DIRETRIZES:
- {test_instruction}
- Crie ou altere arquivos necessários usando as skills apropriadas.
- Caso ocorra algum erro durante a execução/testes, utilize a capacidade de Auto-Healing para corrigir.
"""

    messages = [
        {"role": "system", "content": "Você é um engenheiro de software autônomo baseado no padrão ReAct."},
        {"role": "user", "content": agent_prompt}
    ]

    # Mapeamento sintético das ferramentas de código
    code_skills: List[Dict[str, Any]] = [
        {"intent": "query_knowledge", "script": "query_knowledge.py", "description": "Busca contexto técnico na base vetorial"},
        {"intent": "code_engineer", "script": "code_engineer.py", "description": "Escreve e altera arquivos no projeto"},
        {"intent": "code_checker", "script": "code_checker.py", "description": "Executa a suíte de testes unitários"}
    ]

    def dummy_classifier(user_input: str, active_project: str, messages_history: Any = None) -> str:
        return f'{{"intent": "code_engineer", "project": "{active_project}", "use_rag": true, "test_cmd": "python3 skills/code_checker.py {project_path}"}}'

    # 4. Execução guiada por metas via Engine
    response_text, _ = engine.run(
        user_input=agent_prompt,
        messages_history=messages,
        dynamic_skills=code_skills,
        classify_prompt_builder=dummy_classifier
    )

    # 5. Commit Final
    print("\n🔒 [Git Commit] Finalizando alterações...")
    commit_msg = f"feat: {prompt_task}"
    run_skill_script("git_guard.py", ["commit", project_path, "-m", commit_msg])

    print("\n🎉 [AGENTE DE CÓDIGO CONCLUÍDO]")
    print(f"\nResumo da execução:\n{response_text}\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wygor Code Agent (ReAct Light Client)")
    parser.add_argument("task", help="Descrição da tarefa de código")
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("-r", "--repo", default=".")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    run_agent_task(
        args.task,
        project_path=args.repo,
        project_name=args.project,
        no_tests=args.no_tests,
        verbose=args.verbose
    )