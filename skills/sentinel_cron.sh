#!/usr/bin/env bash

# Entra na pasta do projeto e roda o agente com a instrução de verificação
cd /home/wfelipe/Documents/wygor-core
/usr/bin/python3 wygor.py agent "Análise a telemetria recente, identifique falhas graves e aplique auto-healing se necessário" -p wygor-core >> /tmp/wygor_sentinel_cron.log 2>&1