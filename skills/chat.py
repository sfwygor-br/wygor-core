#!/usr/bin/env python3
import os
import sys
import json
import re
import argparse
import subprocess
import urllib.request
import threading
import time
import importlib.util
import glob
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.db_service import execute_query, check_tables_status
from skills.model_manager import get_model_for_role
from utils.prompt_loader import load_prompt

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

ROUTER_MODEL = get_model_for_role("router", default="qwen2.5-coder:3b")
CHAT_MODEL = get_model_for_role("complex", default="qwen2.5-coder:3b")

SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")

def load_dynamic_skills(verbose=False):
    """Varre a pasta skills/ mapeando manifestos plug-and-play."""
    skills = []
    if os.path.exists(SKILLS_DIR):
        for file in glob.glob(os.path.join(SKILLS_DIR, "*.py")):
            mod_name = os.path.basename(file)[:-3]
            if mod_name in ["chat", "code_agent", "ingest_docs", "watch", "memory", "git_guard", "code_engineer", "code_checker"]:
                continue

            spec = importlib.util.spec_from_file_location(mod_name, file)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                if hasattr(mod, "SKILL_MANIFEST"):
                    manifest = mod.SKILL_MANIFEST
                    manifest["file_path"] = file
                    skills.append(manifest)
            except Exception as e:
                if verbose:
                    print(f"⚠️ Warning: Falha ao carregar skill '{file}': {e}")
    return skills

class AsciiLoader:
    def __init__(self, message="Processando", min_display=0.5):
        self.message = message
        self.min_display = min_display
        self.stop_running = False
        self.thread = None
        self.start_time = None

        self.frames = [
            r"  o>  /|    .  ",
            r"  o_  /|   .   ",
            r"  o\_.  .      ",
            r" \o/•          ",
            r"  o===> •      ",
            r"  o/      •--->",
            r"  o>           "
        ]

    def _animate(self):
        idx = 0
        self.start_time = time.time()
        while not self.stop_running:
            frame = self.frames[idx % len(self.frames)]
            sys.stdout.write(f"\r🛠️  {self.message} {frame}")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.25)

        elapsed = time.time() - self.start_time
        if elapsed < self.min_display:
            time.sleep(self.min_display - elapsed)

        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def start(self):
        self.stop_running = False
        self.thread = threading.Thread(target=self._animate)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.stop_running = True
        if self.thread:
            self.thread.join()

def sanitize_for_json(text):
    if not text:
        return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

def run_skill(script_name, args_list, capture_output=True):
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

def create_session(project_name, title="Nova Sessão"):
    sql = "INSERT INTO chat_sessions (project_name, title) VALUES (%s, %s) RETURNING id;"
    try:
        row = execute_query(sql, (project_name, title), fetch="one")
        return row[0] if row else None
    except Exception:
        return None

def save_message_to_db(session_id, role, content):
    if not session_id:
        return
    try:
        execute_query("INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s);", (session_id, role, content))
        execute_query("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (session_id,))
    except Exception:
        pass

def load_session_messages(session_id):
    sql = "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY id ASC;"
    try:
        rows = execute_query(sql, (session_id,), commit=False, fetch="all") or []
        return [{"role": r[0], "content": r[1]} for r in rows]
    except Exception:
        return []

def get_last_session_id(project_name):
    sql = "SELECT id FROM chat_sessions WHERE project_name = %s ORDER BY updated_at DESC LIMIT 1;"
    try:
        row = execute_query(sql, (project_name,), commit=False, fetch="one")
        return row[0] if row else None
    except Exception:
        return None

def classify_intent(user_input, active_project="default", verbose=False):
    dynamic_skills = load_dynamic_skills(True)
    
    base_intents = ["chat", "session_manager", "db_migrate"]
    dynamic_intents = [s.get("intent") for s in dynamic_skills if s.get("intent")]
    valid_intents = list(set(base_intents + dynamic_intents))
    
    allowed_intents_str = ", ".join([f'"{i}"' for i in valid_intents])

    skills_catalog = []
    for s in dynamic_skills:
        actions_str = ", ".join([f'"{a}"' for a in s.get('allowed_actions', ['list'])])
        skills_catalog.append(
            f"• SKILL INTENT: \"{s.get('intent')}\"\n"
            f"  - Descrição: {s.get('description')}\n"
            f"  - Ações permitidas (`action`): [{actions_str}]\n"
            f"  - Palavras-chave: {', '.join(s.get('keywords', ['n/a']))}"
        )
    skills_text = "\n".join(skills_catalog) if skills_catalog else "Nenhuma skill dinâmica registrada."

    try:
        prompt = load_prompt(
            "router_system.txt",
            allowed_intents_str=allowed_intents_str,
            skills_text=skills_text,
            active_project=active_project,
            user_input=user_input
        )

    except Exception as e:
        if verbose:
            print(f"⚠️ Erro ao carregar template de prompt: {e}")
        return {"intent": "chat", "project": active_project}

    if verbose:
        loader = AsciiLoader(f"⚙️ Classificando intenção '{prompt}'")
    else:
        loader = AsciiLoader(f"⚙️ Classificando intenção... ")

    loader.start()

    try:

        payload = {
            "model": ROUTER_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "keep_alive": "30m"}
        }

        req = urllib.request.Request(
            OLLAMA_GENERATE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                parsed = json.loads(res.get("response", "{}"))
                
                intent = parsed.get("intent")
                if intent not in valid_intents:
                    if verbose:
                        print(f"⚠️ Intent alucinada '{intent}' bloqueada pela Whitelist! Forçando fallback para 'chat'.")
                    parsed["intent"] = "chat"

                if verbose:
                    print(f"\n💬 [Raciocínio - Decisão do Roteador ({ROUTER_MODEL})]:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n")
                return parsed
        except Exception as e:
            if verbose:
                print(f"⚠️ Erro no roteador: {e}. Assumindo 'chat'.")
            return {"intent": "chat", "project": active_project}

    finally:
        loader.stop()

def send_chat_message(messages):
    sanitized = []
    for msg in messages:
        sanitized.append({"role": msg["role"], "content": sanitize_for_json(msg.get("content", ""))})

    payload = {
        "model": CHAT_MODEL,
        "messages": sanitized,
        "stream": False,
        "options": {"keep_alive": "30m"}
    }
    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("message", {}).get("content", "")
    except Exception as e:
        return f"❌ Erro na comunicação com a LLM ({CHAT_MODEL}): {e}"


def get_system_instruction():
    dynamic_skills = load_dynamic_skills(verbose=False)
    catalog = []
    for s in dynamic_skills:
        actions = ", ".join([f'"{a}"' for a in s.get('allowed_actions', [])])
        catalog.append(
            f"• SKILL: \"{s.get('intent')}\"\n"
            f"  - Descrição: {s.get('description')}\n"
            f"  - Ações: [{actions}]"
        )
    skills_text = "\n".join(catalog) if catalog else "Nenhuma skill dinâmica registrada."

    return (
        "Você é o Wygor Core, um ecossistema autônomo com capacidade de execução nativa de comandos Linux e auditoria no SO.\n\n"
        "CATÁLOGO DE SKILLS DINÂMICAS REGISTRADAS NO SISTEMA:\n"
        f"{skills_text}\n\n"
        "Quando o usuário perguntar sobre suas skills, ferramentas ou capacidades internas, "
        "baseie-se estritamente na lista de SKILLS DINÂMICAS acima para detalhar cada uma."
    )

def start_interactive_chat(project_name="default", initial_verbose=True, resume_last=True, session_id=None):
    active_project = project_name
    verbose_mode = initial_verbose
    current_session_id = session_id

    if resume_last and not current_session_id:
        current_session_id = get_last_session_id(active_project)

    system_instruction = get_system_instruction()

    messages = [
        {"role": "system", "content": system_instruction}
    ]

    if current_session_id:
        saved_messages = load_session_messages(current_session_id)
        if saved_messages:
            messages.extend(saved_messages)
            print(f"🔄 Contexto da Sessão #{current_session_id} restaurado ({len(saved_messages)} mensagens).")
        else:
            current_session_id = create_session(active_project)
    else:
        current_session_id = create_session(active_project)

    print("=" * 65)
    print(f"🤖 Wygor Core Chat (Modo Agente Autônomo) - Projeto: [{active_project}] | Sessão: #{current_session_id}")
    print("Comandos do Chat:")
    print(" - /sessions       : Lista todas as sessões anteriores")
    print(" - /resume <id>    : Carrega o contexto de uma sessão específica")
    print(" - /title <nome>   : Define um título para a sessão atual")
    print(" - /verbose        : Liga/Desliga exibição detalhada de raciocínio")
    print(" - /exit           : Encerra o chat")
    print("=" * 65 + "\n")

    while True:
        try:
            status_v = " [VERBOSE ON]" if verbose_mode else ""
            user_input = input(f"wygor({active_project}#s{current_session_id}){status_v}> ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["/exit", "exit", "quit"]:
                print("👋 Encerrando sessão do Wygor Chat.")
                break

            if user_input.lower() == "/verbose":
                verbose_mode = not verbose_mode
                print(f"🔍 Modo Transparente (Verbose) {'ATIVADO ✅' if verbose_mode else 'DESATIVADO ❌'}\n")
                continue

            if user_input.lower() == "/sessions":
                run_skill("session_manager.py", ["list", "-p", active_project], capture_output=False)
                continue

            if user_input.lower().startswith("/resume "):
                target_id = user_input.split()[1]
                loaded = load_session_messages(target_id)
                if loaded:
                    current_session_id = int(target_id)
                    messages = [{"role": "system", "content": system_instruction}] + loaded
                    print(f"✅ Sessão #{current_session_id} carregada com sucesso!\n")
                else:
                    print(f"❌ Não foi possível carregar a sessão #{target_id}.\n")
                continue

            if user_input.lower().startswith("/title "):
                new_title = user_input[7:].strip()
                if new_title and current_session_id:
                    run_skill("session_manager.py", ["rename", "--id", str(current_session_id), "--title", new_title], capture_output=False)
                continue

            intent_data = classify_intent(user_input, active_project, verbose=verbose_mode)
            intent = intent_data.get("intent", "chat")
            use_rag = intent_data.get("use_rag", False)
            target_project = intent_data.get("project", active_project)

            dynamic_skills = load_dynamic_skills(True)
            dynamic_map = {s["intent"]: s for s in dynamic_skills}

            if intent in dynamic_map:
                skill_info = dynamic_map[intent]
                script_target = skill_info.get("file_path") or os.path.join(SKILLS_DIR, skill_info["script"])

                # Se for auto_exec, injetamos o input bruto do usuário como parâmetro
                if intent == "auto_exec":
                    args_list = [user_input]
                else:
                    args_list = ["-p", active_project]
                    action = intent_data.get("action")
                    if action:
                        args_list.append(action)

                    for k, v in intent_data.items():
                        if k not in ["intent", "project", "action", "use_rag"] and v:
                            args_list.extend([f"--{k.replace('_', '-')}", str(v)])

                loader = AsciiLoader(f"⚙️ Executando skill '{intent}'")
                loader.start()
                try:
                    ok, out, err = run_skill(script_target, args_list, capture_output=True)
                finally:
                    loader.stop()

                full_output = f"{out}\n{err}".strip()

                if "ERR_MISSING_TABLE" in full_output or "UndefinedTable" in full_output or "does not exist" in full_output:
                    print("\n⚠️ Tabela ausente detectada! Executando auto-migração do schema...\n")
                    loader = AsciiLoader("🛠️ Executando migração de banco")
                    loader.start()
                    try:
                        mig_ok, mig_out, mig_err = run_skill("db_migrate.py", ["apply"], capture_output=True)
                    finally:
                        loader.stop()

                    if mig_ok:
                        print("🔄 Re-executando a skill solicitada...")
                        loader = AsciiLoader(f"⚙️ Executando skill '{intent}'")
                        loader.start()
                        try:
                            ok, out, err = run_skill(script_target, args_list, capture_output=True)
                        finally:
                            loader.stop()
                        full_output = f"{out}\n{err}".strip()

                messages.append({"role": "user", "content": user_input})
                save_message_to_db(current_session_id, "user", user_input)

                system_feedback_prompt = f"""
[RETORNO DA EXECUÇÃO DO TERMINAL (SKILL: '{intent}')]:
Status da Execução: {'Sucesso' if ok else 'Interrompido / Falha'}
Saída Capturada do Terminal:
{full_output}

INSTRUÇÕES OBRIGATÓRIAS DE RESPOSTA:
1. Você é o executor nativo do Wygor Core. O comando BASH ACIMA JÁ FOI EXECUTADO NO SISTEMA OPERACIONAL.
2. Apresente os dados e métricas capturados no terminal acima de forma concisa e direta.
3. NUNCA diga que não pode executar comandos, que não tem acesso ao sistema ou que é uma IA de texto.
"""
                messages.append({"role": "system", "content": system_feedback_prompt})

                loader = AsciiLoader("🤖 Formulando resposta")
                loader.start()
                try:
                    response = send_chat_message(messages)
                finally:
                    loader.stop()

                print(f"\n🤖 Wygor:\n{response}\n")
                messages.append({"role": "assistant", "content": response})
                save_message_to_db(current_session_id, "assistant", response)

            else:
                messages.append({"role": "user", "content": user_input})
                save_message_to_db(current_session_id, "user", user_input)

                if use_rag or intent == "query_knowledge":
                    loader = AsciiLoader("🧠 Consultando base vetorial de conhecimento (RAG)...")
                    loader.start()
                    try:
                        rag_args = [user_input]
                        if target_project and str(target_project).lower() not in ["all", "global", "none", "*", "null"]:
                            rag_args.extend(["-p", target_project])

                        ok, rag_out, rag_err = run_skill("query_knowledge.py", rag_args, capture_output=True)
                        
                        if ok and rag_out.strip():
                            rag_context = f"[DOCUMENTOS INDEXADOS RECUPERADOS DA BASE DE DADOS]:\n{rag_out.strip()}"
                            messages.append({"role": "system", "content": rag_context})
                            if verbose_mode:
                                print(f"\n✅ [RAG] Contexto vetorial injetado ({len(rag_out)} caracteres).")
                        else:
                            if verbose_mode:
                                print(f"\n⚠️ [RAG] Nenhum documento retornado na busca vetorial.")
                            messages.append({
                                "role": "system",
                                "content": "⚠️ Nota do Sistema: A consulta de conhecimento no banco vetorial foi realizada, mas nenhum documento relevante foi retornado para esta busca."
                            })
                    finally:
                        loader.stop()

                loader = AsciiLoader("💬 Pensando...")
                loader.start()
                try:
                    response = send_chat_message(messages)
                finally:
                    loader.stop()

                print(f"\n🤖 Wygor:\n{response}\n")
                messages.append({"role": "assistant", "content": response})
                save_message_to_db(current_session_id, "assistant", response)

        except KeyboardInterrupt:
            print("\n👋 Chat interrompido.")
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wygor Chat Interativo com Persistência e Roteamento Autônomo")
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--resume-last", action="store_true")
    parser.add_argument("--session-id", type=int)

    args = parser.parse_args()

    start_interactive_chat(
        project_name=args.project, 
        initial_verbose=args.verbose, 
        resume_last=args.resume_last, 
        session_id=args.session_id
    )