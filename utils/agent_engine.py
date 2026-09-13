#!/usr/bin/env python3
import os
import sys
import json
import re
import subprocess
import urllib.request
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from skills.model_manager import get_model_for_role

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")


def sanitize_for_json(text):
    if not text:
        return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)


def run_skill_script(script_name, args_list, capture_output=True):
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


def detect_and_install_missing_module(error_log):
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
    def __init__(self, fast_model=None, complex_model=None, project_name="default", max_steps=5, verbose=False):
        self.fast_model = fast_model or get_model_for_role("router", default="qwen2.5-coder:3b")
        self.complex_model = complex_model or get_model_for_role("complex", default="qwen2.5-coder:7b")
        self.project_name = project_name
        self.max_steps = max_steps
        self.verbose = verbose

    def _log(self, title, content):
        if self.verbose:
            print(f"\n⚙️ [{title}]:\n{content}\n")

    def call_llm(self, model, prompt_or_messages, format_json=False):
        """Dispara requisição ao Ollama para generate ou chat."""
        if isinstance(prompt_or_messages, list):
            sanitized = []
            for m in prompt_or_messages:
                sanitized.append({"role": m["role"], "content": sanitize_for_json(m.get("content", ""))})

            payload = {
                "model": model,
                "messages": sanitized,
                "stream": False,
                "options": {"keep_alive": "30m"}
            }
            url = OLLAMA_CHAT_URL
        else:
            payload = {
                "model": model,
                "prompt": prompt_or_messages,
                "stream": False,
                "options": {"keep_alive": "30m"}
            }
            if format_json:
                payload["format"] = "json"
                payload["options"]["temperature"] = 0.0

            url = OLLAMA_GENERATE_URL

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                if isinstance(prompt_or_messages, list):
                    return res.get("message", {}).get("content", "")
                return res.get("response", "")
        except Exception as e:
            return f"❌ Erro na comunicação com LLM ({model}): {e}"

    def auto_heal(self, full_output):
        """Aplica regras automáticas de Auto-Healing."""
        if any(err in full_output for err in ["ERR_MISSING_TABLE", "UndefinedTable", "does not exist"]):
            self._log("Healing Triggered", "Tabela ausente detectada. Executando db_migrate.py apply...")
            ok, out, err = run_skill_script("db_migrate.py", ["apply"])
            return ok, f"[DB Migration Healing]: {out}\n{err}"

        installed, module_name = detect_and_install_missing_module(full_output)
        if installed:
            return True, f"[Package Healing]: Pacote '{module_name}' foi instalado com sucesso."

        return False, None

    def execute_action(self, intent_data, user_input, dynamic_skills):
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
                if k not in ["intent", "project", "action", "use_rag"] and v:
                    args_list.extend([f"--{k.replace('_', '-')}", str(v)])

        ok, out, err = run_skill_script(script_target, args_list, capture_output=True)
        full_output = f"{out}\n{err}".strip()

        healed, heal_msg = self.auto_heal(full_output)
        if healed:
            self._log("Healing Success", "Re-executando a skill após auto-correção...")
            ok, out, err = run_skill_script(script_target, args_list, capture_output=True)
            full_output = f"{heal_msg}\n\n[Re-execução após Healing]:\n{out}\n{err}".strip()

        return ok, full_output, healed

    def run(self, user_input, messages_history, dynamic_skills, classify_prompt_builder):
        """
        Executa o loop ReAct completo:
        1. Classificação rápida com contexto histórico (Fast Model)
        2. Thought & Action (Fast/Complex Model)
        3. Observation & Auto-Healing
        4. Resposta Final / Escalada (Complex Model)
        """
        # --- ETAPA 1: Classificação e Intent Routing com Histórico Contextual ---
        prompt = classify_prompt_builder(user_input, self.project_name, messages_history=messages_history)
        raw_intent = self.call_llm(self.fast_model, prompt, format_json=True)

        try:
            intent_data = json.loads(raw_intent)
        except Exception:
            intent_data = {"intent": "chat", "project": self.project_name}

        intent = intent_data.get("intent", "chat")
        use_rag = intent_data.get("use_rag", False)
        target_project = intent_data.get("project", self.project_name)

        self._log(f"Pensamento: {prompt}", json.dumps(intent_data, indent=2, ensure_ascii=False))
        self._log(f"Decisão do Roteador ({self.fast_model})", json.dumps(intent_data, indent=2, ensure_ascii=False))

        # --- ETAPA 2: Ação de Skill Operacional ---
        dynamic_map = {s["intent"]: s for s in dynamic_skills}
        if intent in dynamic_map:
            self._log("Action Step", f"Executando skill dinamicamente: {intent}")
            ok, full_output, healed = self.execute_action(intent_data, user_input, dynamic_skills)

            system_feedback_prompt = f"""
[RETORNO DA EXECUÇÃO DO TERMINAL (SKILL: '{intent}')]:
Status da Execução: {'Sucesso' if ok else 'Interrompido / Falha'}
Healing Aplicado: {'Sim' if healed else 'Não'}
Saída Capturada do Terminal:
{full_output}

INSTRUÇÕES OBRIGATÓRIAS DE RESPOSTA:
1. Você é o executor nativo do Wygor Core. O comando BASH ACIMA JÁ FOI EXECUTADO NO SISTEMA OPERACIONAL.
2. Apresente os dados e métricas capturados no terminal acima de forma concisa e direta.
3. NUNCA diga que não pode executar comandos, que não tem acesso ao sistema ou que é uma IA de texto.
"""
            active_model = self.complex_model if (not ok or healed) else self.fast_model

            temp_messages = list(messages_history)
            temp_messages.append({"role": "user", "content": user_input})
            temp_messages.append({"role": "system", "content": system_feedback_prompt})

            response = self.call_llm(active_model, temp_messages)
            return response, intent_data

        # --- ETAPA 3: Ação Conversacional / RAG / Raciocínio Profundo ---
        temp_messages = list(messages_history)
        temp_messages.append({"role": "user", "content": user_input})

        if use_rag or intent == "query_knowledge":
            self._log("Observation Step", "Buscando contexto na base vetorial RAG...")
            rag_args = [user_input]
            if target_project and str(target_project).lower() not in ["all", "global", "none", "*", "null"]:
                rag_args.extend(["-p", target_project])

            ok, rag_out, rag_err = run_skill_script("query_knowledge.py", rag_args, capture_output=True)
            if ok and rag_out.strip():
                temp_messages.append({
                    "role": "system",
                    "content": f"[DOCUMENTOS INDEXADOS RECUPERADOS DA BASE DE DADOS]:\n{rag_out.strip()}"
                })
            else:
                temp_messages.append({
                    "role": "system",
                    "content": "⚠️ Nota do Sistema: A consulta de conhecimento no banco vetorial foi realizada, mas nenhum documento relevante foi retornado."
                })

        response = self.call_llm(self.complex_model, temp_messages)
        return response, intent_data