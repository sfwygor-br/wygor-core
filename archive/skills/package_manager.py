#!/usr/bin/env python3
"""
Skill para gerenciar pacotes Python: instalar, listar, verificar.
Uso: python package_manager.py install requests flask
     python package_manager.py list
"""
import sys
import subprocess
import argparse

def install_packages(packages):
    for pkg in packages:
        print(f"Instalando {pkg}...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)
            print(f"✅ {pkg} instalado com sucesso.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Falha ao instalar {pkg}: {e}", file=sys.stderr)
            return False
    return True

def list_packages():
    result = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
    print(result.stdout)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerenciador de pacotes Python")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="Instalar pacotes")
    install_parser.add_argument("packages", nargs="+", help="Nomes dos pacotes")

    list_parser = subparsers.add_parser("list", help="Listar pacotes instalados")

    args = parser.parse_args()
    if args.command == "install":
        success = install_packages(args.packages)
    elif args.command == "list":
        success = list_packages()
    else:
        success = False

    sys.exit(0 if success else 1)