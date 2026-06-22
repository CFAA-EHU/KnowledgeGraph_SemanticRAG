#!/bin/bash
set -e

SERVICE=/etc/systemd/system/ollama.service

cat > /tmp/ollama_service_new.conf << 'EOF'
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=/usr/local/cuda/bin:/opt/bin/:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin"
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_MAX_QUEUE=8"

[Install]
WantedBy=default.target
EOF

cp /tmp/ollama_service_new.conf $SERVICE
systemctl daemon-reload
systemctl restart ollama
sleep 3
systemctl is-active ollama && echo "Ollama reiniciado OK con OLLAMA_NUM_PARALLEL=4"
