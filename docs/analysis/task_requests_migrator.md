# RequestsMigrator 任務分析

## 概述

RequestsMigrator 將開放中的預約記錄直接遷移到 FOLIO。與 LoansMigrator 類似，它**不產生中間 JSON 檔案**，而是直接透過 FOLIO Circulation API 即時建立預約請求。它會查詢 FOLIO 中的 User、Item、Holdings 資訊，組裝完整的 Request 物件後 POST 到 FOLIO。

## 任務類型

- **類別**: Migrator（直接遷移）
- **migration_task_type**: `RequestsMigrator`
- **FOLIO 物件類型**: Request
- **來源資料格式**: TSV

## 工作流程

```
requests.tsv（來源資料）
    ↓ 讀取並驗證預約記錄
    ↓ （選用）比對 Item/User 條碼是否存在於已遷移資料
    ↓ 取得 Tenant 時區
    ↓ 依 request_date 排序
    ↓ 逐筆處理：
    ↓   查詢 User（by barcode）→ 取得 patron_id
    ↓   查詢 Item（by barcode）→ 取得 item_id、holdingsRecordId
    ↓   查詢 Holdings → 取得 instanceId
    ↓   判斷 request_type（Item 狀態為 Available → Page）
    ↓   POST 建立 Request
預約記錄直接寫入 FOLIO
```

## 呼叫的 FOLIO API

### 初始化階段

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/configurations/entries?query=(module==ORG and configName==localeSettings)` | GET | 取得 Tenant 時區設定 |

### 執行階段（每筆預約記錄）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/users?query=barcode=={barcode}` | GET | 以條碼查詢 User，取得 patron UUID |
| `/item-storage/items?query=barcode=={barcode}` | GET | 以條碼查詢 Item，取得 item UUID 和 holdingsRecordId |
| `/holdings-storage/holdings/{uuid}` | GET | 以 UUID 取得 Holdings Record，取得 instanceId |
| `/circulation/requests` | POST | **核心操作** — 建立預約請求 |

### 條碼驗證（選用，若提供 item_files / patron_files）

不額外呼叫 API，而是讀取本地已產生的 JSON 檔案比對條碼。

## 輸入檔案

| 檔案 | 來源目錄 | 說明 |
|---|---|---|
| `requests.tsv` | `source_data/requests/` | 預約來源資料 |
| `folio_items.json` | `results/`（選用） | 已遷移 Items（用於條碼驗證） |
| `folio_users.json` | `results/`（選用） | 已遷移 Users（用於條碼驗證） |

## requests.tsv 必要欄位

```tsv
item_barcode	patron_barcode	request_date	request_expiration_date	request_type	pickup_servicepoint_id	comment
```

| 欄位 | 必填 | 說明 |
|---|---|---|
| `item_barcode` | 是 | Item 條碼 |
| `patron_barcode` | 是 | 讀者條碼 |
| `request_date` | 是 | 預約日期（ISO 格式） |
| `request_expiration_date` | 是 | 預約到期日 |
| `request_type` | 是 | 預約類型：`Hold`、`Recall`、`Page` |
| `pickup_servicepoint_id` | 是 | 取書服務點 UUID |
| `comment` | 否 | 備註 |

### request_type 說明

- **Hold**: Item 已被借出，等待歸還後取書
- **Recall**: Item 已被借出，催還後取書
- **Page**: Item 在架上（Available），請求從書庫取出

> RequestsMigrator 會自動判斷：若 Item 狀態為 Available，會將 request_type 強制改為 Page。

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `failed_requests.tsv` | `results/` | 失敗的預約記錄 |
| `requests_migration.md` | `reports/` | 遷移報告 |

## 關鍵設定

```json
{
    "name": "migrate_open_requests",
    "migration_task_type": "RequestsMigrator",
    "open_requests_file": {"file_name": "requests.tsv", "suppress": false},
    "starting_row": 1,
    "item_files": [],
    "patron_files": []
}
```

### 設定說明

- **open_requests_file**: 單一檔案（注意：不是陣列，與 LoansMigrator 不同）
- **starting_row**: 起始行號（用於從中斷點繼續）
- **item_files / patron_files**: 若提供，會先驗證條碼

## Request 物件組裝

RequestsMigrator 在 `prepare_legacy_request()` 中組裝完整的 FOLIO Request：

```json
{
    "requestType": "Hold",
    "requestDate": "2024-01-15T08:00:00.000+08:00",
    "requestExpirationDate": "2024-07-15",
    "requesterId": "<patron UUID from API>",
    "itemId": "<item UUID from API>",
    "holdingsRecordId": "<from item's holdingsRecordId>",
    "instanceId": "<from holdings' instanceId>",
    "fulfilmentPreference": "Hold Shelf",
    "pickupServicePointId": "<from TSV>",
    "requestLevel": "Item"
}
```

## 注意事項

- **非 Transform + BatchPost 模式**: RequestsMigrator 直接呼叫 API
- **API 呼叫密集**: 每筆預約需 3 次 GET（User + Item + Holdings）+ 1 次 POST，速度較慢
- **執行前提**: Item 和 User 必須已存在於 FOLIO，且 Item 已透過 BatchPoster 寫入
- **排序**: 預約記錄會依 `request_date` 排序後處理，確保先進先出
- **fulfilmentPreference Bug**: folio_migration_tools 原始碼中 `fulfilmentPreference` 拼寫為 `fulfilmentPreference`（少一個 l），與 FOLIO API 要求的 `fulfillmentPreference` 不同。需要在安裝後手動 patch：
  ```python
  # legacy_request.py 第 Q5 行
  # 將 "fulfilmentPreference" 改為 "fulfillmentPreference"
  ```
- **超過 50% 失敗率**: 自動停止
