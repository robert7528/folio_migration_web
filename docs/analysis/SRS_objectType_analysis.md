# folio_migration_tools SRS objectType 錯誤分析報告

## 問題描述

執行以下指令時出現錯誤：

```shell
folio-migration-tools mapping_files/marc_config.json --base_folder_path ./ post_srs_bibs
```

錯誤訊息：

```
2026-01-27 16:47:05,015 ERROR   Wrong type. Only one of Extradata, Items, Holdings, Instances, ShadowInstances, Users, Organizations, Orders are allowed, received object_type='SRS' instead    post_srs_bibs
2026-01-27 16:47:05,015 ERROR   Halting post_srs_bibs
```

---

## 分析結果

### 1. folio_migration_tools 是否支援 SRS object_type？

**答案：目前不支援。**

| 來源 | 是否列出 SRS | 位置 |
|------|-------------|------|
| 文檔 (migration_tasks.md) | 是 | 第 68, 140, 153 行 |
| 範例設定檔 (exampleConfiguration.json) | 是 | 第 42 行 |
| 實際程式碼 (batch_poster.py) | **否** | `get_api_info()` 函數 |

這是一個**文檔與程式碼不一致**的問題。

---

### 2. 為什麼錯誤訊息中沒有 SRS？

錯誤來源檔案：

```
D:\FOLIO-FSE\folio_migration_tools\src\folio_migration_tools\migration_tasks\batch_poster.py
```

問題函數 `get_api_info()` (第 944-1038 行)：

```python
def get_api_info(object_type: str, use_safe: bool = True):
    choices = {
        "Extradata": {
            "object_name": "",
            "api_endpoint": "",
            ...
        },
        "Items": {
            "object_name": "items",
            "api_endpoint": "/item-storage/batch/synchronous",
            ...
        },
        "Holdings": {
            "object_name": "holdingsRecords",
            "api_endpoint": "/holdings-storage/batch/synchronous",
            ...
        },
        "Instances": {
            "object_name": "instances",
            "api_endpoint": "/instance-storage/batch/synchronous",
            ...
        },
        "ShadowInstances": {...},
        "Users": {...},
        "Organizations": {...},
        "Orders": {...},
        # 注意：這裡沒有 "SRS" 的定義！
    }

    try:
        return choices[object_type]
    except KeyError:
        key_string = ", ".join(choices.keys())
        logging.error(
            f"Wrong type. Only one of {key_string} are allowed, received {object_type=} instead"
        )
        logging.error("Halting")
        sys.exit(1)
```

當傳入 `object_type="SRS"` 時，因為 `choices` 字典中沒有這個 key，就會觸發 `KeyError` 並輸出錯誤訊息後終止程式。

---

### 3. post_srs_bibs 指令應該如何正確使用？

#### 背景說明

根據 CHANGELOG (`v_1_8_6`) 中的記錄：

> Make the BibsTransformer to create Source=FOLIO records without SRS records [#449](https://github.com/FOLIO-FSE/folio_migration_tools/issues/449)

以及文檔中的提示 (`migration_tasks.md:77-78`)：

> To load MARC records to SRS for your transformed instances, see: Posting BibTransformer MARC records

#### 結論

**SRS 記錄目前應透過 FOLIO Data Import API 載入，而非 BatchPoster。**

BatchPoster 任務不支援直接載入 SRS 記錄到 Source Record Storage。

---

### 4. 問題程式檔案

| 檔案 | 說明 |
|------|------|
| `batch_poster.py` | 第 944-1038 行的 `get_api_info()` 函數缺少 SRS 定義 |
| `migration_tasks.md` | 文檔錯誤地列出 SRS 為有效的 objectType |
| `exampleConfiguration.json` | 範例設定檔錯誤地使用 `"objectType": "SRS"` |

完整路徑：

```
D:\FOLIO-FSE\folio_migration_tools\src\folio_migration_tools\migration_tasks\batch_poster.py
D:\FOLIO-FSE\folio_migration_tools\docs\source\migration_tasks.md
D:\FOLIO-FSE\migration_repo_template\mapping_files\exampleConfiguration.json
```

---

### 5. 設定檔問題

如果你的 `mapping_files/marc_config.json` 包含類似以下設定：

```json
{
    "name": "post_srs_bibs",
    "migrationTaskType": "BatchPoster",
    "objectType": "SRS",
    "batchSize": 250,
    "files": [
        {
            "file_name": "folio_srs_instances_transform_bibs.json"
        }
    ]
}
```

這個設定是按照官方文檔和範例配置的，**設定本身沒有問題**，但程式碼尚未實現此功能。

---

## 解決方案

### 方案 A：使用 Data Import 載入 SRS 記錄（建議）

這是官方建議的方式。SRS 記錄檔案（如 `folio_srs_instances_transform_bibs.json`）需要透過 FOLIO 的 Data Import 模組載入，而不是 BatchPoster。

步驟：
1. 完成 BibsTransformer 轉換任務，產生 SRS 記錄檔案
2. 使用 BatchPoster 載入 Instances（`objectType: "Instances"`）
3. 透過 FOLIO Data Import API 或 UI 載入 SRS 記錄

### 方案 B：向專案回報此 Bug

這是文檔與程式碼不一致的問題，建議在 GitHub 上提出 issue：

**回報連結：** https://github.com/FOLIO-FSE/folio_migration_tools/issues

**建議的 Issue 標題：**
```
Documentation lists "SRS" as valid objectType for BatchPoster, but it's not implemented
```

**建議的 Issue 內容：**
```markdown
## Description
The documentation (`docs/source/migration_tasks.md`) and example configuration
(`migration_repo_template/mapping_files/exampleConfiguration.json`) both list "SRS"
as a valid objectType for BatchPoster tasks.

However, the `get_api_info()` function in `batch_poster.py` does not include "SRS"
in its choices dictionary, causing the task to fail with:

```
Wrong type. Only one of Extradata, Items, Holdings, Instances, ShadowInstances,
Users, Organizations, Orders are allowed, received object_type='SRS' instead
```

## Expected Behavior
Either:
1. Add SRS support to BatchPoster, or
2. Update documentation and examples to reflect that SRS records must be loaded
   via Data Import

## Affected Files
- `src/folio_migration_tools/migration_tasks/batch_poster.py` (line 944-1038)
- `docs/source/migration_tasks.md` (lines 68, 140, 153)
- `migration_repo_template/mapping_files/exampleConfiguration.json` (line 42)
```

---

## 目前支援的 objectType 列表

| objectType | API Endpoint | 批次處理 | 支援 Upsert |
|------------|--------------|----------|-------------|
| Extradata | 自訂 | 否 | 否 |
| Items | `/item-storage/batch/synchronous` | 是 | 是 |
| Holdings | `/holdings-storage/batch/synchronous` | 是 | 是 |
| Instances | `/instance-storage/batch/synchronous` | 是 | 是 |
| ShadowInstances | `/instance-storage/batch/synchronous` | 是 | 是 |
| Users | `/user-import` | 是 | 否 |
| Organizations | `/organizations/organizations` | 否 | 否 |
| Orders | `/orders/composite-orders` | 否 | 否 |

---

## 參考資料

- [folio_migration_tools GitHub](https://github.com/FOLIO-FSE/folio_migration_tools)
- [FOLIO Data Import Documentation](https://wiki.folio.org/display/FOLIOtips/Data+Import)
- [BatchPoster 原始碼](https://github.com/FOLIO-FSE/folio_migration_tools/blob/main/src/folio_migration_tools/migration_tasks/batch_poster.py)

---

*報告產生日期：2026-01-28*
