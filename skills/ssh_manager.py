#!/usr/bin/env python3
"""
Skill Dinâmica do Wygor Core: Gerenciador de Perfis SSH (CRUD & Status)
"""

import os
import sys
import json
import socket
import argparse
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

from utils.db_service import execute_query

SKILL_MANIFEST = {
    "intent": "ssh_manager",
    "description": "Gerencia perfis de conexão SSH no banco (CRUD) e executa comandos/deploys via ssh e rsync nativos.",
    "keywords": ["cadastrar ssh", "adicionar servidor", "listar ssh", "listar hosts", "remover host", "perfil ssh", "testar conexao ssh", "conexoes ssh", "executar ssh", "rodar comando remoto", "deploy", "rsync", "sincronizar"],
    "allowed_actions": ["add", "list", "remove", "test", "exec", "sync"],
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

def _build_ssh_base(host, port, username, auth_type, key_path, secret_data):
    """Monta a base do comando ssh nativo a partir do perfil salvo no banco."""
    base = ["ssh", "-p", str(port), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new"]
    if auth_type == "key_path" and key_path:
        base += ["-i", os.path.expanduser(key_path)]
    elif auth_type == "key_content" and secret_data:
        print("⚠️ auth_type 'key_content' exige arquivo de chave; use 'key_path'.", file=sys.stderr)
        return None
    elif auth_type == "password":
        print("⚠️ Autenticação por senha exige 'sshpass'; recomendado usar chave SSH.", file=sys.stderr)
        return None
    base.append(f"{username}@{host}")
    return base


def exec_command(project, name, command, timeout=60):
    """Executa um comando remoto usando o binário ssh nativo + perfil salvo no banco."""
    try:
        row = execute_query(
            "SELECT host, port, username, auth_type, key_path, secret_data FROM ssh_hosts WHERE project_name = %s AND name = %s;",
            (project, name), commit=False, fetch="one")
    except Exception as e:
        print(f"❌ Erro ao buscar perfil SSH: {e}", file=sys.stderr)
        sys.exit(1)
    if not row:
        print(f"❌ Perfil '{name}' não encontrado no projeto [{project}].", file=sys.stderr)
        sys.exit(1)

    host, port, username, auth_type, key_path, secret_data = row
    base = _build_ssh_base(host, port, username, auth_type, key_path, secret_data)
    if base is None:
        sys.exit(1)

    print(f"🔌 Executando em {username}@{host}:{port} -> {command}")
    try:
        result = subprocess.run(base + [command], capture_output=True, text=True, timeout=timeout)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        print(f"exit={result.returncode}")
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout após {timeout}s executando comando remoto.", file=sys.stderr)
        return 124
    except FileNotFoundError:
        print("❌ Binário 'ssh' não encontrado no sistema.", file=sys.stderr)
        return 127


def sync_files(project, name, src, dest, timeout=300):
    """Deploy/sincronização de arquivos locais para o host remoto via rsync nativo."""
    try:
        row = execute_query(
            "SELECT host, port, username, auth_type, key_path FROM ssh_hosts WHERE project_name = %s AND name = %s;",
            (project, name), commit=False, fetch="one")
    except Exception as e:
        print(f"❌ Erro ao buscar perfil SSH: {e}", file=sys.stderr)
        sys.exit(1)
    if not row:
        print(f"❌ Perfil '{name}' não encontrado no projeto [{project}].", file=sys.stderr)
        sys.exit(1)

    host, port, username, auth_type, key_path = row
    if auth_type != "key_path" or not key_path:
        print("⚠️ sync exige autenticação por chave (key_path).", file=sys.stderr)
        sys.exit(1)

    ssh_cmd = (f"ssh -p {port} -i {os.path.expanduser(key_path)} "
               f"-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new")
    cmd = ["rsync", "-avz", "--partial", "-e", ssh_cmd, src, f"{username}@{host}:{dest}"]
    print(f"📦 rsync {src} -> {username}@{host}:{dest}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        print(f"exit={result.returncode}")
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout após {timeout}s no rsync.", file=sys.stderr)
        return 124
    except FileNotFoundError:
        print("❌ Binário 'rsync' não encontrado no sistema.", file=sys.stderr)
        return 127

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
    parser.add_argument("-c", "--command", help="Comando remoto a executar (ação exec)")
    parser.add_argument("--src", help="Origem local para rsync (ação sync)")
    parser.add_argument("--dest", help="Destino remoto para rsync (ação sync)")

    args = parser.parse_args()
    
    # Normalização da action vinda do CLI ou Roteador
    action_map = {
        "add": "add", "adicionar": "add", "cadastrar": "add",
        "list": "list", "listar": "list", "sessoes": "list", "hosts": "list",
        "remove": "remove", "remover": "remove", "deletar": "remove",
        "test": "test", "testar": "test",
        "exec": "exec", "run": "exec", "execute": "exec", "rodar": "exec", "comando": "exec",
        "sync": "sync", "rsync": "sync", "deploy": "sync", "enviar": "sync"
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
    elif action == "exec":
        if not args.name or not args.command:
            print("❌ Ação 'exec' exige '--name' e '-c \"<comando>\"'.", file=sys.stderr)
            sys.exit(1)
        sys.exit(exec_command(args.project, args.name, args.command))
    elif action == "sync":
        if not args.name or not args.src or not args.dest:
            print("❌ Ação 'sync' exige '--name', '--src' e '--dest'.", file=sys.stderr)
            sys.exit(1)
        sys.exit(sync_files(args.project, args.name, args.src, args.dest))