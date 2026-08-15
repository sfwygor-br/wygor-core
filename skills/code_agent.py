#!/usr/bin/env python3
import os
import sys
import json
import re
import argparse
import subprocess
import urllib.request
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5-coder:3b")

def run_skill(script_name, args_list):
    """Executa uma skill local e captura o resultado."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    try:
        res = subprocess.run(
            [sys.executable, script_path] + args_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return res.returncode == 0, res.stdout.strip() if res.stdout else "", res.stderr.strip() if res.stderr else ""
    except Exception as e:
        return False, "", str(e)

def ask_llm(prompt, system_prompt="Você é um engenheiro de software especialista em automação."):
    """Consulta o Ollama e extrai o bloco JSON com resiliência."""
    full_prompt = f"{system_prompt}\n\nInstrução: {prompt}\n\nResponda APENAS com um objeto JSON válido no formato solicitado."
    
    payload = {
        "model": CHAT_MODEL,
        "prompt": full_prompt,
        "stream": False
    }
    
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            raw_response = res.get("response", "")
            
            # Tenta extrair o bloco JSON da resposta
            json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(raw_response)
    except Exception as e:
        print(f"❌ Erro ao comunicar com Ollama: {e}", file=sys.stderr)
        return {}

def run_agent_task(prompt_task, project_path=".", project_name="default", max_retries=3, no_tests=False):
    print(f"\n🤖 [WYGOR CODE AGENT] Processando solicitação: '{prompt_task}'\n")

    abs_project_path = os.path.abspath(project_path)

    # 1. Preparar Git Branch
    task_slug = prompt_task[:25].lower().replace(" ", "-")
    print("1️⃣ [Git Guard] Isolando workspace...")
    run_skill("git_guard.py", ["prepare", project_path, "-t", task_slug])

    # 2. Resgatar Contexto RAG
    ok, ctx, _ = run_skill("query_knowledge.py", [prompt_task, "-p", project_name, "-l", "2", "--raw"])
    context_str = f"Contexto do Projeto:\n{ctx}" if ctx else "Nenhum contexto prévio necessário."

    # 3. Planejar Código e Arquivos via LLM
    if no_tests:
        test_instructions = "NÃO crie arquivos de testes unitários. Foque na aplicação principal e informe o 'run_cmd' para executá-la."
        format_example = f"""{{
  "files": [
    {{
      "path": "main.py",
      "content": "print('Hello World')"
    }}
  ],
  "run_cmd": "python3 main.py"
}}"""
    else:
        test_instructions = "Crie o código-fonte e também os testes unitários correspondentes."
        format_example = f"""{{
  "files": [
    {{
      "path": "src/scientific_calc.py",
      "content": "import math\\n\\ndef power(base, exp):\\n    return base ** exp"
    }},
    {{
      "path": "tests/test_scientific_calc.py",
      "content": "import unittest\\nfrom src.scientific_calc import power\\n\\nclass TestCalc(unittest.TestCase):\\n    def test_power(self):\\n        self.assertEqual(power(2, 3), 8)"
    }}
  ],
  "test_cmd": "PYTHONPATH={abs_project_path} python3 -m unittest discover -s {abs_project_path}/tests -p 'test_*.py'",
  "run_cmd": "python3 src/scientific_calc.py"
}}"""

    planning_prompt = f"""
Sua tarefa é implementar a seguinte solicitação: "{prompt_task}".
{context_str}

Instruções adicionais: {test_instructions}

Retorne um JSON no seguinte formato estrito:
{format_example}
"""
    print("2️⃣ [LLM Planning] Gerando arquitetura e código-fonte...")
    plan = ask_llm(planning_prompt)
    files = plan.get("files", [])
    test_cmd = plan.get("test_cmd", f"PYTHONPATH={abs_project_path} python3 -m unittest discover -s {abs_project_path}/tests -p 'test_*.py'")
    run_cmd = plan.get("run_cmd", None)

    if not files:
        print("❌ A LLM não gerou planos válidos de arquivos. Encerrando.")
        return False

    # 4. Escrever Arquivos
    print("3️⃣ [Code Engineer] Escrevendo arquivos gerados no disco...")
    for f in files:
        target_path = os.path.join(project_path, f["path"])
        ok_write, out, _ = run_skill("code_engineer.py", ["write", target_path, "--content", f["content"], "--overwrite"])
        print(f"  └─ {f['path']}: {'✅' if ok_write else '❌'}")

    # 5. Loop de Validação e Auto-Correção (Self-Healing)
    if no_tests:
        print("\n4️⃣ [Execution-Driven Healing] Validando por execução direta (sem unit tests)...")
        for attempt in range(1, max_retries + 1):
            print(f"   🧪 Tentativa {attempt}/{max_retries} de execução...")
            runner_args = [project_path]
            if run_cmd:
                runner_args.extend(["-c", run_cmd])

            ok_run, out_run, err_run = run_skill("code_runner.py", runner_args)

            if ok_run:
                print("   ✅ O programa executou com sucesso sem erros!")
                if out_run:
                    print(f"   📄 Output:\n{out_run}")
                break

            print(f"   ⚠️ Execução falhou com erros! Ativando auto-correção via log de execução...")
            error_logs = err_run if err_run else out_run
            print(f"   ❌ Log de Erro:\n{error_logs}")

            fix_prompt = f"""
O código gerado para a tarefa '{prompt_task}' falhou durante a execução com o comando '{run_cmd}'.
Log de erro / Traceback:
{error_logs}

Corrija o código para solucionar a falha e garantir que o programa execute do início ao fim sem erros. 
Retorne um JSON estrito:
{{
  "files": [
    {{
      "path": "caminho/do/arquivo.py",
      "content": "código corrigido"
    }}
  ]
}}
"""
            fixes = ask_llm(fix_prompt)
            for f in fixes.get("files", []):
                target_path = os.path.join(project_path, f["path"])
                run_skill("code_engineer.py", ["write", target_path, "--content", f["content"], "--overwrite"])

    else:
        print("\n4️⃣ [Code Checker] Rodando testes unitários e verificações...")
        for attempt in range(1, max_retries + 1):
            print(f"   🧪 Tentativa {attempt}/{max_retries} de validação...")
            ok_check, out_check, err_check = run_skill("code_checker.py", [project_path, "-c", test_cmd])

            if ok_check:
                print("   ✅ Todos os testes passaram com sucesso!")
                break

            print(f"   ⚠️ Validação falhou! Ativando ciclo de auto-correção (Self-Healing)...")
            error_logs = err_check if err_check else out_check

            fix_prompt = f"""
O código gerado para a tarefa '{prompt_task}' apresentou o seguinte erro de teste:
{error_logs}

Corrija o código para solucionar a falha. Retorne um JSON estrito:
{{
  "files": [
    {{
      "path": "src/nome_do_arquivo.py",
      "content": "código corrigido"
    }},
    {{
      "path": "tests/test_nome_do_arquivo.py",
      "content": "código de teste corrigido herdando de unittest.TestCase"
    }}
  ]
}}
"""
            fixes = ask_llm(fix_prompt)
            for f in fixes.get("files", []):
                target_path = os.path.join(project_path, f["path"])
                run_skill("code_engineer.py", ["write", target_path, "--content", f["content"], "--overwrite"])

        # 6. Execução final do projeto quando usado modo com testes
        print("\n5️⃣ [Code Runner] Executando o programa gerado...")
        runner_args = [project_path]
        if run_cmd:
            runner_args.extend(["-c", run_cmd])
        run_skill("code_runner.py", runner_args)

    # 7. Commit das Alterações
    print("\n6️⃣ [Git Commit] Registrando a solução no Git...")
    commit_msg = f"feat: {prompt_task}"
    run_skill("git_guard.py", ["commit", project_path, "-m", commit_msg])

    print("\n🎉 [AGENTE DE CÓDIGO CONCLUÍDO COM SUCESSO!]")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agente Autônomo de Código do Wygor Core")
    parser.add_argument("task", help="Descrição em linguagem natural da tarefa")
    parser.add_argument("-p", "--project", default="default", help="Nome do projeto no pgvector")
    parser.add_argument("-r", "--repo", default=".", help="Caminho do repositório/workspace")
    parser.add_argument("--no-tests", action="store_true", help="Ignora testes unitários e valida através de execução direta (Execution-Driven Healing)")

    args = parser.parse_args()
    run_agent_task(
        args.task, 
        project_path=args.repo, 
        project_name=args.project, 
        no_tests=args.no_tests
    )