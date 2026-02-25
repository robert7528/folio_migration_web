# FOLIO 書目資料轉檔與匯入機制比較分析

## 摘要

FOLIO 系統中存在兩種不同的書目資料轉檔與匯入機制，各有其設計目的與適用場景：

- **folio_migration_tools**：以遷移為導向的完整框架，設計用於從舊有系統批次轉換 MARC 記錄為 FOLIO 的 Instances 與 SRS 記錄
- **folio_data_import**：現代化的非同步 CLI 工具，設計用於透過 Data Import API (Change Manager) 串流 MARC 記錄直接匯入 FOLIO

---

## 1. 架構設計的差異（類別結構、模組組織）

### 1.1 folio_migration_tools

**模組組織**
```
folio_migration_tools/
├── migration_tasks/
│   ├── migration_task_base.py    # 所有遷移任務的抽象基底類別
│   ├── bibs_transformer.py       # MARC 轉換為 Instances/SRS
│   ├── batch_poster.py           # 批次發送記錄到 FOLIO API
│   ├── holdings_marc_transformer.py
│   ├── holdings_csv_transformer.py
│   └── items_transformer.py
└── custom_exceptions.py
```

**類別繼承結構**
```
MigrationTaskBase (抽象基底類別)
├── BibsTransformer
├── HoldingsMarcTransformer
├── HoldingsCsvTransformer
├── ItemsTransformer
└── BatchPoster
```

**設計特點**
- 採用繼承架構，所有任務繼承自 `MigrationTaskBase`
- 使用 Pydantic 進行設定驗證（`TaskConfiguration` 類別）
- 支援任務鏈（Task Chain）執行多個遷移步驟
- 同步處理為主，僅在 upsert 版本查詢時使用非同步

### 1.2 folio_data_import

**模組組織**
```
folio_data_import/
├── MARCDataImport.py    # 主要 MARC 匯入任務協調
├── BatchPoster.py       # Inventory 記錄批次發送
└── custom_exceptions.py # 自訂例外定義
```

**類別結構**
```
CLI 入口點
├── main() in MARCDataImport.py
│   └── MARCImportJob (非同步)
│       ├── create_folio_import_job()
│       ├── set_job_profile()
│       ├── process_records()
│       └── get_job_status()
│
└── main() in BatchPoster.py
    └── BatchPoster (非同步)
        ├── post_batch()
        ├── fetch_existing_records()
        └── rerun_failed_records_one_by_one()
```

**設計特點**
- 完全非同步設計（asyncio）
- CLI 優先的介面設計
- 獨立的功能模組，無繼承關係
- 使用 Context Manager 模式管理資源

### 1.3 架構比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| 設計模式 | 繼承 + 任務鏈 | 組合 + 獨立模組 |
| 執行方式 | 同步為主 | 完全非同步 |
| 設定管理 | Pydantic BaseModel | Pydantic BaseModel |
| 入口點 | 統一的遷移框架 | 獨立 CLI 工具 |
| 擴展性 | 透過繼承擴展 | 透過組合擴展 |

---

## 2. 資料轉換流程的不同（處理步驟、中間格式）

### 2.1 folio_migration_tools 轉換流程

```
原始 MARC 記錄 (Binary .mrc 檔案)
        ↓
MarcFileProcessor
  - 驗證 MARC 記錄格式
  - 提取個別記錄
        ↓
BibsRulesMapper
  - 套用 marc-instance-mapping-rules.json 對應規則
  - 轉換 MARC 欄位為 FOLIO Instance 欄位
  - 套用參照資料查詢（館藏地、狀態等）
  - 產生 Instance 與 SRS 記錄的 UUID
  - 處理舊系統 ID 對應
        ↓
中間輸出 (JSONL 格式)
  - 每行一筆 JSON 記錄
  - Tab 分隔格式：[空欄位]\t[JSON 記錄]
        ↓
Extradata 提取
  - 附註、前後關聯題名等分離處理
        ↓
最終輸出檔案
  - folio_instances_{task}.json
  - folio_srs_instances_{task}.json
  - folio_extradata_{task}.jsonl (選用)
        ↓
BatchPoster 讀取輸出檔案
        ↓
批次處理（可設定批次大小）
        ↓
API 發送到 FOLIO
```

**格式轉換範例**

輸入：MARC 格式
```
Leader: 00000nam a2200000 a 4500
001: 12345
245: $a 書籍標題 $c 作者名
```

輸出：FOLIO Instance JSON
```json
{
  "id": "uuid",
  "hrid": "in12345",
  "source": "MARC",
  "title": "書籍標題",
  "contributors": [{"name": "作者名", "contributorTypeId": "..."}],
  "identifiers": [{"value": "12345", "identifierTypeId": "..."}],
  "administrativeNotes": ["Legacy ID: 12345"]
}
```

輸出：FOLIO SRS JSON
```json
{
  "id": "uuid",
  "recordType": "MARC_BIB",
  "sourceId": "...",
  "parsedRecord": {
    "id": "uuid",
    "content": {/* 二進位 MARC 資料的 JSON 表示 */}
  }
}
```

### 2.2 folio_data_import 轉換流程

```
MARC 二進位檔案
        ↓
pymarc.MARCReader
  - 讀取二進位 MARC 記錄 (0x1D 終止符)
  - 驗證記錄格式
        ↓
Marc Record Preprocessors (選用)
  - 移除欄位
  - 正規化資料
  - 新增/修改欄位
        ↓
as_marc() 轉換
  - 記錄轉回二進位格式
        ↓
批次累積
  - 建立 N 筆記錄的批次（可設定）
  - 每筆編碼為 base64 JSON 表示
        ↓
批次酬載 (Batch Payload)
{
  "id": "uuid",
  "recordsMetadata": {
    "last": boolean,
    "counter": int,
    "contentType": "MARC_RAW",
    "total": int
  },
  "initialRecords": [
    {"record": "base64_encoded_marc"}
  ]
}
        ↓
POST 到 /change-manager/jobExecutions/{job_id}/records
        ↓
FOLIO 處理
  - Data Import profile 轉換 MARC → Instances
  - 在 FOLIO 中建立/更新記錄
        ↓
任務狀態輪詢
  - 監控 /metadata-provider/jobExecutions
  - 更新進度條
        ↓
任務摘要
{
  "jobExecutionId": "uuid",
  "totalRecords": int,
  "BIBLIOGRAPHIC": {
    "created": int,
    "updated": int,
    "error": int
  }
}
```

### 2.3 流程比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| 轉換位置 | 本地工具執行 | FOLIO 伺服器端執行 |
| 對應規則 | 外部 JSON 對應規則檔 | FOLIO Data Import Profile |
| 中間格式 | JSONL (轉換後的 Instance/SRS) | Base64 編碼的原始 MARC |
| SRS 建立 | 工具直接產生 | Data Import 自動建立 |
| 彈性度 | 高（可自訂對應規則） | 中（依賴 FOLIO profile） |

---

## 3. 設定檔格式與使用方式的差異

### 3.1 folio_migration_tools 設定檔

**主設定檔結構** (`exampleConfiguration.json`)
```json
{
  "libraryInformation": {
    "tenantId": "diku",
    "okapiUrl": "https://folio-dev.example.com",
    "okapiUsername": "admin",
    "libraryName": "範例圖書館",
    "folioRelease": "quesnelia",
    "addTimeStampToFileNames": true,
    "iterationIdentifier": "iteration_1",
    "multiFieldDelimiter": "<^>",
    "logLevelDebug": false
  },
  "migrationTasks": [
    {
      "name": "transform_bibs",
      "migrationTaskType": "BibsTransformer",
      "ilsFlavour": "tag001",
      "files": [
        {
          "file_name": "bibs.mrc",
          "discovery_suppressed": false
        }
      ],
      "tags_to_delete": ["590", "938"],
      "addAdministrativeNotesWithLegacyIds": true,
      "updateHridSettings": false
    },
    {
      "name": "post_instances",
      "migrationTaskType": "BatchPoster",
      "objectType": "Instances",
      "batchSize": 250,
      "rerunFailedRecords": true,
      "usesSafeInventoryEndpoints": true,
      "files": [
        {
          "file_name": "folio_instances_transform_bibs.json"
        }
      ]
    }
  ]
}
```

**BibsTransformer 設定參數**
```python
class TaskConfiguration(MarcTaskConfigurationBase):
    ils_flavour: IlsFlavour          # "tag001", "custom", "aleph" 等
    custom_bib_id_field: str         # 預設 "001"，可設為 "991$a"
    add_administrative_notes_with_legacy_ids: bool  # 預設 True
    tags_to_delete: List[str]        # 要刪除的 MARC 欄位
    data_import_marc: bool           # 產生二進位 MARC 檔案（預設 True）
    parse_cataloged_date: bool       # 解析日期欄位（預設 False）
    reset_hrid_settings: bool        # 重設 HRID 計數器（預設 False）
    update_hrid_settings: bool       # 更新 FOLIO HRID 設定（預設 True）
```

**對應檔案類型**

1. **JSON 對應檔案**（複雜轉換）
   - `marc-instance-mapping-rules.json`
   - `holdingsrecord_mapping.json`
   - `item_mapping_for_*.json`

2. **TSV 參照資料檔案**（簡單查詢對應）
   - `locations.tsv`
   - `material_types.tsv`
   - `loan_types.tsv`

### 3.2 folio_data_import 設定檔

**CLI 參數方式**
```bash
folio-marc-data-import \
  --gateway-url https://folio-dev.example.com \
  --tenant-id diku \
  --username admin \
  --password <your_password> \
  --marc-file-paths bibs.mrc \
  --import-profile-name "Default MARC-to-Instance" \
  --batch-size 50 \
  --batch-delay 0.5
```

**JSON 設定檔方式**
```json
{
  "marc_files": ["bibs.mrc"],
  "import_profile_name": "Default MARC-to-Instance",
  "batch_size": 10,
  "batch_delay": 0,
  "no_progress": false,
  "no_summary": false,
  "split_files": false,
  "split_size": 1000,
  "job_ids_file_path": "marc_import_job_ids.txt"
}
```

**MARCImportJob 設定參數**
```python
class Config(BaseModel):
    marc_files: List[Path]           # MARC 檔案清單
    import_profile_name: str         # Data Import Job Profile 名稱
    batch_size: int                  # 每批次記錄數（1-1000，預設 10）
    batch_delay: float               # 批次間延遲秒數（預設 0）
    marc_record_preprocessors: List[Callable] | str | None  # 前處理器
    no_progress: bool                # 停用進度條
    no_summary: bool                 # 略過最終摘要
    split_files: bool                # 分割大型檔案
    split_size: int                  # 每分割檔案記錄數（預設 1000）
    job_ids_file_path: Path | None   # 儲存 Job ID 的檔案
```

### 3.3 設定檔比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| 設定方式 | 必須使用 JSON 設定檔 | CLI 參數或 JSON 設定檔 |
| 任務定義 | 支援多任務鏈 | 單一任務執行 |
| 對應規則 | 外部對應檔案 | FOLIO 內建 Profile |
| 彈性度 | 高度可設定 | 較為簡化 |
| 學習曲線 | 較高 | 較低 |

---

## 4. 批次處理機制的差異

### 4.1 folio_migration_tools 的 batch_poster.py

**同步批次發送**
```python
def post_batch(self, batch, failed_recs_file, num_records):
    # 1. 若為 upsert 操作，取得現有記錄版本
    if self.query_params.get("upsert", False):
        self.set_version(batch, query_endpoint, object_type)

    # 2. 準備酬載
    if object_name == "users":
        payload = {"users": batch, "totalRecords": len(batch)}
    elif total_records:
        payload = {"records": batch, "totalRecords": len(batch)}
    else:
        payload = {object_name: batch}

    # 3. POST 到 API
    response = http_client.post(url, json=payload, params=query_params)

    # 4. 處理回應
    if response.status_code == 201:
        # 成功
    elif response.status_code == 200:
        # 批次處理端點回應
        json_report = json.loads(response.text)
        created = json_report.get("createdRecords", 0)
        updated = json_report.get("updatedRecords", 0)
        failed = json_report.get("failedRecords", 0)
```

**API 端點對應**
```python
"Instances"       → "/instance-storage/batch/synchronous"
"Holdings"        → "/holdings-storage/batch/synchronous"
"Items"           → "/item-storage/batch/synchronous"
"ShadowInstances" → "/instance-storage/batch/synchronous"
"Users"           → "/user-import"
"Organizations"   → "/organizations/organizations"
"Orders"          → "/orders/composite-orders"
"Extradata"       → 自訂端點（附註、合訂本、課程等）
```

**重試機制**
```python
def rerun_run():
    if failed_records_exist:
        batch_size = 1                    # 改為單筆處理
        files = [failed_records_file]
        rerun_failed_records = False
        do_work()                         # 逐筆重試失敗記錄
```

### 4.2 folio_data_import 的 BatchPoster.py

**非同步批次發送**
```python
async def post_batch(batch):
    # 1. 追蹤新建與更新數量
    num_creates = 0
    num_updates = 0

    # 2. 若為 ShadowInstances，轉換來源為聯盟格式
    if object_type == "ShadowInstances":
        set_consortium_source(record)

    # 3. 若為 upsert，取得並準備版本
    if upsert:
        await set_versions_for_upsert(batch)
        for record in batch:
            if "_version" in record:
                num_updates += 1
            else:
                num_creates += 1

    # 4. 建立酬載並發送
    payload = {object_name: batch}
    response = await http_client.post(api_endpoint, json=payload, params=query_params)

    return response, num_creates, num_updates
```

**並行取得版本（Upsert 用）**
```python
async def fetch_existing_records(record_ids):
    fetch_batch_size = 90  # FOLIO CQL OR 查詢限制

    # 建立並行取得任務
    tasks = []
    for i in range(0, len(record_ids), fetch_batch_size):
        batch_slice = record_ids[i:i+fetch_batch_size]
        query = f"id==({' OR '.join(batch_slice)})"
        tasks.append(folio_get_async(query_endpoint, params={"query": query}))

    # 並行執行所有取得任務
    results = await asyncio.gather(*tasks)
    return existing_records
```

**Context Manager 模式**
```python
async with BatchPoster(...) as poster:
    stats = await poster.do_work(files)
    if config.rerun_failed_records:
        await poster.rerun_failed_records_one_by_one()
```

### 4.3 批次處理比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| 執行模式 | 同步 | 非同步 (asyncio) |
| API 端點 | Storage APIs (/instance-storage/batch) | Change Manager API |
| 版本查詢 | 混合（非同步查詢） | 完全非同步 |
| 並行度 | 低 | 高 |
| 批次大小 | 可大量設定（如 250） | 較小（預設 10） |
| 資源管理 | 傳統方式 | Context Manager |

---

## 5. 錯誤處理機制的比較

### 5.1 folio_migration_tools 錯誤處理

**自訂例外類別**
```python
class TransformationProcessError(Exception):
    """致命的程序層級錯誤"""
    pass

class TransformationRecordFailedError(Exception):
    """個別記錄失敗"""
    pass
```

**HTTP 錯誤處理**
```python
if status_code == 401:
    # 重新認證並重試
    folio_client.login()
    retry_post()

elif status_code == 422:
    # 驗證錯誤 - 記錄層級失敗
    write_to_failed_records_file()
    continue

elif status_code == 400:
    # JSON 解析錯誤 - 致命
    raise TransformationProcessError()

elif status_code == 413 and "DB_ALLOW_SUPPRESS_OPTIMISTIC_LOCKING" in response:
    # 樂觀鎖問題 - 致命
    raise TransformationProcessError()
```

**失敗記錄追蹤**
- 寫入 `failed_records_recs_{task}.jsonl`
- JSONL 格式（每行一個 JSON 物件）
- 預設啟用自動重試
- 差異偵測（處理記錄數 vs 伺服器記錄數）

### 5.2 folio_data_import 錯誤處理

**自訂例外類別**
```python
class FolioDataImportError(Exception):
    """基礎例外"""
    pass

class FolioDataImportBatchError(FolioDataImportError):
    """批次發送失敗"""
    batch_id: str
    message: str

class FolioDataImportJobError(FolioDataImportError):
    """任務執行失敗"""
    job_id: str
    message: str
```

**HTTP 錯誤處理與重試策略**
```python
# 連線錯誤 - 總是重試
if isinstance(e, folioclient.FolioConnectionError):
    retry_with_exponential_backoff()  # 最多 3 次，退避 2^attempt 秒

# 伺服器錯誤 (5xx) - 重試
elif e.response.status_code >= 500:
    retry_with_exponential_backoff()

# 速率限制 (429) - 延長等待後重試
elif e.response.status_code == 429:
    retry_with_5_second_wait()

# 客戶端錯誤 (4xx 除 429) - 不重試
elif e.response.status_code in [401, 404, 422]:
    raise_immediately()
```

**任務層級重試**
```python
if FolioDataImportJobError:
    if retry_count < MAX_JOB_RETRIES (2):
        cancel_current_job()
        retry_import_marc_file()
    else:
        log_critical_error_and_exit()
```

### 5.3 錯誤處理比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| 例外架構 | 2 個類別（程序/記錄） | 3 個類別（基礎/批次/任務） |
| 重試策略 | 自動重試失敗記錄 | 指數退避 + 任務重試 |
| 認證錯誤 | 重新登入並重試 | 直接失敗 |
| 失敗記錄儲存 | JSONL 格式 | JSONL 或 MARC 格式 |
| 任務取消 | 不支援 | 支援任務取消 |

---

## 6. 轉出的檔案類型及格式差異

### 6.1 folio_migration_tools 輸出檔案

| 檔案名稱 | 格式 | 說明 |
|---------|------|------|
| `folio_instances_{task}.json` | JSONL | 轉換後的 Instance 記錄 |
| `folio_srs_instances_{task}.json` | JSONL | SRS (Source Record Storage) 記錄 |
| `folio_extradata_{task}.jsonl` | JSONL | 附加資料（附註、前後關聯等） |
| `failed_records_recs_{task}.jsonl` | JSONL | 失敗的記錄 |
| `{task}_migration_report.md` | Markdown | 遷移報告 |
| `{task}_migration_report.json` | JSON | 遷移報告（機器可讀） |
| `{task}.mrc` | Binary MARC | 用於 Data Import overlay（選用） |

**Instance JSONL 格式範例**
```json
{"id":"uuid-1","hrid":"in00001","title":"書籍標題1","source":"MARC",...}
{"id":"uuid-2","hrid":"in00002","title":"書籍標題2","source":"MARC",...}
```

### 6.2 folio_data_import 輸出檔案

| 檔案名稱 | 格式 | 說明 |
|---------|------|------|
| `bad_marc_records_{timestamp}.mrc` | Binary MARC | 無法解析的 MARC 記錄 |
| `failed_batches_{timestamp}.mrc` | Binary MARC | HTTP 發送失敗的批次 |
| `marc_import_job_ids.txt` | Text | 所有任務 UUID 記錄 |
| `failed_records_{object_type}.jsonl` | JSONL | BatchPoster 失敗記錄 |

**任務摘要輸出範例**
```
Summary     | BIBLIOGRAPHIC
------------|---------------
created     | 1000
updated     | 50
error       | 5
Total errors: 5, Job ID: abc123-...
```

### 6.3 輸出檔案比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| 主要輸出 | 轉換後的 JSON 記錄 | 無（直接匯入 FOLIO） |
| 失敗記錄 | JSONL | Binary MARC 或 JSONL |
| 報告格式 | Markdown + JSON | 控制台表格 |
| 稽核追蹤 | 遷移報告 | Job ID 檔案 |

---

## 7. Instances 與 SRS Records 的處理差異

### 7.1 folio_migration_tools 的處理方式

**Instance 記錄**
- 由工具直接從 MARC 轉換產生
- 包含完整的書目資料（標題、作者、識別碼、分類號等）
- 可透過 `add_administrative_notes_with_legacy_ids` 設定加入舊系統 ID
- 支援透過設定控制 discovery suppression

**SRS 記錄**
- 由工具產生，與 Instance 平行
- 透過共用的 source ID 與 Instance 連結
- 保存原始 MARC 資料於 `parsedRecord.content`
- 支援 overlay 更新與 MARC 保存工作流程

**關聯性**
```
Instance Record ←——1:1——→ SRS Record
     ↑                        ↑
     │                        │
  [FOLIO 詮釋資料]       [原始 MARC 資料]
     │                        │
     └── 透過 sourceId 連結 ──┘
```

**程式碼層級處理**
```python
# BibsTransformer 中
def transform_record(marc_record):
    # 產生 Instance
    instance = mapper.transform_marc_to_instance(marc_record)

    # 產生 SRS
    srs_record = {
        "id": str(uuid.uuid4()),
        "recordType": "MARC_BIB",
        "sourceId": instance["id"],
        "parsedRecord": {
            "content": marc_record_as_json
        }
    }

    return instance, srs_record
```

### 7.2 folio_data_import 的處理方式

**Instance 記錄**
- 不直接由工具產生
- 將原始 MARC 資料發送到 Data Import Profile
- 由 FOLIO 伺服器端的 Data Import Profile 執行 MARC → Instance 轉換
- Instance 欄位對應由 FOLIO 內建的 Profile 規則決定

**SRS 記錄**
- 由 Data Import 自動建立，作為 MARC 儲存
- 工具無需處理 SRS 產生邏輯
- 與 Instance 的連結由 FOLIO 自動管理

**BatchPoster 的 Instance 處理**
- 可發送預先轉換的 Instance
- 支援 ShadowInstances 用於聯盟環境
- 對 ShadowInstances，來源欄位會加上前綴：`"MARC"` → `"CONSORTIUM-MARC"`
- MARC 來源的 Instance 記錄有保護機制（patch paths 受限）

```python
# BatchPoster 中的 ShadowInstances 處理
if object_type == "ShadowInstances":
    for record in batch:
        set_consortium_source(record)  # 修改 source 欄位
```

### 7.3 Instance/SRS 處理比較表

| 面向 | folio_migration_tools | folio_data_import |
|------|----------------------|-------------------|
| Instance 產生位置 | 本地工具 | FOLIO 伺服器 |
| SRS 產生位置 | 本地工具 | FOLIO 伺服器 |
| 對應規則控制 | 外部 JSON 檔案 | FOLIO Data Import Profile |
| 欄位轉換彈性 | 高（可完全自訂） | 中（依賴 Profile） |
| 聯盟支援 | ECS tenant 支援 | ShadowInstances 模式 |

---

## 8. 各自的優缺點與適用場景建議

### 8.1 folio_migration_tools

**優點**
1. **完整的遷移框架**：支援使用者、訂單、課程等多種資料類型
2. **本地轉換控制**：可完全自訂 MARC 到 Instance 的對應規則
3. **豐富的 Upsert 選項**：支援保留統計代碼、行政附註、暫時館藏地等
4. **任務鏈支援**：可在單一設定檔中定義多個連續任務
5. **詳細的遷移報告**：產生 Markdown 與 JSON 格式報告
6. **Extradata 處理**：支援附註、合訂本、前後關聯等複雜資料
7. **離線轉換**：可先轉換再批次匯入，便於檢查與修正

**缺點**
1. **學習曲線較高**：設定檔格式複雜，需理解多種對應檔案
2. **同步執行**：處理大量資料時效能較低
3. **設定檔必要**：無法透過簡單的命令列參數執行
4. **維護成本**：需要維護外部對應規則檔案

**適用場景**
- 從舊有 ILS 系統進行完整遷移
- 需要同時遷移館藏、單件、使用者等多種資料
- 需要高度自訂的 MARC 轉換規則
- 需要離線轉換並檢查結果
- 複雜的 Upsert 需求（保留特定欄位）

### 8.2 folio_data_import

**優點**
1. **簡化的介面**：CLI 優先設計，快速上手
2. **非同步效能**：完全非同步設計，處理效能較佳
3. **即時進度追蹤**：Rich 進度條顯示上傳與處理進度
4. **FOLIO 原生整合**：使用 FOLIO 的 Data Import API
5. **檔案分割支援**：可自動分割大型 MARC 檔案
6. **任務追蹤**：自動記錄所有 Job ID 供稽核使用
7. **Preprocessors**：支援 MARC 記錄前處理

**缺點**
1. **功能範圍較窄**：僅支援 MARC 匯入
2. **依賴 FOLIO Profile**：轉換規則受限於 FOLIO 內建的 Data Import Profile
3. **較少離線控制**：無法在匯入前詳細檢視轉換結果
4. **較小批次**：預設批次大小較小，可能影響大量資料處理

**適用場景**
- 遷移後的定期 MARC 記錄匯入
- 使用現有 Data Import Profile 進行 overlay 更新
- 需要即時進度追蹤的作業
- 僅需匯入 MARC 資料（不涉及館藏/單件）
- 偏好 CLI 操作的工作流程

### 8.3 決策流程圖

```
開始
  │
  ▼
是否為完整的系統遷移？
  │
  ├── 是 ──→ 使用 folio_migration_tools
  │
  ▼
是否需要遷移多種資料類型（使用者、訂單等）？
  │
  ├── 是 ──→ 使用 folio_migration_tools
  │
  ▼
是否需要高度自訂的 MARC 對應規則？
  │
  ├── 是 ──→ 使用 folio_migration_tools
  │
  ▼
是否僅需匯入 MARC 記錄？
  │
  ├── 是 ──→ 使用 folio_data_import
  │
  ▼
是否偏好簡單的 CLI 介面？
  │
  ├── 是 ──→ 使用 folio_data_import
  │
  ▼
使用 folio_migration_tools（預設）
```

### 8.4 總結比較表

| 評估面向 | folio_migration_tools | folio_data_import |
|---------|----------------------|-------------------|
| **功能範圍** | 廣泛（多種資料類型） | 專注（僅 MARC） |
| **使用複雜度** | 高 | 低 |
| **效能** | 中 | 高（非同步） |
| **彈性度** | 高 | 中 |
| **學習曲線** | 陡峭 | 平緩 |
| **維護成本** | 高 | 低 |
| **適用規模** | 大型遷移專案 | 日常匯入作業 |
| **最佳使用情境** | 系統遷移 | 持續性資料匯入 |

---

## 附錄：關鍵程式碼位置參考

### folio_migration_tools
- 核心轉換：`folio_migration_tools/migration_tasks/bibs_transformer.py`
- 批次發送：`folio_migration_tools/migration_tasks/batch_poster.py`
- 設定範本：`migration_repo_template/mapping_files/exampleConfiguration.json`

### folio_data_import
- MARC 匯入：`folio_data_import/MARCDataImport.py`
- 批次發送：`folio_data_import/BatchPoster.py`
- 例外定義：`folio_data_import/custom_exceptions.py`
