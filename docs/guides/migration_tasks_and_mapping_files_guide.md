# Migration Tasks 與 Mapping Files 完整指南

> 本文件說明 folio_migration_tools 各 migration task 所需的 mapping files 格式、migration_config.json 設定，以及檔案之間的對應關係。基於 THU（東海大學）專案的實際驗證結果。

---

## 目錄

1. [整體架構](#一整體架構)
2. [libraryInformation 設定](#二libraryinformation-設定)
3. [BibsTransformer — 書目轉檔](#三bibstransformer--書目轉檔)
4. [HoldingsCsvTransformer — 館藏轉檔](#四holdingscsvtransformer--館藏轉檔)
5. [ItemsTransformer — 單冊轉檔](#五itemstransformer--單冊轉檔)
6. [UserTransformer — 讀者轉檔](#六usertransformer--讀者轉檔)
7. [LoansMigrator — 借閱遷移](#七loansmigrator--借閱遷移)
8. [RequestsMigrator — 預約遷移](#八requestsmigrator--預約遷移)
9. [ManualFeeFinesTransformer — 罰金轉檔](#九manualfeefinestransformer--罰金轉檔)
10. [BatchPoster — 批次匯入](#十batchposter--批次匯入)
11. [執行順序](#十一執行順序)
12. [Mapping File 欄位命名規則](#十二mapping-file-欄位命名規則)
13. [完整 migration_config.json 範例](#十三完整-migration_configjson-範例)

---

## 一、整體架構

### 目錄結構

```
clients/<client>/iterations/<iteration>/
├── mapping_files/
│   ├── migration_config.json          ← 主設定檔（含 libraryInformation + migrationTasks）
│   ├── holdingsrecord_mapping.json    ← Holdings 欄位對應
│   ├── item_mapping.json              ← Items 欄位對應
│   ├── user_mapping.json              ← Users 欄位對應
│   ├── manual_feefines_map.json       ← Fee/Fines 欄位對應
│   ├── locations.tsv                  ← 館藏位置對應
│   ├── material_types.tsv             ← 資料類型對應
│   ├── loan_types.tsv                 ← 借閱類型對應
│   ├── item_statuses.tsv              ← 單冊狀態對應
│   ├── call_number_type_mapping.tsv   ← 索書號類型對應
│   ├── user_groups.tsv                ← 讀者群組對應
│   ├── feefine_owners.tsv             ← 罰金 Owner 對應
│   ├── feefine_types.tsv              ← 罰金類型對應
│   └── feefine_service_points.tsv     ← 罰金服務點對應
├── source_data/
│   ├── instances/    ← bibs.mrc
│   ├── holdings/     ← holdings.tsv
│   ├── items/        ← items.tsv（+ holdings.tsv workaround）
│   ├── users/        ← users.tsv
│   ├── loans/        ← loans.tsv
│   ├── requests/     ← requests.tsv
│   └── fees_fines/   ← feefines.tsv（注意目錄名是 fees_fines）
└── results/          ← 轉檔輸出

config/<client>/mapping_files/
└── keepsite_service_points.tsv        ← HyLib 館別 → FOLIO Service Point UUID
```

### Task 類型

| 類別 | Task Type | 用途 | 需要 Mapping Files |
|------|-----------|------|-------------------|
| Transform | BibsTransformer | MARC → Instances JSON | 無 |
| Transform | HoldingsCsvTransformer | TSV → Holdings JSON | `holdingsrecord_mapping.json`, `locations.tsv`, `call_number_type_mapping.tsv` |
| Transform | ItemsTransformer | TSV → Items JSON | `item_mapping.json`, `locations.tsv`, `material_types.tsv`, `loan_types.tsv`, `item_statuses.tsv` |
| Transform | UserTransformer | TSV → Users JSON | `user_mapping.json`, `user_groups.tsv` |
| Transform | ManualFeeFinesTransformer | TSV → Extradata | `manual_feefines_map.json`, `feefine_owners.tsv`, `feefine_types.tsv`, `feefine_service_points.tsv` |
| Migrator | LoansMigrator | TSV → 直接 POST FOLIO | 無（TSV 內含 service_point_id） |
| Migrator | RequestsMigrator | TSV → 直接 POST FOLIO | 無（需要 items/users 的 transform 輸出 JSON） |
| Poster | BatchPoster | JSON/Extradata → POST FOLIO | 無 |

---

## 二、libraryInformation 設定

`migration_config.json` 的頂層必須包含 `libraryInformation`：

```json
{
    "libraryInformation": {
        "tenantId": "fs00001280",
        "multiFieldDelimiter": "<^>",
        "okapiUrl": "https://api-thu.folio.ebsco.com",
        "okapiUsername": "HyWebFOLIO",
        "logLevelDebug": false,
        "libraryName": "Tunghai University",
        "folioRelease": "sunflower",
        "addTimeStampToFileNames": false,
        "iterationIdentifier": "thu_migration"
    },
    "migrationTasks": [...]
}
```

| 欄位 | 說明 |
|------|------|
| `tenantId` | FOLIO 租戶 ID |
| `okapiUrl` | FOLIO API gateway URL |
| `okapiUsername` | FOLIO 登入帳號 |
| `libraryName` | 圖書館名稱 |
| `folioRelease` | FOLIO 版本（如 `sunflower`） |
| `iterationIdentifier` | iteration 目錄名稱 |
| `addTimeStampToFileNames` | 建議設為 `false` |
| `multiFieldDelimiter` | 多值欄位分隔符（預設 `<^>`） |

---

## 三、BibsTransformer — 書目轉檔

### migration_config.json

```json
{
    "name": "transform_bibs",
    "migrationTaskType": "BibsTransformer",
    "addAdministrativeNotesWithLegacyIds": true,
    "hridHandling": "default",
    "ilsFlavour": "tag001",
    "tags_to_delete": [],
    "files": [{"file_name": "bibs.mrc", "discovery_suppressed": false}],
    "updateHridSettings": false
}
```

### 來源檔案

- `source_data/instances/bibs.mrc` — MARC ISO 2709 格式

### Mapping Files

無需額外 mapping files。BibsTransformer 使用內建的 MARC-to-FOLIO 對應規則。

### 輸出

- `folio_instances_transform_bibs.json` — Instances JSON
- `folio_srs_instances_transform_bibs.json` — SRS（Source Record Storage）JSON

### 對應 BatchPoster Tasks

```json
{
    "name": "post_instances",
    "migrationTaskType": "BatchPoster",
    "objectType": "Instances",
    "batchSize": 250,
    "files": [{"file_name": "folio_instances_transform_bibs.json"}]
},
{
    "name": "post_srs_bibs",
    "migrationTaskType": "BatchPoster",
    "objectType": "SRS",
    "batchSize": 250,
    "files": [{"file_name": "folio_srs_instances_transform_bibs.json"}]
}
```

---

## 四、HoldingsCsvTransformer — 館藏轉檔

### migration_config.json

```json
{
    "name": "transform_holdings_csv",
    "migrationTaskType": "HoldingsCsvTransformer",
    "holdingsMapFileName": "holdingsrecord_mapping.json",
    "locationMapFileName": "locations.tsv",
    "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
    "defaultCallNumberTypeName": "Library of Congress classification",
    "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
    "hridHandling": "default",
    "files": [{"file_name": "holdings.tsv"}],
    "updateHridSettings": false
}
```

### 來源檔案

- `source_data/items/holdings.tsv`（**注意**：因 folio_migration_tools bug，實際從 `items/` 讀取，不是 `holdings/`）

### Mapping Files（3 個）

#### holdingsrecord_mapping.json

定義 TSV 欄位到 FOLIO Holdings 欄位的對應：

```json
{
    "data": [
        {"folio_field": "legacyIdentifier", "legacy_field": "HOLDINGS_ID", "value": ""},
        {"folio_field": "formerIds[0]", "legacy_field": "HOLDINGS_ID", "value": ""},
        {"folio_field": "instanceId", "legacy_field": "BIB_ID", "value": ""},
        {"folio_field": "permanentLocationId", "legacy_field": "LOCATION", "value": ""},
        {"folio_field": "callNumber", "legacy_field": "CALL_NUMBER", "value": ""},
        {"folio_field": "callNumberTypeId", "legacy_field": "CALL_NUMBER_TYPE", "value": ""},
        {"folio_field": "notes[0].note", "legacy_field": "NOTE", "value": ""},
        {"folio_field": "notes[0].holdingsNoteTypeId", "legacy_field": "Not mapped", "value": "<UUID>"},
        {"folio_field": "notes[0].staffOnly", "legacy_field": "Not mapped", "value": "false"}
    ]
}
```

> `holdingsNoteTypeId` 的 UUID 需從 FOLIO 查詢取得。

#### locations.tsv

將來源位置代碼對應到 FOLIO location code：

```
folio_code	LOCATION
00	00
00AT	00AT
LB3F	LB3F
Migration	*
```

- 第一欄 `folio_code`：FOLIO location 的 `code`
- 第二欄 `LOCATION`：來源 TSV 中 LOCATION 欄位的值
- `*` 行為 fallback（未匹配時使用）

#### call_number_type_mapping.tsv

```
folio_name	CALL_NUMBER_TYPE
Dewey Decimal classification	DDC
Library of Congress classification	LCC
CCL	*
```

- 第一欄 `folio_name`：FOLIO call number type 名稱
- 第二欄 `CALL_NUMBER_TYPE`：來源 TSV 中的索書號類型代碼

### 輸出

- `folio_holdings_transform_holdings_csv.json`

### 對應 BatchPoster Task

```json
{
    "name": "post_holdings_csv",
    "migrationTaskType": "BatchPoster",
    "objectType": "Holdings",
    "batchSize": 250,
    "files": [{"file_name": "folio_holdings_transform_holdings_csv.json"}]
}
```

---

## 五、ItemsTransformer — 單冊轉檔

### migration_config.json

```json
{
    "name": "transform_items",
    "migrationTaskType": "ItemsTransformer",
    "itemsMappingFileName": "item_mapping.json",
    "locationMapFileName": "locations.tsv",
    "materialTypesMapFileName": "material_types.tsv",
    "loanTypesMapFileName": "loan_types.tsv",
    "itemStatusesMapFileName": "item_statuses.tsv",
    "defaultCallNumberTypeName": "Library of Congress classification",
    "defaultLoanTypeName": "Can circulate",
    "hridHandling": "default",
    "files": [{"file_name": "items.tsv"}],
    "updateHridSettings": false
}
```

### 來源檔案

- `source_data/items/items.tsv`

### Mapping Files（5 個）

#### item_mapping.json

```json
{
    "data": [
        {"folio_field": "legacyIdentifier", "legacy_field": "BARCODE", "fallback_legacy_field": "ITEM_ID", "value": ""},
        {"folio_field": "barcode", "legacy_field": "BARCODE", "value": ""},
        {"folio_field": "holdingsRecordId", "legacy_field": "HOLDINGS_ID", "value": ""},
        {"folio_field": "materialTypeId", "legacy_field": "MATERIAL_TYPE", "value": ""},
        {"folio_field": "permanentLoanTypeId", "legacy_field": "LOAN_TYPE", "value": ""},
        {"folio_field": "permanentLocationId", "legacy_field": "LOCATION", "value": ""},
        {"folio_field": "itemLevelCallNumber", "legacy_field": "CALL_NUMBER", "value": ""},
        {"folio_field": "copyNumber", "legacy_field": "COPY_NUMBER", "value": ""},
        {"folio_field": "yearCaption[0]", "legacy_field": "YEAR", "value": ""},
        {"folio_field": "status.name", "legacy_field": "STATUS", "value": ""}
    ]
}
```

#### locations.tsv

與 Holdings 共用同一份（見上方）。

#### material_types.tsv

```
folio_name	MATERIAL_TYPE
A	A
BOOK	BOOK
DVD	DVD
MIGRATION	*
```

- 第一欄 `folio_name`：FOLIO material type 名稱
- 第二欄 `MATERIAL_TYPE`：來源 TSV 中的資料類型代碼
- `*` 為 fallback

#### loan_types.tsv

```
folio_name	LOAN_TYPE
一般圖書(可外借)	*
```

- 第一欄 `folio_name`：FOLIO loan type 名稱
- 全部使用 `*` fallback 時表示所有 item 使用同一種借閱類型

#### item_statuses.tsv

```
legacy_code	folio_name
Available	Available
```

- 第一欄 `legacy_code`：來源 TSV 中的狀態值
- 第二欄 `folio_name`：FOLIO item status 名稱

### 輸出

- `folio_items_transform_items.json`

### 對應 BatchPoster Task

```json
{
    "name": "post_items",
    "migrationTaskType": "BatchPoster",
    "objectType": "Items",
    "batchSize": 250,
    "files": [{"file_name": "folio_items_transform_items.json"}]
}
```

---

## 六、UserTransformer — 讀者轉檔

### migration_config.json

```json
{
    "name": "transform_users",
    "migrationTaskType": "UserTransformer",
    "userMappingFileName": "user_mapping.json",
    "groupMapPath": "user_groups.tsv",
    "useGroupMap": true,
    "userFile": {"file_name": "users.tsv"}
}
```

> **注意**：Users 使用 `userFile`（單數物件），不是 `files`（陣列）。

### 來源檔案

- `source_data/users/users.tsv`

### Mapping Files（2 個）

#### user_mapping.json

定義 TSV 欄位到 FOLIO User 欄位的對應（THU 範例，共 30 個欄位）：

```json
{
    "data": [
        {"folio_field": "barcode", "legacy_field": "reader_code", "value": ""},
        {"folio_field": "patronGroup", "legacy_field": "readerTypeCode", "value": ""},
        {"folio_field": "personal.lastName", "legacy_field": "reader_name", "value": ""},
        {"folio_field": "personal.email", "legacy_field": "email", "value": "",
         "rules": {"regexGetFirstMatchOrEmpty": "(^[a-zA-Z0-9_\\-\\.]+@[a-zA-Z0-9_\\-\\.]+)"}},
        {"folio_field": "username", "legacy_field": "email", "fallback_legacy_field": "reader_code", "value": "",
         "rules": {"regexGetFirstMatchOrEmpty": "([a-zA-Z0-9_\\-\\.]+)@.*"}},
        {"folio_field": "expirationDate", "legacy_field": "expired_date", "value": ""},
        ...
    ]
}
```

**重要欄位說明**：

| folio_field | 說明 |
|------------|------|
| `barcode` | 讀者條碼（用於 Loans/Requests 的 patron_barcode 查詢） |
| `patronGroup` | 讀者群組（經 `user_groups.tsv` 對應） |
| `legacyIdentifier` | 舊系統 ID |
| `username` | 登入帳號（可用 regex 從 email 擷取） |
| `personal.addresses[0].addressTypeId` | 地址類型 UUID（需從 FOLIO 查詢） |
| `notes[0].typeId` | Note type UUID（需從 FOLIO 查詢） |

#### user_groups.tsv

```
readerTypeCode	folio_group
A	A
A1	A
B	B
C1	C1
*	error
```

- 第一欄名稱必須與 `user_mapping.json` 中 `patronGroup` 對應的 `legacy_field` 一致（此例為 `readerTypeCode`，但 Web Portal 模板使用 `PATRON_TYPE`）
- 第二欄 `folio_group`：FOLIO patron group 名稱
- `*	error` 表示未匹配的讀者類型會標記為錯誤

### 輸出

- `folio_users_transform_users.json` — Users JSON
- `extradata_transform_users.extradata` — 額外資料（permissions, notes 等）

### 對應 BatchPoster Tasks

```json
{
    "name": "post_users",
    "migrationTaskType": "BatchPoster",
    "objectType": "Users",
    "batchSize": 250,
    "files": [{"file_name": "folio_users_transform_users.json"}]
},
{
    "name": "post_extradata_users",
    "migrationTaskType": "BatchPoster",
    "objectType": "Extradata",
    "batchSize": 250,
    "files": [{"file_name": "extradata_transform_users.extradata"}]
}
```

---

## 七、LoansMigrator — 借閱遷移

### migration_config.json

```json
{
    "name": "migrate_loans",
    "migrationTaskType": "LoansMigrator",
    "fallbackServicePointId": "3a40852d-49fd-4df2-a1f9-6e2641a6e91f",
    "openLoansFiles": [
        {
            "file_name": "loans.tsv",
            "service_point_id": ""
        }
    ],
    "startingRow": 1
}
```

### 來源檔案

- `source_data/loans/loans.tsv`

### TSV 格式

```
item_barcode	patron_barcode	due_date	out_date	renewal_count	next_item_status	service_point_id
C723018	c400030044	2026-03-11T23:59:59.000000+08:00	2026-01-16T16:18:18.287000+08:00	0		3a40852d-...
```

### Mapping Files

無。LoansMigrator 直接使用 TSV 中的欄位，透過 FOLIO API `POST /circulation/check-out-by-barcode` 建立借閱。

### 重要參數

| 參數 | 說明 |
|------|------|
| `fallbackServicePointId` | TSV 中 `service_point_id` 為空時的備用值（FOLIO service point UUID） |
| `openLoansFiles[].service_point_id` | 該檔案的預設 service point（優先級低於 TSV 每行的值） |
| `startingRow` | 從第幾行開始處理（1 = 跳過 header 從第一筆資料開始） |

### service_point_id 優先級

TSV 每行 > `openLoansFiles[].service_point_id` > `fallbackServicePointId`

---

## 八、RequestsMigrator — 預約遷移

### migration_config.json

```json
{
    "name": "migrate_requests",
    "migrationTaskType": "RequestsMigrator",
    "openRequestsFile": {"file_name": "requests.tsv"},
    "item_files": [{"file_name": "folio_items_transform_items.json"}],
    "patron_files": [{"file_name": "folio_users_transform_users.json"}]
}
```

### 來源檔案

- `source_data/requests/requests.tsv`

### TSV 格式

```
item_barcode	patron_barcode	pickup_servicepoint_id	request_date	request_expiration_date	comment	request_type
C719476	d10055001	3a40852d-...	2026-02-24T08:48:08.500000+08:00	2027-02-24T23:59:59.000000+08:00	Migrated from HyLib	Hold
```

### Mapping Files

無額外 mapping files，但需要之前 transform 產生的 JSON 輸出：
- `folio_items_transform_items.json`（items transform 的輸出）
- `folio_users_transform_users.json`（users transform 的輸出）

> **注意**：必須先完成 Items 和 Users 的 transform，RequestsMigrator 才能找到這些 JSON 檔案。

---

## 九、ManualFeeFinesTransformer — 罰金轉檔

### migration_config.json

```json
{
    "name": "transform_feefines",
    "migrationTaskType": "ManualFeeFinesTransformer",
    "feefinesMap": "manual_feefines_map.json",
    "feefinesOwnerMap": "feefine_owners.tsv",
    "feefinesTypeMap": "feefine_types.tsv",
    "servicePointMap": "feefine_service_points.tsv",
    "files": [{"file_name": "feefines.tsv"}]
}
```

> **注意**：`servicePointMap` 是必要欄位，缺少會報錯 "Field required servicePointMap"。

### 來源檔案

- `source_data/fees_fines/feefines.tsv`（目錄名是 `fees_fines`，不是 `feefines`）

### TSV 格式

```
amount	remaining	patron_barcode	item_barcode	billed_date	type	lending_library	borrowing_desk
100.0	100.0	T9901234	0012345	2024-03-15T10:30:00.000000+08:00	逾期罰金	thu
```

### Mapping Files（4 個）

#### manual_feefines_map.json

```json
{
    "data": [
        {"folio_field": "legacyIdentifier", "legacy_field": "", "value": ""},
        {"folio_field": "account.amount", "legacy_field": "amount", "value": ""},
        {"folio_field": "account.remaining", "legacy_field": "remaining", "value": ""},
        {"folio_field": "account.paymentStatus.name", "legacy_field": "", "value": "Outstanding"},
        {"folio_field": "account.status.name", "legacy_field": "", "value": "Open"},
        {"folio_field": "account.userId", "legacy_field": "patron_barcode", "value": ""},
        {"folio_field": "account.itemId", "legacy_field": "item_barcode", "value": ""},
        {"folio_field": "account.feeFineId", "legacy_field": "type", "value": ""},
        {"folio_field": "account.ownerId", "legacy_field": "lending_library", "value": ""},
        {"folio_field": "feefineaction.accountId", "legacy_field": "", "value": ""},
        {"folio_field": "feefineaction.userId", "legacy_field": "patron_barcode", "value": ""},
        {"folio_field": "feefineaction.dateAction", "legacy_field": "billed_date", "value": ""},
        {"folio_field": "feefineaction.comments", "legacy_field": "", "value": ""},
        {"folio_field": "feefineaction.createdAt", "legacy_field": "borrowing_desk", "value": ""}
    ]
}
```

**重要**：`account.*` 和 `feefineaction.*` 欄位名稱必須小寫，不能用大寫。

#### feefine_owners.tsv

```
lending_library	folio_owner
thu	Tunghai University
*	Tunghai University
```

- 第一欄 `lending_library`：來源 TSV 中的值
- 第二欄 `folio_owner`：FOLIO Fee/Fine Owner 名稱（必須與 FOLIO 設定完全一致）

#### feefine_types.tsv

```
type	folio_feeFineType
逾期罰金	Overdue fine
*	Overdue fine
```

- 第一欄 `type`：來源 TSV 中的罰金類型名稱
- 第二欄 `folio_feeFineType`：FOLIO Fee/Fine Type 名稱

#### feefine_service_points.tsv

```
borrowing_desk	folio_name
*	Main circulation desk
```

- 第一欄 `borrowing_desk`：來源 TSV 中的值
- 第二欄必須叫 `folio_name`（不是 `folio_servicepoint` 或 `folio_servicePointId`）

### 輸出

- `extradata_transform_feefines.extradata` — 每筆 fee/fine 產生 2 行（`account` + `feefineaction`）

### 對應 BatchPoster Task

```json
{
    "name": "post_feefines",
    "migrationTaskType": "BatchPoster",
    "objectType": "Extradata",
    "batchSize": 1,
    "files": [{"file_name": "extradata_transform_feefines.extradata"}]
}
```

> **注意**：`batchSize` 建議設為 `1`。

---

## 十、BatchPoster — 批次匯入

BatchPoster 負責將 Transform 的輸出 POST 到 FOLIO。

### 通用格式

```json
{
    "name": "post_<type>",
    "migrationTaskType": "BatchPoster",
    "objectType": "<ObjectType>",
    "batchSize": <N>,
    "files": [{"file_name": "<output_file>"}]
}
```

### objectType 對照表

| objectType | 對應 API | 來源 |
|-----------|---------|------|
| `Instances` | `/instance-storage/instances` | BibsTransformer 輸出 |
| `SRS` | `/source-storage/snapshots` + `/records` | BibsTransformer 輸出 |
| `Holdings` | `/holdings-storage/holdings` | HoldingsCsvTransformer 輸出 |
| `Items` | `/item-storage/items` | ItemsTransformer 輸出 |
| `Users` | `/users` | UserTransformer 輸出 |
| `Extradata` | 依 extradata 內容而定 | UserTransformer / ManualFeeFinesTransformer 輸出 |

### batchSize 建議值

| objectType | 建議 batchSize |
|-----------|---------------|
| Instances, Holdings, Items, Users, SRS | `250` |
| Extradata (feefines) | `1` |
| Extradata (users) | `250` |

---

## 十一、執行順序

Tasks 之間有相依性，必須按以下順序執行：

```
1. transform_bibs          → post_instances → post_srs_bibs
2. transform_holdings_csv  → post_holdings_csv
3. transform_items         → post_items
4. transform_users         → post_users → post_extradata_users
5. migrate_loans           （需要 Items + Users 已匯入 FOLIO）
6. migrate_requests        （需要 Items + Users 已匯入 FOLIO + transform 輸出 JSON）
7. transform_feefines      → post_feefines（需要 Users + Items 已匯入 FOLIO）
```

**規則**：
- Transform 必須在對應的 BatchPoster 之前
- Loans/Requests/Fee-Fines 必須在 Items 和 Users 匯入 FOLIO 之後
- RequestsMigrator 還需要 items 和 users 的 transform JSON 輸出檔案存在

---

## 十二、Mapping File 欄位命名規則

TSV mapping files 的欄位名稱有嚴格規定，以下是已驗證的正確名稱：

| Mapping File | 第一欄（來源值） | 第二欄（FOLIO 值） |
|-------------|----------------|------------------|
| `locations.tsv` | `folio_code` | `LOCATION` |
| `material_types.tsv` | `folio_name` | `MATERIAL_TYPE` |
| `loan_types.tsv` | `folio_name` | `LOAN_TYPE` |
| `item_statuses.tsv` | `legacy_code` | `folio_name` |
| `call_number_type_mapping.tsv` | `folio_name` | `CALL_NUMBER_TYPE` |
| `user_groups.tsv` | `readerTypeCode`（或 `PATRON_TYPE`） | `folio_group` |
| `feefine_owners.tsv` | `lending_library` | `folio_owner` |
| `feefine_types.tsv` | `type` | `folio_feeFineType` |
| `feefine_service_points.tsv` | `borrowing_desk` | `folio_name` |
| `keepsite_service_points.tsv` | `keepsite_id` | `service_point_id` |

### Fallback 行（`*`）

大部分 TSV 支援 `*` 作為 fallback，表示「其他所有未匹配的值使用此對應」：

```
folio_name	LOAN_TYPE
一般圖書(可外借)	*
```

---

## 十三、完整 migration_config.json 範例

以 THU 為例，包含所有已驗證的 tasks：

```json
{
    "libraryInformation": {
        "tenantId": "fs00001280",
        "multiFieldDelimiter": "<^>",
        "okapiUrl": "https://api-thu.folio.ebsco.com",
        "okapiUsername": "HyWebFOLIO",
        "logLevelDebug": false,
        "libraryName": "Tunghai University",
        "folioRelease": "sunflower",
        "addTimeStampToFileNames": false,
        "iterationIdentifier": "thu_migration"
    },
    "migrationTasks": [
        {
            "name": "transform_bibs",
            "migrationTaskType": "BibsTransformer",
            "addAdministrativeNotesWithLegacyIds": true,
            "hridHandling": "default",
            "ilsFlavour": "tag001",
            "tags_to_delete": [],
            "files": [{"file_name": "bibs.mrc", "discovery_suppressed": false}],
            "updateHridSettings": false
        },
        {
            "name": "post_instances",
            "migrationTaskType": "BatchPoster",
            "objectType": "Instances",
            "batchSize": 250,
            "files": [{"file_name": "folio_instances_transform_bibs.json"}]
        },
        {
            "name": "post_srs_bibs",
            "migrationTaskType": "BatchPoster",
            "objectType": "SRS",
            "batchSize": 250,
            "files": [{"file_name": "folio_srs_instances_transform_bibs.json"}]
        },
        {
            "name": "transform_holdings_csv",
            "migrationTaskType": "HoldingsCsvTransformer",
            "holdingsMapFileName": "holdingsrecord_mapping.json",
            "locationMapFileName": "locations.tsv",
            "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
            "defaultCallNumberTypeName": "Library of Congress classification",
            "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
            "hridHandling": "default",
            "files": [{"file_name": "holdings.tsv"}],
            "updateHridSettings": false
        },
        {
            "name": "post_holdings_csv",
            "migrationTaskType": "BatchPoster",
            "objectType": "Holdings",
            "batchSize": 250,
            "files": [{"file_name": "folio_holdings_transform_holdings_csv.json"}]
        },
        {
            "name": "transform_items",
            "migrationTaskType": "ItemsTransformer",
            "itemsMappingFileName": "item_mapping.json",
            "locationMapFileName": "locations.tsv",
            "materialTypesMapFileName": "material_types.tsv",
            "loanTypesMapFileName": "loan_types.tsv",
            "itemStatusesMapFileName": "item_statuses.tsv",
            "defaultCallNumberTypeName": "Library of Congress classification",
            "defaultLoanTypeName": "Can circulate",
            "hridHandling": "default",
            "files": [{"file_name": "items.tsv"}],
            "updateHridSettings": false
        },
        {
            "name": "post_items",
            "migrationTaskType": "BatchPoster",
            "objectType": "Items",
            "batchSize": 250,
            "files": [{"file_name": "folio_items_transform_items.json"}]
        },
        {
            "name": "transform_users",
            "migrationTaskType": "UserTransformer",
            "userMappingFileName": "user_mapping.json",
            "groupMapPath": "user_groups.tsv",
            "useGroupMap": true,
            "userFile": {"file_name": "users.tsv"}
        },
        {
            "name": "post_users",
            "migrationTaskType": "BatchPoster",
            "objectType": "Users",
            "batchSize": 250,
            "files": [{"file_name": "folio_users_transform_users.json"}]
        },
        {
            "name": "post_extradata_users",
            "migrationTaskType": "BatchPoster",
            "objectType": "Extradata",
            "batchSize": 250,
            "files": [{"file_name": "extradata_transform_users.extradata"}]
        },
        {
            "name": "migrate_loans",
            "migrationTaskType": "LoansMigrator",
            "fallbackServicePointId": "3a40852d-49fd-4df2-a1f9-6e2641a6e91f",
            "openLoansFiles": [{"file_name": "loans.tsv", "service_point_id": ""}],
            "startingRow": 1
        },
        {
            "name": "migrate_requests",
            "migrationTaskType": "RequestsMigrator",
            "openRequestsFile": {"file_name": "requests.tsv"},
            "item_files": [{"file_name": "folio_items_transform_items.json"}],
            "patron_files": [{"file_name": "folio_users_transform_users.json"}]
        },
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

---

## 附錄：常見錯誤

| 錯誤訊息 | 原因 | 解決 |
|---------|------|------|
| `None of the files listed in task configuration found` | 來源檔案不在正確的 `source_data/` 子目錄 | 確認檔案路徑和目錄名 |
| `Field required servicePointMap` | ManualFeeFinesTransformer 缺少 servicePointMap | 新增 `"servicePointMap": "feefine_service_points.tsv"` |
| `Column folio_name missing from servicepoints map file` | feefine_service_points.tsv 第二欄名稱錯誤 | 改為 `folio_name` |
| `Fee/Fine Owner not found` | FOLIO 中 Owner 名稱與 TSV 不一致 | 確認大小寫和空格完全一致 |
| `Cannot check out item that already has an open loan` | Item 已有 open loan | 先還書（check-in）再重新借出 |

---

*本文件基於 THU 專案實際驗證結果。最後更新：2026-03-10*
