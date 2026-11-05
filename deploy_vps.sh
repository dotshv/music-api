#!/usr/bin/env bash
set -e

sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg nginx certbot python3-certbot-nginx git curl

mkdir -p /home/ubuntu/api
cd /home/ubuntu/api

if [ ! -d "/home/ubuntu/api/venv" ]; then
    python3 -m venv /home/ubuntu/api/venv
fi

/home/ubuntu/api/venv/bin/pip install --upgrade pip
/home/ubuntu/api/venv/bin/pip install -r /home/ubuntu/api/requirements.txt

sudo tee /etc/systemd/system/toxics-api.service > /dev/null << 'EOF'
[Unit]
Description=Toxics Music API Daemon
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/api
ExecStart=/home/ubuntu/api/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3
EnvironmentFile=/home/ubuntu/api/.env

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/nginx/sites-available/toxics.me > /dev/null << 'EOF'
server {
    listen 80;
    server_name toxics.me www.toxics.me;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/toxics.me /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

sudo systemctl daemon-reload
sudo systemctl enable toxics-api
sudo systemctl restart toxics-api

echo "Setup completed successfully! Run certbot for SSL: sudo certbot --nginx -d toxics.me -d www.toxics.me"

