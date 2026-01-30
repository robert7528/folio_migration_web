# FOLIO Migration Web - Deployment Guide

## Prerequisites

- Rocky Linux 8/9 or similar RHEL-based distribution
- Python 3.10+ (3.13 recommended)
- Nginx
- Git
- uv (Python package manager)

## Installation Steps

### 1. Install System Dependencies

```bash
# Install Python and development tools
sudo dnf install -y python3.13 python3.13-devel git nginx

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2. Create Application User

```bash
# Create folio user
sudo useradd -r -m -d /opt/folio_migration_web -s /bin/bash folio

# Switch to folio user
sudo -u folio -i
```

### 3. Clone and Setup Application

```bash
# Clone repository (as folio user)
cd /opt/folio_migration_web
git clone https://github.com/FOLIO-FSE/folio_migration_web.git .

# Create virtual environment
uv venv .venv --python 3.13

# Activate and install
source .venv/bin/activate
uv pip install -e .

# Create data directories
mkdir -p data clients logs
```

### 4. Configure Application

```bash
# Copy and edit configuration
cp .env.example .env
nano .env
```

**Important settings to configure in `.env`:**
```
APP_ENV=production
DEBUG=false
CLIENTS_DIR=/opt/folio_migration_web/clients
DATABASE_URL=sqlite:///./data/migration.db
```

### 5. Initialize Database

```bash
# Run the application once to create tables
python -c "from folio_migration_web.db.database import init_db; init_db()"
```

### 6. Setup Systemd Service

```bash
# Exit folio user
exit

# Copy service file
sudo cp /opt/folio_migration_web/deployment/folio-migration-web.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable folio-migration-web
sudo systemctl start folio-migration-web

# Check status
sudo systemctl status folio-migration-web
```

### 7. Configure Nginx

```bash
# Copy nginx configuration
sudo cp /opt/folio_migration_web/deployment/nginx.conf /etc/nginx/sites-available/folio-migration
sudo cp /opt/folio_migration_web/deployment/nginx-common.conf /etc/nginx/snippets/folio-migration-common.conf

# Create sites-enabled directory if not exists
sudo mkdir -p /etc/nginx/sites-enabled

# Enable site
sudo ln -s /etc/nginx/sites-available/folio-migration /etc/nginx/sites-enabled/

# Edit server_name in nginx config
sudo nano /etc/nginx/sites-available/folio-migration
# Change: server_name migration.example.com;
# To: server_name your-actual-domain.com;

# Include sites-enabled in nginx.conf if not already
sudo nano /etc/nginx/nginx.conf
# Add in http block: include /etc/nginx/sites-enabled/*;

# Test nginx configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### 8. Configure Firewall

```bash
# Allow HTTP/HTTPS
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## Verify Installation

```bash
# Check service status
sudo systemctl status folio-migration-web

# Check logs
sudo journalctl -u folio-migration-web -f

# Test locally
curl http://localhost:8000/api/clients

# Test via nginx
curl http://your-domain.com/
```

## Updating

```bash
# Stop service
sudo systemctl stop folio-migration-web

# Update code
sudo -u folio -i
cd /opt/folio_migration_web
git pull

# Update dependencies
source .venv/bin/activate
uv pip install -e .
exit

# Restart service
sudo systemctl start folio-migration-web
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u folio-migration-web -n 50

# Check permissions
ls -la /opt/folio_migration_web/
```

### 502 Bad Gateway
```bash
# Check if application is running
sudo systemctl status folio-migration-web

# Check if port is listening
ss -tlnp | grep 8000
```

### File upload fails
```bash
# Check nginx client_max_body_size
sudo nginx -T | grep client_max_body_size

# Check disk space
df -h /opt/folio_migration_web/
```

## Security Notes

1. **Production SSL**: Enable HTTPS in nginx configuration
2. **Firewall**: Only allow necessary ports
3. **Updates**: Keep system and Python packages updated
4. **Backups**: Regular backup of `/opt/folio_migration_web/data/` and `/opt/folio_migration_web/clients/`

## Directory Structure

```
/opt/folio_migration_web/
├── .env                    # Configuration
├── .venv/                  # Python virtual environment
├── data/
│   └── migration.db        # SQLite database
├── clients/                # Client project directories
│   ├── thu/
│   ├── tpml/
│   └── ...
├── logs/                   # Application logs
├── static/                 # Static files (CSS, JS)
├── templates/              # HTML templates
└── src/                    # Application source code
```
