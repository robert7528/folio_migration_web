# FOLIO Migration Tools - Task Configuration JSON 配置檔完整分析

本文件分析 `folio_migration_tools` 的 Task Configuration JSON 配置檔結構和用法。

## 目錄

- [一、基本結構和必要欄位](#一基本結構和必要欄位)
- [二、三個配置檔的差異和特色](#二三個配置檔的差異和特色)
- [三、不同 migrationTaskType 的配置方式](#三不同-migrationtasktype-的配置方式)
- [四、常用參數的意義和設定建議](#四常用參數的意義和設定建議)
- [五、配置檔如何對應到轉檔程式](#五配置檔如何對應到轉檔程式)
- [六、最佳實踐建議](#六最佳實踐建議)

---

## 一、基本結構和必要欄位

配置檔由兩個主要區塊組成：

```json
{
  "libraryInformation": { ... },   // 圖書館/租戶設定
  "migrationTasks": [ ... ]        // 遷移任務陣列
}
```

### 1.1 libraryInformation（必要欄位）

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| `tenantId` | string | FOLIO 租戶 ID | `"fs00001280"` |
| `okapiUrl` / `gatewayUrl` | string | FOLIO API 閘道 URL | `"https://api-thu.folio.ebsco.com"` |
| `okapiUsername` / `folioUsername` | string | API 登入帳號 | `"EBSCOAdmin"` |
| `folioRelease` | enum | FOLIO 版本 | `"sunflower"`, `"orchid"`, `"trillium"` |
| `iterationIdentifier` | string | 迭代目錄名稱 | `"current"`, `"test_run"` |

### 1.2 libraryInformation（選用欄位）

| 欄位 | 預設值 | 說明 |
|------|--------|------|
| `multiFieldDelimiter` | `"<delimiter>"` | 多值欄位分隔符 |
| `logLevelDebug` | `false` | 啟用除錯日誌 |
| `addTimeStampToFileNames` | `false` | 輸出檔名加時間戳記 |
| `failedPercentageThreshold` | `20` | 失敗比例閾值（%） |
| `libraryName` | - | 圖書館名稱（僅供識別） |
| `ecsTenantId` | `""` | ECS 環境的租戶 ID |

### 1.3 migrationTasks 任務定義（必要欄位）

每個任務至少需要：

```json
{
  "name": "任務名稱",           // 用於呼叫和識別
  "migrationTaskType": "類型"   // 決定執行哪個 Transformer
}
```

---

## 二、三個配置檔的差異和特色

### 2.1 比較總覽

| 特性 | exampleConfiguration | icMigrationTestConfiguration | taskConfig (THU) |
|------|---------------------|------------------------------|------------------|
| **用途** | 範本/教學 | 整合測試（完整功能展示） | 實際生產環境 |
| **FOLIO 版本** | orchid | sunflower | sunflower |
| **任務數量** | 3 個 | 30+ 個 | 15 個 |
| **複雜度** | 基礎 | 非常完整 | 中等 |
| **分隔符** | `<^>` | `;` | `<^>` |
| **批次大小** | 250 | 250 | 500-1000 |

### 2.2 exampleConfiguration.json（範本）

最簡配置，只有 bibs 轉換和發布：

```json
{
  "name": "transform_bibs",
  "migrationTaskType": "BibsTransformer",
  "ilsFlavour": "tag001",
  "files": [{ "file_name": "FILE_NAME.mrc" }]
}
```

**特點：**
- 適合初學者理解基本結構
- 僅包含書目轉換的最小必要設定
- 使用佔位符提示使用者填入實際值

### 2.3 icMigrationTestConfiguration.json（測試）

**特點：**
- 涵蓋所有任務類型：
  - Authority（權威記錄）
  - Bibs（書目）
  - Holdings（MARC + CSV 兩種格式）
  - Items（館藏項目）
  - Users（讀者）
  - Loans（借閱）
  - Requests（預約請求）
  - Courses（課程）
  - Organizations（組織/供應商）
  - Orders（訂單）
  - FeeFines（費用罰款）

- 展示進階功能：
  - `boundwithRelationshipFilePath`：合訂本關係
  - `holdingsMergeCriteria`：館藏合併條件
  - `previouslyGeneratedHoldingsFiles`：引用先前產生的檔案

### 2.4 taskConfig.json（THU 生產）

實際使用的配置，包含特定設定：

```json
{
  "name": "bibs",
  "useTenantMappingRules": true,      // 使用租戶規則
  "deactivate035From001": true,        // 停用 035 自動生成
  "tagsToDelete": ["095", "809", "949", "999"]  // 刪除特定 MARC 欄位
}
```

**特點：**
- 較大的批次大小（500-1000）以提升效能
- 針對特定資料格式的客製化設定
- 包含完整的 Inventory 和 Circulation 遷移流程

---

## 三、不同 migrationTaskType 的配置方式

### 3.1 BibsTransformer（書目轉換）

```json
{
  "name": "bibs",
  "migrationTaskType": "BibsTransformer",
  "ilsFlavour": "tag001",                    // 必要：ILS 類型
  "files": [{ "file_name": "bibs.mrc" }],    // 必要：來源檔案
  "tagsToDelete": ["095", "999"],            // 刪除 MARC 欄位
  "hridHandling": "default",                 // HRID 處理方式
  "addAdministrativeNotesWithLegacyIds": true,
  "createSourceRecords": true,               // 是否建立 SRS
  "updateHridSettings": true,
  "resetHridSettings": false
}
```

**程式碼對應：** `bibs_transformer.py:26-106`

```python
class TaskConfiguration(MarcTaskConfigurationBase):
    ils_flavour: IlsFlavour          # 必要
    tags_to_delete: List[str] = []
    add_administrative_notes_with_legacy_ids: bool = True
    # ...
```

### 3.2 HoldingsMarcTransformer（MARC 館藏轉換）

```json
{
  "name": "holdingsmarc",
  "migrationTaskType": "HoldingsMarcTransformer",
  "legacyIdMarcPath": "001",
  "locationMapFileName": "locations.tsv",           // 必要
  "fallbackHoldingsTypeId": "xxx-uuid-xxx",         // 必要
  "defaultCallNumberTypeName": "Dewey Decimal classification",
  "createSourceRecords": false,
  "boundwithRelationshipFilePath": "bound_with.tsv"  // 選用：合訂本
}
```

### 3.3 HoldingsCsvTransformer（CSV 館藏轉換）

```json
{
  "name": "holdings",
  "migrationTaskType": "HoldingsCsvTransformer",
  "holdingsMapFileName": "holdings_mapping.json",   // 欄位對應
  "locationMapFileName": "locations.tsv",
  "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
  "holdingsMergeCriteria": ["instanceId", "permanentLocationId", "callNumber"],
  "previouslyGeneratedHoldingsFiles": ["folio_holdings_mfhd.json"]
}
```

**holdingsMergeCriteria 說明：**
- 當多筆來源記錄符合相同條件時，合併為單一 Holdings 記錄
- 常用組合：`instanceId` + `permanentLocationId` + `callNumber`

### 3.4 ItemsTransformer（館藏項目轉換）

```json
{
  "name": "items",
  "migrationTaskType": "ItemsTransformer",
  "itemsMappingFileName": "item_mapping.json",      // 必要
  "locationMapFileName": "locations.tsv",           // 必要
  "materialTypesMapFileName": "material_types.tsv", // 必要
  "loanTypesMapFileName": "loan_types.tsv",         // 必要
  "itemStatusesMapFileName": "item_statuses.tsv",
  "statisticalCodesMapFileName": "statcodes.tsv",
  "callNumberTypeMapFileName": "call_number_type_mapping.tsv"
}
```

**必要的對應檔案：**
- `item_mapping.json`：欄位對應定義
- `locations.tsv`：館藏地對應
- `material_types.tsv`：資料類型對應
- `loan_types.tsv`：借閱類型對應

### 3.5 UserTransformer（讀者轉換）

```json
{
  "name": "users",
  "migrationTaskType": "UserTransformer",
  "userMappingFileName": "user_mapping.json",
  "groupMapPath": "user_groups.tsv",
  "departmentsMapPath": "user_departments.tsv",
  "useGroupMap": true,
  "userFile": { "file_name": "users.tsv" }   // 注意：單檔，非陣列
}
```

**注意事項：**
- `userFile` 是單一檔案物件，不是陣列
- `useGroupMap` 控制是否使用群組對應檔

### 3.6 BatchPoster（批次發布）

```json
{
  "name": "bibs_poster",
  "migrationTaskType": "BatchPoster",
  "objectType": "Instances",   // 物件類型
  "batchSize": 500,
  "files": [{ "file_name": "folio_instances_bibs.json" }]
}
```

**支援的 objectType：**
- `Instances`：書目實例
- `Holdings`：館藏記錄
- `Items`：館藏項目
- `Users`：讀者
- `SRS`：來源記錄儲存
- `Extradata`：額外資料（Notes、Permissions 等）
- `Orders`：訂單
- `Authorities`：權威記錄

### 3.7 LoansMigrator（借閱遷移）

```json
{
  "name": "loans",
  "migrationTaskType": "LoansMigrator",
  "fallbackServicePointId": "xxx-uuid-xxx",    // 必要：預設服務點
  "startingRow": 1,
  "utcDifference": 6,                          // 時區差異（小時）
  "openLoansFiles": [{ "file_name": "open_loans.tsv" }],
  "item_files": [{ "file_name": "folio_items.json" }],
  "patron_files": [{ "file_name": "folio_users.json" }]
}
```

**注意事項：**
- 需要先完成 Items 和 Users 的轉換
- `utcDifference` 用於時區轉換

### 3.8 其他任務類型

| 任務類型 | 用途 | 主要設定 |
|----------|------|----------|
| `AuthorityTransformer` | 權威記錄轉換 | `ilsFlavour`, `files` |
| `RequestsMigrator` | 預約請求遷移 | `openRequestsFile`, `item_files`, `patron_files` |
| `CoursesMigrator` | 課程遷移 | `compositeCourseMapPath`, `termsMapPath` |
| `ReservesMigrator` | 課程預約遷移 | `locationMapPath`, `courseReserveFilePath` |
| `OrganizationTransformer` | 組織/供應商轉換 | `organizationMapPath`, `organizationTypesMapPath` |
| `OrdersTransformer` | 訂單轉換 | `ordersMappingFileName`, `acquisitionMethodMapFileName` |
| `ManualFeeFinesTransformer` | 費用罰款轉換 | `feefinesMap`, `feefinesOwnerMap` |

---

## 四、常用參數的意義和設定建議

### 4.1 HRID 處理（hridHandling）

```python
class HridHandling(str, Enum):
    default = "default"        # FOLIO 自動編號，001 移到 035
    preserve001 = "preserve001" # 保留 001 作為 HRID
```

| 情境 | 建議設定 | 說明 |
|------|----------|------|
| 全新遷移 | `default` | 讓 FOLIO 產生新的 HRID |
| 需保留原系統編號 | `preserve001` | 保持與原系統一致 |
| 多來源合併 | `default` | 避免 HRID 衝突 |

### 4.2 ILS Flavour（ilsFlavour）

```python
class IlsFlavour(str, Enum):
    aleph = "aleph"           # Ex Libris Aleph
    voyager = "voyager"       # Ex Libris Voyager
    sierra = "sierra"         # III Sierra
    millennium = "millennium" # III Millennium
    koha = "koha"            # Koha
    tag001 = "tag001"        # 通用（使用 001 作為 ID）
    custom = "custom"        # 搭配 customBibIdField 使用
    none = "none"            # 不處理 legacy ID
```

**選擇建議：**
- 如果您使用的 ILS 在清單中，選擇對應的選項
- 如果不確定，使用 `tag001`（最通用）
- 如果 legacy ID 在非標準欄位，使用 `custom` 並設定 `customBibIdField`

### 4.3 批次大小（batchSize）

| objectType | 建議 batchSize | 說明 |
|------------|---------------|------|
| Instances | 250-500 | 平衡速度和記憶體 |
| Holdings | 500-1000 | 記錄較小 |
| Items | 500-1000 | 記錄較小 |
| Users | 250 | 含複雜權限資料 |
| SRS | 250 | MARC 較大 |
| Extradata | 1 | 需逐筆處理 |
| Orders | 1 | 複雜物件，需逐筆 |

### 4.4 檔案定義（FileDefinition）

```json
{
  "file_name": "bibs.mrc",
  "discovery_suppressed": false,    // OPAC 隱藏
  "staff_suppressed": false,        // 員工介面隱藏
  "create_source_records": true,    // 建立 SRS 記錄
  "statistical_code": "MIGRATION"   // 統計代碼
}
```

**欄位說明：**
- `discovery_suppressed`：設為 `true` 時，記錄不會出現在 OPAC
- `staff_suppressed`：設為 `true` 時，記錄對員工也隱藏
- `create_source_records`：控制是否在 SRS 中保留 MARC 原始記錄
- `statistical_code`：用於追蹤遷移來源

### 4.5 錯誤處理閾值

```json
{
  "failedRecordsThreshold": 5000,      // 失敗記錄數量上限
  "failedPercentageThreshold": 20,     // 失敗比例上限（%）
  "genericExceptionThreshold": 50      // 一般例外上限
}
```

**建議設定：**
- 測試階段：較高的閾值（如 25%）允許發現更多問題
- 生產階段：較低的閾值（如 5%）確保資料品質

---

## 五、配置檔如何對應到轉檔程式

### 5.1 執行流程

```
配置 JSON
    ↓
LibraryConfiguration (library_configuration.py:101)
    ↓
AbstractTaskConfiguration (task_configuration.py:12)
    ↓
具體 TaskConfiguration（各 Transformer 內定義）
    ↓
MigrationTaskBase.__init__ (migration_task_base.py:40)
    ↓
具體 Transformer.do_work()
```

### 5.2 BibsTransformer 對應關係

**配置檔欄位 → 程式碼位置**

| JSON 欄位 | Python 屬性 | 定義位置 |
|-----------|-------------|----------|
| `ilsFlavour` | `task_config.ils_flavour` | `bibs_transformer.py:27-34` |
| `tagsToDelete` | `task_config.tags_to_delete` | `bibs_transformer.py:58-68` |
| `files` | `task_configuration.files` | `migration_task_base.py:470-476` |
| `hridHandling` | `task_config.hrid_handling` | `migration_task_base.py:486-496` |
| `createSourceRecords` | `task_config.create_source_records` | `migration_task_base.py:477-485` |

### 5.3 初始化流程

`bibs_transformer.py:112-145`：

```python
def __init__(self, task_config, library_config, folio_client):
    super().__init__(library_config, task_config, folio_client)

    # 1. 載入統計代碼對應
    if self.task_config.statistical_codes_map_file_name:
        statcode_mapping = self.load_ref_data_mapping_file(...)

    # 2. 檢查來源檔案存在
    self.check_source_files(
        self.folder_structure.legacy_records_folder,
        self.task_configuration.files
    )

    # 3. 初始化 MARC 規則映射器
    self.mapper = BibsRulesMapper(
        self.folio_client, library_config, self.task_configuration
    )

    # 4. 處理 HRID 重設
    if task_config.reset_hrid_settings and task_config.update_hrid_settings:
        self.mapper.hrid_handler.reset_instance_hrid_counter()
```

### 5.4 命名轉換（Camel Case ↔ Snake Case）

配置檔使用 camelCase，Python 使用 snake_case，由 Pydantic 自動轉換：

```python
# task_configuration.py:8-9
def to_camel(string):
    return camelize(string)

model_config = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
)
```

**對應表：**

| JSON (camelCase) | Python (snake_case) |
|------------------|---------------------|
| `ilsFlavour` | `ils_flavour` |
| `tagsToDelete` | `tags_to_delete` |
| `hridHandling` | `hrid_handling` |
| `createSourceRecords` | `create_source_records` |
| `updateHridSettings` | `update_hrid_settings` |
| `addAdministrativeNotesWithLegacyIds` | `add_administrative_notes_with_legacy_ids` |

### 5.5 檔案結構對應

執行任務時，程式會根據配置建立以下結構：

```
{base_folder}/
└── iterations/
    └── {iterationIdentifier}/
        ├── source_data/
        │   ├── instances/     ← BibsTransformer 來源
        │   ├── holdings/      ← HoldingsTransformer 來源
        │   ├── items/         ← ItemsTransformer 來源
        │   └── users/         ← UserTransformer 來源
        ├── results/
        │   ├── folio_instances_{name}.json
        │   ├── folio_holdings_{name}.json
        │   ├── folio_items_{name}.json
        │   └── folio_srs_instances_{name}.json
        └── reports/
            └── {name}_transformation_report.md
```

---

## 六、最佳實踐建議

### 6.1 任務命名

使用描述性名稱，輸出檔會包含任務名稱：

```
folio_instances_{name}.json
folio_holdings_{name}.json
```

**建議：**
- 使用小寫和底線：`transform_bibs`, `post_holdings`
- 包含動作：`transform_`, `post_`, `migrate_`
- 區分來源：`holdings_marc`, `holdings_csv`

### 6.2 任務順序

遵循依賴關係：

```
1. Authority（如有）
2. Bibs → post_instances → post_srs_bibs
3. Holdings (MARC) → post_holdings → post_srs_holdings
4. Holdings (CSV)
5. Items → post_items
6. Users → post_users
7. Loans
8. Requests
9. Courses → Reserves
10. Organizations → Orders
```

### 6.3 測試迭代

使用 `iterationIdentifier` 區分不同測試：

```json
"iterationIdentifier": "test_run_001"
"iterationIdentifier": "test_run_002"
"iterationIdentifier": "production"
```

### 6.4 錯誤閾值設定

**測試階段：**
```json
{
  "failedPercentageThreshold": 25,
  "logLevelDebug": true
}
```

**生產階段：**
```json
{
  "failedPercentageThreshold": 5,
  "logLevelDebug": false
}
```

### 6.5 效能優化

1. **調整批次大小**：根據伺服器資源調整
2. **分割大檔案**：將大型 MARC 檔案分割處理
3. **平行執行**：獨立的任務可同時執行

### 6.6 版本控制

建議將配置檔納入版本控制：

```
mapping_files/
├── taskConfig.json
├── taskConfig.test.json
├── taskConfig.production.json
└── README.md
```

---

## 附錄：參考檔案位置

| 檔案 | 路徑 |
|------|------|
| 範本配置 | `migration_repo_template/mapping_files/exampleConfiguration.json` |
| 測試配置 | `migration_example/config/icMigrationTestConfiguration.json` |
| THU 配置 | `migration_thu/mapping_files/taskConfig.json` |
| Library Configuration 定義 | `folio_migration_tools/src/folio_migration_tools/library_configuration.py` |
| Task Configuration 定義 | `folio_migration_tools/src/folio_migration_tools/task_configuration.py` |
| BibsTransformer | `folio_migration_tools/src/folio_migration_tools/migration_tasks/bibs_transformer.py` |
| MigrationTaskBase | `folio_migration_tools/src/folio_migration_tools/migration_tasks/migration_task_base.py` |

---

*文件產生日期：2025-01-26*
*分析工具：Claude Code*
