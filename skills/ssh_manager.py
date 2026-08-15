#!/usr/bin/env python3
"""
Skill Dinâmica do Wygor Core: Gerenciador de Perfis SSH (CRUD & Status)
"""

import os
import sys
import json
import socket
import argparse

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

from utils.db_service import execute_query

SKILL_MANIFEST = {
    "intent": "ssh_manager",
    "description": "Gerencia perfis de conexão SSH no banco de dados (CRUD). Permite cadastrar, listar, remover e testar conexões de servidores.",
    "keywords": ["cadastrar ssh", "adicionar servidor", "listar ssh", "listar hosts", "remover host", "perfil ssh", "testar conexao ssh", "conexoes ssh"],
    "allowed_actions": ["add", "list", "remove", "test"],
    "script": "skills/ssh_manager.py"
}

def add_host(project, name, host, port, username, auth_type, key_path, secret_data, description):
    sql = """
    INSERT INTO ssh_hosts (project_name, name, host, port, username, auth_type, key_path, secret_data, description)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (project_name, name) DO UPDATE SET
        host = EXCLUDED.host,
        port = EXCLUDED.port,
        username = EXCLUDED.username,
        auth_type = EXCLUDED.auth_type,
        key_path = EXCLUDED.key_path,
        secret_data = EXCLUDED.secret_data,
        description = EXCLUDED.description,
        updated_at = CURRENT_TIMESTAMP;
    """
    try:
        execute_query(sql, (project, name, host, port, username, auth_type, key_path, secret_data, description))
        print(f"✅ Perfil SSH '{name}' cadastrado/atualizado no projeto [{project}]!")
    except Exception as e:
        if "UndefinedTable" in str(e) or "ssh_hosts" in str(e):
            print("ERR_MISSING_TABLE: A tabela 'ssh_hosts' não existe no banco de dados.", file=sys.stderr)
        else:
            print(f"❌ Erro ao salvar perfil SSH: {e}", file=sys.stderr)
        sys.exit(1)

def list_hosts(project, raw=False):
    sql = "SELECT id, name, host, port, username, auth_type, key_path, description FROM ssh_hosts WHERE project_name = %s ORDER BY name ASC;"
    try:
        rows = execute_query(sql, (project,), commit=False, fetch="all") or []
    except Exception as e:
        if "UndefinedTable" in str(e) or "ssh_hosts" in str(e):
            print("ERR_MISSING_TABLE: A tabela 'ssh_hosts' não existe no banco de dados.", file=sys.stderr)
        else:
            print(f"❌ Erro ao consultar perfis SSH: {e}", file=sys.stderr)
        sys.exit(1)

    hosts = [{"id": r[0], "name": r[1], "host": r[2], "port": r[3], "username": r[4], "auth_type": r[5], "key_path": r[6], "description": r[7]} for r in rows]

    if raw:
        print(json.dumps(hosts, indent=2, ensure_ascii=False))
        return

    print(f"\n🌐 --- SERVIDORES SSH CADASTRADOS [{project.upper()}] ---")
    if not hosts:
        print("Nenhum servidor SSH encontrado para este projeto.")
        print("---------------------------------------------------\n")
        return

    for h in hosts:
        print(f"🔹 [{h['name']}] -> {h['username']}@{h['host']}:{h['port']}")
        print(f"   Auth: {h['auth_type']} | Chave: {h['key_path'] or 'N/A'}")
        if h['description']:
            print(f"   Nota: {h['description']}")
    print("---------------------------------------------------\n")

def remove_host(project, name):
    sql = "DELETE FROM ssh_hosts WHERE project_name = %s AND name = %s;"
    try:
        deleted = execute_query(sql, (project, name), fetch="rowcount")
        if deleted > 0:
            print(f"🗑️ Perfil SSH '{name}' removido do projeto [{project}].")
        else:
            print(f"⚠️ Nenhum perfil encontrado com o nome '{name}' no projeto [{project}].")
    except Exception as e:
        print(f"❌ Erro ao remover perfil SSH: {e}", file=sys.stderr)
        sys.exit(1)

def test_connectivity(project, name):
    sql = "SELECT host, port FROM ssh_hosts WHERE project_name = %s AND name = %s;"
    try:
        row = execute_query(sql, (project, name), commit=False, fetch="one")
    except Exception as e:
        print(f"❌ Erro ao buscar perfil SSH: {e}", file=sys.stderr)
        sys.exit(1)

    if not row:
        print(f"❌ Perfil '{name}' não encontrado no projeto [{project}].")
        return

    host, port = row[0], row[1]
    print(f"🔍 Testando porta SSH ({host}:{port})...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"✅ Sucesso: Porta SSH {port} em {host} está aberta e acessível.")
        else:
            print(f"⚠️ Inacessível: Não foi possível conectar a {host}:{port} (Código: {result}).")
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill de Gerenciamento de SSH")
    parser.add_argument("action", nargs="?", default="list")
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("--name", help="Nome do servidor")
    parser.add_argument("--host", help="IP ou Hostname")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--username", default="root")
    parser.add_argument("--auth-type", default="key_path", choices=["key_path", "key_content", "password"])
    parser.add_argument("--key-path", help="Caminho do arquivo de chave SSH")
    parser.add_argument("--secret", help="Senha ou conteúdo da chave")
    parser.add_argument("--description", help="Descrição do servidor")
    parser.add_argument("--raw", action="store_true")

    args = parser.parse_args()
    
    # Normalização da action vinda do CLI ou Roteador
    action_map = {
        "add": "add", "adicionar": "add", "cadastrar": "add",
        "list": "list", "listar": "list", "sessoes": "list", "hosts": "list",
        "remove": "remove", "remover": "remove", "deletar": "remove",
        "test": "test", "testar": "test"
    }
    action = action_map.get((args.action or "list").lower(), "list")

    if action == "add":
        if not args.name or not args.host:
            print("❌ Parâmetros '--name' e '--host' são obrigatórios para a ação 'add'.", file=sys.stderr)
            sys.exit(1)
        add_host(args.project, args.name, args.host, args.port, args.username, args.auth_type, args.key_path, args.secret, args.description)
    elif action == "list":
        list_hosts(args.project, raw=args.raw)
    elif action == "remove":
        if not args.name:
            print("❌ Parâmetro '--name' é obrigatório para a ação 'remove'.", file=sys.stderr)
            sys.exit(1)
        remove_host(args.project, args.name)
    elif action == "test":
        if not args.name:
            print("❌ Parâmetro '--name' é obrigatório para a ação 'test'.", file=sys.stderr)
            sys.exit(1)
        test_connectivity(args.project, args.name)