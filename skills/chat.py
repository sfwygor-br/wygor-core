#!/usr/bin/env python3
import os
import sys
import json
import re
import argparse
import subprocess
import urllib.request
from dotenv import load_dotenv
import threading
import time
import importlib.util
import glob

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").split('/api')[0].rstrip('/')
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
CHAT_MODEL = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:14b")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(BASE_DIR, "skills")

def load_dynamic_skills(verbose=False):
    """Varre a pasta skills/ mapeando manifestos plug-and-play."""
    skills = []
    if os.path.exists(SKILLS_DIR):
        for file in glob.glob(os.path.join(SKILLS_DIR, "*.py")):
            # Evita carregar o próprio chat.py ou scripts auxiliares como skill dinâmica
            mod_name = os.path.basename(file)[:-3]
            if mod_name in ["chat", "code_agent", "ingest_docs", "query_knowledge", "watch", "memory", "git_guard", "code_engineer", "code_checker", "db_migrate"]:
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

# ============================================
# ANIMAÇÃO ASCII (Loader)
# ============================================
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

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
def sanitize_for_json(text):
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text

def summarize_log(text, max_lines=20):
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:10] + ["... (linhas suprimidas) ..."] + lines[-10:])

def run_skill(script_name, args_list, capture_output=True):
    if os.path.isabs(script_name):
        script_path = script_name
    else:
        # Busca tanto na raiz quanto na pasta skills/
        path_in_skills = os.path.join(SKILLS_DIR, script_name)
        path_in_root = os.path.join(BASE_DIR, script_name)
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

def classify_intent(user_input, active_project="default", verbose=False):
    dynamic_skills = load_dynamic_skills(True)
    
    # Monta catálogo dinâmico legível para o LLM
    skills_catalog = []
    for s in dynamic_skills:
        skills_catalog.append(
            f"- INTENT: \"{s.get('intent')}\"\n"
            f"  DESCRIÇÃO: {s.get('description')}\n"
            f"  PALAVRAS-CHAVE: {', '.join(s.get('keywords', ['n/a']))}"
        )
    skills_text = "\n".join(skills_catalog) if skills_catalog else "Nenhuma skill dinâmica registrada no momento."

    prompt = f"""
[SISTEMA DE ROTEAMENTO DE INTENÇÕES E EXTRAÇÃO DE PARÂMETROS - WYGOR CORE]

Sua única função é analisar a mensagem do usuário, identificar a intenção correta e extrair parâmetros estruturados.

CONTEXTO ATUAL:
- Projeto Ativo: "{active_project}"
- Skills Dinâmicas Plug-and-Play Registradas:
{skills_text}

======================================================================
HIERARQUIA RÍGIDA DE CLASSIFICAÇÃO (Siga esta ordem estritamente):
======================================================================

1. SKILLS DINÂMICAS (PRIORIDADE CRÍTICA / 0):
   - Se o usuário pedir para rodar, testar, verificar ou executar qualquer função correspondente à DESCRIÇÃO de uma skill cadastrada acima (ex: autodiagnóstico, latência, GPU, hardware, status do ambiente), retorne OBLIGATORIAMENTE o nome EXATO da 'intent' dessa skill.
   - NUNCA use nomes genéricos ("skill_dinamica", "diagnostico"). Use o identificador exato (ex: "auto_diag").

2. INGEST ("ingest"):
   - Ordens diretas para indexar, ler, reindexar ou ingerir repositórios/pastas na base vetorial.
   - Parâmetro "path": Caminho da pasta/repositório indicado pelo usuário (padrão: ".").

3. CODE_TASK ("code_task"):
   - Solicitações para criar, alterar, refatorar, corrigir bugs ou gerar código no projeto.
   - Parâmetros: "task" (a descrição do que deve ser feito), "no_tests" (boolean, true se pedir explicitamente sem testes).

4. RUN_CODE ("run_code"):
   - Execução de scripts genéricos no terminal ou comandos do sistema operacional.
   - Parâmetros: "command" (comando opcional), "project_path" (padrão: ".").

5. QUERY ("query"):
   - Dúvidas técnicas sobre o código do projeto ativo, perguntas sobre arquitetura ou dados armazenados no banco vetorial.
   - Parâmetro "query": A pergunta formulada de forma limpa.

6. CHAT ("chat"):
   - Conversa casual, saudações ou dúvidas puramente conceituais que NÃO dependem do contexto do código nem exigem execução local.

======================================================================
EXEMPLOS DE ENTRADA E SAÍDA (FEW-SHOT):
======================================================================
Entrada: "verifique a latencia do ollama e o status da gpu"
Saída: {{"intent": "auto_diag", "project": "{active_project}"}}

Entrada: "rode o autodiagnostico de hardware"
Saída: {{"intent": "auto_diag", "project": "{active_project}"}}

Entrada: "indexe a pasta /home/user/meu_projeto"
Saída: {{"intent": "ingest", "project": "{active_project}", "path": "/home/user/meu_projeto"}}

Entrada: "crie uma funcao de login em python sem criar testes"
Saída: {{"intent": "code_task", "project": "{active_project}", "task": "crie uma funcao de login em python", "no_tests": true}}

Entrada: "como funciona a classe AsciiLoader?"
Saída: {{"intent": "query", "project": "{active_project}", "query": "como funciona a classe AsciiLoader?"}}

======================================================================
MENSAGEM DO USUÁRIO A PROCESSAR:
"{user_input}"

Retorne APENAS o JSON no formato:
{{"intent": "<nome_da_intent>", "project": "{active_project}", ...parâmetros_extras}}
"""
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0  # Zera a aleatoriedade para máxima precisão
        }
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
            
            # Trava de segurança: Se caiu em chat mas citou palavra-chave de alguma skill
            if parsed.get("intent") == "chat":
                for skill in dynamic_skills:
                    s_intent = skill.get("intent", "")
                    if s_intent and (s_intent in user_input.lower() or "diag" in user_input.lower()):
                        parsed["intent"] = s_intent
                        break

            if verbose:
                print(f"\n💬 [Raciocínio - Decisão do Roteador]:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n")
            return parsed
    except Exception as e:
        if verbose:
            print(f"⚠️ Erro no roteador: {e}. Assumindo 'chat'.")
        return {"intent": "chat", "project": active_project}

def send_chat_message(messages):
    sanitized = []
    for msg in messages:
        content = msg.get("content", "")
        content = sanitize_for_json(content)
        if msg.get("role") == "system" and len(content) > 1000:
            content = summarize_log(content, max_lines=15)
        sanitized.append({"role": msg["role"], "content": content})

    payload = {
        "model": CHAT_MODEL,
        "messages": sanitized,
        "stream": False
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
        return f"❌ Erro na comunicação com a LLM: {e}"

def start_interactive_chat(project_name="default", initial_verbose=False):
    active_project = project_name
    verbose_mode = initial_verbose

    print("=" * 65)
    print(f"🤖 Wygor Core Chat (Modo Agente Autônomo) - Projeto: [{active_project}]")
    print("Comandos do Chat:")
    print(" - /verbose   : Liga/Desliga exibição detalhada de raciocínio")
    print(" - /exit      : Encerra o chat")
    print("=" * 65 + "\n")

    messages = [
        {"role": "system", "content": "Você é o Wygor, um assistente especialista em engenharia de software e automação."}
    ]

    while True:
        try:
            status_v = " [VERBOSE ON]" if verbose_mode else ""
            user_input = input(f"wygor({active_project}){status_v}> ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["/exit", "exit", "quit"]:
                print("👋 Encerrando sessão do Wygor Chat.")
                break

            if user_input.lower() == "/verbose":
                verbose_mode = not verbose_mode
                print(f"🔍 Modo Transparente (Verbose) {'ATIVADO ✅' if verbose_mode else 'DESATIVADO ❌'}\n")
                continue

            # --- ROTEAMENTO ---
            intent_data = classify_intent(user_input, active_project, verbose=verbose_mode)
            intent = intent_data.get("intent", "chat")

            # Mapeamento dinâmico de skills da pasta skills/
            dynamic_skills = load_dynamic_skills(True)
            dynamic_map = {s["intent"]: s for s in dynamic_skills}

            # ========================================
            # 0. EXECUÇÃO DE SKILL DINÂMICA (Plug-and-Play)
            # ========================================
            if intent in dynamic_map:
                skill_info = dynamic_map[intent]
                script_target = skill_info.get("file_path") or os.path.join("skills", skill_info["script"])

                loader = AsciiLoader(f"⚙️ Executando skill '{intent}'")
                loader.start()
                try:
                    ok, out, err = run_skill(script_target, [], capture_output=True)
                finally:
                    loader.stop()

                output = out if out else err
                print(f"\n{output}\n")

                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "assistant", "content": f"Resultado do {intent}:\n{output}"})

            # ========================================
            # 1. QUERY (Perguntas)
            # ========================================
            elif intent == "query":
                proj = intent_data.get("project") or active_project
                q = intent_data.get("query") or user_input

                loader = AsciiLoader(f"🔎 Buscando na base vetorial '{proj}'")
                loader.start()
                try:
                    ok, ctx, _ = run_skill("query_knowledge.py", [q, "-p", proj, "-l", "3", "--raw"])
                finally:
                    loader.stop()

                if verbose_mode:
                    print(f"📄 [Raciocínio - Contexto Resgatado do pgvector]:\n{ctx}\n")

                context_str = f"Contexto recuperado da base de dados ({proj}):\n{ctx}\n\n" if ctx else "Nenhum dado encontrado na base vetorial."
                prompt_with_ctx = f"{context_str}\nPergunta do usuário: {user_input}"

                messages.append({"role": "user", "content": prompt_with_ctx})

                loader = AsciiLoader("💬 Gerando resposta")
                loader.start()
                try:
                    response = send_chat_message(messages)
                finally:
                    loader.stop()

                print(f"🤖 Wygor:\n{response}\n")
                messages.append({"role": "assistant", "content": response})

            # ========================================
            # 2. INGEST
            # ========================================
            elif intent == "ingest":
                target_path = intent_data.get("path") or ""
                if not target_path or target_path.strip() == "":
                    print("⚠️ Comando 'ingest' requer um caminho. Exemplo: ingest /caminho/para/pasta")
                    continue
                if not os.path.isabs(target_path):
                    target_path = os.path.abspath(target_path)
                if not os.path.exists(target_path):
                    print(f"❌ Caminho não encontrado: {target_path}")
                    continue

                proj = intent_data.get("project") or active_project
                print(f"\n⚙️  [Agente Autônomo] Mapeando repositório: {target_path} (Projeto: {proj})...\n")

                loader = AsciiLoader(f"📂 Indexando '{target_path}'")
                loader.start()
                try:
                    args = [target_path, "-p", proj]
                    ok, out, err = run_skill("ingest_docs.py", args, capture_output=False)
                    active_project = proj
                finally:
                    loader.stop()

                out_sum = summarize_log(out, 10) if out else ""
                err_sum = summarize_log(err, 10) if err else ""
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "system", "content": f"Ação 'ingest' executada. Status: {'Sucesso' if ok else 'Falha'}. Saída: {out_sum}\n{err_sum}"})
                print(f"\n✅ Mapeamento concluído para o projeto [{active_project}]!\n")

            # ========================================
            # 3. CODE_TASK
            # ========================================
            elif intent == "code_task":
                task = intent_data.get("task") or user_input
                proj = intent_data.get("project") or active_project
                no_tests = intent_data.get("no_tests", False)

                mode_str = " (Execução Direta / Sem Unit Tests)" if no_tests else " (Com Unit Tests)"
                print(f"\n🛠️  [Agente Autônomo] Iniciando desenvolvimento{mode_str}...\n")

                agent_args = [task, "-p", proj]
                if no_tests:
                    agent_args.append("--no-tests")
                if verbose_mode:
                    agent_args.append("-v")

                loader = AsciiLoader("🧠 Agente codificando...")
                loader.start()
                try:
                    ok, out, err = run_skill("code_agent.py", agent_args, capture_output=False)
                finally:
                    loader.stop()

                out_sum = summarize_log(out, 20) if out else ""
                err_sum = summarize_log(err, 20) if err else ""
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "system", "content": f"Ação 'code_task' concluída. Tarefa: '{task}'. Status: {'Sucesso' if ok else 'Falha'}.\nResultado:\n{out_sum}\n{err_sum}"})
                print()

            # ========================================
            # 4. RUN_CODE
            # ========================================
            elif intent == "run_code":
                proj_path = intent_data.get("project_path") or "."
                cmd = intent_data.get("command")

                loader = AsciiLoader(f"🚀 Executando em '{proj_path}'")
                loader.start()
                try:
                    args = [proj_path]
                    if cmd:
                        args.extend(["-c", cmd])
                    ok, out, err = run_skill("code_runner.py", args, capture_output=False)
                finally:
                    loader.stop()

                out_sum = summarize_log(out, 20) if out else ""
                err_sum = summarize_log(err, 20) if err else ""
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "system", "content": f"Ação 'run_code' executada em {proj_path}. Status: {'Sucesso' if ok else 'Falha'}.\nSTDOUT:\n{out_sum}\nSTDERR:\n{err_sum}"})
                print()

            # ========================================
            # 5. CHAT (fallback)
            # ========================================
            else:
                messages.append({"role": "user", "content": user_input})

                loader = AsciiLoader("💬 Pensando...")
                loader.start()
                try:
                    response = send_chat_message(messages)
                finally:
                    loader.stop()

                print(f"\n🤖 Wygor:\n{response}\n")
                messages.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            print("\n👋 Chat interrompido.")
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wygor Chat Interativo com Roteamento Autônomo")
    parser.add_argument("-p", "--project", default="default", help="Nome do projeto inicial")
    parser.add_argument("-v", "--verbose", action="store_true", help="Ativa modo detalhado de logs e raciocínio")
    args = parser.parse_args()

    start_interactive_chat(project_name=args.project, initial_verbose=args.verbose)