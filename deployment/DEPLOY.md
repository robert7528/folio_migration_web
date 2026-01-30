# FOLIO Migration Web - Deployment Guide

## Prerequisites

- Rocky Linux 8/9 or similar RHEL-based distribution
- Python 3.10+ (3.13 recommended)
- Nginx (已安裝)
- Git
- uv (Python package manager)

## Installation Steps

### 1. 安裝 uv（如果還沒安裝）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2. 建立目錄並 Clone

```bash
# 建立目錄
sudo mkdir -p /folio/folio_migration_web
sudo chown $USER:$USER /folio/folio_migration_web

# Clone
cd /folio/folio_migration_web
git clone https://github.com/robert7528/folio_migration_web.git .
```

### 3. 建立虛擬環境並安裝

```bash
# 建立虛擬環境
uv venv .venv --python 3.13

# 啟動並安裝
source .venv/bin/activate
uv pip install -e .

# 建立資料目錄
mkdir -p data clients
```

### 4. 設定環境變數

```bash
cp .env.example .env
nano .env
```

確認以下設定：
```
APP_ENV=production
DEBUG=false
```

### 5. 安裝 Systemd 服務

```bash
sudo cp deployment/folio-migration-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable folio-migration-web
sudo systemctl start folio-migration-web

# 檢查狀態
sudo systemctl status folio-migration-web
```

### 6. 設定 Nginx（不影響現有設定）

複製設定檔到 conf.d（使用獨立檔名）：

```bash
sudo cp deployment/nginx-folio-migration.conf /etc/nginx/conf.d/folio-migration.conf
```

編輯設定檔，修改 port 和 server_name：

```bash
sudo nano /etc/nginx/conf.d/folio-migration.conf
```

重點修改：
- `listen 8080;` → 改成您要的 port（如 80 沒被佔用可改成 80）
- `server_name _;` → 改成您的域名或 IP

測試並重載：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 7. 開放防火牆（如需要）

```bash
# 如果使用 8080 port
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

## 驗證安裝

```bash
# 檢查服務狀態
sudo systemctl status folio-migration-web

# 檢查 log
sudo journalctl -u folio-migration-web -f

# 測試 API（直接連 uvicorn）
curl http://localhost:8000/api/health

# 測試 Nginx（假設用 8080）
curl http://localhost:8080/api/health
```

## 更新程式

```bash
cd /folio/folio_migration_web
git pull
source .venv/bin/activate
uv pip install -e .
sudo systemctl restart folio-migration-web
```

## 目錄結構

```
/folio/folio_migration_web/
├── .env                    # 環境設定
├── .venv/                  # Python 虛擬環境
├── data/
│   └── migration.db        # SQLite 資料庫
├── clients/                # 客戶專案目錄
│   ├── thu/
│   ├── tpml/
│   └── ...
├── static/                 # 靜態檔案 (CSS, JS)
├── templates/              # HTML 模板
└── src/                    # 程式原始碼
```

## 疑難排解

### 服務無法啟動
```bash
sudo journalctl -u folio-migration-web -n 50
```

### 502 Bad Gateway
```bash
# 確認 uvicorn 有在跑
ss -tlnp | grep 8000
```

### 檔案上傳失敗
```bash
# 檢查 nginx client_max_body_size
sudo nginx -T | grep client_max_body_size

# 檢查磁碟空間
df -h /folio/
```
