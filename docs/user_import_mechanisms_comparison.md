# FOLIO 使用者資料轉檔與匯入機制比較分析

## 目錄
1. [概述](#概述)
2. [架構設計差異](#架構設計差異)
3. [資料轉換流程的不同](#資料轉換流程的不同)
4. [設定檔格式與使用方式](#設定檔格式與使用方式)
5. [批次處理機制的差異](#批次處理機制的差異)
6. [錯誤處理方式](#錯誤處理方式)
7. [優缺點與適用場景](#優缺點與適用場景)
8. [總結比較表](#總結比較表)

---

## 概述

本文比較兩種 FOLIO 使用者資料轉檔與匯入機制：

| 項目 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| **主要用途** | 完整的資料遷移轉換工具 | 輕量級資料匯入工具 |
| **核心類別** | `UserTransformer` + `BatchPoster` | `UserImporter` + `BatchPoster` |
| **處理模式** | 同步處理 | **非同步處理 (asyncio)** |
| **設計理念** | 轉換優先，匯入為後續步驟 | 匯入優先，轉換在匯入時進行 |

---

## 架構設計差異

### folio_migration_tools 架構

```
┌─────────────────────────────────────────────────────────────┐
│                    Migration Task Pipeline                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────┐    ┌─────────────────┐                │
│   │  UserTransformer│───►│   BatchPoster   │───► FOLIO API  │
│   │  (轉換階段)      │    │   (匯入階段)     │                │
│   └────────┬────────┘    └─────────────────┘                │
│            │                                                 │
│            ▼                                                 │
│   ┌─────────────────┐                                       │
│   │   UserMapper    │                                       │
│   │   (映射邏輯)     │                                       │
│   └────────┬────────┘                                       │
│            │                                                 │
│            ▼                                                 │
│   ┌─────────────────┐    ┌─────────────────┐                │
│   │ MappingFileBase │    │  RefDataMapping │                │
│   │  (欄位映射)      │    │  (參考資料映射)  │                │
│   └─────────────────┘    └─────────────────┘                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**特點：**
- **分離式架構**：轉換與匯入是兩個獨立任務
- **繼承體系**：`UserMapper` 繼承自 `MappingFileMapperBase`
- **中間檔案**：轉換後產生 JSON 檔案，再由 BatchPoster 匯入
- **Schema 驗證**：從 GitHub 動態獲取 FOLIO Schema 進行驗證

```python
# UserMapper 初始化 - 從 GitHub 取得 Schema
class UserMapper(MappingFileMapperBase):
    def __init__(self, ...):
        user_schema = folio_client.get_from_github(
            "folio-org", "mod-user-import", "/ramls/schemas/userdataimport.json"
        )
```

### folio_data_import 架構

```
┌─────────────────────────────────────────────────────────────┐
│                   UserImporter (All-in-One)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────────────────────────────────┐       │
│   │              UserImporter                        │       │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────────────┐  │       │
│   │  │ 讀取    │──│ 映射    │──│ 建立/更新 User  │  │───► FOLIO
│   │  │ JSON-L  │  │ 參考資料 │  │ (即時 API 呼叫) │  │       │
│   │  └─────────┘  └─────────┘  └─────────────────┘  │       │
│   │                     │                           │       │
│   │                     ▼                           │       │
│   │  ┌─────────────────────────────────────────┐   │       │
│   │  │ 額外處理: RequestPreference, Permissions │   │       │
│   │  │           ServicePointsUser              │   │       │
│   │  └─────────────────────────────────────────┘   │       │
│   └─────────────────────────────────────────────────┘       │
│                                                              │
│   ┌─────────────────────────────────────────────────┐       │
│   │              Async HTTP Client (httpx)           │       │
│   │   - 並行請求控制 (Semaphore)                     │       │
│   │   - 非同步批次處理                               │       │
│   └─────────────────────────────────────────────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**特點：**
- **整合式架構**：讀取、映射、匯入在單一類別完成
- **非同步設計**：使用 `asyncio` + `httpx` 實現並行處理
- **即時 API 呼叫**：直接對 FOLIO API 進行 CRUD 操作
- **智慧更新**：自動判斷新增或更新，支援欄位保護

```python
# UserImporter 非同步處理
class UserImporter:
    async def process_line(self, user: str, line_number: int):
        async with self.limit_simultaneous_requests:  # 並行控制
            user_obj = await self.process_user_obj(user)
            existing_user = await self.get_existing_user(user_obj)
            # ... 映射與處理
            new_user_obj = await self.create_or_update_user(...)
```

---

## 資料轉換流程的不同

### folio_migration_tools 轉換流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 來源資料      │     │ 映射處理      │     │ 輸出檔案      │
│ (CSV/TSV)    │────►│ UserMapper   │────►│ (JSON-Lines) │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ 映射檔案處理  │
                     │ - JSON 映射  │
                     │ - TSV 參考資料│
                     │ - 規則引擎    │
                     └──────────────┘
```

**轉換步驟：**

1. **讀取來源資料** (CSV/TSV)
2. **載入映射檔案** (`user_mapping.json`)
3. **逐筆轉換**：
   - 基礎欄位映射 (`folio_field` ← `legacy_field`)
   - 參考資料映射 (`user_groups.tsv`, `user_departments.tsv`)
   - 規則處理 (regex, fallback)
   - 日期格式轉換
4. **Schema 驗證**
5. **寫入輸出檔案** (`folio_users_*.json`)
6. **另行執行 BatchPoster 匯入**

```python
# UserMapper.perform_additional_mapping()
def perform_additional_mapping(self, legacy_user, folio_user, index_or_id):
    # 處理 Notes
    self.notes_mapper.map_notes(...)

    # 設定預設值
    folio_user["personal"]["preferredContactTypeId"] = "email"
    folio_user["active"] = True
    folio_user["requestPreference"] = {"holdShelf": True, "delivery": False}

    # 驗證必填欄位
    clean_folio_object = self.validate_required_properties(...)
    if not clean_folio_object.get("personal", {}).get("lastName", ""):
        raise TransformationRecordFailedError(index_or_id, "Last name is missing", "")
```

### folio_data_import 轉換流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 來源資料      │     │ 即時處理      │     │ FOLIO API    │
│ (JSON-Lines) │────►│ UserImporter │────►│ (即時呼叫)   │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────────────────────────┐
                     │ 參考資料 ID 映射 (啟動時載入)      │
                     │ - patron_group_map               │
                     │ - address_type_map               │
                     │ - department_map                 │
                     │ - service_point_map              │
                     └──────────────────────────────────┘
```

**轉換步驟：**

1. **啟動時載入參考資料** (從 FOLIO API 動態獲取)
2. **讀取 JSON-Lines 檔案** (已是 FOLIO 格式)
3. **逐筆處理**：
   - 查詢現有使用者 (by `id`, `username`, `barcode`, `externalSystemId`)
   - 映射 patron group (名稱 → UUID)
   - 映射 address types (名稱 → UUID)
   - 映射 departments (名稱 → UUID)
   - 處理欄位保護
4. **即時建立/更新** (直接呼叫 API)
5. **處理相關物件**：
   - `RequestPreference`
   - `PermissionUser`
   - `ServicePointsUser`

```python
# UserImporter.process_line() - 即時處理與 API 呼叫
async def process_line(self, user: str, line_number: int):
    user_obj = await self.process_user_obj(user)

    # 查詢現有使用者
    existing_user = await self.get_existing_user(user_obj)

    # 映射參考資料
    await self.map_address_types(user_obj, line_number)
    await self.map_patron_groups(user_obj, line_number)
    await self.map_departments(user_obj, line_number)

    # 建立或更新
    new_user_obj = await self.create_or_update_user(...)

    # 處理相關物件
    await self.create_or_update_rp(...)
    await self.create_perms_user(...)
    await self.handle_service_points_user(...)
```

---

## 設定檔格式與使用方式

### folio_migration_tools 設定檔

#### 1. 任務設定 (`taskConfig.json`)

```json
{
  "libraryInformation": {
    "tenantId": "your_tenant_id",
    "okapiUrl": "https://okapi.example.com",
    "okapiUsername": "EBSCOAdmin",
    "libraryName": "thu",
    "folioRelease": "sunflower"
  },
  "migrationTasks": [
    {
      "name": "users",
      "migrationTaskType": "UserTransformer",
      "groupMapPath": "user_groups.tsv",
      "userMappingFileName": "user_mapping.json",
      "departmentsMapPath": "user_departments.tsv",
      "useGroupMap": true,
      "userFile": {
        "file_name": "users.tsv"
      }
    },
    {
      "name": "users_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "Users",
      "batchSize": 250,
      "files": [
        { "file_name": "folio_users_users.json" }
      ]
    }
  ]
}
```

#### 2. 欄位映射 (`user_mapping.json`)

```json
{
  "data": [
    {
      "folio_field": "barcode",
      "legacy_field": "reader_code",
      "value": "",
      "description": ""
    },
    {
      "folio_field": "externalSystemId",
      "legacy_field": "email",
      "fallback_legacy_field": "reader_code",
      "value": "",
      "description": ""
    },
    {
      "folio_field": "username",
      "legacy_field": "email",
      "fallback_legacy_field": "reader_code",
      "rules": {
        "regexGetFirstMatchOrEmpty": "([a-zA-Z0-9_\\-\\.]+)@.*"
      },
      "description": ""
    },
    {
      "folio_field": "customFields.licenseid",
      "legacy_field": "license_id",
      "value": "",
      "description": ""
    }
  ]
}
```

#### 3. 參考資料映射 (`user_groups.tsv`)

```tsv
readerTypeCode	folio_group
A	A
A1	A
B	B
C1	C1
*	error
```

### folio_data_import 設定

#### 1. 命令列參數

```bash
python -m folio_data_import.UserImport \
  --gateway-url "https://api.folio.example.com" \
  --tenant-id "your_tenant_id" \
  --username "admin" \
  --password "<your_password>" \
  --library-name "thu" \
  --user-file-paths "/path/to/folio_users.json" \
  --batch-size 250 \
  --user-match-key "externalSystemId" \
  --default-preferred-contact-type "email" \
  --fields-to-protect "personal.email,barcode"
```

#### 2. 設定檔 (JSON)

```json
{
  "library_name": "thu",
  "batch_size": 250,
  "user_match_key": "externalSystemId",
  "only_update_present_fields": false,
  "default_preferred_contact_type": "002",
  "fields_to_protect": ["personal.email", "barcode"],
  "limit_simultaneous_requests": 10,
  "user_file_paths": ["/path/to/folio_users.json"]
}
```

#### 3. 環境變數

```bash
export FOLIO_GATEWAY_URL="https://api.folio.example.com"
export FOLIO_TENANT_ID="your_tenant_id"
export FOLIO_USERNAME="admin"
export FOLIO_PASSWORD="<your_password>"
export FOLIO_LIBRARY_NAME="thu"
export FOLIO_FIELDS_TO_PROTECT="personal.email,barcode"
export FOLIO_LIMIT_ASYNC_REQUESTS=10
export FOLIO_USER_IMPORT_BATCH_SIZE=250
```

### 設定方式比較

| 項目 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| **設定格式** | JSON 配置檔 | 命令列 + JSON + 環境變數 |
| **映射定義** | 外部 JSON + TSV 映射檔 | 內建，參考資料從 API 動態載入 |
| **轉換規則** | 支援 regex, fallback, 靜態值 | 不支援，需預先轉換 |
| **自訂欄位** | 透過映射檔動態支援 | 透過輸入檔案直接支援 |

---

## 批次處理機制的差異

### folio_migration_tools BatchPoster

```python
# 同步批次處理
class BatchPoster(MigrationTaskBase):
    def do_work(self):
        for file in self.files:
            with open(file) as f:
                batch = []
                for line in f:
                    batch.append(json.loads(line))
                    if len(batch) >= self.batch_size:
                        self.post_batch(batch)  # 同步 POST
                        batch = []
```

**特點：**
- 同步處理，一次一個批次
- 使用 `folioclient` 的同步 HTTP 方法
- 批次大小可設定 (預設 250)
- 支援多種物件類型 (Users, Instances, Holdings, Items, etc.)

### folio_data_import UserImporter

```python
# 非同步並行處理
class UserImporter:
    async def process_file(self, openfile):
        tasks = []
        for line_number, user in enumerate(openfile):
            tasks.append(self.process_line(user, line_number))
            if len(tasks) == self.config.batch_size:
                await asyncio.gather(*tasks)  # 並行執行
                tasks = []
```

**特點：**
- 非同步處理，並行執行多個請求
- 使用 `httpx.AsyncClient`
- 並行數量限制 (Semaphore, 預設 10)
- 每筆記錄獨立處理 (create/update)

### folio_data_import BatchPoster

```python
# 非同步批次處理 (用於 Inventory)
class BatchPoster:
    async def post_batch(self, batch: List[dict]):
        if self.config.upsert:
            await self.set_versions_for_upsert(batch)  # 先查詢現有記錄

        response = await self.folio_client.async_httpx_client.post(
            api_endpoint, json=payload, params=query_params
        )
```

**特點：**
- 非同步批次處理
- 支援 upsert 模式 (需查詢 `_version`)
- 支援欄位保護 (statistical codes, administrative notes, etc.)
- 支援失敗記錄重跑

### 批次處理比較

| 項目 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| **處理模式** | 同步 | 非同步 |
| **並行能力** | 無 | 可控制並行數 |
| **批次大小** | 可設定 | 可設定 |
| **Upsert** | BatchPoster 支援 | 完整支援 |
| **欄位保護** | 無 | 支援多種欄位保護 |
| **進度顯示** | 日誌輸出 | Rich 進度條 |

---

## 錯誤處理方式

### folio_migration_tools 錯誤處理

```python
# 自訂例外類別
class TransformationRecordFailedError(Exception):
    def __init__(self, index_or_id, message, data_value):
        self.id = index_or_id
        self.message = message
        self.data_value = data_value

class TransformationProcessError(Exception):
    def __init__(self, index_or_id, message, data_value):
        self.id = index_or_id
        self.message = message
        self.data_value = data_value
```

**錯誤處理機制：**
1. **轉換階段**：
   - `TransformationRecordFailedError`：單筆記錄失敗，繼續處理
   - `TransformationProcessError`：嚴重錯誤，終止處理
   - 失敗記錄寫入 `failed_records_*.txt`
   - 遷移報告記錄統計

2. **匯入階段**：
   - HTTP 錯誤由 `folioclient` 處理
   - 批次失敗記錄日誌
   - 失敗百分比閾值檢查

```python
# UserMapper 錯誤處理
def perform_additional_mapping(self, legacy_user, folio_user, index_or_id):
    if not clean_folio_object.get("personal", {}).get("lastName", ""):
        raise TransformationRecordFailedError(
            index_or_id, "Last name is missing", ""
        )
```

### folio_data_import 錯誤處理

```python
# 自訂例外類別
class FolioDataImportError(Exception):
    """Base class for all exceptions"""
    pass

class FolioDataImportBatchError(FolioDataImportError):
    def __init__(self, batch_id, message, exception=None):
        self.batch_id = batch_id
        self.message = message

class FolioDataImportJobError(FolioDataImportError):
    def __init__(self, job_id, message, exception=None):
        self.job_id = job_id
        self.message = message
```

**錯誤處理機制：**
1. **非同步錯誤處理**：
   - 每筆記錄獨立 try-except
   - 失敗不影響其他記錄處理
   - 失敗記錄寫入錯誤檔案

2. **API 錯誤處理**：
   - HTTP 錯誤狀態碼檢查
   - 詳細錯誤訊息記錄
   - 相關物件處理分開 try-except

3. **重跑機制**：
   - 支援失敗記錄逐筆重跑
   - 重跑結果分開統計

```python
# UserImporter 錯誤處理
async def create_or_update_user(self, user_obj, existing_user, ...):
    if existing_user:
        try:
            update_user.raise_for_status()
            async with self.lock:
                self.stats.updated += 1
            return existing_user
        except Exception as ee:
            logger.error(f"Row {line_number}: User update failed: {ee}")
            await self.errorfile.write(json.dumps(existing_user) + "\n")
            async with self.lock:
                self.stats.failed += 1
            return {}
```

### 錯誤處理比較

| 項目 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| **例外類別** | 轉換專用例外 | 匯入/批次專用例外 |
| **失敗隔離** | 單筆隔離 | 單筆隔離 |
| **失敗記錄** | 檔案輸出 | 檔案輸出 |
| **重跑機制** | 無內建 | 支援逐筆重跑 |
| **統計報告** | 遷移報告 (Markdown) | 即時統計 + 日誌 |

---

## 優缺點與適用場景

### folio_migration_tools

#### 優點
1. **完整的轉換能力**
   - 支援複雜的欄位映射規則 (regex, fallback, 靜態值)
   - 支援自訂欄位 (customFields)
   - 支援 Notes 處理
   - Schema 驗證確保資料品質

2. **分離式設計**
   - 轉換與匯入分開，便於除錯
   - 中間檔案可供檢查
   - 可重複執行匯入步驟

3. **豐富的報告**
   - 詳細的遷移報告 (Markdown)
   - 欄位映射統計
   - 資料問題日誌

4. **多種資料來源支援**
   - CSV, TSV 格式
   - 靈活的分隔符設定

#### 缺點
1. **同步處理效能較低**
2. **需要兩步驟執行** (轉換 + 匯入)
3. **不支援即時更新判斷**
4. **欄位保護功能有限**

#### 適用場景
- **大規模初次遷移**
- **複雜的欄位轉換需求**
- **需要詳細遷移報告**
- **來源資料為 CSV/TSV 格式**

### folio_data_import

#### 優點
1. **高效能非同步處理**
   - 並行 API 呼叫
   - 可控制並行數量
   - 適合大量資料處理

2. **智慧更新機制**
   - 自動判斷新增或更新
   - 支援欄位保護
   - 支援 upsert 模式

3. **完整的相關物件處理**
   - RequestPreference
   - PermissionUser
   - ServicePointsUser

4. **便利的操作介面**
   - 命令列參數
   - 環境變數支援
   - Rich 進度條

5. **錯誤恢復機制**
   - 失敗記錄重跑
   - 詳細的失敗日誌

#### 缺點
1. **需要預先轉換好的資料**
   - 輸入必須是 FOLIO 格式的 JSON
   - 不支援複雜的欄位映射規則

2. **參考資料映射簡單**
   - 僅支援名稱 → UUID 映射
   - 無法處理複雜的轉換邏輯

3. **無中間檔案**
   - 難以檢查轉換結果
   - 除錯較不直覺

#### 適用場景
- **資料同步/更新**
- **已有 FOLIO 格式資料**
- **需要高效能批次處理**
- **增量更新場景**
- **與其他系統整合**

---

## 總結比較表

| 比較項目 | folio_migration_tools | folio_data_import |
|---------|----------------------|-------------------|
| **主要類別** | `UserTransformer` + `BatchPoster` | `UserImporter` |
| **處理模式** | 同步 | 非同步 (asyncio) |
| **輸入格式** | CSV/TSV | JSON-Lines (FOLIO 格式) |
| **輸出方式** | 中間檔案 → API | 直接 API |
| **映射能力** | 強 (規則引擎) | 弱 (僅 ID 映射) |
| **效能** | 中等 | 高 (並行處理) |
| **更新支援** | BatchPoster 有限支援 | 完整支援 (upsert) |
| **欄位保護** | 無 | 支援 |
| **相關物件** | 需額外處理 | 內建支援 |
| **錯誤重跑** | 無 | 支援 |
| **報告** | 詳細 Markdown | 即時統計 |
| **適用場景** | 初次遷移 | 同步/更新 |

### 建議使用策略

```
┌─────────────────────────────────────────────────────────────┐
│                    資料遷移/匯入流程建議                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐                                       │
│  │ 來源資料 CSV/TSV │                                       │
│  └────────┬─────────┘                                       │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────────────────────────────┐                   │
│  │     folio_migration_tools            │                   │
│  │     UserTransformer                  │                   │
│  │     (複雜轉換、Schema 驗證)           │                   │
│  └────────┬─────────────────────────────┘                   │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────────┐                                       │
│  │ FOLIO JSON-Lines │                                       │
│  └────────┬─────────┘                                       │
│           │                                                  │
│           ├─── 初次遷移 ───►┌──────────────────────┐        │
│           │                 │ migration_tools      │        │
│           │                 │ BatchPoster          │        │
│           │                 └──────────────────────┘        │
│           │                                                  │
│           └─── 後續同步 ───►┌──────────────────────┐        │
│                             │ folio_data_import    │        │
│                             │ UserImporter         │        │
│                             │ (高效能、智慧更新)    │        │
│                             └──────────────────────┘        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**最佳實踐：**
1. **初次遷移**：使用 `folio_migration_tools` 進行完整轉換，利用其強大的映射能力和報告功能
2. **日常同步**：使用 `folio_data_import` 進行高效能的增量更新
3. **混合使用**：先用 `UserTransformer` 轉換，再用 `folio_data_import.UserImporter` 匯入，結合兩者優點
