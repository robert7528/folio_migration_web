# LoansMigrator 任務分析

## 概述

LoansMigrator 將開放中的借閱記錄直接遷移到 FOLIO。與其他 Transformer 不同，LoansMigrator **不產生中間 JSON 檔案**，而是直接透過 FOLIO Circulation API 即時執行借出操作。它模擬真實的借閱流程（check-out by barcode），確保 FOLIO 的借閱業務邏輯完整觸發。

## 任務類型

- **類別**: Migrator（直接遷移，非 Transform + BatchPost 模式）
- **migration_task_type**: `LoansMigrator`
- **FOLIO 物件類型**: Loan
- **來源資料格式**: TSV

## 工作流程

```
loans.tsv（來源資料）
    ↓ 讀取並驗證借閱記錄（檢查必要欄位）
    ↓ （選用）比對 Item/User 條碼是否存在於已遷移資料
    ↓ 檢查 SMTP 設定（避免遷移觸發通知信）
    ↓ 取得 Tenant 時區
    ↓ 逐筆呼叫 Circulation API 執行 Check-out
    ↓ 處理失敗情況（重試、狀態修正）
    ↓ 更新到期日、續借次數
    ↓ 設定最終 Item 狀態（Declared lost、Claimed returned 等）
借閱記錄直接寫入 FOLIO
```

## 呼叫的 FOLIO API

### 初始化階段

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/smtp-configuration` | GET | 檢查 SMTP 是否已停用（防止遷移觸發 email 通知） |
| `/configurations/entries?query=(module==ORG and configName==localeSettings)` | GET | 取得 Tenant 時區設定 |

### 執行階段（每筆借閱記錄）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/circulation/check-out-by-barcode` | POST | **核心操作** — 以 Item 和 Patron 條碼執行借出 |
| `/circulation/loans/{id}` | PUT | 更新借閱記錄（修改到期日、續借次數） |
| `/circulation/loans/{id}/declare-item-lost` | POST | 宣告 Item 遺失 |
| `/circulation/loans/{id}/claim-item-returned` | POST | 宣告 Item 聲稱歸還 |
| `/circulation/loans/{id}/change-due-date` | POST | 變更到期日 |

### 錯誤處理相關

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/item-storage/items?query=(barcode=="{barcode}")` | GET | 以條碼查詢 Item（處理狀態衝突時） |
| `/item-storage/items/{id}` | PUT | 更新 Item 狀態（如設為 Available 後重試 check-out） |
| `/users?query=(barcode=="{barcode}")` | GET | 以條碼查詢 User（處理 inactive user 時） |
| `/users/{id}` | PUT | 更新 User（暫時啟用 → check-out → 停用） |
| `/loan-storage/loans?query=(itemId=="{id}")` | GET | 檢查 Item 是否已有借出記錄（避免重複） |

## 輸入檔案

| 檔案 | 來源目錄 | 說明 |
|---|---|---|
| `loans.tsv` | `source_data/loans/` | 借閱來源資料 |
| `folio_items.json` | `results/`（選用） | 已遷移 Items（用於條碼驗證） |
| `folio_users.json` | `results/`（選用） | 已遷移 Users（用於條碼驗證） |

## loans.tsv 必要欄位

```tsv
item_barcode	patron_barcode	due_date	out_date	renewal_count	next_item_status
```

| 欄位 | 必填 | 說明 |
|---|---|---|
| `item_barcode` | 是 | Item 條碼 |
| `patron_barcode` | 是 | 讀者條碼 |
| `due_date` | 是 | 到期日（ISO 格式） |
| `out_date` | 是 | 借出日（ISO 格式） |
| `renewal_count` | 否 | 續借次數（預設 0） |
| `next_item_status` | 否 | 目標狀態（Available / Checked out / Declared lost / Claimed returned） |
| `proxy_patron_barcode` | 否 | 代理讀者條碼 |

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `failed_loans.tsv` | `results/` | 失敗的借閱記錄 |
| `loans_migration.md` | `reports/` | 遷移報告 |

## 關鍵設定

```json
{
    "name": "migrate_open_loans",
    "migration_task_type": "LoansMigrator",
    "open_loans_files": [{"file_name": "loans.tsv", "suppress": false}],
    "fallback_service_point_id": "3a40852d-49fd-4df2-a1f9-6e2641a6e91f",
    "starting_row": 1,
    "item_files": [],
    "patron_files": []
}
```

### 設定說明

- **fallback_service_point_id**: 預設服務點 UUID（check-out 時使用的服務點）
- **starting_row**: 起始行號（用於從中斷點繼續，預設 1）
- **item_files / patron_files**: 若提供，會先驗證條碼是否存在於已遷移資料中

## 錯誤處理機制

LoansMigrator 內建多重重試和錯誤修復邏輯：

1. **Item 已借出**: 檢查是否為同一筆借閱 → 若否，將 Item 狀態設為 Available 後重試
2. **Inactive User**: 暫時啟用 User → check-out → 恢復停用狀態
3. **Aged to lost / Declared lost**: 將 Item 設為 Available → check-out → 恢復原狀態
4. **Claimed returned**: 將 Item 設為 Available → check-out
5. **超過 50% 失敗率**: 自動停止，防止大規模錯誤

## 注意事項

- **非 Transform + BatchPost 模式**: LoansMigrator 直接呼叫 API，不產生中間 JSON
- **SMTP 必須停用**: 遷移借閱會觸發通知信，必須先在 FOLIO Settings 停用 SMTP
- **執行前提**: Item 和 User 必須已存在於 FOLIO（需先完成 Inventory + User 遷移和 BatchPost）
- **速度**: 逐筆 API 呼叫，速度較慢（約每秒 2-5 筆）
- **Service Point**: 每筆借閱會記錄在哪個服務點借出，影響歸還流程
- **可重跑**: 會自動跳過已借出的 Item（重複借閱會被偵測）
