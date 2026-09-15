#!/usr/bin/env python3
import os
import sys
import argparse
import threading
import time
import importlib.util
import glob
import json
import urllib.request
import platform
import socket
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.db_service import execute_query
from skills.model_manager import get_model_for_role
from utils.prompt_loader import load_prompt
from utils.agent_engine import ReActEngine, run_skill_script

load_dotenv()

ROUTER_MODEL: str = get_model_for_role("router", default="qwen2.5-coder:3b")
CHAT_MODEL: str = get_model_for_role("complex", default="qwen2.5-coder:7b")
OLLAMA_EMBED_URL: str = f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/embeddings"
EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
SKILLS_DIR: str = os.path.join(PROJECT_ROOT, "skills")


def load_dynamic_skills(verbose: bool = False) -> List[Dict[str, Any]]:
    """Carrega dinamicamente os manifestos de skills registrados no diretório /skills."""
    skills: List[Dict[str, Any]] = []
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


def get_embedding(text: str) -> List[float]:
    """Gera o vetor de embedding para a memória episódica."""
    payload = {"model": EMBED_MODEL, "prompt": text[:4000]}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("embedding", [])
    except Exception as e:
        print(f"⚠️ Erro ao gerar embedding da Memória Episódica: {e}")
        return []


def summarize_and_save_session_memory(session_id: Optional[int], project_name: str) -> None:
    """Sintetiza e persiste a memória episódica da sessão no pgvector."""
    if not session_id:
        return

    messages = load_session_messages(session_id)
    if not messages or len(messages) < 2:
        return

    print(f"\n🧠 [Memória Episódica] Gerando síntese pós-sessão #{session_id}...")

    formatted_transcript = []
    for m in messages:
        if m.get("role") in ["user", "assistant"]:
            label = "Usuário" if m["role"] == "user" else "Assistente"
            formatted_transcript.append(f"{label}: {m['content']}")

    transcript_text = "\n".join(formatted_transcript)

    synthesis_prompt = (
        "Você é o sintetizador de Memória Episódica do Wygor Core.\n"
        "Resuma a sessão a seguir destacando:\n"
        "1. Objetivos principais e problemas abordados.\n"
        "2. Decisões tomadas, comandos executados e soluções validadas.\n"
        "3. Preferências do usuário e contextos para interações futuras.\n\n"
        f"TRANSCRIÇÃO DA SESSÃO #{session_id}:\n{transcript_text}\n\n"
        "SÍNTESE EXECUTIVA CONCISA:"
    )

    try:
        engine = ReActEngine(project_name=project_name)
        summary = engine.call_llm(CHAT_MODEL, synthesis_prompt)

        if not summary or "Erro na comunicação" in summary:
            print("⚠️ Falha ao gerar síntese da sessão.")
            return

        vector = get_embedding(summary)
        sql = """
            INSERT INTO chat_episodic_memories (session_id, project_name, summary, embedding)
            VALUES (%s, %s, %s, %s::vector);
        """
        execute_query(sql, (session_id, project_name, summary, vector if vector else None))
        print(f"✅ Memória Episódica da Sessão #{session_id} persistida no pgvector com sucesso!")
    except Exception as e:
        print(f"⚠️ Falha ao salvar Memória Episódica: {e}")


class AsciiLoader:
    """Animação ASCII interativa com cronômetro em tempo real durante o processamento do ReAct Engine."""
    def __init__(self, message: str = "Processando SLM", min_display: float = 0.5) -> None:
        self.message = message
        self.min_display = min_display
        self.stop_running = False
        self.thread: Optional[threading.Thread] = None
        self.start_time: Optional[float] = None
        self.frames = [
            r"  o>  /|    .  ",
            r"  o_  /|   .   ",
            r"  o\_.  .      ",
            r" \o/•          ",
            r"  o===> •      ",
            r"  o/      •--->",
            r"  o>           "
        ]

    def _animate(self) -> None:
        idx = 0
        self.start_time = time.time()
        while not self.stop_running:
            elapsed = time.time() - self.start_time
            frame = self.frames[idx % len(self.frames)]
            sys.stdout.write(f"\r🛠️  {self.message} {frame} \033[93m[{elapsed:.1f}s]\033[0m")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)

        elapsed = time.time() - (self.start_time or time.time())
        if elapsed < self.min_display:
            time.sleep(self.min_display - elapsed)

        sys.stdout.write("\r" + " " * 85 + "\r")
        sys.stdout.flush()

    def start(self) -> None:
        self.stop_running = False
        self.thread = threading.Thread(target=self._animate)
        self.thread.daemon = True
        self.thread.start()

    def stop(self) -> None:
        self.stop_running = True
        if self.thread:
            self.thread.join()


def create_session(project_name: str, title: str = "Nova Sessão") -> Optional[int]:
    sql = "INSERT INTO chat_sessions (project_name, title) VALUES (%s, %s) RETURNING id;"
    try:
        row = execute_query(sql, (project_name, title), fetch="one")
        return row[0] if row else None
    except Exception:
        return None


def save_message_to_db(
    session_id: Optional[int], 
    role: str, 
    content: str, 
    prompt_tokens: int = 0, 
    completion_tokens: int = 0
) -> None:
    if not session_id:
        return
    try:
        total_tokens = prompt_tokens + completion_tokens
        execute_query(
            "INSERT INTO chat_messages (session_id, role, content, prompt_tokens, completion_tokens, total_tokens) VALUES (%s, %s, %s, %s, %s, %s);",
            (session_id, role, content, prompt_tokens, completion_tokens, total_tokens)
        )
        execute_query(
            """UPDATE chat_sessions 
               SET total_prompt_tokens = COALESCE(total_prompt_tokens, 0) + %s,
                   total_completion_tokens = COALESCE(total_completion_tokens, 0) + %s,
                   total_tokens = COALESCE(total_tokens, 0) + %s,
                   updated_at = CURRENT_TIMESTAMP 
               WHERE id = %s;""",
            (prompt_tokens, completion_tokens, total_tokens, session_id)
        )
    except Exception:
        pass


def load_session_messages(session_id: int) -> List[Dict[str, str]]:
    sql = "SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY id ASC;"
    try:
        rows = execute_query(sql, (session_id,), commit=False, fetch="all") or []
        return [{"role": r[0], "content": r[1]} for r in rows]
    except Exception:
        return []


def get_last_session_id(project_name: str) -> Optional[int]:
    sql = "SELECT id FROM chat_sessions WHERE project_name = %s ORDER BY updated_at DESC LIMIT 1;"
    try:
        row = execute_query(sql, (project_name,), commit=False, fetch="one")
        return row[0] if row else None
    except Exception:
        return None


def display_session_stats(session_id: Optional[int], project_name: str, messages_history: List[Dict[str, str]]) -> None:
    """Exibe a telemetria e o consumo da sessão atual."""
    sql = """
        SELECT COALESCE(total_prompt_tokens, 0), 
               COALESCE(total_completion_tokens, 0), 
               COALESCE(total_tokens, 0)
        FROM chat_sessions WHERE id = %s;
    """
    row = execute_query(sql, (session_id,), commit=False, fetch="one") or (0, 0, 0)
    prompt_tok, comp_tok, total_tok = row

    context_chars = sum(len(m.get("content", "")) for m in messages_history)
    estimated_context_tokens = int(context_chars / 4)

    print("\n" + "=" * 55)
    print(f"📊 TELEMETRIA E ESTATÍSTICAS DA SESSÃO #{session_id}")
    print("=" * 55)
    print(f"📂 Projeto Ativo:               {project_name}")
    print(f"💬 Turnos Gravados:             {len(messages_history) // 2}")
    print(f"🧠 Contexto Ativo (Estimado):   ~{estimated_context_tokens:,} tokens ({context_chars:,} chars)")
    print(f"📥 Tokens de Entrada (Prompt):   {prompt_tok:,}")
    print(f"📤 Tokens de Saída (Completion): {comp_tok:,}")
    print(f"⚡ Total Acumulado na Sessão:   {total_tok:,}")
    print("=" * 55 + "\n")


def get_environment_context() -> str:
    """Coleta o estado do SO e ambiente ativo para injeção no roteador V3.0."""
    try:
        hostname = socket.gethostname()
        system_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        python_ver = platform.python_version()
        return f"Hostname: {hostname} | SO: {system_info} | Python: {python_ver} | Dir: {PROJECT_ROOT}"
    except Exception:
        return "Ambiente Linux / Parrot OS / Ubuntu Server"


def build_classify_prompt(user_input: str, active_project: str, messages_history: Optional[List[Dict[str, str]]] = None) -> str:
    """Constrói o prompt enriquecido de roteamento com injeção de estado do ambiente."""
    dynamic_skills = load_dynamic_skills(False)
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

    history_text = ""
    if messages_history:
        recent = [m for m in messages_history if m.get("role") in ["user", "assistant"]][-6:]
        if recent:
            formatted_msgs = []
            for m in recent:
                role_label = "Usuário" if m["role"] == "user" else "Assistente"
                preview = m["content"][:300].replace("\n", " ")
                formatted_msgs.append(f"{role_label}: {preview}")
            history_text = "\n".join(formatted_msgs)

    env_context = get_environment_context()

    return load_prompt(
        "router_system.txt",
        allowed_intents_str=allowed_intents_str,
        skills_text=skills_text,
        active_project=active_project,
        user_input=user_input,
        env_context=env_context,
        chat_history=history_text if history_text else "Sem histórico recente."
    )


def get_system_instruction() -> str:
    """Retorna a instrução do sistema base e persona da v3.0."""
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
        "Você é o Wygor Core, um ecossistema autônomo com inteligência operacional e capacidade de execução nativa no Parrot OS e Ubuntu Server.\n\n"
        "PERFIL DA PERSONA E POSTURA TÉCNICA:\n"
        "- Você atua como Arquiteto de Software e Engenheiro Backend Senior, além de Professor Técnico.\n"
        "- Possui ampla experiência em sistemas críticos, bancos relacionais e vetoriais (Oracle PL/SQL, PostgreSQL/pgvector), APIs RESTful (Python/Node.js), ecossistemas Linux e IA local sob TDD/SDD.\n"
        "- Sua comunicação é clara, direta, estruturada e altamente didática.\n"
        "- DELIBERAÇÃO E ARQUITETURA: Quando uma solicitação do usuário admitir mais de uma abordagem técnica viável, NÃO execute comandos precipitadamente. Apresente primeiro as opções (ex: 'Podemos seguir pela Abordagem A ou pela Abordagem B') acompanhadas dos prós e contras arquiteturais antes de agir.\n\n"
        "REGRAS INQUEBRÁVEIS DE ACESSO AO SISTEMA:\n"
        "1. VOCÊ TEM ACESSO TOTAL AO SISTEMA OPERACIONAL E HARDWARE VIA SKILLS.\n"
        "2. NUNCA diga 'Como modelo de IA, não tenho acesso...' ou 'Não posso verificar isso'.\n"
        "3. Se você necessita de dados do sistema, acione a skill correspondente no ReAct Engine para obtê-los.\n\n"
        "CATÁLOGO DE SKILLS DINÂMICAS REGISTRADAS NO SISTEMA:\n"
        f"{skills_text}\n"
    )


def start_interactive_chat(
    project_name: str = "default", 
    initial_verbose: bool = True, 
    resume_last: bool = True, 
    session_id: Optional[int] = None
) -> None:
    active_project = project_name
    verbose_mode = initial_verbose
    current_session_id = session_id

    if resume_last and not current_session_id:
        current_session_id = get_last_session_id(active_project)

    system_instruction = get_system_instruction()
    messages = [{"role": "system", "content": system_instruction}]

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
    print(f"🤖 Wygor Core Chat (ReAct Engine V3.0) - Projeto: [{active_project}] | Sessão: #{current_session_id}")
    print("Comandos do Chat:")
    print(" - /sessions       : Lista todas as sessões anteriores")
    print(" - /resume <id>    : Carrega o contexto de uma sessão específica")
    print(" - /stats          : Exibe métricas de telemetria e contexto da sessão")
    print(" - /title <nome>   : Define um título para a sessão atual")
    print(" - /verbose        : Liga/Desliga exibição detalhada de raciocínio")
    print(" - /exit           : Encerra o chat")
    print("=" * 65 + "\n")

    try:
        while True:
            status_v = " [VERBOSE ON]" if verbose_mode else ""
            user_input = input(f"wygor({active_project}#s{current_session_id}){status_v}> ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["/exit", "exit", "quit"]:
                print("👋 Encerrando sessão do Wygor Chat.")
                summarize_and_save_session_memory(current_session_id, active_project)
                break

            if user_input.lower() == "/verbose":
                verbose_mode = not verbose_mode
                print(f"🔍 Modo Transparente (Verbose) {'ATIVADO ✅' if verbose_mode else 'DESATIVADO ❌'}\n")
                continue

            if user_input.lower() == "/stats":
                display_session_stats(current_session_id, active_project, messages)
                continue

            if user_input.lower() == "/sessions":
                run_skill_script("session_manager.py", ["list", "-p", active_project], capture_output=False)
                continue

            if user_input.lower().startswith("/resume "):
                parts = user_input.split()
                if len(parts) > 1:
                    target_id = parts[1]
                    loaded = load_session_messages(int(target_id))
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
                    run_skill_script("session_manager.py", ["rename", "--id", str(current_session_id), "--title", new_title], capture_output=False)
                continue

            engine = ReActEngine(
                fast_model=ROUTER_MODEL,
                complex_model=CHAT_MODEL,
                project_name=active_project,
                verbose=verbose_mode
            )

            dynamic_skills = load_dynamic_skills(verbose=verbose_mode)
            loader = AsciiLoader("🤖 Processando ReAct Engine V3.0")
            loader.start()

            try:
                response_text, intent_data = engine.run(
                    user_input=user_input,
                    messages_history=messages,
                    dynamic_skills=dynamic_skills,
                    classify_prompt_builder=build_classify_prompt
                )
            finally:
                loader.stop()

            messages.append({"role": "user", "content": user_input})
            save_message_to_db(current_session_id, "user", user_input)

            messages.append({"role": "assistant", "content": response_text})
            save_message_to_db(current_session_id, "assistant", response_text)

            print(f"\n🤖 Wygor:\n{response_text}\n")

    except KeyboardInterrupt:
        print("\n👋 Chat interrompido.")
        summarize_and_save_session_memory(current_session_id, active_project)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wygor Chat Interativo com ReAct Engine V3.0")
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