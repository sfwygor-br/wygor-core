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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.model_manager import get_model_for_role
from utils.prompt_loader import load_prompt

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")


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
    """Executa um script de skill no ambiente Python atual."""
    if os.path.isabs(script_name):
        script_path = script_name
    else:
        path_in_skills = os.path.join(SKILLS_DIR, script_name)
        path_in_root = os.path.join(PROJECT_ROOT, script_name)
        script_path = path_in_skills if os.path.exists(path_in_skills) else path_in_root

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
    """Healing: detecta módulos Python ausentes e tenta instalar via pip."""
    match = re.search(r"ModuleNotFoundError: No module named '(\w+)'", error_log)
    if match:
        module = match.group(1)
        print(f"   📦 [Auto-Healing] Instalando dependência faltante: {module}...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", module], check=True, capture_output=True)
            print(f"   ✅ Pacote '{module}' instalado com sucesso.")
            return True, module
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Falha ao instalar '{module}': {e.stderr.decode() if e.stderr else ''}")
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
            print(f"\n⚙️ [{title}]:\n{content}\n")

    def call_llm(self, model: str, prompt_or_messages: Any, format_json: bool = False) -> str:
        """Dispara requisição ao Ollama e exibe telemetria detalhada se verbose=True."""
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

        # Log detalhado do prompt injetado no SLM
        self._log(f"SLM INPUT PROMPT ({model})", injected_prompt_preview)

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                total_time = round(time.time() - start_time, 2)
                
                # Extração de métricas nativas do Ollama
                p_tokens = res.get("prompt_eval_count", 0)
                c_tokens = res.get("eval_count", 0)
                eval_dur_s = (res.get("eval_duration", 0) or 1) / 1e9
                tok_per_sec = round(c_tokens / eval_dur_s, 2) if eval_dur_s > 0 else 0.0

                content = res.get("message", {}).get("content", "") if isinstance(prompt_or_messages, list) else res.get("response", "")

                metrics_str = (
                    f"⏱️ Tempo total: {total_time}s | "
                    f"📥 Prompt Tokens: {p_tokens} | "
                    f"📤 Completion Tokens: {c_tokens} | "
                    f"⚡ Velocidade: {tok_per_sec} tok/s"
                )

                self._log(f"SLM OUTPUT RESPONSE ({model})", f"{content}\n\n📊 [{metrics_str}]")
                return content
        except Exception as e:
            return f"❌ Erro na comunicação com LLM ({model}): {e}"

    def auto_heal(self, full_output: str) -> Tuple[bool, Optional[str]]:
        """Aplica regras automáticas de Auto-Healing."""
        if any(err in full_output for err in ["ERR_MISSING_TABLE", "UndefinedTable", "does not exist"]):
            self._log("Healing Triggered", "Tabela ausente detectada. Executando db_migrate.py apply...")
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
        """Mapeia a intenção e executa a Skill no SO."""
        intent = intent_data.get("intent", "chat")
        dynamic_map = {s["intent"]: s for s in dynamic_skills}

        if intent not in dynamic_map:
            return False, f"Skill '{intent}' não encontrada no catálogo.", False

        skill_info = dynamic_map[intent]
        script_target = skill_info.get("file_path") or os.path.join(SKILLS_DIR, skill_info["script"])

        if intent == "auto_exec":
            args_list = [user_input]
        else:
            args_list = ["-p", self.project_name]
            action = intent_data.get("action")
            if action:
                args_list.append(action)

            for k, v in intent_data.items():
                if k not in ["intent", "project", "action", "use_rag", "deliberative_turn", "summary", "assumptions", "dependencies", "test_cmd"] and v:
                    args_list.extend([f"--{k.replace('_', '-')}", str(v)])

        ok, out, err = run_skill_script(script_target, args_list, capture_output=True)
        full_output = f"{out}\n{err}".strip()

        healed, heal_msg = self.auto_heal(full_output)
        if healed:
            self._log("Healing Success", "Re-executando a skill após auto-correção...")
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
        """
        Executa o Pipeline de Engenharia em Malha Fechada (Closed-Loop):
        1. Altera/Cria arquivo via code_engineer.py (sem commit prévio).
        2. Executa o teste/comando via auto_exec.py ou code_checker.py no SO.
        3. Se aprovação (returncode == 0): Dispara git_guard.py para commit validado.
        4. Se falha (returncode != 0): Injeta STDERR na LLM para re-gravação e re-teste.
        """
        test_cmd: str = intent_data.get("test_cmd", "python3 -m unittest")
        target_file: Optional[str] = intent_data.get("file")
        repo_path: str = intent_data.get("repository", ".")

        self._log("Closed-Loop Pipeline", f"Iniciando ciclo autônomo de engenharia para: {user_input}")

        for attempt in range(1, max_attempts + 1):
            self._log("Loop Step", f"Tentativa {attempt}/{max_attempts} - Gravando alterações de código...")

            ok_code, out_code, healed_code = self.execute_action(intent_data, user_input, dynamic_skills)
            if not ok_code:
                return f"❌ Falha na etapa de escrita do código: {out_code}", intent_data

            self._log("Loop Step", f"Executando validação em runtime: `{test_cmd}`")
            ok_test, out_test, err_test = run_skill_script(
                "auto_exec.py", 
                [test_cmd], 
                capture_output=True
            )

            if ok_test and "ERROR:" not in err_test and "Traceback" not in err_test:
                self._log("Closed-Loop Success", "Validação concluída com sucesso! Disparando Git Commit Validado...")

                commit_msg = f"feat(auto-fix): {intent_data.get('summary', 'refatoracao validada em malha fechada')}"
                ok_git, out_git, err_git = run_skill_script(
                    "git_guard.py", 
                    ["commit", repo_path, "-m", commit_msg], 
                    capture_output=True
                )

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

            self._log("Closed-Loop Auto-Fix", f"Falha detectada no teste. Reinjetando STDERR na LLM...")

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
        """Executa o fluxo completo do ReAct Engine V3.0."""
        # --- ETAPA 1: Classificação Avançada ---
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

        self._log(f"Diagnóstico do Roteador V3.0 ({self.fast_model})", json.dumps(intent_data, indent=2, ensure_ascii=False))

        # --- Early Context Retrieval (RAG) ---
        rag_context = ""
        if use_rag or intent in ["query_knowledge", "code_engineer"]:
            self._log("Early Context RAG", "Recuperando contexto vetorial preventivo...")
            rag_args = [user_input]
            if target_project and str(target_project).lower() not in ["all", "global", "none", "*", "null"]:
                rag_args.extend(["-p", target_project])

            ok_rag, rag_out, _ = run_skill_script("query_knowledge.py", rag_args, capture_output=True)
            if ok_rag and rag_out.strip():
                rag_context = rag_out.strip()

        dynamic_map = {s["intent"]: s for s in dynamic_skills}

        # --- ETAPA 2: Pipeline de Engenharia Closed-Loop (code_engineer) ---
        if intent == "code_engineer":
            return self.execute_engineering_pipeline(user_input, intent_data, dynamic_skills, messages_history)

        # --- ETAPA 3: Camada Cognitiva e Deliberação ---
        plan_context = ""
        if deliberative_turn and intent not in dynamic_map:
            self._log("Deliberator Turn", "Invocando análise deliberativa para diálogo...")
            deliberative_prompt = load_prompt("deliberator_system.txt")
            
            temp_messages = list(messages_history)
            temp_messages.append({"role": "system", "content": deliberative_prompt})
            if rag_context:
                temp_messages.append({"role": "system", "content": f"[CONTEXTO TÉCNICO RAG]:\n{rag_context}"})
            temp_messages.append({"role": "user", "content": f"Diagnóstico do Roteador:\n{json.dumps(intent_data, ensure_ascii=False)}\n\nSolicitação: {user_input}"})

            response = self.call_llm(self.complex_model, temp_messages)
            return response, intent_data
        elif deliberative_turn and intent in dynamic_map:
            self._log("Deliberator Turn", "Gerando plano de execução prévio...")
            deliberative_prompt = load_prompt("deliberator_system.txt")
            temp_messages = list(messages_history)
            temp_messages.append({"role": "system", "content": deliberative_prompt})
            if rag_context:
                temp_messages.append({"role": "system", "content": f"[CONTEXTO TÉCNICO RAG]:\n{rag_context}"})
            temp_messages.append({"role": "user", "content": f"Diagnóstico do Roteador:\n{json.dumps(intent_data, ensure_ascii=False)}\n\nSolicitação: {user_input}"})

            plan_context = self.call_llm(self.complex_model, temp_messages)
            self._log("Plano Deliberado", plan_context)

        # --- ETAPA 4: Execução da Action Skill Padrão ---
        if intent in dynamic_map:
            self._log("Action Step", f"Executando skill dinamicamente no SO: {intent}")
            ok, full_output, healed = self.execute_action(intent_data, user_input, dynamic_skills)

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

        # Fallback para chat padrão
        temp_messages = list(messages_history)
        temp_messages.append({"role": "user", "content": user_input})
        if rag_context:
            temp_messages.append({"role": "system", "content": f"[CONTEXTO RAG]:\n{rag_context}"})

        response = self.call_llm(self.complex_model, temp_messages)
        return response, intent_data