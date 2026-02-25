# folio_migration_tools 問題報告

## 環境資訊

| 項目 | 值 |
|------|-----|
| folio_migration_tools 版本 | 1.10.2 |
| FOLIO Release | Sunflower |
| Tenant ID | your_tenant_id |
| OKAPI URL | https://okapi.example.com |

---

## 問題一：createSourceRecords 與 dataImportMarc 的互斥關係

### 現象描述

在 `migration_config.json` 中設定 `"createSourceRecords": true`，期望產生 SRS JSON 檔案 (`folio_srs_instances_transform_bibs.json`)，但執行 `transform_bibs` 後並未產生該檔案。

### 配置內容

```json
{
    "name": "transform_bibs",
    "migrationTaskType": "BibsTransformer",
    "addAdministrativeNotesWithLegacyIds": true,
    "createSourceRecords": true,
    "ilsFlavour": "tag001",
    "tags_to_delete": [],
    "files": [
        {
            "file_name": "202601150950-14.iso",
            "discovery_suppressed": false,
            "create_source_records": true
        }
    ],
    "updateHridSettings": false,
    "hridHandling": "default"
}
```

### 實際產出檔案

```
iterations/thu_migration/results/
├── folio_instances_transform_bibs.json      # ✓ 有產生
├── folio_marc_instances_transform_bibs.mrc  # ✓ 有產生
├── instances_id_map.json                    # ✓ 有產生
└── folio_srs_instances_transform_bibs.json  # ✗ 未產生
```

### 根本原因

查看原始碼 `rules_mapper_base.py` 第 55-60 行：

```python
self.create_source_records = all(
    [
        self.task_configuration.create_source_records,
        (not getattr(self.task_configuration, "data_import_marc", False)),
    ]
)
```

**發現 `create_source_records` 只有在以下兩個條件都滿足時才會為 True：**
1. `createSourceRecords: true`
2. `dataImportMarc: false`

但 `dataImportMarc` 的預設值是 `true`（見 `bibs_transformer.py` 第 69-79 行）。

### 文件問題

1. **JSON Schema 中的預設值描述不準確**
   - Schema 顯示 `createSourceRecords` 預設為 `false`
   - 但未說明 `dataImportMarc` 會影響 `createSourceRecords` 的實際行為

2. **兩個設定的互斥關係未在文件中說明**
   - 使用者無法從文件得知需要同時設定 `createSourceRecords: true` 和 `dataImportMarc: false`

### 建議

1. 在文件中明確說明 `createSourceRecords` 和 `dataImportMarc` 的互斥關係
2. 或考慮讓這兩個設定可以獨立運作

---

## 問題二：dataImportMarc: false 時出現 Subject Source 錯誤

### 現象描述

當設定 `dataImportMarc: false` 和 `createSourceRecords: true` 時，執行 `transform_bibs` 會在處理第一筆記錄時失敗。

### 錯誤訊息

```
2026-02-02 11:55:54,586 CRITICAL 1 Critical Process issue. Check configuration, mapping files and reference data 798698 Subject source not found for  =650  \0$aComputer science. transform_bibs
```

### 配置內容

```json
{
    "name": "transform_bibs",
    "migrationTaskType": "BibsTransformer",
    "createSourceRecords": true,
    "dataImportMarc": false,
    ...
}
```

### MARC 記錄內容

```
=650  \0$aComputer science.
```

第二指標 `0` 表示 Library of Congress Subject Headings (LCSH)。

### Tenant 設定確認

**Subject Sources 存在：**

```bash
curl -s "https://okapi.example.com/subject-sources?limit=100" \
  -H "x-okapi-tenant: your_tenant_id" \
  -H "x-okapi-token: $FOLIO_TOKEN" | jq '.subjectSources[] | {name, code}'
```

輸出：
```json
{ "name": "Library of Congress Subject Headings", "code": "lcsh" }
{ "name": "Library of Congress Children's and Young Adults' Subject Headings", "code": "cyac" }
{ "name": "Medical Subject Headings", "code": "mesh" }
...
```

**Mapping Rules 正確配置：**

```bash
curl -s "https://okapi.example.com/mapping-rules/marc-bib" \
  -H "x-okapi-tenant: your_tenant_id" \
  -H "x-okapi-token: $FOLIO_TOKEN" | jq '.["650"]'
```

650 欄位的 mapping rules 包含針對 `ind2=0` 的設定：

```json
{
    "entity": [
        {
            "target": "subjects.value",
            ...
        },
        {
            "rules": [
                {
                    "conditions": [
                        {
                            "type": "set_subject_source_id",
                            "parameter": {
                                "name": "Library of Congress Subject Headings"
                            }
                        }
                    ]
                }
            ],
            "target": "subjects.sourceId",
            ...
        }
    ],
    "indicators": {
        "ind1": "*",
        "ind2": "0"
    }
}
```

### 分析

1. Subject source "Library of Congress Subject Headings" 在 FOLIO 中存在
2. Mapping rules 正確設定 ind2=0 對應到 LCSH
3. 但 folio_migration_tools 報告找不到 subject source

錯誤訊息格式 `Subject source not found for  =650` 中，"for" 和 "=650" 之間有兩個空格，表示 `parameter['name']` 可能是空的。這暗示工具可能套用了錯誤的 mapping rule（第一個沒有 indicator 限制的 rule，而非 ind2=0 的 rule）。

### 相關原始碼

`conditions.py` 第 837-852 行：

```python
def condition_set_subject_source_id(
    self, legacy_id, value, parameter, marc_field: field.Field
):
    try:
        t = self.get_ref_data_tuple_by_name(
            self.folio.folio_get_all("/subject-sources", "subjectSources"),
            "subject_sources",
            parameter["name"],
        )
        self.mapper.migration_report.add("MappedSubjectSources", t[1])
        return t[0]
    except Exception as e:
        raise TransformationProcessError(
            legacy_id,
            f"Subject source not found for {parameter['name']} {marc_field}",
        ) from e
```

---

## 問題三：BatchPoster 不支援 objectType: "SRS"

### 現象描述

執行 `post_srs_bibs` task 時，即使有 SRS JSON 檔案，BatchPoster 也會拒絕處理。

### 配置內容

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

### 錯誤訊息

```
2026-02-02 12:21:21,720 ERROR Wrong type. Only one of Extradata, Items, Holdings, Instances, ShadowInstances, Users, Organizations, Orders are allowed, received object_type='SRS' instead post_srs_bibs
2026-02-02 12:21:21,720 ERROR Halting post_srs_bibs
```

### 分析

BatchPoster 在版本 1.10.2 中不再支援 `objectType: "SRS"`。

支援的 objectType 清單：
- Extradata
- Items
- Holdings
- Instances
- ShadowInstances
- Users
- Organizations
- Orders

**SRS 已從支援清單中移除。**

### 影響

這表示即使問題二被解決（成功產生 `folio_srs_instances_transform_bibs.json`），也無法使用 BatchPoster 將 SRS 記錄匯入 FOLIO。

### 疑問

1. SRS 記錄現在應該如何匯入 FOLIO？
2. 是否應該只使用 Data Import 功能匯入 `.mrc` 檔案？
3. 如果 SRS 不再支援，為什麼 `createSourceRecords` 設定仍然存在？

---

## 目前的 Workaround

由於上述三個問題，目前唯一可行的方式是使用 `dataImportMarc: true`（預設值）：

```json
{
    "name": "transform_bibs",
    "migrationTaskType": "BibsTransformer",
    "createSourceRecords": true,
    "dataImportMarc": true,
    "ilsFlavour": "tag001",
    "hridHandling": "default",
    ...
}
```

**產出檔案與匯入方式：**

| 檔案 | 用途 | 匯入方式 |
|------|------|----------|
| `folio_instances_transform_bibs.json` | Instance 記錄 | BatchPoster (`post_instances`) |
| `folio_marc_instances_transform_bibs.mrc` | MARC/SRS 記錄 | FOLIO Data Import UI |

**注意：** 這種方式需要在 BatchPoster 匯入 Instances 後，再手動使用 FOLIO 的 Data Import 功能匯入 `.mrc` 檔案。無法完全自動化。

---

## 期望行為

1. **createSourceRecords 設定應獨立運作**
   - 設定 `createSourceRecords: true` 應該產生 SRS JSON，無論 `dataImportMarc` 的值為何
   - 或者在文件中明確說明兩者的互斥關係

2. **Subject Source 查找應正常運作**
   - 當 `dataImportMarc: false` 時，應該正確解析 mapping rules 並找到對應的 subject source

3. **BatchPoster 應支援 SRS**
   - 如果 `createSourceRecords` 設定仍然存在，BatchPoster 應該支援 `objectType: "SRS"`
   - 或者移除 `createSourceRecords` 設定並更新文件說明只能透過 Data Import 匯入 MARC/SRS

---

## 重現步驟

1. 建立 migration_config.json：
   ```json
   {
       "libraryInformation": {
           "tenantId": "your_tenant_id",
           "okapiUrl": "https://okapi.example.com",
           ...
       },
       "migrationTasks": [
           {
               "name": "transform_bibs",
               "migrationTaskType": "BibsTransformer",
               "createSourceRecords": true,
               "dataImportMarc": false,
               "ilsFlavour": "tag001",
               "hridHandling": "default",
               "files": [
                   {
                       "file_name": "test.mrc",
                       "discovery_suppressed": false,
                       "create_source_records": true
                   }
               ]
           }
       ]
   }
   ```

2. 準備包含 650 欄位（ind2=0）的 MARC 檔案

3. 執行：
   ```bash
   python -m folio_migration_tools migration_config.json transform_bibs --base_folder_path ./
   ```

4. 觀察錯誤訊息

---

## 相關檔案

- `src/folio_migration_tools/marc_rules_transformation/rules_mapper_base.py` (第 55-60 行)
- `src/folio_migration_tools/marc_rules_transformation/conditions.py` (第 837-852 行)
- `src/folio_migration_tools/migration_tasks/bibs_transformer.py` (第 69-79 行)

---

## 聯絡資訊

報告日期：2026-02-02
