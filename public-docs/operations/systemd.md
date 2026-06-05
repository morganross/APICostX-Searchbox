# Systemd Self-Hosting

Searchbox does not require Docker. A normal Linux VPS or workstation can run it as a Python virtualenv service.

## Install

```bash
git clone https://github.com/searchbox/searchbox.git
cd searchbox
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` for your providers.

For local/private deployments, the convenient default is:

```text
AUTH_DISABLED=true
```

If the service is exposed beyond a trusted private network, enable auth:

```text
AUTH_DISABLED=false
SEARCH_API_KEY=<strong random token>
```

## Example Unit

Create `/etc/systemd/system/searchbox.service`:

```ini
[Unit]
Description=Searchbox retrieval service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/searchbox
Environment=SEARCHBOX_ENV_FILE=/opt/searchbox/.env
ExecStart=/opt/searchbox/venv/bin/uvicorn main:app --host 127.0.0.1 --port 9000
Restart=on-failure
RestartSec=5
User=searchbox
Group=searchbox

[Install]
WantedBy=multi-user.target
```

Adjust paths and user/group for your machine.

## Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now searchbox.service
sudo systemctl status searchbox.service
```

## Check

```bash
curl -sS http://127.0.0.1:9000/health
curl -sS http://127.0.0.1:9000/health/monitor
```

## Update

```bash
cd /opt/searchbox
git pull
. venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart searchbox.service
```

## Persistent Files

By default, runtime `data/` and `logs/` are repo-relative. If you deploy somewhere ephemeral, configure these paths explicitly:

```text
ADVANCED_PROVIDER_QUOTA_FILE=/var/lib/searchbox/advanced_provider_daily_usage.json
ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE=/var/lib/searchbox/advanced_provider_monthly_usage.json
ADVANCED_PROVIDER_COOLDOWN_FILE=/var/lib/searchbox/advanced_provider_cooldowns.json
SEARCHBOX_LOG_DIR=/var/log/searchbox
```
