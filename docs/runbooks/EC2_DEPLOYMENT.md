# EC2 Deployment Runbook (Always-On Workers)

This runbook gets the agent running continuously on one EC2 host with `systemd`.

## 1) What to Create in AWS

Create:
1. EC2 instance: `t3.large` (recommended baseline), **Ubuntu 22.04 LTS (x86_64)**, 60-100 GB `gp3`.
2. Security group:
   - inbound `22` from your IP only.
   - for dashboard access, add inbound `8020` from your IP (or from your VPN/CIDR only).
3. Optional Elastic IP if you want a stable public IP for SSH.

Why this size:
1. 2 vCPU/8 GB is enough for v1 (ingest + analysis + Telegram listener).
2. No GPU required.
3. Prefer x86 for TDLib session bootstrap stability. ARM builds can fail at auth bootstrap on some hosts.
4. Ubuntu 22.04 is currently the most stable tested path for `aiotdlib==0.27.6` bootstrap.

## 2) Connect and clone repo

```bash
ssh -i <your-key>.pem ubuntu@<ec2-public-ip>
git clone https://github.com/mo-root/Poylmarket_NEWS_AGENT.git
cd Poylmarket_NEWS_AGENT
```

## 3) Prepare host

```bash
bash scripts/ec2_prepare_host.sh
```

Note:
Use Ubuntu 24.04+ for the current `aiotdlib` runtime (`libc++` dependencies). Amazon Linux 2023 may fail to load TDLib without extra manual library packaging.

## 4) Put env files on host

Create secure env directory:

```bash
sudo mkdir -p /etc/polymarket-news-agent
sudo chown ubuntu:ubuntu /etc/polymarket-news-agent
chmod 700 /etc/polymarket-news-agent
```

Create DB/runtime env file:
1. copy your local `.env` values into:
   - `/etc/polymarket-news-agent/.env`

Create Telegram env file:
1. copy your Telegram runtime values into:
   - `/etc/polymarket-news-agent/telegram.env`
2. keep `TELEGRAM_READ_ONLY_MODE=true` unless you explicitly need writes.

Permissions:

```bash
chmod 600 /etc/polymarket-news-agent/.env /etc/polymarket-news-agent/telegram.env
```

## 5) Bootstrap Telegram session once (interactive)

```bash
.venv/bin/python scripts/telegram_session_bootstrap.py --env-file /etc/polymarket-news-agent/telegram.env
```

This must complete successfully before starting long-running Telegram workers.

## 6) Install and start systemd services

```bash
sudo bash scripts/install_ec2_services.sh \
  "$(pwd)" \
  "ubuntu" \
  "/etc/polymarket-news-agent/.env" \
  "/etc/polymarket-news-agent/telegram.env"
```

Services started:
1. `polymarket-ingest.service`
2. `polymarket-analyze.service`
3. `telegram-market-agent.service`
4. `workspace-dashboard.service` (public bind `0.0.0.0:8020` by default)

## 7) Verify liveness

```bash
sudo systemctl status polymarket-ingest.service --no-pager
sudo systemctl status polymarket-analyze.service --no-pager
sudo systemctl status telegram-market-agent.service --no-pager
sudo systemctl status workspace-dashboard.service --no-pager
```

Tail logs:

```bash
tail -f logs/worker_ingest.log
tail -f logs/worker_analyze.log
tail -f logs/worker_telegram_agent.log
tail -f logs/workspace_dashboard.log

Open dashboard:

```bash
http://<ec2-public-ip>:8020
```
```

## 8) Common operations

Restart a worker:

```bash
sudo systemctl restart telegram-market-agent.service
sudo systemctl restart workspace-dashboard.service
```

Restart all:

```bash
sudo systemctl restart polymarket-ingest.service polymarket-analyze.service telegram-market-agent.service workspace-dashboard.service
```

Stop all:

```bash
sudo systemctl stop polymarket-ingest.service polymarket-analyze.service telegram-market-agent.service workspace-dashboard.service
```

## 9) Scale strategy

If throughput pressure appears:
1. Increase `--concurrency` and `--channel-limit` in `telegram-market-agent.service`.
2. Move to larger x86 instance (`m7i.xlarge` or above).
3. Keep one Telegram agent process per session directory to avoid TDLib session lock conflicts.
