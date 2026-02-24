# FOLIO Loans 轉檔匯入完整指南

> 本文件說明如何使用 folio_migration_tools 的 LoansMigrator 將未歸還借閱記錄遷移到 FOLIO。

---

## 目錄

1. [前置條件](#一前置條件)
2. [整體流程概覽](#二整體流程概覽)
3. [來源資料格式](#三來源資料格式)
4. [Service Point 對應](#四service-point-對應)
5. [轉換工具：convert_thu_loans.py](#五轉換工具convert_thu_loanspy)
6. [loans.tsv 格式](#六loanstsv-格式)
7. [migration_config.json 設定](#七migration_configjson-設定)
8. [執行 LoansMigrator](#八執行-loansmigrator)
9. [驗證](#九驗證)
10. [Batch Deletion（還書）](#十batch-deletion還書)
11. [常見問題與解決](#十一常見問題與解決)

---

## 一、前置條件

Loans 遷移必須在以下資料匯入完成後才能執行：

```
Instances (書目) ─→ Holdings (館藏) ─→ Items (項目) ─→ Users (讀者) ─→ Loans (借閱)
```

- **Items** 必須已存在於 FOLIO，因為 loan 透過 item barcode 關聯
- **Users** 必須已存在於 FOLIO，因為 loan 透過 patron barcode 關聯
- **Service Points** 必須已設定，loan 需指定借出服務點

---

## 二、整體流程概覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Loans Migration Flow                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 來源資料 (CSV)                                                  │
│     └── thu_loan.csv (HyWeb 系統匯出的借閱中資料)                    │
│                                                                     │
│  2. 轉換                                                            │
│     └── convert_thu_loans.py                                        │
│         ├── Input:  thu_loan.csv + keepsite_service_points.tsv      │
│         └── Output: loans.tsv                                       │
│                                                                     │
│  3. 匯入                                                            │
│     └── LoansMigrator (via Web Portal)                              │
│         ├── 讀取 loans.tsv                                          │
│         ├── 驗證 item barcode / patron barcode 存在                 │
│         └── POST /circulation/check-out-by-barcode                  │
│                                                                     │
│  4. 刪除（還書）                                                     │
│     └── Batch Deletion (via Web Portal)                             │
│         ├── 先查詢是否有 open loan                                   │
│         └── POST /circulation/check-in-by-barcode                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、來源資料格式

THU 的來源資料是 HyWeb 系統匯出的 CSV，主要欄位：

| CSV 欄位 | 說明 | 範例 |
|----------|------|------|
| `barcode` | 單件條碼（item barcode） | `C723018` |
| `readerCode` | 讀者帳號（patron barcode） | `c400030044` |
| `lenddate` | 借出日期 | `2026-01-16 16:18:18.287` |
| `returndate` | 應還日期 | `2026-03-11 23:59:59.000` |
| `continueNum` | 續借次數 | `0` |
| `lendKeepSiteId` | 借出館別 ID | `1`, `5`, `24` |

檔案位置：`source_data/loans/thu_loan.csv`

---

## 四、Service Point 對應

LoansMigrator 需要 `service_point_id`（FOLIO UUID），用來記錄在哪個服務點借出。

### keepsite_service_points.tsv

將 HyWeb 的 `lendKeepSiteId` 對應到 FOLIO service point UUID：

```tsv
keepsite_id	service_point_id
1	3a40852d-49fd-4df2-a1f9-6e2641a6e91f
5	0e42b962-8278-4bd2-998a-12b2992f47cb
24	ba40d992-1bc6-4346-bbbd-f2074d45cb9d
```

**如何取得 service point UUID：**
- Web Portal → Lookup UUID → `/service-points`
- 或 FOLIO API: `GET /service-points?query=name=="Main circulation desk"`

檔案位置：`config/thu/mapping_files/keepsite_service_points.tsv`

---

## 五、轉換工具：convert_thu_loans.py

位置：`tools/convert_thu_loans.py`

### 用法（Linux server）

```bash
cd /folio/folio_migration_web
python tools/convert_thu_loans.py \
    clients/thu/iterations/thu_migration/source_data/loans/thu_loan.csv \
    clients/thu/iterations/thu_migration/source_data/loans/loans.tsv \
    config/thu/mapping_files/keepsite_service_points.tsv
```

### 轉換邏輯

1. 讀取 CSV，擷取必要欄位
2. 日期格式轉換：`2026-01-16 16:18:18.287` → `2026-01-16T16:18:18.287000+08:00`
3. 透過 `keepsite_service_points.tsv` 將 `lendKeepSiteId` → `service_point_id`
4. 輸出 loans.tsv

如有未對應的 `lendKeepSiteId`，會顯示警告：
```
WARNING: unmapped lendKeepSiteId values: ['99']
```

---

## 六、loans.tsv 格式

LoansMigrator 要求的 TSV 欄位：

| 欄位 | 必填 | 說明 | 範例 |
|------|------|------|------|
| `item_barcode` | 是 | 單件條碼 | `C723018` |
| `patron_barcode` | 是 | 讀者帳號 | `c400030044` |
| `due_date` | 是 | 應還日期（ISO 8601） | `2026-03-11T23:59:59.000000+08:00` |
| `out_date` | 是 | 借出日期（ISO 8601） | `2026-01-16T16:18:18.287000+08:00` |
| `renewal_count` | 否 | 續借次數 | `0` |
| `next_item_status` | 否 | 借出後 item 狀態（通常留空） | |
| `service_point_id` | 否 | 服務點 UUID | `3a40852d-49fd-...` |

範例：
```tsv
item_barcode	patron_barcode	due_date	out_date	renewal_count	next_item_status	service_point_id
C723018	c400030044	2026-03-11T23:59:59.000000+08:00	2026-01-16T16:18:18.287000+08:00	0		3a40852d-49fd-4df2-a1f9-6e2641a6e91f
```

檔案位置：`source_data/loans/loans.tsv`（在 iteration 目錄下）

---

## 七、migration_config.json 設定

在 `migration_config.json` 的 `tasks` 陣列中加入 LoansMigrator task：

```json
{
    "name": "migrate_loans",
    "migrationTaskType": "LoansMigrator",
    "openLoansFiles": [
        {
            "file_name": "loans.tsv",
            "service_point_id": "3a40852d-49fd-4df2-a1f9-6e2641a6e91f"
        }
    ],
    "fallbackServicePointId": "3a40852d-49fd-4df2-a1f9-6e2641a6e91f"
}
```

### 參數說明

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `name` | string | 是 | 任務名稱 |
| `migrationTaskType` | string | 是 | 固定為 `"LoansMigrator"` |
| `openLoansFiles` | array | 是 | loans 檔案列表 |
| `openLoansFiles[].file_name` | string | 是 | TSV 檔案名稱 |
| `openLoansFiles[].service_point_id` | string | 否 | 該檔案的預設 service point UUID |
| `fallbackServicePointId` | string (UUID) | 是 | 備用服務點（當 TSV 中未指定時使用） |

**注意：** `service_point_id` 優先級：TSV 每行的 `service_point_id` > `openLoansFiles[].service_point_id` > `fallbackServicePointId`

---

## 八、執行 LoansMigrator

### 透過 Web Portal

1. 進入 Project → THU → Migrations
2. 選擇 iteration（如 `thu_migration`）
3. 選擇 Task: `migrate_loans`
4. 點擊 Execute

### 執行過程

LoansMigrator 會：
1. 讀取 loans.tsv，驗證每行資料
2. 對每筆 loan 呼叫 `POST /circulation/check-out-by-barcode`
3. 成功：item status 變為 "Checked out"，產生 loan 記錄
4. 失敗原因可能：item 不存在、patron 不存在、item 已被借出

### 執行結果

```
Loaded and validated 27 loans in total
...
27 records processed. 8 posted, 19 failed.
```

常見失敗原因：
- `Could not find an existing Item with Barcode` — item 不存在於 FOLIO
- `Cannot check out item that already has an open loan` — item 已有 open loan

---

## 九、驗證

### 1. 確認 loan 已建立

```bash
# 查詢 open loans
curl -s "${FOLIO_URL}/circulation/loans?query=status.name==Open&limit=100" \
  -H "x-okapi-tenant: ${TENANT}" \
  -H "x-okapi-token: ${TOKEN}" | jq '.totalRecords'
```

### 2. 確認 item status

借出成功的 item 應該變為 "Checked out"：

```bash
curl -s "${FOLIO_URL}/item-storage/items?query=barcode==C723018" \
  -H "x-okapi-tenant: ${TENANT}" \
  -H "x-okapi-token: ${TOKEN}" | jq '.items[0].status.name'
# "Checked out"
```

### 3. 流通日誌

FOLIO UI → Circulation log，應可看到「透過越權借出」(Override) 記錄。

---

## 十、Batch Deletion（還書）

如果需要刪除（撤銷）已匯入的 loans，Web Portal 的 Batch Deletion 使用 FOLIO check-in API 進行還書，而非直接刪除 loan storage 記錄。

### 還書流程

```
1. 讀取 loans.tsv，取得 item_barcode + service_point_id
2. 對每筆記錄：
   a. 查詢 /circulation/loans 確認是否有 open loan
   b. 沒有 open loan → skip（不產生流通紀錄）
   c. 有 open loan → POST /circulation/check-in-by-barcode
3. Check-in 成功後：
   - Loan status → Closed
   - Item status → Available（或 In transit，視 service point 而定）
   - 產生流通日誌（已關閉借閱 + 已歸還）
```

### 使用方式

1. Web Portal → Batch Deletion
2. 選擇 LoansMigrator 的 execution
3. 點擊 Start Deletion
4. 結果：Deleted = 還書成功, Skipped = 沒有 open loan

### service_point_id 來源

還書時需要 service_point_id，取得優先級：
1. loans.tsv 每行的 `service_point_id` 欄位
2. migration_config.json 中 LoansMigrator task 的 `fallbackServicePointId`

### 為什麼用 check-in 而不是 DELETE

| 方式 | Loan Status | Item Status | 流通日誌 |
|------|------------|-------------|---------|
| `DELETE /loan-storage/loans/{id}` | 直接刪除 | 仍為 Checked out | 無 |
| `POST /circulation/check-in-by-barcode` | Closed | Available | 有（已關閉借閱 + 已歸還） |

直接 DELETE 會導致 item 永遠停在 "Checked out" 狀態，必須手動修正。

---

## 十一、常見問題與解決

### Q1: loans.tsv 中的 service_point_id 為空

**原因：** `lendKeepSiteId` 在 `keepsite_service_points.tsv` 中沒有對應。

**解決：**
1. 找出未對應的 keepsite_id（轉換工具會顯示 WARNING）
2. 在 FOLIO 查詢或建立對應的 service point
3. 更新 `keepsite_service_points.tsv`
4. 重新執行轉換

如無法對應，LoansMigrator 會使用 `fallbackServicePointId`。

### Q2: Item 不存在導致 loan 失敗

**原因：** 該 item barcode 未匯入 FOLIO（可能來源資料中缺少該筆 item）。

**解決：** 確認 items 轉檔是否完整，或從來源系統補匯缺少的 items。

### Q3: Patron 不存在導致 loan 失敗

**原因：** 該讀者帳號未匯入 FOLIO。

**解決：** 確認 users 轉檔是否完整。注意 patron_barcode 要對應 FOLIO user 的 barcode 欄位。

### Q4: 還書後 item status 顯示 "In transit" 而非 "Available"

**原因：** 還書的 service point 與 item 的 effective location 所屬 service point 不同。

**說明：** 這是 FOLIO 正常的流通邏輯，表示 item 需要從還書點運送到所屬館別。可在 FOLIO UI 手動確認收到（Receive）來清除 In transit 狀態。

### Q5: 還書產生兩筆流通日誌

**說明：** 這是正常行為。每次 check-in 都會產生：
1. **已關閉借閱**（Closed loan）— 記錄 loan 結束
2. **已歸還**（Checked in）— 記錄 item 歸還動作

---

## 附錄：目錄結構

```
clients/thu/iterations/thu_migration/
├── mapping_files/
│   └── migration_config.json      # 含 LoansMigrator task 設定
├── source_data/
│   └── loans/
│       ├── thu_loan.csv           # HyWeb 匯出的借閱中資料
│       └── loans.tsv              # 轉換後供 LoansMigrator 使用
└── results/
    └── ...                        # 執行結果

config/thu/mapping_files/
└── keepsite_service_points.tsv    # lendKeepSiteId → service_point_id 對應
```

---

*本文件最後更新：2026-02-24*
