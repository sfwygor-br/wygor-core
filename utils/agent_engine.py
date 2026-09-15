#!/usr/bin/env python3
import os
import sys
import json
import re
import time
import subprocess
import urllib.request
from typing import Dict, Any, List, Tuple, Optional, TypedDict
from dotenv import load_dotenv
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.model_manager import get_model_for_role
from utils.prompt_loader import load_prompt

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip('/')

SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")
SOUND_PATH = "/usr/share/sounds/freedesktop/stereo/service-logout.oga"

# Cores ANSI Hacker Old-School
C_GREEN = "\033[1;32m"
C_DARK_GREEN = "\033[0;32m"
C_CYAN = "\033[1;36m"
C_YELLOW = "\033[1;33m"
C_RED = "\033[1;31m"
C_RESET = "\033[0m"


def play_completion_sound(sound_path: str = SOUND_PATH) -> None:
    if shutil.which("paplay"):
        cmd = ["paplay", sound_path]
    elif shutil.which("canberra-gtk-play"):
        cmd = ["canberra-gtk-play", "-f", sound_path]
    elif shutil.which("ffplay"):
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", sound_path]
    else:
        return

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class ExecutionTrace(TypedDict):
    attempt: int
    success: bool
    stdout: str
    stderr: str
    code_updated: bool


def sanitize_for_json(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)


def run_skill_script(script_name: str, args_list: List[str], capture_output: bool = True) -> Tuple[bool, str, str]:
    if os.path.isabs(script_name):
        script_path = script_name
    elif os.path.exists(os.path.join(PROJECT_ROOT, script_name)):
        script_path = os.path.join(PROJECT_ROOT, script_name)
    elif os.path.exists(os.path.join(SKILLS_DIR, script_name)):
        script_path = os.path.join(SKILLS_DIR, script_name)
    else:
        script_path = os.path.join(SKILLS_DIR, os.path.basename(script_name))

    try:
        res = subprocess.run(
            [sys.executable, script_path] + args_list,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True
        )
        out = res.stdout.strip() if res.stdout else ""
        err = res.stderr.strip() if res.stderr else ""
        return res.returncode == 0, out, err
    except Exception as e:
        return False, "", str(e)


def detect_and_install_missing_module(error_log: str) -> Tuple[bool, Optional[str]]:
    match = re.search(r"ModuleNotFoundError: No module named '(\w+)'", error_log)
    if match:
        module = match.group(1)
        print(f"{C_YELLOW}[!] AUTO-HEALING: Instalando módulo ausente '{module}'...{C_RESET}")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", module], check=True, capture_output=True)
            print(f"{C_GREEN}[✓] Pacote '{module}' instalado com sucesso.{C_RESET}")
            return True, module
        except subprocess.CalledProcessError as e:
            print(f"{C_RED}[✗] Falha ao instalar '{module}': {e.stderr.decode() if e.stderr else ''}{C_RESET}")
            return False, module
    return False, None


class ReActEngine:
    def __init__(
        self, 
        fast_model: Optional[str] = None, 
        complex_model: Optional[str] = None, 
        project_name: str = "default", 
        max_steps: int = 5, 
        verbose: bool = False
    ) -> None:
        self.fast_model: str = fast_model or get_model_for_role("router", default="qwen2.5-coder:3b")
        self.complex_model: str = complex_model or get_model_for_role("complex", default="qwen2.5-coder:7b")
        self.project_name: str = project_name
        self.max_steps: int = max_steps
        self.verbose: bool = verbose

    def _log(self, title: str, content: str) -> None:
        if self.verbose:
            filler = '─' * max(0, 45 - len(title))
            print(f"\n{C_DARK_GREEN}┌─── [ DEBUG :: {title} ] {filler}┐{C_RESET}")
            for line in content.splitlines():
                print(f"{C_DARK_GREEN}│{C_RESET} {line}")
            border_bottom = '─' * 60
            print(f"{C_DARK_GREEN}└{border_bottom}┘{C_RESET}\n")

    def _call_deepseek_api(self, model: str, prompt_or_messages: Any, format_json: bool = False) -> str:
        if not DEEPSEEK_API_KEY:
            return "❌ Erro: DEEPSEEK_API_KEY não configurada no .env"

        start_time = time.time()
        
        if isinstance(prompt_or_messages, list):
            sanitized_messages = []
            for m in prompt_or_messages:
                sanitized_messages.append({
                    "role": m.get("role", "user"),
                    "content": sanitize_for_json(m.get("content", ""))
                })
        else:
            sanitized_messages = [{"role": "user", "content": sanitize_for_json(str(prompt_or_messages))}]

        payload = {
            "model": model,
            "messages": sanitized_messages,
            "stream": False
        }

        if format_json:
            payload["response_format"] = {"type": "json_object"}

        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        self._log(f"DEEPSEEK API INPUT ({model})", json.dumps(payload, indent=2, ensure_ascii=False))

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                res = json.loads(response.read().decode("utf-8"))
                total_time = round(time.time() - start_time, 2)
                
                content = res.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = res.get("usage", {})
                p_tokens = usage.get("prompt_tokens", 0)
                c_tokens = usage.get("completion_tokens", 0)

                telemetry_box = f"TIME: {total_time}s | PROMPT TOKENS: {p_tokens} | COMPLETION TOKENS: {c_tokens} (DeepSeek API)"
                self._log(f"DEEPSEEK API OUTPUT ({model})", f"{content}\n\n[TELEMETRY: {telemetry_box}]")
                return content
        except Exception as e:
            return f"❌ Erro na comunicação com DeepSeek API ({model}): {e}"

    def call_llm(self, model: str, prompt_or_messages: Any, format_json: bool = False) -> str:
        # Roteamento transparente se o modelo for DeepSeek
        if model.lower().startswith("deepseek"):
            return self._call_deepseek_api(model, prompt_or_messages, format_json)

        start_time = time.time()

        if isinstance(prompt_or_messages, list):
            sanitized = []
            for m in prompt_or_messages:
                sanitized.append({"role": m["role"], "content": sanitize_for_json(m.get("content", ""))})

            payload = {
                "model": model,
                "messages": sanitized,
                "stream": False,
                "options": {"keep_alive": "30m", "num_ctx": 8192}
            }
            url = OLLAMA_CHAT_URL
            injected_prompt_preview = json.dumps(sanitized, indent=2, ensure_ascii=False)
        else:
            payload = {
                "model": model,
                "prompt": prompt_or_messages,
                "stream": False,
                "options": {"keep_alive": "30m", "num_ctx": 8192}
            }
            if format_json:
                payload["format"] = "json"
                payload["options"]["temperature"] = 0.0

            url = OLLAMA_GENERATE_URL
            injected_prompt_preview = prompt_or_messages

        self._log(f"SLM INPUT ({model})", injected_prompt_preview)

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                total_time = round(time.time() - start_time, 2)
                
                p_tokens = res.get("prompt_eval_count", 0) or 0
                c_tokens = res.get("eval_count", 0) or 0
                eval_dur_ns = res.get("eval_duration") or 0
                eval_dur_s = eval_dur_ns / 1e9 if eval_dur_ns > 0 else 1.0
                tok_per_sec = round(c_tokens / eval_dur_s, 2) if eval_dur_s > 0 else 0.0

                content = res.get("message", {}).get("content", "") if isinstance(prompt_or_messages, list) else res.get("response", "")

                telemetry_box = (
                    f"TIME: {total_time}s | PROMPT TOKENS: {p_tokens} | "
                    f"COMPLETION TOKENS: {c_tokens} | SPEED: {tok_per_sec} tok/s"
                )
                self._log(f"SLM OUTPUT ({model})", f"{content}\n\n[TELEMETRY: {telemetry_box}]")
                return content
        except Exception as e:
            return f"❌ Erro na comunicação com LLM ({model}): {e}"

    def auto_heal(self, full_output: str) -> Tuple[bool, Optional[str]]:
        if any(err in full_output for err in ["ERR_MISSING_TABLE", "UndefinedTable", "does not exist"]):
            print(f"{C_YELLOW}[!] AUTO-HEALING: Tabela ausente detectada. Executando db_migrate...{C_RESET}")
            ok, out, err = run_skill_script("db_migrate.py", ["apply"])
            return ok, f"[DB Migration Healing]: {out}\n{err}"

        installed, module_name = detect_and_install_missing_module(full_output)
        if installed:
            return True, f"[Package Healing]: Pacote '{module_name}' foi instalado com sucesso."

        return False, None

    def execute_action(
        self, 
        intent_data: Dict[str, Any], 
        user_input: str, 
        dynamic_skills: List[Dict[str, Any]]
    ) -> Tuple[bool, str, bool]:
        intent = intent_data.get("intent", "chat")
        dynamic_map = {s["intent"]: s for s in dynamic_skills}

        if intent not in dynamic_map:
            return False, f"Skill '{intent}' não encontrada no catálogo.", False

        skill_info = dynamic_map[intent]
        script_target = skill_info.get("file_path") or skill_info.get("script") or os.path.join(SKILLS_DIR, f"{intent}.py")

        if intent == "auto_exec":
            args_list = [user_input]
        else:
            args_list = ["-p", self.project_name]
            action = intent_data.get("action")
            if action:
                args_list.append(action)

            ignored_keys = {"intent", "project", "action", "use_rag", "deliberative_turn", "summary", "assumptions", "dependencies", "test_cmd"}
            for k, v in intent_data.items():
                if k not in ignored_keys and v is not None:
                    args_list.extend([f"--{k.replace('_', '-')}", str(v)])

        ok, out, err = run_skill_script(script_target, args_list, capture_output=True)
        full_output = f"{out}\n{err}".strip()

        healed, heal_msg = self.auto_heal(full_output)
        if healed:
            print(f"{C_CYAN}[↺] Re-executando skill após Auto-Healing...{C_RESET}")
            ok, out, err = run_skill_script(script_target, args_list, capture_output=True)
            full_output = f"{heal_msg}\n\n[Re-execução após Healing]:\n{out}\n{err}".strip()

        return ok, full_output, healed

    def execute_engineering_pipeline(
        self, 
        user_input: str, 
        intent_data: Dict[str, Any], 
        dynamic_skills: List[Dict[str, Any]], 
        messages_history: List[Dict[str, str]], 
        max_attempts: int = 3
    ) -> Tuple[str, Dict[str, Any]]:
        test_cmd: str = intent_data.get("test_cmd", "python3 -m unittest")
        target_file: Optional[str] = intent_data.get("file")
        repo_path: str = intent_data.get("repository", ".")

        print(f"{C_CYAN}[+] Iniciando Closed-Loop Pipeline para: {intent_data.get('summary', 'refatoração')}{C_RESET}")

        err_test = ""
        out_test = ""
        for attempt in range(1, max_attempts + 1):
            print(f"{C_DARK_GREEN} ├─ [Step {attempt}/{max_attempts}] Aplicando código em disco...{C_RESET}")

            ok_code, out_code, _ = self.execute_action(intent_data, user_input, dynamic_skills)
            if not ok_code:
                return f"❌ Falha na etapa de escrita do código: {out_code}", intent_data

            print(f"{C_DARK_GREEN} ├─ [Validation] Executando comando: `{test_cmd}`{C_RESET}")
            ok_test, out_test, err_test = run_skill_script("auto_exec.py", [test_cmd], capture_output=True)

            if ok_test and "ERROR:" not in err_test and "Traceback" not in err_test:
                print(f"{C_GREEN} └─ [✓] Testes Aprovados! Registrando Git Commit...{C_RESET}")
                play_completion_sound()

                commit_msg = f"feat(auto-fix): {intent_data.get('summary', 'refatoracao validada em malha fechada')}"
                run_skill_script("git_guard.py", ["commit", repo_path, "-m", commit_msg], capture_output=True)

                reviewer_prompt = load_prompt("reviewer_system.txt")
                engineer_prompt = load_prompt("engineer_system.txt")

                final_system_prompt = f"""
{reviewer_prompt}

{engineer_prompt}

[PIPELINE EM MALHA FECHADA - CONCLUÍDO COM SUCESSO]:
- Tentativas realizadas: {attempt}
- Validação executada: `{test_cmd}`
- Git Commit: Registrado com sucesso (`{commit_msg}`)

SAÍDA REAL DO TESTE (STDOUT):
{out_test}

Apresente um resumo claro e técnico do código implementado e dos testes validados.
"""
                temp_messages = list(messages_history)
                temp_messages.append({"role": "user", "content": user_input})
                temp_messages.append({"role": "system", "content": final_system_prompt})

                response = self.call_llm(self.complex_model, temp_messages)
                return response, intent_data

            print(f"{C_YELLOW} ├─ [!] Falha detectada no runtime. Injetando STDERR na LLM para retentativa...{C_RESET}")

            fix_prompt = f"""
[FALHA DE EXECUÇÃO EM RUNTIME - TENTATIVA {attempt}/{max_attempts}]
O código foi alterado, mas o comando de teste falhou no SO.

COMANDO EXECUTADO: `{test_cmd}`
SAÍDA DE ERRO (STDERR / TRACEBACK):
{err_test if err_test else out_test}

INSTRUÇÕES DE REFATORAÇÃO:
1. Analise o traceback e identifique a causa exata do erro.
2. Forneça o novo payload JSON corrigido para a skill 'code_engineer' corrigir o arquivo '{target_file}'.
"""
            raw_fix = self.call_llm(self.complex_model, fix_prompt, format_json=True)
            try:
                intent_data = json.loads(raw_fix)
            except Exception:
                pass

        return f"❌ Limite de {max_attempts} tentativas atingido sem aprovação nos testes.\nÚltimo Erro:\n{err_test}", intent_data

    def run(
        self, 
        user_input: str, 
        messages_history: List[Dict[str, str]], 
        dynamic_skills: List[Dict[str, Any]], 
        classify_prompt_builder: Any
    ) -> Tuple[str, Dict[str, Any]]:
        prompt = classify_prompt_builder(user_input, self.project_name, messages_history=messages_history)
        raw_intent = self.call_llm(self.fast_model, prompt, format_json=True)

        try:
            intent_data = json.loads(raw_intent)
        except Exception:
            intent_data = {"intent": "chat", "project": self.project_name, "use_rag": False, "deliberative_turn": False}

        intent = intent_data.get("intent", "chat")
        use_rag = intent_data.get("use_rag", False)
        target_project = intent_data.get("project", self.project_name)
        deliberative_turn = intent_data.get("deliberative_turn", False)

        print(f"{C_GREEN}[+] ROUTER :: Intent='{intent}' | Project='{target_project}' | RAG={use_rag}{C_RESET}")
        self._log("ROUTER JSON RAW", json.dumps(intent_data, indent=2, ensure_ascii=False))

        rag_context = ""
        if use_rag or intent in ["query_knowledge", "code_engineer"]:
            print(f"{C_DARK_GREEN}[+] RAG :: Consultando base vetorial pgvector...{C_RESET}")
            rag_args = [user_input]
            if target_project and str(target_project).lower() not in ["all", "global", "none", "*", "null"]:
                rag_args.extend(["-p", str(target_project)])

            ok_rag, rag_out, _ = run_skill_script("query_knowledge.py", rag_args, capture_output=True)
            if ok_rag and rag_out.strip():
                rag_context = rag_out.strip()

        dynamic_map = {s["intent"]: s for s in dynamic_skills}

        if intent == "code_engineer":
            return self.execute_engineering_pipeline(user_input, intent_data, dynamic_skills, messages_history)

        plan_context = ""
        if deliberative_turn and intent not in dynamic_map:
            deliberative_prompt = load_prompt("deliberator_system.txt")
            temp_messages = list(messages_history)
            temp_messages.append({"role": "system", "content": deliberative_prompt})
            if rag_context:
                temp_messages.append({"role": "system", "content": f"[CONTEXTO TÉCNICO RAG]:\n{rag_context}"})
            temp_messages.append({"role": "user", "content": f"Diagnóstico do Roteador:\n{json.dumps(intent_data, ensure_ascii=False)}\n\nSolicitação: {user_input}"})

            response = self.call_llm(self.complex_model, temp_messages)
            return response, intent_data
        elif deliberative_turn and intent in dynamic_map:
            deliberative_prompt = load_prompt("deliberator_system.txt")
            temp_messages = list(messages_history)
            temp_messages.append({"role": "system", "content": deliberative_prompt})
            if rag_context:
                temp_messages.append({"role": "system", "content": f"[CONTEXTO TÉCNICO RAG]:\n{rag_context}"})
            temp_messages.append({"role": "user", "content": f"Diagnóstico do Roteador:\n{json.dumps(intent_data, ensure_ascii=False)}\n\nSolicitação: {user_input}"})

            plan_context = self.call_llm(self.complex_model, temp_messages)

        if intent in dynamic_map:
            print(f"{C_CYAN}[>] EXEC :: Disparando skill '{intent}' no SO...{C_RESET}")
            ok, full_output, healed = self.execute_action(intent_data, user_input, dynamic_skills)

            if ok:
                play_completion_sound()

            reviewer_prompt = load_prompt("reviewer_system.txt")
            engineer_prompt = load_prompt("engineer_system.txt")
            status_msg = "Sucesso na Execução" if ok else "Interrompido / Falha na Execução"

            system_feedback_prompt = f"""
{reviewer_prompt}

{engineer_prompt}

[PLANO PRÉVIO DELIBERADO]:
{plan_context if plan_context else 'Sem plano prévio.'}

[RETORNO REAL DA EXECUÇÃO DO TERMINAL (SKILL: '{intent}')]:
Status: {status_msg}
Auto-Healing Aplicado: {'Sim' if healed else 'Não'}
Saída do Terminal (STDOUT/STDERR):
{full_output}

REGRAS CRÍTICAS DA RESPOSTA FINAL:
1. Apresente SOMENTE os dados e saídas reais obtidos acima. NUNCA simule testes ou saídas falsas.
2. Garanta que todo código Python gerado ou exibido utilize tipagem estrita ('TypedDict', 'dataclass' ou 'type hints').
"""
            active_model = self.complex_model if (not ok or healed or deliberative_turn) else self.fast_model

            temp_messages = list(messages_history)
            temp_messages.append({"role": "user", "content": user_input})
            if rag_context:
                temp_messages.append({"role": "system", "content": f"[CONTEXTO RAG RECUPERADO]:\n{rag_context}"})
            temp_messages.append({"role": "system", "content": system_feedback_prompt})

            response = self.call_llm(active_model, temp_messages)
            return response, intent_data

        temp_messages = list(messages_history)
        temp_messages.append({"role": "user", "content": user_input})
        if rag_context:
            temp_messages.append({"role": "system", "content": f"[CONTEXTO RAG]:\n{rag_context}"})

        response = self.call_llm(self.complex_model, temp_messages)
        return response, intent_data