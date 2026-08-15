#!/usr/bin/env python3
import sys
import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def print_help():
    print("""
🤖 Wygor Core CLI - Motor Contextual Multi-Projeto

Uso:
  wygor agent "<instrução>" [-p PROJETO] -r <path>  Executa tarefa de código 100% autônoma
  wygor migrate                         Executa as migrações pendentes do banco
  wygor search "<query>" [-p PROJETO]   Busca contexto RAG Híbrido (Vector + Keyword)
  wygor ingest <caminho> [-p PROJETO]   Ingestão incremental de repositórios / pastas
  wygor watch <caminho> [-p PROJETO]    Monitora alterações e re-indexa em tempo real
  wygor memory "<nota>" [-p PROJETO]    Grava uma decisão/memória técnica no banco
  wygor git prepare <path> -t "<task>"  Prepara Git local e cria branch de trabalho
  wygor git commit <path> -m "<msg>"    Registra alterações locais no Git
  wygor code write <file> --content ""  Criar/escrever um arquivo de código
  wygor code patch <file> --old "" --new "" Modificar um trecho do código existente
  wygor check <path> [-c "<comando>"]   Executa linters e suíte de testes no projeto
  wygor manual [SEÇÃO]                  Exibe o manual de instruções e engenharia
  wygor chat                            Abre o chat interativo (Stateful + Multi-Projeto)
  wygor telemetry [collect|list|clear] [--unit U] [--minutes N]  Coleta telemetria do sistema
  wygor telclassify [--window-hours N] Classifica e vetoriza logs em system_telemetry (RAG)
  wygor native run -c "<cmd>" | native check | native history  Executa pipeline Bash nativo auto-healing
  wygor help                            Exibe esta ajuda
""")

def show_manual(section=None):
    manual_dir = os.path.join(SCRIPT_DIR, "docs/manual")
    if not os.path.exists(manual_dir):
        print("⚠️ Diretório de manual não encontrado em docs/manual.")
        return

    files = sorted([f for f in os.listdir(manual_dir) if f.endswith(".md")])
    if not files:
        print("⚠️ Nenhum arquivo de manual encontrado.")
        return

    print("📖 === MANUAL DE INSTRUÇÕES & ENGENHARIA WYGOR CORE ===\n")
    for f in files:
        if section and section.lower() not in f.lower():
            continue
        path = os.path.join(manual_dir, f)
        print(f"--- [ Seção: {f} ] ---")
        with open(path, "r", encoding="utf-8") as file:
            print(file.read())
        print("\n" + "="*50 + "\n")

def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "agent":
        script = os.path.join(SCRIPT_DIR, "skills/code_agent.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "migrate":
        script = os.path.join(SCRIPT_DIR, "skills/db_migrate.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "search":
        script = os.path.join(SCRIPT_DIR, "skills/query_knowledge.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "ingest":
        script = os.path.join(SCRIPT_DIR, "skills/ingest_docs.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "watch":
        script = os.path.join(SCRIPT_DIR, "skills/watch.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "memory":
        script = os.path.join(SCRIPT_DIR, "skills/memory.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "git":
        script = os.path.join(SCRIPT_DIR, "skills/git_guard.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "code":
        script = os.path.join(SCRIPT_DIR, "skills/code_engineer.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "check":
        script = os.path.join(SCRIPT_DIR, "skills/code_checker.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "manual":
        sec = args[0] if len(args) > 0 else None
        show_manual(section=sec)
    elif cmd == "chat":
        script = os.path.join(SCRIPT_DIR, "skills/chat.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "telemetry":
        # Observabilidade externa nao-invasiva (Spec 002): collect | list | clear
        sub_action = args[0] if len(args) > 0 and args[0] in ("collect", "list", "clear") else "collect"
        script = os.path.join(SCRIPT_DIR, "skills/telemetry_collector.py")
        subprocess.run([sys.executable, script, sub_action] + args[1:])
    elif cmd == "telclassify":
        # Classifica e vetoriza logs de telemetria no escopo system_telemetry (Spec 002)
        script = os.path.join(SCRIPT_DIR, "skills/telemetry_classify.py")
        subprocess.run([sys.executable, script] + args)
    elif cmd == "native":
        # Executor nativo de sistema: pipelines bash com auto-healing (Spec 002)
        sub_action = args[0] if len(args) > 0 and args[0] in ("run", "check", "history") else "run"
        script = os.path.join(SCRIPT_DIR, "skills/native_workflow.py")
        subprocess.run([sys.executable, script, sub_action] + args[1:])
    elif cmd in ("status", "info"):
        script = os.path.join(SCRIPT_DIR, "skills/db_migrate.py")
        subprocess.run([sys.executable, script, "--status"])
    elif cmd in ("help", "-h", "--help"):
        print_help()
    else:
        print(f"❌ Comando desconhecido: '{cmd}'")
        print_help()

if __name__ == "__main__":
    main()
