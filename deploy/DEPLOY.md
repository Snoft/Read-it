# Deploy

Same shape as the CRM, so the runbook is short. Hetzner box, Caddy in front, one
systemd unit, unprivileged user.

## Once

```bash
adduser --disabled-password --gecos "" readit
su - readit
git clone <repo> app && cd app
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # put the API key in, chmod 600 .env
```

`/etc/systemd/system/readit.service`

```ini
[Unit]
Description=Readit
After=network.target

[Service]
User=readit
WorkingDirectory=/home/readit/app
EnvironmentFile=/home/readit/app/.env
ExecStart=/home/readit/app/.venv/bin/uvicorn deploy.app:app --host 127.0.0.1 --port 8011
Restart=always

[Install]
WantedBy=multi-user.target
```

Caddyfile:

```
readit.santino.life {
    reverse_proxy 127.0.0.1:8011
    basic_auth { santino <bcrypt-hash> }
}
```

`caddy hash-password` gives the hash. Then:

```bash
systemctl enable --now readit && systemctl reload caddy
```

## Shipping a change

```bash
git push
ssh root@<host> "su - readit -c 'cd ~/app && git pull && .venv/bin/pip install -r requirements.txt' && systemctl restart readit"
```

## Before you make the repo public

```bash
git log -p | grep -iE "sk-|api[_-]?key|ANTHROPIC" | head
```

Anything found means rewriting history, not just deleting the file. Check before
the first push, not after.
