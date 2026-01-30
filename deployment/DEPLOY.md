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
ROOT_PATH=/folio
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

### 6. 設定 Nginx

複製到 service 目錄（符合您現有架構）：

```bash
sudo cp deployment/nginx-folio-migration.conf /etc/nginx/conf.d/service/folio-migration.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 7. 驗證安裝

```bash
# 檢查服務狀態
sudo systemctl status folio-migration-web

# 測試 API（直接連 uvicorn）
curl http://localhost:8000/api/health

# 測試透過 Nginx
curl https://your-domain/folio/api/health
```

存取網址：`https://your-domain/folio/`

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
# 檢查磁碟空間
df -h /folio/
```
