#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

def run_cmd(cmd, cwd=None, check=True):
    """Executa comandos shell de forma segura e retorna a saída."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=check
        )
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stderr.strip(), e.returncode

def ensure_git_repo(repo_path):
    """Garante que o diretório seja um repositório Git. Se não for, inicializa."""
    repo_path = os.path.abspath(repo_path)
    
    if not os.path.exists(repo_path):
        os.makedirs(repo_path, exist_ok=True)
        print(f"📁 Diretório criado: {repo_path}")

    git_dir = os.path.join(repo_path, ".git")
    if not os.path.exists(git_dir):
        print(f"⚙️ Inicializando repositório Git local em: {repo_path}")
        out, code = run_cmd("git init", cwd=repo_path)
        if code != 0:
            print(f"❌ Erro ao inicializar Git: {out}", file=sys.stderr)
            return False
            
        # Cria um .gitignore padrão se não existir
        gitignore = os.path.join(repo_path, ".gitignore")
        if not os.path.exists(gitignore):
            with open(gitignore, "w", encoding="utf-8") as f:
                f.write(".venv/\n__pycache__/\n*.pyc\nnode_modules/\n.env\n.DS_Store\ndist/\nbuild/\n")
            print("📄 Arquivo .gitignore padrão criado.")

        # Commit inicial para consolidar o estado
        run_cmd("git add .", cwd=repo_path)
        run_cmd('git commit -m "chore: initial commit by wygor-core"', cwd=repo_path, check=False)

    return True

def checkout_task_branch(repo_path, task_name, prefix="feat"):
    """Cria e altera para uma branch isolada de trabalho."""
    repo_path = os.path.abspath(repo_path)
    if not ensure_git_repo(repo_path):
        return False

    # Sanitiza nome da branch
    clean_task = task_name.lower().replace(" ", "-").replace("/", "-")
    # Limpa caracteres especiais mantendo alfanuméricos e hífens
    clean_task = "".join(c for c in clean_task if c.isalnum() or c == "-")
    branch_name = f"{prefix}/wygor-{clean_task}"

    print(f"🔀 Alternando/Criando branch local: {branch_name}")
    
    # Tenta dar checkout na branch caso já exista, ou cria uma nova com -b
    out, code = run_cmd(f"git checkout {branch_name}", cwd=repo_path, check=False)
    if code != 0:
        out, code = run_cmd(f"git checkout -b {branch_name}", cwd=repo_path)
        if code != 0:
            print(f"❌ Erro ao criar branch: {out}", file=sys.stderr)
            return False

    print(f"✅ Workspace pronto na branch '{branch_name}'!")
    return True

def commit_changes(repo_path, message):
    """Realiza o staging e commit local das alterações."""
    repo_path = os.path.abspath(repo_path)
    
    status, _ = run_cmd("git status --porcelain", cwd=repo_path)
    if not status:
        print("ℹ️ Nenhuma alteração pendente para commit.")
        return True

    print("📦 Adicionando arquivos alterados/criados no Git...")
    run_cmd("git add .", cwd=repo_path)
    
    out, code = run_cmd(f'git commit -m "{message}"', cwd=repo_path)
    if code == 0:
        print(f"💾 Commit local realizado: \"{message}\"")
        return True
    else:
        print(f"⚠️ Falha ao criar commit: {out}", file=sys.stderr)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerenciador de Workspace Git Local do Wygor Core")
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcomandos do Git Guard")

    # init/prepare
    prepare_parser = subparsers.add_parser("prepare", help="Garante Git e prepara branch de trabalho")
    prepare_parser.add_argument("path", help="Caminho do repositório/projeto")
    prepare_parser.add_argument("-t", "--task", required=True, help="Nome/Descrição da tarefa")
    prepare_parser.add_argument("--type", default="feat", choices=["feat", "fix", "refactor", "docs"], help="Tipo da branch")

    # commit
    commit_parser = subparsers.add_parser("commit", help="Comita alterações locais")
    commit_parser.add_argument("path", help="Caminho do repositório/projeto")
    commit_parser.add_argument("-m", "--message", required=True, help="Mensagem do commit")

    args = parser.parse_args()

    if args.subcommand == "prepare":
        success = checkout_task_branch(args.path, args.task, prefix=args.type)
        sys.exit(0 if success else 1)
    elif args.subcommand == "commit":
        success = commit_changes(args.path, args.message)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
