# folio_migration_tools Bug: RequestsMigrator fulfilmentPreference 拼字錯誤

## 環境資訊

| 項目 | 值 |
|------|-----|
| folio_migration_tools 版本 | 1.10.2 |
| FOLIO 平台 | EBSCO-hosted (api-thu.folio.ebsco.com) |
| Tenant ID | fs00001280 |
| 發現日期 | 2026-03-04 |

---

## 問題描述

RequestsMigrator 建立預約時，所有 request 都失敗，錯誤訊息：

```
Fulfillment preference must be one of the following: Hold Shelf, Delivery
```

即使 request JSON 中已包含 `"fulfilmentPreference": "Hold Shelf"`，FOLIO API 仍然拒絕。

---

## 根本原因

folio_migration_tools 的 `LegacyRequest.to_dict()` 使用**英式拼法** `fulfilmentPreference`（單 l），但較新版本的 FOLIO mod-circulation API 期望**美式拼法** `fulfillmentPreference`（雙 l）。

FOLIO API 不認得英式拼法的欄位名，導致收到 `null` 值：

```json
{
    "errors": [
        {
            "message": "Fulfillment preference must be one of the following: Hold Shelf, Delivery",
            "parameters": [
                {
                    "key": "fulfillmentPreference",
                    "value": null
                }
            ],
            "code": "FULFILLMENT_PREFERENCE_IS_NOT_ALLOWED"
        }
    ]
}
```

### 問題程式碼

檔案：`folio_migration_tools/transaction_migration/legacy_request.py`

```python
# 第 89-105 行 to_dict() 方法
def to_dict(self):
    return {
        "requestLevel": "Item",
        "requestType": self.request_type,
        "fulfilmentPreference": self.fulfillment_preference,  # ← Bug: 英式拼法
        ...
    }

# 第 107-127 行 serialize() 方法
def serialize(self):
    req = self.to_dict()
    required = [
        ...
        "fulfilmentPreference",  # ← Bug: 英式拼法
        ...
    ]
```

### 驗證

使用 curl 直接呼叫 FOLIO API 測試：

```bash
# 英式拼法 → 失敗（value: null）
curl -X POST "${FOLIO_URL}/circulation/requests" \
  -d '{"fulfilmentPreference": "Hold Shelf", ...}'
# 結果: FULFILLMENT_PREFERENCE_IS_NOT_ALLOWED

# 美式拼法 → 成功
curl -X POST "${FOLIO_URL}/circulation/requests" \
  -d '{"fulfillmentPreference": "Hold Shelf", ...}'
# 結果: 200 OK, request 建立成功
```

---

## 修補方式

修改 folio_migration_tools 安裝目錄中的 `legacy_request.py`，將英式拼法改為美式拼法：

```bash
SITE_PKG=/folio/folio_migration_web/clients/thu/.venv/lib/python3.13/site-packages/folio_migration_tools

# 修補
sed -i 's/"fulfilmentPreference"/"fulfillmentPreference"/g' \
  "$SITE_PKG/transaction_migration/legacy_request.py"

# 清除 bytecode cache
rm -f "$SITE_PKG/transaction_migration/__pycache__/legacy_request*.pyc"
```

修補後 `grep` 確認：

```bash
grep "fillmentPreference" "$SITE_PKG/transaction_migration/legacy_request.py"
# 應顯示:
#   "fulfillmentPreference": self.fulfillment_preference,
#   "fulfillmentPreference",
```

---

## 影響範圍

- **僅影響 RequestsMigrator**（其他 Migrator 不使用此欄位）
- 所有 request 都會失敗（Hold、Page、Recall 全部受影響）
- 不影響資料完整性（request 未建立，無需清理）

---

## 建議

1. 向 folio_migration_tools 上游提交 PR 修正此拼字問題
   - GitHub: https://github.com/FOLIO-FSE/folio_migration_tools
   - 修改檔案：`src/folio_migration_tools/transaction_migration/legacy_request.py`
   - 將 `fulfilmentPreference` → `fulfillmentPreference`（兩處）
2. 升級 folio_migration_tools 後需確認是否已包含此修正
3. 在本地修補後，每次重新安裝 folio_migration_tools 都需要重新套用修補

---

## 相關資源

- FOLIO mod-circulation API: `/circulation/requests`
- FOLIO Request schema: `fulfillmentPreference` 欄位
- folio_migration_tools source: `transaction_migration/legacy_request.py`

---

*記錄日期：2026-03-04*
