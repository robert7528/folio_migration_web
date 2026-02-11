# FOLIO Migration Tools 架構概述

## 目錄
1. [專案概述](#專案概述)
2. [專案目錄結構](#專案目錄結構)
3. [核心模組和類別關係](#核心模組和類別關係)
4. [支援的遷移類型和對應程式](#支援的遷移類型和對應程式)
5. [資料處理流程](#資料處理流程)
6. [設計模式的應用](#設計模式的應用)
7. [附錄：關鍵類別參考](#附錄關鍵類別參考)

---

## 專案概述

**folio_migration_tools** 是一套用於將傳統圖書館系統資料遷移至 FOLIO LSP (Library Services Platform) 的 Python 工具集。

### 基本資訊
- **版本**: 1.10.1
- **Python 版本要求**: >= 3.12
- **授權**: MIT License
- **入口點**: `folio_migration_tools.__main__:main`

### 主要依賴套件
| 套件 | 用途 |
|------|------|
| `folioclient` | FOLIO API 互動 |
| `pymarc` | MARC 記錄處理 |
| `pydantic` | 配置驗證和資料模型 |
| `folio-uuid` | 確定性 UUID 生成 |
| `folio-data-import` | 資料匯入功能 |
| `i18n` | 國際化支援 |

---

## 專案目錄結構

```
folio_migration_tools/
├── src/
│   └── folio_migration_tools/
│       ├── __init__.py
│       ├── __main__.py                    # 程式入口點
│       ├── library_configuration.py       # 圖書館配置模型
│       ├── task_configuration.py          # 任務配置基類
│       ├── mapper_base.py                 # Mapper 基類
│       ├── migration_report.py            # 遷移報告生成
│       ├── folder_structure.py            # 資料夾結構管理
│       ├── helper.py                      # 輔助函數
│       ├── custom_exceptions.py           # 自定義例外
│       ├── extradata_writer.py            # 額外資料寫入
│       ├── i18n_config.py / i18n_cache.py # 國際化支援
│       │
│       ├── migration_tasks/               # 遷移任務類別 (14 個)
│       │   ├── migration_task_base.py     # 任務基類
│       │   ├── batch_poster.py            # 批次上傳
│       │   ├── bibs_transformer.py        # 書目轉換
│       │   ├── holdings_csv_transformer.py # 館藏 CSV 轉換
│       │   ├── holdings_marc_transformer.py# 館藏 MARC 轉換
│       │   ├── items_transformer.py       # 館藏品項轉換
│       │   ├── user_transformer.py        # 讀者轉換
│       │   ├── orders_transformer.py      # 訂單轉換
│       │   ├── organization_transformer.py # 組織轉換
│       │   ├── loans_migrator.py          # 借閱遷移
│       │   ├── requests_migrator.py       # 預約遷移
│       │   ├── reserves_migrator.py       # 指定參考書遷移
│       │   ├── courses_migrator.py        # 課程遷移
│       │   └── manual_fee_fines_transformer.py # 罰款轉換
│       │
│       ├── mapping_file_transformation/   # CSV/TSV 映射轉換 (9 個)
│       │   ├── mapping_file_mapper_base.py # 映射檔 Mapper 基類
│       │   ├── ref_data_mapping.py        # 參考資料映射
│       │   ├── holdings_mapper.py         # 館藏映射器
│       │   ├── item_mapper.py             # 品項映射器
│       │   ├── user_mapper.py             # 讀者映射器
│       │   ├── order_mapper.py            # 訂單映射器
│       │   ├── organization_mapper.py     # 組織映射器
│       │   ├── courses_mapper.py          # 課程映射器
│       │   ├── notes_mapper.py            # 註記映射器
│       │   └── manual_fee_fines_mapper.py # 罰款映射器
│       │
│       ├── marc_rules_transformation/     # MARC 規則轉換 (8 個)
│       │   ├── rules_mapper_base.py       # MARC 規則 Mapper 基類
│       │   ├── rules_mapper_bibs.py       # 書目規則映射器
│       │   ├── rules_mapper_holdings.py   # 館藏規則映射器
│       │   ├── marc_file_processor.py     # MARC 檔案處理器
│       │   ├── marc_reader_wrapper.py     # MARC 讀取器包裝
│       │   ├── hrid_handler.py            # HRID 處理器
│       │   ├── conditions.py              # 條件判斷
│       │   └── holdings_statementsparser.py # 館藏聲明解析
│       │
│       └── transaction_migration/         # 交易遷移模型 (4 個)
│           ├── legacy_loan.py             # 傳統借閱模型
│           ├── legacy_request.py          # 傳統預約模型
│           ├── legacy_reserve.py          # 傳統指定參考書模型
│           └── transaction_result.py      # 交易結果模型
│
├── pyproject.toml                         # 專案配置
└── tests/                                 # 測試目錄
```

---

## 核心模組和類別關係

### 類別繼承圖

```
                                MapperBase
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            RulesMapperBase   MappingFileMapperBase  │
                    │               │               │
            ┌───────┴───────┐   ┌──┴───────────────┼──────────┐
            │               │   │                  │          │
    BibsRulesMapper  HoldingsRulesMapper  ItemMapper  UserMapper  HoldingsMapper
                                         OrderMapper  OrganizationMapper
                                         CoursesMapper  NotesMapper


                            MigrationTaskBase
                                    │
        ┌───────────┬───────────┬───┴───────┬───────────┬───────────┐
        │           │           │           │           │           │
  BibsTransformer  HoldingsCsvTransformer  ItemsTransformer  UserTransformer  BatchPoster
  HoldingsMarcTransformer  OrdersTransformer  OrganizationTransformer  LoansMigrator
                           RequestsMigrator  ReservesMigrator  CoursesMigrator
```

### 核心類別說明

#### 1. MapperBase (`mapper_base.py`)
所有 Mapper 類別的基礎類別，提供：
- 遷移報告追蹤 (`migration_report`)
- 參考資料映射 (`get_mapped_ref_data_value`)
- 錯誤處理機制
- UUID 生成基底字串 (`base_string_for_folio_uuid`)
- 統計代碼映射

```python
class MapperBase:
    def __init__(self, library_configuration, task_configuration, folio_client):
        self.migration_report = MigrationReport()
        self.folio_client = folio_client
        # ...
```

#### 2. MigrationTaskBase (`migration_task_base.py`)
所有遷移任務的抽象基類，定義：
- 資料夾結構管理 (`FolderStructure`)
- 來源檔案驗證
- ID 映射載入
- 日誌設定
- 抽象方法：`do_work()`, `wrap_up()`, `get_object_type()`

```python
class MigrationTaskBase:
    @staticmethod
    @abstractmethod
    def get_object_type() -> FOLIONamespaces:
        raise NotImplementedError()

    @abstractmethod
    def do_work(self):
        raise NotImplementedError()

    @abstractmethod
    def wrap_up(self):
        raise NotImplementedError()
```

#### 3. MappingFileMapperBase (`mapping_file_mapper_base.py`)
處理 CSV/TSV 資料轉換的基類：
- JSON 映射檔解析
- 欄位映射邏輯
- 值轉換規則 (regex, replace, fallback)
- 陣列屬性處理
- Schema 驗證

#### 4. RulesMapperBase (`rules_mapper_base.py`)
處理 MARC 記錄轉換的基類：
- MARC 欄位處理
- HRID 管理
- 條件式規則應用
- SRS 記錄生成

---

## 支援的遷移類型和對應程式

### 資料轉換任務 (Transformers)

| 任務類型 | 類別名稱 | 資料來源 | 目標物件 |
|---------|---------|---------|---------|
| 書目轉換 | `BibsTransformer` | MARC 檔案 | Instances |
| 館藏轉換 (MARC) | `HoldingsMarcTransformer` | MARC 檔案 | Holdings |
| 館藏轉換 (CSV) | `HoldingsCsvTransformer` | CSV/TSV 檔案 | Holdings |
| 品項轉換 | `ItemsTransformer` | CSV/TSV 檔案 | Items |
| 讀者轉換 | `UserTransformer` | CSV/TSV 檔案 | Users |
| 訂單轉換 | `OrdersTransformer` | CSV/TSV 檔案 | Orders |
| 組織轉換 | `OrganizationTransformer` | CSV/TSV 檔案 | Organizations |
| 罰款轉換 | `ManualFeeFinesTransformer` | CSV/TSV 檔案 | Manual Fee/Fines |

### 資料遷移任務 (Migrators)

| 任務類型 | 類別名稱 | 說明 |
|---------|---------|------|
| 借閱遷移 | `LoansMigrator` | 遷移當前借閱記錄 |
| 預約遷移 | `RequestsMigrator` | 遷移預約請求 |
| 指定參考書遷移 | `ReservesMigrator` | 遷移課程指定參考書 |
| 課程遷移 | `CoursesMigrator` | 遷移課程資訊 |

### 資料上傳任務

| 任務類型 | 類別名稱 | 說明 |
|---------|---------|------|
| 批次上傳 | `BatchPoster` | 將轉換後的資料批次上傳至 FOLIO |

### 支援的物件類型 (BatchPoster)

```python
# 支援的 API 端點
{
    "Instances": "/instance-storage/batch/synchronous",
    "Holdings": "/holdings-storage/batch/synchronous",
    "Items": "/item-storage/batch/synchronous",
    "Users": "/user-import",
    "Organizations": "/organizations/organizations",
    "Orders": "/orders/composite-orders",
    "Extradata": [多種額外資料端點]
}
```

---

## 資料處理流程

### 整體執行流程

```
┌─────────────────┐
│  命令列參數     │
│  (config.json)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ __main__.py     │
│ 載入配置        │
│ 建立 FolioClient│
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 任務發現機制     │────►│ inheritors()    │
│ (反射機制)      │     │ 找出所有子類    │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│ 實例化對應任務   │
│ Task.__init__() │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 執行任務        │
│ task.do_work()  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 收尾處理        │
│ task.wrap_up()  │
└─────────────────┘
```

### 任務發現機制 (`__main__.py`)

```python
def inheritors(base_class):
    """遞迴找出所有繼承自 base_class 的子類"""
    subclasses = set()
    work = [base_class]
    while work:
        parent = work.pop()
        for child in parent.__subclasses__():
            if child not in subclasses:
                subclasses.add(child)
                work.append(child)
    return subclasses
```

### CSV/TSV 資料轉換流程

```
┌────────────────┐
│ Legacy Data    │
│ (CSV/TSV)      │
└───────┬────────┘
        │
        ▼
┌────────────────┐     ┌────────────────────┐
│ 讀取映射檔     │────►│ mapping.json       │
│ setup_records_map()│  │ (folio_field,      │
└───────┬────────┘     │  legacy_field,     │
        │              │  value, rules)     │
        ▼              └────────────────────┘
┌────────────────┐
│ 逐行處理       │
│ get_objects()  │
└───────┬────────┘
        │
        ▼
┌────────────────┐     ┌────────────────────┐
│ 欄位映射       │────►│ RefDataMapping     │
│ do_map()       │     │ (TSV 參考資料)     │
└───────┬────────┘     └────────────────────┘
        │
        ▼
┌────────────────┐
│ 額外處理       │
│ perform_additional_mapping()
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ 輸出 FOLIO JSON│
│ results_file   │
└────────────────┘
```

### MARC 資料轉換流程

```
┌────────────────┐
│ MARC Files     │
│ (.mrc)         │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ MARCReaderWrapper │
│ (pymarc)       │
└───────┬────────┘
        │
        ▼
┌────────────────┐     ┌────────────────────┐
│ MarcFileProcessor │  │ Tenant Rules       │
│ 處理單筆記錄    │◄───│ (FOLIO 映射規則)   │
└───────┬────────┘     └────────────────────┘
        │
        ▼
┌────────────────┐
│ RulesMapperBase│
│ parse_bib()    │
│ parse_holdings()
└───────┬────────┘
        │
        ├──────────────────┐
        ▼                  ▼
┌────────────────┐  ┌────────────────┐
│ FOLIO Instance │  │ SRS Record     │
│ JSON           │  │ (選擇性)       │
└────────────────┘  └────────────────┘
```

### 資料夾結構 (FolderStructure)

```
{base_folder}/
├── .gitignore                    # 自動維護
├── mapping_files/                # 映射檔案
│   ├── *.json                    # JSON 映射檔
│   └── *.tsv                     # TSV 參考資料映射
│
└── iterations/
    └── {iteration_identifier}/
        ├── source_data/          # 來源資料
        │   ├── instances/
        │   ├── holdings/
        │   ├── items/
        │   └── users/
        │
        ├── results/              # 輸出結果
        │   ├── folio_*.json      # 轉換後的 FOLIO 物件
        │   ├── *_id_map.json     # ID 映射檔
        │   ├── extradata*.extradata
        │   └── failed_records*.txt
        │
        └── reports/              # 報告
            ├── report_*.md       # 遷移報告
            ├── log_*.log         # 日誌檔
            ├── data_issues_*.tsv # 資料問題報告
            └── .raw/             # 原始報告 JSON
```

---

## 設計模式的應用

### 1. 模板方法模式 (Template Method Pattern)

**應用位置**: `MigrationTaskBase` 和所有 Transformer 類別

```python
class MigrationTaskBase:
    def __init__(self, ...):
        # 通用初始化邏輯
        self.folder_structure.setup_migration_file_structure()
        self.setup_logging()

    @abstractmethod
    def do_work(self):
        """由子類實作具體轉換邏輯"""
        raise NotImplementedError()

    @abstractmethod
    def wrap_up(self):
        """由子類實作收尾邏輯"""
        raise NotImplementedError()
```

子類別實作：
```python
class BibsTransformer(MigrationTaskBase):
    def do_work(self):
        self.do_work_marc_transformer()  # 呼叫父類的 MARC 處理邏輯

    def wrap_up(self):
        self.mapper.migration_report.write_migration_report(...)
```

### 2. 策略模式 (Strategy Pattern)

**應用位置**: 映射策略選擇

兩種映射策略：
- **MARC 規則映射** (`RulesMapperBase`): 用於 MARC 資料
- **CSV 映射檔映射** (`MappingFileMapperBase`): 用於扁平化資料

```python
# MARC 策略
class BibsRulesMapper(RulesMapperBase):
    def parse_bib(self, marc_record, ...):
        # MARC 特定的轉換邏輯

# CSV 策略
class ItemMapper(MappingFileMapperBase):
    def do_map(self, legacy_object, ...):
        # CSV 特定的轉換邏輯
```

### 3. 工廠模式 (Factory Pattern)

**應用位置**: 任務實例化 (`__main__.py`)

```python
def main():
    # 動態發現所有任務類別
    migration_task_types = {
        c.__name__: c for c in inheritors(MigrationTaskBase)
    }

    # 根據配置實例化對應任務
    task_class = migration_task_types[task_config.migration_task_type]
    task = task_class(task_config, library_config, folio_client)
```

### 4. 建造者模式 (Builder Pattern)

**應用位置**: Pydantic 配置模型

```python
class TaskConfiguration(AbstractTaskConfiguration):
    name: Annotated[str, Field(...)]
    files: Annotated[List[FileDefinition], Field(...)]
    batch_size: Annotated[int, Field(...)] = 500
    # ... 更多屬性
```

### 5. 複合模式 (Composite Pattern)

**應用位置**: 任務配置結構

```python
{
    "libraryInformation": { ... },          # LibraryConfiguration
    "migrationTasks": [                     # 任務陣列
        { "migrationTaskType": "BibsTransformer", ... },
        { "migrationTaskType": "BatchPoster", ... }
    ]
}
```

### 6. 裝飾者模式 (Decorator Pattern)

**應用位置**: Pydantic Field 註解

```python
class TaskConfiguration(AbstractTaskConfiguration):
    ils_flavour: Annotated[
        IlsFlavour,
        Field(
            title="ILS flavour",
            description="The type of ILS you are migrating records from.",
            alias="ils_flavor",  # 支援駝峰和蛇形命名
        ),
    ]
```

### 7. 迭代器模式 (Iterator Pattern)

**應用位置**: 資料讀取

```python
class MappingFileMapperBase:
    def get_objects(self, source_file, file_name: Path):
        total_rows, empty_rows, reader = self._get_delimited_file_reader(...)
        yield from reader  # 生成器模式，節省記憶體
```

### 8. 單例模式 (Singleton-like)

**應用位置**: `FolioClient` 在整個任務執行期間共用

```python
def main():
    folio_client = FolioClient(...)  # 建立一次
    for task_config in configs:
        task = TaskClass(..., folio_client)  # 共用 client
```

---

## 附錄：關鍵類別參考

### FOLIONamespaces (物件類型)

```python
class FOLIONamespaces(Enum):
    instances = "instances"
    holdings = "holdings"
    items = "items"
    users = "users"
    organizations = "organizations"
    orders = "orders"
    loans = "loans"
    requests = "requests"
    other = "other"
    # ...
```

### HridHandling (HRID 處理方式)

```python
class HridHandling(str, Enum):
    default = "default"        # FOLIO 生成 HRID
    preserve001 = "preserve001" # 保留 001 作為 HRID
```

### IlsFlavour (來源系統類型)

```python
class IlsFlavour(str, Enum):
    aleph = "aleph"
    voyager = "voyager"
    sierra = "sierra"
    millennium = "millennium"
    koha = "koha"
    tag001 = "tag001"
    custom = "custom"
    none = "none"
```

### FolioRelease (FOLIO 版本)

```python
class FolioRelease(str, Enum):
    ramsons = "ramsons"
    sunflower = "sunflower"
    trillium = "trillium"
    umbrellaleaf = "umbrellaleaf"
```

---

## 總結

folio_migration_tools 是一個設計良好的資料遷移框架，具有以下特點：

1. **模組化設計**: 清晰的模組分離 (tasks, mappers, transformations)
2. **可擴展性**: 透過繼承機制輕鬆新增遷移任務
3. **配置驅動**: 使用 JSON 配置檔定義遷移行為
4. **雙軌映射**: 支援 MARC 規則和 CSV 映射兩種方式
5. **完善的報告**: 自動生成遷移報告和資料問題日誌
6. **錯誤處理**: 完整的例外處理和失敗記錄機制
7. **UUID 確定性**: 使用 folio-uuid 確保可重複的 ID 生成
