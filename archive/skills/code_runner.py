#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

def run_project(project_path, command=None, timeout=10):
    """Executa um comando ou script dentro do workspace do projeto."""
    abs_path = os.path.abspath(project_path)
    
    if not os.path.exists(abs_path):
        print(f"❌ Erro: O diretório do projeto '{abs_path}' não existe.", file=sys.stderr)
        return False

    # Se nenhum comando específico foi passado, tenta achar um ponto de entrada padrão
    if not command:
        if os.path.exists(os.path.join(abs_path, "main.py")):
            command = f"python3 main.py"
        elif os.path.exists(os.path.join(abs_path, "app.py")):
            command = f"python3 app.py"
        else:
            print("❌ Nenhum comando de execução fornecido e nenhum 'main.py' ou 'app.py' encontrado na raiz.", file=sys.stderr)
            return False

    print(f"🚀 Executando projeto em '{abs_path}'...")
    print(f"💻 Comando: {command}\n" + "-"*40)

    # Prepara o ambiente garantindo o PYTHONPATH correto
    env = os.environ.copy()
    env["PYTHONPATH"] = abs_path

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=abs_path,
            env=env,
            text=True,
            timeout=timeout
        )
        print("-" * 40)
        if result.returncode == 0:
            print("✅ Execução finalizada com sucesso!")
            return True
        else:
            print(f"⚠️ A execução retornou código de saída {result.returncode}.")
            return False
    except subprocess.TimeoutExpired:
        print(f"\n❌ Erro: A execução excedeu o limite de {timeout} segundos (Timeout).", file=sys.stderr)
        return False
    except Exception as e:
        print(f"\n❌ Erro ao executar o projeto: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill para Executar Projetos do Wygor")
    parser.add_argument("project_path", help="Caminho do diretório do projeto")
    parser.add_argument("-c", "--command", default=None, help="Comando personalizado para execução")
    parser.add_argument("-t", "--timeout", type=int, default=10, help="Timeout em segundos")

    args = parser.parse_args()
    success = run_project(args.project_path, command=args.command, timeout=args.timeout)
    sys.exit(0 if success else 1)