#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess

def detect_test_runner(repo_path):
    """Detecta automaticamente qual ferramenta de teste/linter usar com base na estrutura do projeto."""
    abs_path = os.path.abspath(repo_path)

    # 1. Node.js / TypeScript / JavaScript
    pkg_json = os.path.join(abs_path, "package.json")
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    return "npm test"
                if "check" in scripts:
                    return "npm run check"
        except Exception:
            pass

    # 2. Python
    if os.path.exists(os.path.join(abs_path, "pytest.ini")) or \
       os.path.exists(os.path.join(abs_path, "tests")) or \
       any(f.endswith(".py") for f in os.listdir(abs_path) if os.path.isfile(os.path.join(abs_path, f))):
        # Tenta pytest primeiro, caindo para python -m unittest se necessário
        return "pytest"

    # 3. Rust
    if os.path.exists(os.path.join(abs_path, "Cargo.toml")):
        return "cargo test"

    # 4. Go
    if os.path.exists(os.path.join(abs_path, "go.mod")):
        return "go test ./..."

    # 5. C / C++ (Makefile)
    if os.path.exists(os.path.join(abs_path, "Makefile")):
        return "make test"

    return None

def _build_command(command, abs_path):
    """Resolve o comando de validação preferindo o .venv do projeto quando existir."""
    if command == "pytest":
        venv_py = os.path.join(abs_path, ".venv", "bin", "python")
        if os.path.exists(venv_py):
            return f'"{venv_py}" -m pytest'
    return command


def run_validation(repo_path, command=None, timeout=60):
    """Executa a validação e retorna status, stdout e stderr."""
    abs_path = os.path.abspath(repo_path)

    if not command:
        command = detect_test_runner(abs_path)

    if not command:
        print("⚠️ Nenhum runner de teste detectado automaticamente. Especifique com --cmd.", file=sys.stderr)
        return False, "Nenhum test runner configurado ou detectado."

    command = _build_command(command, abs_path)

    print(f"🧪 Executando validação: `{command}` em {abs_path}...")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=abs_path,
            text=True,
            capture_output=True,
            timeout=timeout
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        passed = (result.returncode == 0)

        if passed:
            print("✅ Validação/Testes concluídos com SUCESSO!")
            if stdout:
                print(f"\n--- Resumo ---\n{stdout[:1000]}")
        else:
            print("❌ Validação/Testes FALHARAM!")
            print(f"\n--- Output de Erro ---\n{stderr if stderr else stdout}")

        return passed, stderr if stderr else stdout

    except subprocess.TimeoutExpired:
        msg = f"⏱️ Tempo limite excedido ({timeout}s) ao executar: {command}"
        print(msg, file=sys.stderr)
        return False, msg
    except Exception as e:
        msg = f"❌ Erro ao executar validação: {e}"
        print(msg, file=sys.stderr)
        return False, msg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill de Validação e Checagem de Código (Linter & Testes) do Wygor Core")
    parser.add_argument("path", help="Caminho do repositório/projeto")
    parser.add_argument("-c", "--cmd", help="Comando customizado para rodar linters/testes (ex: 'pytest', 'npm test', 'flake8')")
    parser.add_argument("-t", "--timeout", type=int, default=60, help="Tempo limite de execução em segundos (default: 60)")

    args = parser.parse_args()

    success, output = run_validation(args.path, command=args.cmd, timeout=args.timeout)
    sys.exit(0 if success else 1)
