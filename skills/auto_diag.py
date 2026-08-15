#!/usr/bin/env python3
"""
Skill de Autodiagnóstico e Telemetria do Wygor Core.
Avalia a capacidade computacional local, modelo Ollama ativo e latência,
persistindo o estado no PgVector sob o projeto 'system_telemetry'.
"""

import os
import sys
import json
import time
import socket
import platform
import argparse
import urllib.request
import subprocess
#import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Manifesto lido dinamicamente pelo Roteador Plug-and-Play
SKILL_MANIFEST = {
    "intent": "auto_diag",
    "description": "Executa autodiagnóstico de hardware, latência de IA e status do ambiente local, salvando a telemetria na base vetorial.",
    "script": "auto_diag.py"
}

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip('/')
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embeddings"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")



def check_gpu():
    """Verifica presença, VRAM e utilização da GPU via nvidia-smi."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().split("\n")[0].split(",")
            return {
                "available": True,
                "name": lines[0].strip(),
                "vram_total_mb": float(lines[1].strip()),
                "vram_free_mb": float(lines[2].strip()),
                "gpu_utilization_pct": float(lines[3].strip())
            }
    except Exception:
        pass
    return {"available": False, "name": "N/A", "vram_total_mb": 0, "vram_free_mb": 0, "gpu_utilization_pct": 0}

def check_ollama_status():
    """Mede a latência e recupera a lista de modelos ativos no Ollama local."""
    models = []
    latency_ms = -1
    status = "offline"

    start_t = time.time()
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL)
        with urllib.request.urlopen(req, timeout=3) as resp:
            latency_ms = round((time.time() - start_t) * 1000, 2)
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                status = "online"
    except Exception as e:
        status = f"error: {str(e)}"

    return {
        "status": status,
        "latency_ms": latency_ms,
        "available_models": models
    }

def collect_telemetry():
    """Mapeia o SO, CPU, GPU e decide a recomendação de execução."""
    gpu_info = check_gpu()
    ollama_info = check_ollama_status()
    
    system_info = {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count() or 1
    }

    # Critério de transbordo: se não houver GPU e a latência do Ollama for > 300ms, recomenda CLOUD
    needs_cloud = (not gpu_info["available"]) and (ollama_info["latency_ms"] > 300 or ollama_info["status"] != "online")
    recommended_tier = "cloud" if needs_cloud else "local"

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": system_info,
        "gpu": gpu_info,
        "ollama": ollama_info,
        "recommended_tier": recommended_tier
    }

def get_embedding(text):
    """Gera o vetor do relatório para busca RAG futura no PgVector."""
    payload = {"model": EMBED_MODEL, "prompt": text[:4000]}
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("embedding", [])
    except Exception:
        return []

def save_to_pgvector(telemetry):
    """Salva a telemetria na tabela document_chunks sob o escopo 'system_telemetry'."""
    try:
        import psycopg2
    except ImportError:
        print("❌ Erro: psycopg2 não instalado. Execute: pip install psycopg2-binary", file=sys.stderr)
        return False
        
    content_str = (
        f"Diagnóstico de Sistema [{telemetry['timestamp']}]\n"
        f"Host: {telemetry['system']['hostname']} | SO: {telemetry['system']['os']} ({telemetry['system']['architecture']})\n"
        f"CPUs: {telemetry['system']['cpu_count']} | GPU: {telemetry['gpu']['name']} (Disponível: {telemetry['gpu']['available']}, VRAM Livre: {telemetry['gpu']['vram_free_mb']}MB)\n"
        f"Ollama Status: {telemetry['ollama']['status']} | Latência: {telemetry['ollama']['latency_ms']}ms | Modelos: {', '.join(telemetry['ollama']['available_models'])}\n"
        f"Recomendação de Execução: {telemetry['recommended_tier'].upper()}"
    )

    vec = get_embedding(content_str)

    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cur = conn.cursor()

        sql = """
        INSERT INTO document_chunks (project_name, file_path, content, embedding)
        VALUES (%s, %s, %s, %s::vector);
        """
        file_path = f"telemetry_{telemetry['system']['hostname']}.json"
        
        cur.execute(sql, ("system_telemetry", file_path, content_str, vec if vec else None))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Erro ao salvar telemetria no banco: {e}", file=sys.stderr)
        return False

def run_diagnostics(save=True, raw=False):
    telemetry = collect_telemetry()
    
    if save:
        save_to_pgvector(telemetry)

    if raw:
        print(json.dumps(telemetry, indent=2, ensure_ascii=False))
    else:
        print("\n📊 --- RELATÓRIO DE AUTODIAGNÓSTICO ---")
        print(f"🖥️ Hostname     : {telemetry['system']['hostname']} ({telemetry['system']['os']} {telemetry['system']['architecture']})")
        print(f"⚡ CPU Cores    : {telemetry['system']['cpu_count']}")
        print(f"🎮 GPU          : {telemetry['gpu']['name']} (VRAM Livre: {telemetry['gpu']['vram_free_mb']} MB)")
        print(f"🦙 Ollama Status: {telemetry['ollama']['status'].upper()} (Latência: {telemetry['ollama']['latency_ms']} ms)")
        print(f"📦 Modelos      : {', '.join(telemetry['ollama']['available_models']) if telemetry['ollama']['available_models'] else 'Nenhum'}")
        print(f"🎯 Recomendação : Executar preferencialmente em [{telemetry['recommended_tier'].upper()}]")
        print("----------------------------------------\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill de Autodiagnóstico e Telemetria Wygor Core")
    # Ignora a action enviada pelo roteador (ex: list, run)
    parser.add_argument("action", nargs="?", default="run", help="Ação a ser executada")
    # Aceita o parâmetro de projeto injetado pelo chat.py
    parser.add_argument("-p", "--project", default="default", help="Nome do projeto ativo")
    parser.add_argument("--no-save", action="store_true", help="Executa sem salvar no banco de dados")
    parser.add_argument("--raw", action="store_true", help="Saída em formato JSON puro")

    args = parser.parse_args()
    run_diagnostics(save=not args.no_save, raw=args.raw)
