# Fee/Fines (罰則) 遷移指南

本指南說明如何將 HyLib 系統的逾期罰金遷移到 FOLIO 平台。

## 前置條件

1. **使用者已遷移** — 罰金需要對應到 FOLIO 中的使用者（patron_barcode）
2. **館藏已遷移** — 罰金需要對應到 FOLIO 中的館藏項目（item_barcode）
3. **FOLIO Fee/Fine 設定已完成**（見下方「FOLIO 前置設定」）
4. **Web Portal 已部署並設定好 FOLIO 連線憑證**

## 遷移流程概覽

```
HyLib CSV → convert_thu_feefines.py → feefines.tsv
         → ManualFeeFinesTransformer → extradata 檔案
         → BatchPoster (Extradata) → POST 到 FOLIO
```

| 步驟 | 工具 | 說明 |
|------|------|------|
| 1. 轉換 | `convert_thu_feefines.py` | HyLib CSV 轉為 FOLIO TSV 格式 |
| 2. Transform | ManualFeeFinesTransformer | TSV 轉為 FOLIO extradata 格式 |
| 3. Post | BatchPoster (Extradata) | 將 extradata 寫入 FOLIO |

## FOLIO 前置設定（手動）

在 FOLIO Settings → Users → Fee/Fine 中：

1. **建立 Owner**：`Tunghai University`
   - 確認 Owner 有關聯到至少一個 Service Point
2. **建立 Fee/Fine Type**：在 `Tunghai University` 下建立 `Overdue fine`
   - Settings → Users → Fee/Fine → Manual charges → 選擇 Owner → 新增

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

# 將 HyLib CSV 轉為 FOLIO TSV
python tools/convert_thu_feefines.py \
    clients/thu/iterations/thu_migration/source_data/fees_fines/thu_feefines-15.csv \
    clients/thu/iterations/thu_migration/source_data/fees_fines/feefines.tsv
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

## 步驟三：設定 migration_config.json

在 `mapping_files/migration_config.json` 中加入兩個 task：

```json
{
  "migrationTasks": [
    {
      "name": "transform_feefines",
      "migrationTaskType": "ManualFeeFinesTransformer",
      "feeFinesFile": "source_data/fees_fines/feefines.tsv",
      "feeFinesMapping": "mapping_files/manual_feefines_map.json",
      "feeFineOwnerMappingFileName": "mapping_files/feefine_owners.tsv",
      "feeFineTypeMappingFileName": "mapping_files/feefine_types.tsv"
    },
    {
      "name": "post_feefines",
      "migrationTaskType": "BatchPoster",
      "objectType": "Extradata",
      "batchSize": 10,
      "files": []
    }
  ]
}
```

> **注意**：BatchPoster 的 `files` 會自動找到 ManualFeeFinesTransformer 產生的 extradata 檔案。

## 步驟四：透過 Web Portal 執行

1. 開啟 Web Portal → 選擇 THU client
2. 到 **Executions** 頁面
3. 先執行 `transform_feefines`（ManualFeeFinesTransformer）
4. 等待完成後，執行 `post_feefines`（BatchPoster）
5. 觀察進度和記錄數

## 步驟五：驗證

### 方法一：FOLIO API 確認

```bash
# 查詢 Tunghai University 的 fee/fine 總數
curl -s "${FOLIO_URL}/accounts?query=feeFineOwner==Tunghai*&limit=0" \
  -H "x-okapi-tenant: ${FOLIO_TENANT}" \
  -H "x-okapi-token: ${FOLIO_TOKEN}" | jq '.totalRecords'

# 查詢特定使用者的 fee/fine
curl -s "${FOLIO_URL}/accounts?query=userId==${USER_UUID}&limit=100" \
  -H "x-okapi-tenant: ${FOLIO_TENANT}" \
  -H "x-okapi-token: ${FOLIO_TOKEN}" | jq '.accounts[] | {amount, remaining, status}'
```

### 方法二：Web Portal Data Validation

1. 到 **Data Validation** 頁面
2. 選擇 `transform_feefines` 或 `post_feefines` 的執行記錄
3. 點擊 **Validate** 執行驗證
4. 檢查結果：found / not_found / mismatch

驗證會比較以下欄位：
- `amount` — 罰金金額
- `remaining` — 未繳餘額
- `status.name` — 帳戶狀態（Open/Closed）

## 批次刪除（回滾）

如需刪除已遷移的 fee/fine 記錄：

1. 到 **Batch Deletion** 頁面
2. 選擇 `transform_feefines` 或 `post_feefines` 的執行記錄
3. 點擊 **Preview** 確認刪除範圍
4. 點擊 **Start Deletion** 開始刪除
5. 每筆記錄透過 `DELETE /accounts/{id}` API 刪除

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
