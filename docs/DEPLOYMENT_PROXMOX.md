# DEPLOYMENT PROXMOX — OKX AI Trading Grid System

Panduan lengkap untuk deploy sistem ke **Proxmox home server** menggunakan **LXC container** dengan **Ubuntu 24.04 LTS**.

---

## 1. Arsitektur

```text
┌─────────────────────────────────────────────────┐
│              PROXMOX HOME SERVER                │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  LXC: "okx-trading" (Ubuntu 24.04)        │  │
│  │                                           │  │
│  │  Docker Compose:                          │  │
│  │  ┌─────────────┐  ┌─────────────┐        │  │
│  │  │ telegram-bot│  │ app (API)   │        │  │
│  │  │  (polling)  │  │  :8000      │        │  │
│  │  └──────┬──────┘  └──────┬──────┘        │  │
│  │         │                │               │  │
│  │  ┌──────▼──────┐        │               │  │
│  │  │  redis      │        │               │  │
│  │  │  (cache)    │        │               │  │
│  │  └─────────────┘        │               │  │
│  └─────────────────────────┼───────────────┘  │
└────────────────────────────┼──────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  SUPABASE (Cloud DB)        │
              │  PostgreSQL 15              │
              │  (Phase 1: Beta Trial)      │
              └─────────────────────────────┘
```

**Catatan:** Telegram bot menggunakan **polling mode** (koneksi outbound).
Tidak perlu port forwarding atau public IP. Home server di belakang NAT/router tetap bisa jalan.

---

## 2. Spesifikasi LXC

```text
Template:  Ubuntu 24.04 LTS
CPU:       2 cores
RAM:       2 GB (Phase 1, tanpa DB lokal)
Disk:      10 GB
Network:   DHCP (outbound only)
```

---

## 3. Setup Proxmox

### 3.1 Download Template

SSH ke Proxmox host:

```bash
# Update template list
pveam update

# Download Ubuntu 24.04 template
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst

# Verifikasi template tersedia
pveam list local
```

### 3.2 Buat LXC Container

```bash
# Buat container ID 105
pct create 105 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst \
  --hostname okx-trading \
  --cores 2 \
  --memory 2048 \
  --swap 512 \
  --disk 10 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --features nesting=1 \
  --ostype ubuntu

# Start container
pct start 105

# Masuk ke container
pct enter 105
```

### 3.3 Setup Dasar Ubuntu

```bash
# Update package
apt update && apt upgrade -y

# Install dasar
apt install -y curl git nano htop gpg

# Set timezone (opsional)
timedatectl set-timezone Asia/Jakarta
```

### 3.4 Setup Cloudflare WARP (Bypass Blokir DNS ISP / TrustPositif)

Agar container dapat mengakses API OKX, Binance, dan Bybit tanpa terhalang DNS sinkhole ISP Indonesia:

**Langkah A: Di Proxmox Host (Aktifkan TUN Device untuk LXC 105)**
```bash
# Di shell Proxmox host, tambahkan konfigurasi TUN device ke LXC 105
cat << 'EOF' >> /etc/pve/lxc/105.conf
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
EOF

# Restart LXC 105
pct reboot 105
```

**Langkah B: Di Dalam LXC 105 (Install & Connect WARP)**
```bash
pct enter 105

# 1. Tambahkan repository Cloudflare Client
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ noble main" | tee /etc/apt/sources.list.d/cloudflare-client.list

# 2. Install cloudflare-warp
apt update && apt install -y cloudflare-warp

# 3. Registrasi & Connect
warp-cli registration new
warp-cli mode warp
warp-cli connect

# 4. Verifikasi status
warp-cli status
curl https://www.cloudflare.com/cdn-cgi/trace | grep warp
# Output yang benar: warp=on
```

---

## 4. Install Docker

```bash
# Install Docker (official script)
curl -fsSL https://get.docker.com | sh

# Install docker compose plugin
apt install -y docker-compose-plugin

# Verifikasi
docker --version
docker compose version

# Aktifkan Docker service
systemctl enable docker
systemctl start docker
```

---

## 5. Clone & Configure

```bash
# Clone repository
cd /opt
git clone https://github.com/adminberitakarya-Aji/okx.git
cd okx

# Copy environment template
cp .env.example .env

# Edit .env dengan credentials
nano .env
```

### Konfigurasi `.env` yang Diperlukan:

```bash
# ============================================================================
# APPLICATION
# ============================================================================
APP_ENV=production
APP_DEBUG=false
APP_DEV_AUTH_ENABLED=false
APP_SECRET_KEY=<generate-random-secret>

# ============================================================================
# DATABASE (Phase 1: Supabase)
# ============================================================================
# Ganti dengan Supabase connection string Anda
DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxx.supabase.co:5432/postgres

# ============================================================================
# REDIS
# ============================================================================
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=<generate-random-password>

# ============================================================================
# TELEGRAM
# ============================================================================
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_ALLOWED_USER_IDS=<your-user-id>
TELEGRAM_ADMIN_USER_ID=<your-user-id>
# Beta trial: true = anyone can use
TELEGRAM_OPEN_ACCESS=true

# ============================================================================
# OKX (Demo Trading)
# ============================================================================
OKX_API_KEY=<your-demo-api-key>
OKX_API_SECRET=<your-demo-api-secret>
OKX_PASSPHRASE=<your-demo-passphrase>
OKX_DEMO_MODE=true

# ============================================================================
# CREDENTIAL ENCRYPTION (Phase 5: Multi-Tenant)
# ============================================================================
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CREDENTIAL_ENCRYPTION_KEY=<your-fernet-key>
```

---

## 6. Build & Start

> **PENTING:** Selalu gunakan `--env-file` agar Docker Compose membaca `.env` dengan benar.

```bash
# Build images
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml build

# Start semua services
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml up -d

# Cek status
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml ps
```

**Atau gunakan deploy script (otomatis):**
```bash
bash scripts/deploy.sh
```

### Verifikasi:

```bash
# 1. Cek semua containers healthy
docker compose -f deploy/docker/docker-compose.prod.yml ps

# 2. Cek API health
curl http://localhost:8000/health

# 3. Cek log telegram bot
docker logs -f okx-trading-telegram

# 4. Test bot di Telegram
# Buka @gridtrade6_bot → /start
```

---

## 7. Management

### Logs

```bash
# Semua services
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml logs -f

# Telegram bot saja
docker logs -f okx-trading-telegram

# API saja
docker logs -f okx-trading-app
```

### Restart

```bash
# Restart semua
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml restart

# Restart telegram bot saja
docker restart okx-trading-telegram
```

### Update

```bash
cd /opt/okx
git pull
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml build
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml up -d
```

### Stop

```bash
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml down
```

---

## 8. Monitoring

### Healthcheck Otomatis

Docker `restart: unless-stopped` akan otomatis restart container jika crash.

### Cek Status:

```bash
# Semua containers
docker ps

# Resource usage
docker stats
```

### Alert (Opsional):

```bash
# Cron job untuk cek health setiap 5 menit
*/5 * * * * curl -sf http://localhost:8000/health > /dev/null || echo "API DOWN" | mail -s "OKX API Down" admin@example.com
```

---

## 9. Migrasi ke Local PostgreSQL (Phase 2)

Setelah semua flow berjalan stabil, migrasi dari Supabase ke local PostgreSQL.

### 9.1 Export dari Supabase

```bash
# Di LXC, install postgresql-client
apt install -y postgresql-client

# Export data dari Supabase
pg_dump "postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres" \
  > /backup/supabase_dump.sql
```

### 9.2 Aktifkan Local DB

Edit `deploy/docker/docker-compose.prod.yml`:

1. **Uncomment** service `db` (TimescaleDB)
2. **Uncomment** volume `pgdata`
3. **Update** `DATABASE_URL` di semua services:
   ```yaml
   - DATABASE_URL=postgresql+asyncpg://${DB_USER:-okx_user}:${DB_PASSWORD}@db:5432/${DB_NAME:-okx_trading}
   ```

### 9.3 Buat init-db.sql

```bash
# Buat file init database
nano deploy/docker/init-db.sql
```

```sql
-- init-db.sql
CREATE USER okx_user WITH PASSWORD 'your-strong-password';
CREATE DATABASE okx_trading OWNER okx_user;
GRANT ALL PRIVILEGES ON DATABASE okx_trading TO okx_user;
```

### 9.4 Import Data

```bash
# Start db service dulu
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml up -d db

# Import data
docker exec -i okx-trading-db psql -U okx_user okx_trading < /backup/supabase_dump.sql

# Restart semua services
docker compose --env-file /opt/okx/.env -f deploy/docker/docker-compose.prod.yml up -d
```

### 9.5 Backup Otomatis (Cron)

```bash
# Edit crontab
crontab -e

# Tambah backup harian jam 2 pagi
0 2 * * * docker exec okx-trading-db pg_dump -U okx_user okx_trading | gzip > /backup/okx_$(date +\%Y\%m\%d).sql.gz

# Retensi 7 hari
0 3 * * * find /backup -name "*.sql.gz" -mtime +7 -delete
```

---

## 10. Troubleshooting

### Bot tidak merespons

```bash
# Cek log
docker logs -f okx-trading-telegram

# Cek token valid
# Test manual: curl https://api.telegram.org/bot<TOKEN>/getMe
```

### API tidak bisa diakses

```bash
# Cek container status
docker ps | grep okx-trading-app

# Cek log
docker logs okx-trading-app

# Cek health
curl http://localhost:8000/health
```

### Database connection error

```bash
# Cek Supabase reachable
nc -zv db.xxxxx.supabase.co 5432

# Cek DATABASE_URL di .env
grep DATABASE_URL .env
```

### Container restart loop

```bash
# Cek log detail
docker logs --tail 100 okx-trading-app

# Cek environment
docker inspect okx-trading-app | grep -A5 Environment
```

---

## 11. Checklist Deployment

```text
☑ LXC container dibuat ID 105 (Ubuntu 24.04)
☑ TUN device diizinkan di Proxmox host (/etc/pve/lxc/105.conf)
☑ Cloudflare WARP terinstall & status Connected (warp=on)
☑ Docker + Docker Compose terinstall
☑ Repository cloned
☑ .env dikonfigurasi (semua credentials)
☑ Images built
☑ Semua services running
☑ API health check OK
☑ Telegram bot merespons /start
☑ Open access mode aktif (beta trial)
☑ Backup strategy disiapkan
```

---

## 12. Referensi

- [Proxmox VE Documentation](https://pve.proxmox.com/wiki/Main_Page)
- [Docker Documentation](https://docs.docker.com/)
- [Ubuntu 24.04 LTS](https://ubuntu.com/download/server)
- [Supabase](https://supabase.com/docs)