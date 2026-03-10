# ManualFeeFinesTransformer 任務分析

## 概述

ManualFeeFinesTransformer 將 CSV/TSV 格式的費用/罰款記錄轉換為 FOLIO Fee/Fine 物件。它產生包含 `account`（帳款）和 `feefineaction`（帳款動作）的 Extradata 格式檔案，後續由 BatchPoster 以 Extradata 模式寫入 FOLIO。

## 任務類型

- **類別**: Transform（轉換）
- **migration_task_type**: `ManualFeeFinesTransformer`
- **FOLIO 物件類型**: Fee/Fine（Composite: account + feefineaction）
- **來源資料格式**: TSV

## 工作流程

```
feefines.tsv（來源資料）
    ↓ 讀取 TSV 記錄
    ↓ 套用 manual_feefines_map.json 欄位映射
    ↓ 查詢 feefine_owners.tsv → 透過 API 取得 Owner UUID
    ↓ 查詢 feefine_types.tsv → 透過 API 取得 Fee/Fine Type UUID
    ↓ 查詢 feefine_service_points.tsv → 透過 API 取得 Service Point UUID
    ↓ 查詢 User（by barcode）→ 取得 userId
    ↓ 查詢 Item（by barcode）→ 取得 item 資訊
    ↓ 取得 Tenant 時區
    ↓ 產生 composite fee/fine（account + feefineaction）
    ↓ 寫入 Extradata 格式
Extradata 檔案（account\t{json}\nfeefineaction\t{json}）
```

## 呼叫的 FOLIO API

### 初始化階段（讀取參考資料）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/owners` | GET | 取得所有 Fee/Fine Owner（驗證 feefine_owners.tsv 的 `folio_name`） |
| `/feefines` | GET | 取得所有 Fee/Fine Type（驗證 feefine_types.tsv 的 `folio_feeFineType`） |
| `/service-points` | GET | 取得所有 Service Point（驗證 feefine_service_points.tsv 的 `folio_name`） |
| `/configurations/entries?query=(module==ORG and configName==localeSettings)` | GET | 取得 Tenant 時區設定 |

### 轉換階段（每筆記錄）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/users` | GET | 以條碼查詢 User，取得 userId（`folio_get_all`） |
| `/inventory/items` | GET | 以條碼查詢 Item，取得 item 資訊（`folio_get_all`） |

### GitHub（非 FOLIO API）

| 來源 | 用途 |
|---|---|
| `folio-org/mod-feesfines/ramls/accountdata.json` | Account JSON Schema |
| `folio-org/mod-feesfines/ramls/feefineactiondata.json` | Fee/Fine Action JSON Schema |

## 輸入檔案

| 檔案 | 來源目錄 | 說明 |
|---|---|---|
| `feefines.tsv` | `source_data/fees_fines/` ⚠️ | 費用/罰款來源資料 |
| `manual_feefines_map.json` | `mapping_files/` | 欄位映射定義 |
| `feefine_owners.tsv` | `mapping_files/` | Owner 對應表 |
| `feefine_types.tsv` | `mapping_files/` | Fee/Fine Type 對應表 |
| `feefine_service_points.tsv` | `mapping_files/` | Service Point 對應表 |

> ⚠️ **目錄名稱**: folio_migration_tools 使用 `fees_fines`（有底線），不是 `feefines`。

## feefine_owners.tsv 格式

```tsv
legacy_owner	folio_name
default	Tunghai University
```

## feefine_types.tsv 格式

```tsv
legacy_type	folio_feeFineType
default	Overdue fine
```

## feefine_service_points.tsv 格式

```tsv
legacy_code	folio_name
default	Main circulation desk
```

> 使用 `folio_name` 作為 Service Point 的查詢鍵（而非 `folio_servicepoint`）。

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `extradata` | `results/` | Extradata 格式（每筆 fee/fine 產生 2 行） |
| `feefines_transformation.md` | `reports/` | 轉換報告 |

### Extradata 格式範例

```
account	{"id":"uuid-1","ownerId":"...","feeFineId":"...","amount":50.0,...}
feefineaction	{"id":"uuid-2","accountId":"uuid-1","amountAction":50.0,...}
```

每筆來源記錄產生 **2 行 extradata**（1 個 account + 1 個 feefineaction）。

## 關鍵設定

```json
{
    "name": "transform_feefines",
    "migration_task_type": "ManualFeeFinesTransformer",
    "files": [{"file_name": "feefines.tsv", "suppress": false}],
    "feefines_map": "manual_feefines_map.json",
    "feefines_owner_map": "feefine_owners.tsv",
    "feefines_type_map": "feefine_types.tsv",
    "service_point_map": "feefine_service_points.tsv"
}
```

### manual_feefines_map.json 關鍵欄位

映射檔需包含以下 FOLIO 欄位的對應：

- `account.amount` — 罰款金額
- `account.remaining` — 剩餘金額
- `account.ownerId` — Owner UUID（透過 feefine_owners.tsv 對應）
- `account.feeFineId` — Fee/Fine Type UUID（透過 feefine_types.tsv 對應）
- `account.userId` — User UUID（透過 barcode 查詢 API）
- `account.barcode` — Item 條碼
- `feefineaction.dateAction` — 動作日期
- `feefineaction.createdAt` — Service Point UUID（透過 feefine_service_points.tsv 對應）

## 注意事項

- **Extradata 模式**: 不同於 Inventory Transform 產生的純 JSON，Fee/Fine 產出 Extradata 格式，需使用 BatchPoster 的 `object_type: "Extradata"` 模式寫入
- **每筆 2 行**: 統計時需注意 extradata 行數 ÷ 2 = 實際 fee/fine 筆數
- **re-transform 會產生新 UUID**: 重新執行 Transform 會產生不同的 UUID，必須重新 Post，否則驗證會失敗
- **User 和 Item 必須先存在**: Transform 階段就會查詢 FOLIO API 驗證 User 和 Item 條碼
- **Fee/Fine Owner 必須先在 FOLIO 建立**: 在 FOLIO Settings → Fee/Fine → Owners 中手動建立
- **Fee/Fine Type 必須先在 FOLIO 建立**: 在 FOLIO Settings → Fee/Fine → Fee/Fine Types 中建立
