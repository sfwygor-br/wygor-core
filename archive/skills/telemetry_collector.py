#!/usr/bin/env python3
"""Coletor de Telemetria Observavel Nao-Invasiva (Spec 002) - Wygor Core."""

import os
import re
import sys
import json
import subprocess
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SKILL_MANIFEST = {
    "intent": "telemetry_collector",
    "description": "Coleta logs e estados do sistema (PIDs, stdout/stderr, journalctl e /var/log) de forma nao-invasiva, extraindo assinaturas de erros e excecoes.",
    "keywords": ["telemetria", "coletar logs", "logs do sistema", "journalctl", "var log", "pids", "processos"],
    "script": "skills/telemetry_collector.py"
}

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "root")

ERROR_PATTERNS = [
    r"Error:\s[^\n]*",
    r"\w*Exception[^\n]*",
    r"Traceback \([^\n]*",
    r"fatal[^\n]*",
    r"fail[^\n]*",
    r"denied[^\n]*",
]


def get_connection():
    try:
        import psycopg2
        return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    except Exception as e:
        print(f"ERRO conexao: {e}", file=sys.stderr)
        return None

def _run_cmd(cmd, timeout=10):
    try:
        res = subprocess.run(cmd, shell=True, executable="/bin/bash",
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, timeout=timeout)
        return res.stdout or ""
    except Exception as e:
        return f"(coleto impossivel: {e})"

def classify_severity(line):
    low = line.lower()
    if any(k in low for k in ["critical", "severe", "panic", "segmentation", "crash", "fatal"]):
        return "critical"
    if "error" in low or "exception" in low or "traceback" in low:
        return "error"
    if "warn" in low or "denied" in low:
        return "warning"
    return "info"

def extract_signatures(text):
    sigs = []
    for p in ERROR_PATTERNS:
        for m in re.finditer(p, text, re.IGNORECASE):
            s = m.group(0).strip()
            if s and len(s) < 500:
                sigs.append(s)
    uniq, seen = [], set()
    for s in sigs:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:20]

def map_process_pids(process_filter=None):
    if process_filter:
        cmd = f"ps -eo pid,comm,args | grep -i '{process_filter}' | grep -v grep | head -50"
    else:
        cmd = "ps -eo pid,comm,args | head -60"
    rows = []
    for line in _run_cmd(cmd).splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit():
            rows.append({"pid": int(parts[0]), "comm": parts[1],
                         "args": parts[2] if len(parts) > 2 else ""})
    return rows

def collect_journald(unit=None, minutes=30):
    since = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    if unit:
        cmd = f"journalctl -u {unit} --since '{since}' --no-pager 2>/dev/null | tail -200"
    else:
        cmd = f"journalctl --since '{since}' --no-pager 2>/dev/null | tail -200"
    return _run_cmd(cmd)

def collect_varlog():
    out = []
    for name in ("syslog", "dmesg", "kern.log"):
        path = os.path.join("/var/log", name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            if lines:
                out.append(f"<{name}>")
                out.extend(lines[-200:])
        except Exception as e:
            out.append(f"(nao foi possivel ler {path}: {e})")
    return "\n".join(out)

def collect(project="default", minutes=30, unit=None, process=None, raw=False):
    conn = get_connection()
    if not conn:
        return False
    cur = conn.cursor()

    procs = map_process_pids(process)
    journal_text = collect_journald(unit=unit, minutes=minutes)
    varlog_text = collect_varlog()

    combined = []
    if procs:
        block = "\n".join(f"[pid={p['pid']}] {p['comm']}: {p['args']}" for p in procs[:50])
        combined.append(("process", block))
    if journal_text.strip() and "<coleto impossivel" not in journal_text:
        combined.append(("journal", journal_text))
    if varlog_text.strip() and "<coleto impossivel" not in varlog_text:
        combined.append(("varlog", varlog_text))

    events = []
    for source, text in combined:
        signatures = extract_signatures(text) or ["(nenhuma assinatura de erro evidente)"]
        for sig in signatures:
            ev = {"source": source, "severity": classify_severity(sig),
                  "signature": sig, "raw": text[:1200], "process_name": None, "pid": None}
            if source == "process":
                m = re.match(r"\[pid=(\d+)\] (\S+)", text)
                if m:
                    ev["pid"], ev["process_name"] = int(m.group(1)), m.group(2)
            events.append(ev)
            try:
                cur.execute("""
                    INSERT INTO system_telemetry_events
                    (collected_at, source, process_name, pid, scope, severity, signature, raw_message)
                    VALUES (CURRENT_TIMESTAMP, %s, %s, %s, 'system_telemetry', %s, %s, %s);
                """, (source, ev["process_name"], ev["pid"], ev["severity"], ev["signature"], ev["raw"]))
            except Exception as e:
                if "UndefinedTable" in str(e) or "does not exist" in str(e):
                    print("ERR_MISSING_TABLE: Tabela 'system_telemetry_events' ausente.", file=sys.stderr)
                    cur.close(); conn.close(); sys.exit(1)
                conn.rollback()
                print(f"aviso: {e}", file=sys.stderr)

    conn.commit()
    cur.close(); conn.close()

    if raw:
        print("RESULT")
        for ev in events:
            print(json.dumps({"source": ev["source"], "severity": ev["severity"], "signature": ev["signature"]}, ensure_ascii=False))
        return True

    print(f"\nTELEMETRIA [{project}] - processos: {len(procs)} eventos: {len(events)}")
    for ev in events[:20]:
        print(f"  [{ev['severity']}] ({ev['source']}) {ev['signature'][:90]}")
    return True

def list_events(project="default", limit=20, raw=False):
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, collected_at, source, process_name, severity, signature FROM system_telemetry_events WHERE scope='system_telemetry' ORDER BY collected_at DESC LIMIT %s;", (limit,))
        rows = cur.fetchall()
    except Exception as e:
        print(f"erro listar: {e}", file=sys.stderr); return
    finally:
        cur.close(); conn.close()

    for r in rows:
        if raw:
            print(json.dumps({"id": r[0], "source": r[2], "process": r[3], "severity": r[4], "signature": r[5]}, ensure_ascii=False))
        else:
            print(f"[#{r[0]} {r[1]}] [{r[3]}] ({r[4]}) {r[5][:90]}")

def clear_events(project="default"):
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM system_telemetry_events WHERE scope='system_telemetry';")
        conn.commit()
        print("Eventos de telemetria removidos.")
    except Exception as e:
        print(f"erro limpar: {e}", file=sys.stderr)
    finally:
        cur.close(); conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coletor de Telemetria Observavel")
    parser.add_argument("action", nargs="?", default="collect", choices=["collect", "list", "clear"])
    parser.add_argument("-p", "--project", default="default")
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--unit", default=None)
    parser.add_argument("--process", default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args()

    if args.action == "collect":
        collect(args.project, minutes=args.minutes, unit=args.unit, process=args.process, raw=args.raw)
    elif args.action == "list":
        list_events(args.project, limit=args.limit, raw=args.raw)
    elif args.action == "clear":
        clear_events(args.project)
