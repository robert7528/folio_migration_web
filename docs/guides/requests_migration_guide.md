# FOLIO Requests 預約轉檔匯入完整指南

> 本文件說明如何使用 folio_migration_tools 的 RequestsMigrator 將流通預約記錄遷移到 FOLIO。

---

## 目錄

1. [前置條件](#一前置條件)
2. [整體流程概覽](#二整體流程概覽)
3. [來源資料格式](#三來源資料格式)
4. [Service Point 對應](#四service-point-對應)
5. [轉換工具：convert_thu_requests.py](#五轉換工具convert_thu_requestspy)
6. [requests.tsv 格式](#六requeststsv-格式)
7. [migration_config.json 設定](#七migration_configjson-設定)
8. [執行 RequestsMigrator](#八執行-requestsmigrator)
9. [驗證](#九驗證)
10. [Batch Deletion（取消預約）](#十batch-deletion取消預約)
11. [常見問題與解決](#十一常見問題與解決)

---

## 一、前置條件

Requests 遷移必須在以下資料匯入完成後才能執行：

```
Instances (書目) → Holdings (館藏) → Items (項目) → Users (讀者) → Requests (預約)
```

- **Items** 必須已存在於 FOLIO，因為 request 透過 item barcode 關聯
- **Users** 必須已存在於 FOLIO，因為 request 透過 patron barcode 關聯
- **Service Points** 必須已設定，request 需指定取書服務點

> **注意：** 如果同時有 Loans 遷移，建議先執行 Loans 再執行 Requests，因為已被借出的 item 只能建立 Hold 類型的預約。

---

## 二、整體流程概覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Requests Migration Flow                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 來源資料 (CSV)                                                  │
│     └── thu_requests-8.csv (HyLib 系統匯出的預約資料)                │
│                                                                     │
│  2. 轉換                                                            │
│     └── convert_thu_requests.py                                     │
│         ├── Input:  thu_requests-8.csv + keepsite_service_points.tsv│
│         └── Output: requests.tsv                                    │
│                                                                     │
│  3. 匯入                                                            │
│     └── RequestsMigrator (via Web Portal)                           │
│         ├── 讀取 requests.tsv                                       │
│         ├── 查詢 item UUID / patron UUID                            │
│         ├── 自動判斷 request type (Available → Page)                │
│         └── POST /circulation/requests                              │
│                                                                     │
│  4. 刪除（取消預約）                                                 │
│     └── Batch Deletion (via Web Portal)                             │
│         └── DELETE /circulation/requests/{id}                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、來源資料格式

THU 的來源資料是 HyLib 系統匯出的 CSV，主要欄位：

| CSV 欄位 | 說明 | 範例 |
|----------|------|------|
| `barcode` | 單件條碼（item barcode） | `C719476` |
| `readerCode` | 讀者帳號（patron barcode） | `d10055001` |
| `bookdate` | 預約日期 | `2026-02-24 08:48:08.500` |
| `validdate` | 預約到期日 | `2027-02-24 23:59:59.000` |
| `pickupKeepSiteId` | 取書館別 ID | `1`, `4`, `24` |
| `note` | 備註 | `通閱預約` |
| `toReserveType` | 預約類型 | `81`（一般）, `83`（通閱） |
| `bookorder` | 排隊順序 | `0`, `1`, `2` |

檔案位置：`source_data/requests/thu_requests-8.csv`

### HyLib 預約類型對應

| toReserveType | HyLib 意義 | FOLIO request_type |
|---------------|-----------|-------------------|
| 81 | 一般預約 | Hold |
| 83 | 通閱預約（跨館） | Hold |

> **注意：** RequestsMigrator 會自動將 item 狀態為 "Available" 的預約從 Hold 改為 Page。

---

## 四、Service Point 對應

RequestsMigrator 需要 `pickup_servicepoint_id`（FOLIO UUID），用來指定取書服務點。

### keepsite_service_points.tsv

與 Loans 遷移共用同一份對應檔：

```tsv
keepsite_id	service_point_id
1	3a40852d-49fd-4df2-a1f9-6e2641a6e91f
4	（需補上 UUID）
5	0e42b962-8278-4bd2-998a-12b2992f47cb
24	ba40d992-1bc6-4346-bbbd-f2074d45cb9d
```

**如何取得 service point UUID：**
- Web Portal → Lookup UUID → `/service-points`
- 或 FOLIO API: `GET /service-points?query=name=="..."`

> **重要：** Requests 資料中出現了 `pickupKeepSiteId=4`，目前不在 mapping 中，需要補上。

檔案位置：`config/thu/mapping_files/keepsite_service_points.tsv`

---

## 五、轉換工具：convert_thu_requests.py

位置：`tools/convert_thu_requests.py`

### 用法（Linux server）

```bash
cd /folio/folio_migration_web
python tools/convert_thu_requests.py \
    clients/thu/iterations/thu_migration/source_data/requests/thu_requests-8.csv \
    clients/thu/iterations/thu_migration/source_data/requests/requests.tsv \
    config/thu/mapping_files/keepsite_service_points.tsv
```

### 轉換邏輯

1. 讀取 HyLib CSV，擷取必要欄位
2. 日期格式轉換：`2026-02-24 08:48:08.500` → `2026-02-24T08:48:08.500000+08:00`
3. 透過 `keepsite_service_points.tsv` 將 `pickupKeepSiteId` → `pickup_servicepoint_id`
4. 將 `toReserveType` 對應到 FOLIO request type（81/83 → Hold）
5. 依 `request_date` 排序（保持排隊順序）
6. 輸出 requests.tsv

如有未對應的 `pickupKeepSiteId`，會顯示警告：
```
WARNING: unmapped pickupKeepSiteId values: ['4']
  -> Add these to keepsite_service_points.tsv before running migration
```

---

## 六、requests.tsv 格式

RequestsMigrator 要求的 TSV 欄位：

| 欄位 | 必填 | 說明 | 範例 |
|------|------|------|------|
| `item_barcode` | 是 | 單件條碼 | `C719476` |
| `patron_barcode` | 是 | 讀者帳號 | `d10055001` |
| `pickup_servicepoint_id` | 是 | 取書服務點 UUID | `ba40d992-1bc6-...` |
| `request_date` | 是 | 預約日期（ISO 8601） | `2026-02-24T08:48:08.500000+08:00` |
| `request_expiration_date` | 是 | 到期日（ISO 8601） | `2027-02-24T23:59:59.000000+08:00` |
| `comment` | 否 | 備註 | `通閱預約 (migrated from HyLib)` |
| `request_type` | 是 | Hold / Recall / Page | `Hold` |

範例：
```tsv
item_barcode	patron_barcode	pickup_servicepoint_id	request_date	request_expiration_date	comment	request_type
C719476	d10055001	ba40d992-1bc6-4346-bbbd-f2074d45cb9d	2026-02-24T08:48:08.500000+08:00	2027-02-24T23:59:59.000000+08:00	通閱預約 (migrated from HyLib)	Hold
```

檔案位置：`source_data/requests/requests.tsv`（在 iteration 目錄下）

---

## 七、migration_config.json 設定

在 `migration_config.json` 的 `tasks` 陣列中加入 RequestsMigrator task：

```json
{
    "name": "migrate_requests",
    "migrationTaskType": "RequestsMigrator",
    "openRequestsFile": {
        "file_name": "requests.tsv"
    },
    "item_files": [
        {
            "file_name": "folio_items_transform_items.json"
        }
    ],
    "patron_files": [
        {
            "file_name": "folio_users_transform_users.json"
        }
    ]
}
```

### 參數說明

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `name` | string | 是 | 任務名稱 |
| `migrationTaskType` | string | 是 | 固定為 `"RequestsMigrator"` |
| `openRequestsFile` | object | 是 | 預約資料檔案 |
| `openRequestsFile.file_name` | string | 是 | TSV 檔案名稱 |
| `item_files` | array | 否 | 已轉換的 items JSON（用於 barcode 驗證） |
| `patron_files` | array | 否 | 已轉換的 users JSON（用於 barcode 驗證） |

> `item_files` 和 `patron_files` 是可選的，提供時 RequestsMigrator 會先驗證 barcode 是否存在於已轉換的資料中，不提供時則直接查詢 FOLIO API。

---

## 八、執行 RequestsMigrator

### 透過 Web Portal

1. 進入 Project → THU → Migrations
2. 選擇 iteration（如 `thu_migration`）
3. 選擇 Task: `migrate_requests`
4. 點擊 Execute

### 執行過程

RequestsMigrator 會：
1. 讀取 requests.tsv，驗證每行資料
2. 對每筆 request：
   - 透過 barcode 查詢 patron UUID
   - 透過 barcode 查詢 item UUID、holdings UUID、instance UUID
   - 如果 item 狀態為 "Available"，自動將 request type 改為 Page
3. 呼叫 `POST /circulation/requests` 建立預約
4. 包含 `requestProcessingParameters` 以覆寫限制（如 item 不可借閱、讀者被凍結等）

### 執行結果

成功的 request 會在 FOLIO 建立為 Open 狀態的預約。

常見失敗原因：
- `item barcode not found` — item 不存在於 FOLIO
- `patron barcode not found` — 讀者不存在於 FOLIO
- Item 已有相同讀者的 request（重複預約）

---

## 九、驗證

### 1. 確認 request 已建立

```bash
curl -s "${FOLIO_URL}/circulation/requests?query=status==Open*&limit=0" \
  -H "x-okapi-tenant: ${FOLIO_TENANT}" \
  -H "x-okapi-token: ${FOLIO_TOKEN}" | jq '.totalRecords'
```

### 2. 查詢特定 item 的預約

```bash
curl -s "${FOLIO_URL}/circulation/requests?query=item.barcode==C719476" \
  -H "x-okapi-tenant: ${FOLIO_TENANT}" \
  -H "x-okapi-token: ${FOLIO_TOKEN}" | jq '.requests[] | {requestType, status, requestDate}'
```

### 3. FOLIO UI 確認

FOLIO UI → Requests，應可看到遷移的預約記錄。

---

## 十、Batch Deletion（取消預約）

如果需要刪除已匯入的 requests，可透過 Web Portal 的 Batch Deletion 功能。

### 刪除流程

```
1. 讀取 requests.tsv，取得 item_barcode + patron_barcode
2. 對每筆記錄：
   a. 查詢 /circulation/requests 找出該 item 的 open requests
   b. 比對 patron_barcode 確認是同一筆預約
   c. DELETE /circulation/requests/{requestId}
3. 刪除成功後，request 從 FOLIO 移除
```

### 使用方式

1. Web Portal → Batch Deletion
2. 選擇 RequestsMigrator 的 execution
3. 點擊 Start Deletion
4. 結果：Deleted = 刪除成功, Not Found = FOLIO 中無對應預約

---

## 十一、常見問題與解決

### Q1: pickupKeepSiteId 未對應

**原因：** `pickupKeepSiteId` 在 `keepsite_service_points.tsv` 中沒有對應。

**解決：**
1. 找出未對應的 keepsite_id（轉換工具會顯示 WARNING）
2. 在 FOLIO 查詢對應的 service point UUID
3. 更新 `keepsite_service_points.tsv`
4. 重新執行轉換

### Q2: Request type 自動變為 Page

**說明：** RequestsMigrator 會檢查 item 狀態，如果 item 是 "Available"（未被借出），會自動將 Hold 改為 Page。這是 FOLIO 的正常邏輯——只有被借出的 item 才能 Hold，可用的 item 應該 Page（直接調書）。

### Q3: 同一 item 有多筆預約

**說明：** HyLib 的 `bookorder` 欄位表示排隊順序。轉換工具已依 `request_date` 排序，RequestsMigrator 會按順序建立預約，FOLIO 會自動管理排隊。

### Q4: Item 不存在導致 request 失敗

**原因：** 該 item barcode 未匯入 FOLIO。

**解決：** 確認 items 轉檔是否完整。

### Q5: Patron 不存在導致 request 失敗

**原因：** 該讀者帳號未匯入 FOLIO。

**解決：** 確認 users 轉檔是否完整。注意 patron_barcode 要對應 FOLIO user 的 barcode 欄位。

---

## 附錄：目錄結構

```
clients/thu/iterations/thu_migration/
├── mapping_files/
│   └── migration_config.json      # 含 RequestsMigrator task 設定
├── source_data/
│   └── requests/
│       ├── thu_requests-8.csv     # HyLib 匯出的預約資料
│       └── requests.tsv           # 轉換後供 RequestsMigrator 使用
└── results/
    └── ...                        # 執行結果

config/thu/mapping_files/
└── keepsite_service_points.tsv    # pickupKeepSiteId → service_point_id 對應
```

---

*本文件最後更新：2026-03-04*
