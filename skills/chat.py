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
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5-coder:3b")

def run_skill(script_name, args_list, capture_output=True):
    """Executa uma skill local e retorna o resultado e código de saída."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    try:
        if capture_output:
            res = subprocess.run(
                [sys.executable, script_path] + args_list,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True
            )
            return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
        else:
            # Captura stdout/stderr mesmo exibindo no terminal para guardar no histórico
            res = subprocess.run([sys.executable, script_path] + args_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.stdout:
                print(res.stdout, end="")
            if res.stderr:
                print(res.stderr, file=sys.stderr, end="")
            return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def classify_intent(user_input, active_project="default", verbose=False):
    """Determina autonomamente qual skill deve ser invocada com base na intenção."""
    prompt = f"""
Você é o roteador de intenções autônomo do assistente Wygor Core.
Analise a mensagem do usuário e determine a ação correspondente.

Mensagem do usuário: "{user_input}"
Projeto Ativo Atual: "{active_project}"

REGRAS DE CLASSIFICAÇÃO:
1. "code_task": QUALQUER pedido para criar, desenvolver, fazer, gerar, reprogramar, refatorar ou implementar algo NOVO.
   ⚠️ ATENÇÃO: Se a mensagem contiver "Crie", "Faça", "Desenvolva", "Gere" ou "Implemente", a intenção É OBRIGATORIAMENTE "code_task", MESMO QUE diga para rodar ou testar em seguida!
   Identifique se o usuário pediu para evitar/ignorar testes unitários ou testar executando diretamente.
   Campos: "intent": "code_task", "task": "<tarefa_completa>", "project": "<nome_do_projeto>", "no_tests": true/false

2. "run_code": Apenas quando o usuário quer EXECUTAR/RODAR um script/projeto que JÁ EXISTE no disco.
   Campos: "intent": "run_code", "project_path": "<caminho_extraido_ou_.>", "command": "<comando_opcional>"

3. "ingest": Mapear, indexar, ingerir ou ler pastas/arquivos de código na base vetorial.
   Campos: "intent": "ingest", "path": "<caminho_extraido>", "project": "<nome_do_projeto>"

4. "query": Perguntas sobre funcionamento, arquitetura, regras de negócio ou código do projeto na base vetorial.
   Campos: "intent": "query", "query": "<pergunta>", "project": "<nome_do_projeto>"

5. "chat": Conversas gerais, saudações, dúvidas sobre ações recentes/erros anteriores.
   Campos: "intent": "chat"

Retorne APENAS um JSON válido no seguinte formato:
{{
  "intent": "ingest" | "query" | "run_code" | "code_task" | "chat",
  "path": null,
  "project": "{active_project}",
  "query": null,
  "project_path": ".",
  "command": null,
  "task": null,
  "no_tests": false
}}
"""
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
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
            raw = res.get("response", "")
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(json_match.group(0)) if json_match else json.loads(raw)
            if verbose:
                print(f"\n💬 [Raciocínio - Decisão do Roteador]:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n")
            return parsed
    except Exception:
        return {"intent": "chat"}

def send_chat_message(messages):
    """Envia o histórico de chat direto para o Ollama."""
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
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
        {"role": "system", "content": "Você é o Wygor, um assistente especialista em engenharia de software e automação. Você tem acesso ao histórico de comandos executados no terminal pelo usuário e pelas ferramentas."}
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

            # Roteamento autônomo de intenção
            intent_data = classify_intent(user_input, active_project, verbose=verbose_mode)
            intent = intent_data.get("intent", "chat")

            if intent == "ingest":
                target_path = intent_data.get("path") or user_input
                proj = intent_data.get("project") or active_project
                print(f"\n⚙️  [Agente Autônomo] Mapeando repositório: {target_path} (Projeto: {proj})...\n")
                
                args = [target_path, "-p", proj]
                ok, out, err = run_skill("ingest_docs.py", args, capture_output=False)
                active_project = proj
                
                # Alimenta o histórico do chat
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "system", "content": f"Ação 'ingest' executada. Status: {'Sucesso' if ok else 'Falha'}. Saída: {out}\n{err}"})
                print(f"\n✅ Mapeamento concluído para o projeto [{active_project}]!\n")

            elif intent == "query":
                proj = intent_data.get("project") or active_project
                q = intent_data.get("query") or user_input
                print(f"\n🔍 [Agente Autônomo] Pesquisando na base vetorial [{proj}]...\n")
                
                ok, ctx, _ = run_skill("query_knowledge.py", [q, "-p", proj, "-l", "3", "--raw"])
                
                if verbose_mode:
                    print(f"📄 [Raciocínio - Contexto Resgatado do pgvector]:\n{ctx}\n")

                context_str = f"Contexto recuperado da base de dados ({proj}):\n{ctx}\n\n" if ctx else "Nenhum dado encontrado na base vetorial."
                prompt_with_ctx = f"{context_str}\nPergunta do usuário: {user_input}"
                
                messages.append({"role": "user", "content": prompt_with_ctx})
                response = send_chat_message(messages)
                print(f"🤖 Wygor:\n{response}\n")
                messages.append({"role": "assistant", "content": response})

            elif intent == "run_code":
                proj_path = intent_data.get("project_path") or "."
                cmd = intent_data.get("command")
                print(f"\n🚀 [Agente Autônomo] Executando projeto em '{proj_path}'...\n")
                
                args = [proj_path]
                if cmd:
                    args.extend(["-c", cmd])
                ok, out, err = run_skill("code_runner.py", args, capture_output=False)
                
                # Alimenta o histórico do chat para ele ter memória da execução!
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "system", "content": f"Ação 'run_code' executada em {proj_path}. Status: {'Sucesso' if ok else 'Falha'}.\nSTDOUT:\n{out}\nSTDERR:\n{err}"})
                print()

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
                
                ok, out, err = run_skill("code_agent.py", agent_args, capture_output=False)
                
                # Alimenta o histórico com o resultado do agente
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "system", "content": f"Ação 'code_task' concluída. Tarefa: '{task}'. Status: {'Sucesso' if ok else 'Falha'}.\nResultado:\n{out}\n{err}"})
                print()

            else:
                # Conversa padrão ou dúvidas sobre execuções anteriores
                messages.append({"role": "user", "content": user_input})
                response = send_chat_message(messages)
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