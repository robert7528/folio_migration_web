# Fee/Fines (罰則) 遷移指南

本指南說明如何將 HyLib 系統的逾期罰金遷移到 FOLIO 平台。

## 前置條件

1. **使用者已遷移** — 罰金需要對應到 FOLIO 中的使用者（patron_barcode）
2. **館藏已遷移** — 罰金需要對應到 FOLIO 中的館藏項目（item_barcode）
3. **FOLIO Fee/Fine 設定已完成**（見下方「FOLIO 前置設定」）
4. **Web Portal 已部署並設定好 FOLIO 連線憑證**

## 遷移流程概覽

```
HyLib CSV → convert_hylib_feefines.py → feefines.tsv
         → ManualFeeFinesTransformer → extradata 檔案
         → BatchPoster (Extradata) → POST 到 FOLIO
```

| 步驟 | 工具 | 說明 |
|------|------|------|
| 1. 轉換 | `convert_hylib_feefines.py` | HyLib CSV 轉為 FOLIO TSV 格式 |
| 2. Transform | ManualFeeFinesTransformer | TSV 轉為 FOLIO extradata 格式 |
| 3. Post | BatchPoster (Extradata) | 將 extradata 寫入 FOLIO |

## FOLIO 前置設定

在 FOLIO Settings → Fee/Fine 中：

1. **建立 Owner**：`Tunghai University`
   - FOLIO UI 可能會出現 "儲存資料時發生錯誤"（ownerId UUID bug），改用 API 建立：
     ```bash
     curl -s -X POST "${FOLIO_URL}/owners" \
       -H "Content-Type: application/json" \
       -H "X-Okapi-Tenant: ${FOLIO_TENANT}" \
       -H "X-Okapi-Token: ${FOLIO_TOKEN}" \
       -d '{"id": "'$(uuidgen)'", "owner": "Tunghai University", "desc": "東海大學圖書館"}'
     ```
   - 建好後到 FOLIO UI 將所有服務點關聯到此 Owner
2. **建立 Fee/Fine Type**：`Overdue fine`
   - 同樣可用 API：
     ```bash
     curl -s -X POST "${FOLIO_URL}/feefines" \
       -H "Content-Type: application/json" \
       -H "X-Okapi-Tenant: ${FOLIO_TENANT}" \
       -H "X-Okapi-Token: ${FOLIO_TOKEN}" \
       -d '{"id": "'$(uuidgen)'", "feeFineType": "Overdue fine", "ownerId": "<OWNER_UUID>", "automatic": false}'
     ```

> **重要**：Owner 名稱和 Fee/Fine Type 名稱必須與 mapping 檔案中的完全一致。

## 來源資料格式

HyLib 匯出的 CSV 檔案（例如 `thu_feefines-15.csv`）：

| 欄位 | 說明 | 範例 |
|------|------|------|
| `reader_code` | 讀者條碼 | `T9901234` |
| `barcode` | 館藏條碼 | `0012345` |
| `total` | 罰金總額 | `100` |
| `contribute` | 已繳金額 | `0` |
| `insert_date` | 建立日期 | `2024-03-15 10:30:00.000` |
| `name` | 罰金類型名稱 | `逾期罰金(借,預)` |
| `fineTypeId` | 罰金類型代碼 | `2` |
| `status` | 繳費狀態 | `0`（未繳）/ `1`（已繳） |

**注意**：轉換工具只處理 `status == 0`（未繳）的記錄。

## 步驟一：轉換來源資料

在 Linux 伺服器上執行：

```bash
cd /folio/folio_migration_web

# 將 HyLib CSV 轉為 FOLIO TSV（第三個參數為 client_code，對應 feefine_owners.tsv 的 lending_library）
python tools/convert_hylib_feefines.py \
    clients/<client>/iterations/<iteration>/source_data/fees_fines/<input>.csv \
    clients/<client>/iterations/<iteration>/source_data/fees_fines/feefines.tsv \
    <client_code>

# 範例（THU）：
python tools/convert_hylib_feefines.py \
    clients/thu/iterations/thu_migration/source_data/fees_fines/thu_feefines-15.csv \
    clients/thu/iterations/thu_migration/source_data/fees_fines/feefines.tsv \
    thu
```

輸出範例：
```
Converted 15 unpaid fee/fines to .../feefines.tsv
Skipped 0 paid/closed records (status != 0)
```

### 輸出 TSV 格式

| 欄位 | 來源 | 說明 |
|------|------|------|
| `amount` | `total` | 罰金總額 |
| `remaining` | `total - contribute` | 未繳餘額 |
| `patron_barcode` | `reader_code` | 讀者條碼 |
| `item_barcode` | `barcode` | 館藏條碼 |
| `billed_date` | `insert_date` | ISO 8601 格式 +08:00 |
| `type` | `name` | 罰金類型名稱（用於 mapping） |
| `lending_library` | 固定 `thu` | 對應到 Fee/Fine Owner |
| `borrowing_desk` | 留空 | 無對應來源 |

## 步驟二：設定 Mapping 檔案

Mapping 檔案位於 `config/thu/mapping_files/`：

### manual_feefines_map.json

定義 TSV 欄位到 FOLIO 欄位的對應關係。已預設好，通常不需修改。

### feefine_owners.tsv

```
lending_library	folio_owner
thu	Tunghai University
*	Tunghai University
```

將 `lending_library` 欄位對應到 FOLIO 的 Fee/Fine Owner。

### feefine_types.tsv

```
type	folio_feeFineType
逾期罰金	Overdue fine
*	Overdue fine
```

將罰金類型名稱對應到 FOLIO 的 Fee/Fine Type。

### feefine_service_points.tsv（必要）

```
borrowing_desk	folio_name
*	Main circulation desk
```

Service point mapping，`ManualFeeFinesTransformer` 必須要有 `servicePointMap` 欄位。
欄位名稱必須用 `folio_name`（不是 `folio_servicePointId`）。

## 步驟三：設定 migration_config.json

在 `mapping_files/migration_config.json` 中加入兩個 task：

```json
{
  "migrationTasks": [
    {
      "name": "transform_feefines",
      "migrationTaskType": "ManualFeeFinesTransformer",
      "feefinesMap": "manual_feefines_map.json",
      "feefinesOwnerMap": "feefine_owners.tsv",
      "feefinesTypeMap": "feefine_types.tsv",
      "servicePointMap": "feefine_service_points.tsv",
      "files": [{"file_name": "feefines.tsv"}]
    },
    {
      "name": "post_feefines",
      "migrationTaskType": "BatchPoster",
      "objectType": "Extradata",
      "batchSize": 1,
      "files": [{"file_name": "extradata_transform_feefines.extradata"}]
    }
  ]
}
```

> **注意**：
> - `servicePointMap` 是必要欄位，否則 transform 會報錯 "Field required servicePointMap"
> - `feefinesMap` 等欄位名用駝峰式（camelCase），不是 snake_case
> - BatchPoster 的 `batchSize` 建議設為 1（每筆 fee/fine 產生 account + feefineaction 兩條記錄）
> - 來源檔案放在 `source_data/fees_fines/`（注意是 `fees_fines` 不是 `feefines`，這是 folio_migration_tools 內定的目錄名）

## 步驟四：透過 Web Portal 執行

1. 開啟 Web Portal → 選擇 THU client
2. 到 **Executions** 頁面
3. 先執行 `transform_feefines`（ManualFeeFinesTransformer）
4. 等待完成後，執行 `post_feefines`（BatchPoster）
5. 觀察進度和記錄數

## 步驟五：驗證

### 方法一：FOLIO API 確認

```bash
# 查詢 fee/fine 總數
curl -s "${FOLIO_URL}/accounts?limit=0" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}" | python3 -c "import sys,json; print('total:', json.load(sys.stdin).get('totalRecords'))"

# 查詢前 5 筆 fee/fine 的摘要
curl -s "${FOLIO_URL}/accounts?limit=5" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(a['id'], a.get('amount'), a.get('remaining'), a.get('feeFineOwner')) for a in d.get('accounts',[])]"

# 查詢特定 account by UUID
curl -s "${FOLIO_URL}/accounts/${ACCOUNT_UUID}" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}" | python3 -m json.tool

# 查詢特定使用者的 fee/fine
curl -s "${FOLIO_URL}/accounts?query=userId==${USER_UUID}&limit=100" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(a['id'], a.get('amount'), a.get('status',{}).get('name')) for a in d.get('accounts',[])]"
```

### 方法二：Web Portal Data Validation

1. 到 **Data Validation** 頁面
2. 選擇 `transform_feefines`（ManualFeeFinesTransformer）的執行記錄
3. 點擊 **Validate** 執行驗證
4. 檢查結果：found / not_found / mismatch

> **注意**：驗證必須在 `post_feefines` 完成後再執行，因為 `transform_feefines` 每次執行會產生新的 UUID。如果 transform 後又重新 transform 而沒有重新 post，驗證會全部顯示 not_found（UUID 不匹配）。

驗證會比較以下欄位：
- `amount` — 罰金金額
- `remaining` — 未繳餘額
- `status.name` — 帳戶狀態（Open/Closed）

## 批次刪除（回滾）

### 方法一：Web Portal Batch Deletion

1. 到 **Batch Deletion** 頁面
2. 選擇 `transform_feefines`（ManualFeeFinesTransformer）的執行記錄
3. 點擊 **Preview** 確認刪除範圍
4. 點擊 **Start Deletion** 開始刪除
5. 每筆記錄透過 `DELETE /accounts/{id}` API 刪除

### 方法二：FOLIO API 手動刪除

```bash
# 刪除單一 account
curl -s -X DELETE "${FOLIO_URL}/accounts/${ACCOUNT_UUID}" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}"

# 批次刪除所有 accounts（危險！會刪除全部 fee/fine 資料）
curl -s "${FOLIO_URL}/accounts?limit=100" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(a['id']) for a in d.get('accounts',[])]" | while read id; do curl -s -X DELETE "${FOLIO_URL}/accounts/${id}" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}"; echo "Deleted: ${id}"; done

# 確認刪除結果
curl -s "${FOLIO_URL}/accounts?limit=0" -H "X-Okapi-Tenant: ${FOLIO_TENANT}" -H "X-Okapi-Token: ${FOLIO_TOKEN}" | python3 -c "import sys,json; print('remaining:', json.load(sys.stdin).get('totalRecords'))"
```

> **注意**：刪除後如需重新遷移，必須重新執行 `transform_feefines` 和 `post_feefines`。

## 常見問題

### Q: 為什麼只遷移 status=0 的記錄？

已繳清的罰金（status=1）是歷史記錄，遷移到 FOLIO 後會變成 Open 狀態，可能造成混淆。只遷移未繳的罰金確保資料正確性。

### Q: 如果 FOLIO 中找不到 patron_barcode 或 item_barcode 怎麼辦？

ManualFeeFinesTransformer 會在 log 中顯示警告，該筆記錄的 userId 或 itemId 會留空。建議先確認使用者和館藏都已遷移完成。

### Q: 如何處理非「逾期罰金」的罰金類型？

在 `feefine_types.tsv` 中新增對應行，例如：
```
遺失賠償	Lost item processing fee
```
同時在 FOLIO Settings 中建立對應的 Fee/Fine Type。

### Q: 遷移後金額不對怎麼辦？

檢查來源 CSV 中的 `total` 和 `contribute` 欄位。轉換工具計算 `remaining = total - contribute`。如果 contribute 欄位有異常值，可能需要手動修正來源資料。

### Q: BatchPoster 報錯 "Fee/Fine Owner not found"

確認 FOLIO 中的 Owner 名稱與 `feefine_owners.tsv` 中的 `folio_owner` 完全一致（包括大小寫和空格）。

### Q: Transform 報錯 "Column folio_name missing from servicepoints map file"

Service point mapping TSV 的第二欄必須叫 `folio_name`，不是 `folio_servicePointId` 或 `folio_servicepoint`。

### Q: FOLIO UI 建立 Owner 時出現 "儲存資料時發生錯誤"

這是 FOLIO 前端的 bug（ownerId 未自動產生 UUID）。改用 API 建立即可（見「FOLIO 前置設定」）。

### Q: 驗證全部顯示 not_found

確認 transform 和 post 使用的是同一份 extradata。如果重新執行了 transform，UUID 會改變，必須也重新執行 post。
