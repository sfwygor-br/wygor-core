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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from utils.db_service import get_model_for_role

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
CHAT_MODEL = get_model_for_role("complex", default="qwen2.5-coder:3b", env_var="OLLAMA_CHAT_MODEL")

VERBOSE = False

def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)

def sanitize_for_json(text):
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[^\x20-\x7E\n\r\t]', '', text)
    return text

def ask_llm(prompt, system_prompt="Você é um engenheiro de software.", max_retries=2):
    """Consulta o Ollama e extrai JSON com retry e reparo."""
    full_prompt = f"{system_prompt}\n\nInstrução: {prompt}\n\nResponda APENAS com um objeto JSON válido."
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
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                raw = res.get("response", "")
                raw = sanitize_for_json(raw)
                json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if json_match:
                    raw_json = json_match.group(0)
                    raw_json = re.sub(r',\s*}', '}', raw_json)
                    raw_json = re.sub(r',\s*]', ']', raw_json)
                    return json.loads(raw_json, strict=False)
                else:
                    return json.loads(raw, strict=False)
        except Exception as e:
            vprint(f"⚠️ Tentativa {attempt+1} falhou: {e}")
            if attempt == max_retries - 1:
                return {}
    return {}

def run_skill(script_name, args_list):
    script_path = os.path.join(SCRIPT_DIR, script_name)
    try:
        res = subprocess.run(
            [sys.executable, script_path] + args_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def detect_and_install_missing_module(error_log):
    match = re.search(r"ModuleNotFoundError: No module named '(\w+)'", error_log)
    if match:
        module = match.group(1)
        print(f"   📦 Instalando dependência faltante: {module}...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", module], check=True, capture_output=True)
            print(f"   ✅ Pacote '{module}' instalado com sucesso.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Falha ao instalar '{module}': {e.stderr.decode() if e.stderr else ''}")
            return False
    return False

def normalize_files(files_data):
    """
    Converte diferentes formatos de 'files' para uma lista padronizada:
    [{"path": "nome.py", "content": "..."}]
    """
    if isinstance(files_data, list):
        # Já está no formato esperado
        return files_data
    elif isinstance(files_data, dict):
        # Formato: {"arquivo.py": "conteúdo", ...}
        normalized = []
        for path, content in files_data.items():
            normalized.append({"path": path, "content": content})
        return normalized
    else:
        return []

def run_agent_task(prompt_task, project_path=".", project_name="default", max_retries=3, no_tests=False, verbose=False):
    global VERBOSE
    VERBOSE = verbose

    print(f"\n🤖 [WYGOR CODE AGENT] Processando solicitação: '{prompt_task}'\n")

    abs_project_path = os.path.abspath(project_path)

    # 1. Git Prepare
    task_slug = prompt_task[:25].lower().replace(" ", "-")
    print("1️⃣ [Git Guard] Isolando workspace...")
    run_skill("git_guard.py", ["prepare", project_path, "-t", task_slug])

    # 2. RAG Context (truncado)
    print("2️⃣ [Context Gathering] Buscando contexto no pgvector...")
    ok, ctx, _ = run_skill("query_knowledge.py", [prompt_task, "-p", project_name, "-l", "2", "--raw"])
    if ctx and len(ctx) > 1000:
        ctx = ctx[:1000] + "\n... (contexto truncado)"
    if ctx:
        vprint("📚 [RAG Context]:")
        vprint(ctx)
    else:
        vprint("ℹ️ Nenhum contexto específico.")

    context_str = f"Contexto:\n{ctx}" if ctx else ""

    # 3. Planejamento com loop de tentativas
    plan = None
    files = []
    run_cmd = None
    test_cmd = None

    if no_tests:
        test_instructions = "NÃO crie testes. Foque na aplicação principal e informe 'run_cmd'."
        format_example = {
            "files": [{"path": "main.py", "content": "código funcional"}],
            "run_cmd": "python3 main.py"
        }
    else:
        test_instructions = "Crie código e testes unitários."
        format_example = {
            "files": [
                {"path": "src/app.py", "content": "..."},
                {"path": "tests/test_app.py", "content": "..."}
            ],
            "test_cmd": "python3 -m unittest discover",
            "run_cmd": "python3 src/app.py"
        }

    for attempt in range(1, 4):  # até 3 tentativas
        print(f"3️⃣ [LLM Planning] Tentativa {attempt}/3...")
        planning_prompt = f"""
Tarefa: {prompt_task}
{context_str}

DIRETRIZES:
- Código executável e completo.
- Use 'requests' se precisar de API, trate erros.
- Aceite argumentos via sys.argv ou input().
- Inclua if __name__ == "__main__".
- Saída útil no console.

{test_instructions}

Retorne JSON estrito com:
{json.dumps(format_example, indent=2)}
"""
        plan = ask_llm(planning_prompt)

        if not plan:
            vprint("   ⚠️ Plano vazio. Tentando novamente...")
            continue

        # Normaliza o campo 'files'
        raw_files = plan.get("files", [])
        files = normalize_files(raw_files)
        run_cmd = plan.get("run_cmd", None)
        test_cmd = plan.get("test_cmd", None)

        if files:
            vprint("🧠 [Plano Gerado]:")
            vprint(json.dumps(plan, indent=2, ensure_ascii=False))
            break
        else:
            vprint("   ⚠️ Campo 'files' inválido. Tentando novamente...")
            # Tenta com prompt mais curto
            short_prompt = f"Implemente: {prompt_task}. Retorne JSON com 'files' (lista de objetos {{'path','content'}}) e 'run_cmd'."
            plan = ask_llm(short_prompt)
            if plan:
                raw_files = plan.get("files", [])
                files = normalize_files(raw_files)
                if files:
                    run_cmd = plan.get("run_cmd", None)
                    test_cmd = plan.get("test_cmd", None)
                    break

    if not files:
        print("❌ Não foi possível obter um plano válido após 3 tentativas. Encerrando.")
        return False

    # 4. Escrever arquivos
    print("4️⃣ [Code Engineer] Escrevendo arquivos...")
    for f in files:
        target_path = os.path.join(project_path, f.get("path", ""))
        if not target_path:
            print("   ⚠️ Arquivo sem 'path' ignorado.")
            continue
        content = f.get("content", "")
        ok_write, _, _ = run_skill("code_engineer.py", ["write", target_path, "--content", content, "--overwrite"])
        print(f"  └─ {f['path']}: {'✅' if ok_write else '❌'}")

    # 5. Validação
    if no_tests:
        print("\n5️⃣ [Execution-Driven Healing] Validando por execução direta...")
        success = False
        for attempt in range(1, max_retries + 1):
            print(f"   🧪 Tentativa {attempt}/{max_retries} de execução...")
            runner_args = [project_path]
            if run_cmd:
                runner_args.extend(["-c", run_cmd])

            ok_run, out_run, err_run = run_skill("code_runner.py", runner_args)

            if not ok_run:
                print("   ⚠️ Execução falhou. Auto-correção...")
                error_logs = err_run if err_run else out_run
                print(f"   ❌ Erro:\n{error_logs}")

                if detect_and_install_missing_module(error_logs):
                    continue

                fix_prompt = f"""
Erro durante execução:
{error_logs}
Corrija o código e retorne JSON com os arquivos corrigidos.
"""
                fixes = ask_llm(fix_prompt)
                if fixes:
                    raw_fixes = fixes.get("files", [])
                    fixed_files = normalize_files(raw_fixes)
                    for f in fixed_files:
                        target_path = os.path.join(project_path, f.get("path", ""))
                        if target_path:
                            run_skill("code_engineer.py", ["write", target_path, "--content", f.get("content", ""), "--overwrite"])
                continue

            # Verifica saída significativa
            if out_run and len(out_run) > 20:
                print("   ✅ Executou com sucesso e gerou saída!")
                print(f"   📄 Output:\n{out_run}")
                success = True
                break
            else:
                print("   ⚠️ Saída muito curta ou vazia. Corrigindo...")
                fix_prompt = f"""
Saída atual:
{out_run if out_run else "(vazia)"}
Reescreva o código para produzir saída útil conforme solicitado: {prompt_task}
Retorne JSON com os arquivos corrigidos.
"""
                fixes = ask_llm(fix_prompt)
                if fixes:
                    raw_fixes = fixes.get("files", [])
                    fixed_files = normalize_files(raw_fixes)
                    for f in fixed_files:
                        target_path = os.path.join(project_path, f.get("path", ""))
                        if target_path:
                            run_skill("code_engineer.py", ["write", target_path, "--content", f.get("content", ""), "--overwrite"])

        if not success:
            print("⚠️ A validação não obteve sucesso após várias tentativas, mas os arquivos foram gerados.")
    else:
        print("\n5️⃣ [Code Checker] Rodando testes...")
        for attempt in range(1, max_retries + 1):
            print(f"   🧪 Tentativa {attempt}/{max_retries} de validação...")
            ok_check, out_check, err_check = run_skill("code_checker.py", [project_path, "-c", test_cmd])
            if ok_check:
                print("   ✅ Testes passaram!")
                break
            print("   ⚠️ Testes falharam. Corrigindo...")
            error_logs = err_check if err_check else out_check
            fix_prompt = f"Testes falharam: {error_logs}. Corrija e retorne JSON com os arquivos."
            fixes = ask_llm(fix_prompt)
            if fixes:
                raw_fixes = fixes.get("files", [])
                fixed_files = normalize_files(raw_fixes)
                for f in fixed_files:
                    target_path = os.path.join(project_path, f.get("path", ""))
                    if target_path:
                        run_skill("code_engineer.py", ["write", target_path, "--content", f.get("content", ""), "--overwrite"])

    # 6. Commit
    print("\n6️⃣ [Git Commit] Registrando alterações...")
    commit_msg = f"feat: {prompt_task}"
    run_skill("git_guard.py", ["commit", project_path, "-m", commit_msg])

    print("\n🎉 [AGENTE CONCLUÍDO]")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task", help="Descrição da tarefa")
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