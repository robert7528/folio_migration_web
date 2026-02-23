# FOLIO Migration Tools - Mapping Files 結構與用途分析

本文件分析 `folio_migration_tools` 轉檔及匯入時使用的 mapping files 結構和用途。

## 目錄

- [一、Mapping Files 概述](#一mapping-files-概述)
- [二、兩種主要格式](#二兩種主要格式)
- [三、JSON Mapping Files 詳解](#三json-mapping-files-詳解)
- [四、TSV Mapping Files 詳解](#四tsv-mapping-files-詳解)
- [五、Mapping Files 與轉檔程式的對應](#五mapping-files-與轉檔程式的對應)
- [六、兩個專案的差異比較](#六兩個專案的差異比較)
- [七、最佳實踐與建議](#七最佳實踐與建議)

---

## 一、Mapping Files 概述

Mapping files 是 FOLIO 遷移工具的核心配置檔案，用於定義來源資料欄位與目標 FOLIO 欄位之間的對應關係。

### 1.1 兩個專案的檔案清單

**migration_example/mapping_files/** (完整範例，34 個檔案)：
```
JSON 格式 (10 個):
├── composite_order_mapping.json
├── composite_order_mapping_multiple_pols.json
├── course_mapping.json
├── holdingsrecord_mapping.json
├── holdingsrecord_mapping_for_bw_items.json
├── item_mapping_for_bw_items.json
├── item_mapping_for_csv_items.json
├── item_mapping_for_mfhd_attached_items.json
├── manual_feefines_map.json
├── organization_mapping.json
└── user_mapping.json

TSV 格式 (24 個):
├── acquisitionMethodMap.tsv
├── address_categories.tsv
├── call_number_type_mapping.tsv
├── email_categories.tsv
├── feefine_owners.tsv
├── feefine_types.tsv
├── feefines_service_points.tsv
├── item_statuses.tsv
├── loan_types.tsv / loan_types_bw.tsv / loan_types_csv.tsv
├── locations.tsv / locations_bw.tsv
├── material_types.tsv / material_types_bw.tsv / material_types_csv.tsv
├── organization_types.tsv
├── phone_categories.tsv
├── reserve_locations.tsv
├── statcodes.tsv
├── terms_map.tsv
├── user_departments.tsv
└── user_groups.tsv
```

**migration_thu/mapping_files/** (生產環境，10 個檔案)：
```
JSON 格式 (3 個):
├── holdings_mapping.json
├── item_mapping.json
└── user_mapping.json

TSV 格式 (5 個):
├── call_number_type_mapping.tsv
├── loan_types.tsv
├── locations.tsv
├── material_types.tsv
└── user_groups.tsv

配置檔案 (2 個):
├── taskConfig.json
└── exampleConfiguration.json
```

---

## 二、兩種主要格式

### 2.1 格式比較

| 特性 | JSON Mapping Files | TSV Mapping Files |
|------|-------------------|-------------------|
| **用途** | 欄位對欄位的複雜映射 | 參考資料值的對應 |
| **處理類別** | MappingFileMapperBase | RefDataMapping |
| **適用對象** | Items, Holdings, Users, Orders, Organizations | Locations, Material Types, Loan Types, Status |
| **支援功能** | 規則轉換、預設值、fallback | 萬用字元(*)、多欄位對應 |
| **欄位結構** | folio_field, legacy_field, value, rules | legacy_code → folio_code/folio_name |

### 2.2 選擇指南

- **使用 JSON**：當需要將來源資料的多個欄位映射到 FOLIO 物件的複雜結構時
- **使用 TSV**：當需要將來源系統的代碼值轉換為 FOLIO 的參考資料值時

---

## 三、JSON Mapping Files 詳解

### 3.1 基本結構

```json
{
  "data": [
    {
      "folio_field": "FOLIO 欄位路徑",
      "legacy_field": "來源欄位名稱",
      "value": "預設值（可選）",
      "description": "說明（可選）",
      "fallback_legacy_field": "備用來源欄位（可選）",
      "fallback_value": "備用預設值（可選）",
      "rules": { }  // 轉換規則（可選）
    }
  ]
}
```

### 3.2 欄位定義說明

| 欄位 | 必要 | 說明 |
|------|------|------|
| `folio_field` | 是 | FOLIO 目標欄位，支援巢狀路徑（如 `personal.addresses[0].city`） |
| `legacy_field` | 是 | 來源資料欄位名稱，設為 `"Not mapped"` 表示不映射 |
| `value` | 否 | 固定預設值，優先於 legacy_field |
| `description` | 否 | 欄位說明 |
| `fallback_legacy_field` | 否 | 當 legacy_field 為空時使用的備用欄位 |
| `fallback_value` | 否 | 當 legacy_field 為空時使用的備用值 |
| `rules` | 否 | 轉換規則物件 |

### 3.3 支援的規則類型

#### 3.3.1 replaceValues（值替換）

將來源值替換為指定的 FOLIO 值：

```json
{
  "folio_field": "orderType",
  "legacy_field": "ORD TYPE",
  "rules": {
    "replaceValues": {
      "s": "One-Time",
      "p": "Ongoing",
      "l": "Ongoing",
      "n": "One-Time"
    }
  }
}
```

#### 3.3.2 regexGetFirstMatchOrEmpty（正則提取）

使用正則表達式提取值：

```json
{
  "folio_field": "personal.email",
  "legacy_field": "email",
  "rules": {
    "regexGetFirstMatchOrEmpty": "(^[a-zA-Z0-9_\\-\\.]+@[a-zA-Z0-9_\\-\\.]+)"
  }
}
```

```json
{
  "folio_field": "username",
  "legacy_field": "email",
  "fallback_legacy_field": "reader_code",
  "rules": {
    "regexGetFirstMatchOrEmpty": "([a-zA-Z0-9_\\-\\.]+)@.*"
  }
}
```

### 3.4 陣列欄位映射

使用 `[index]` 語法映射陣列元素：

```json
{
  "folio_field": "notes[0].itemNoteTypeId",
  "legacy_field": "公開備註public_notes",
  "value": "8d0a5eca-25de-4391-81a9-236eeefdd20b"
},
{
  "folio_field": "notes[0].note",
  "legacy_field": "公開備註public_notes"
},
{
  "folio_field": "notes[0].staffOnly",
  "legacy_field": "公開備註public_notes",
  "value": false
},
{
  "folio_field": "notes[1].itemNoteTypeId",
  "legacy_field": "員工備註staff_notes",
  "value": "8d0a5eca-25de-4391-81a9-236eeefdd20b"
},
{
  "folio_field": "notes[1].staffOnly",
  "legacy_field": "員工備註staff_notes",
  "value": "true"
}
```

### 3.5 巢狀物件映射

使用點號(.)語法映射巢狀屬性：

```json
{
  "folio_field": "personal.addresses[0].addressLine1",
  "legacy_field": "address"
},
{
  "folio_field": "personal.addresses[0].city",
  "legacy_field": "Not mapped"
},
{
  "folio_field": "personal.addresses[0].addressTypeId",
  "legacy_field": "address",
  "value": "Home"
}
```

### 3.6 特殊欄位：legacyIdentifier

每個 JSON mapping file 都必須包含 `legacyIdentifier` 欄位，用於生成確定性 UUID：

```json
{
  "folio_field": "legacyIdentifier",
  "legacy_field": "序號barcode",
  "fallback_legacy_field": "bib_no"
}
```

**重要性：**
- 用於生成唯一且可重複的 FOLIO UUID
- 支援 fallback，確保總能取得識別碼
- 程式會驗證此欄位必須存在

### 3.7 各類 JSON Mapping Files

#### 3.7.1 item_mapping.json（館藏項目映射）

```json
{
  "data": [
    {"folio_field": "barcode", "legacy_field": "序號barcode"},
    {"folio_field": "holdingsRecordId", "legacy_field": "序號barcode"},
    {"folio_field": "legacyIdentifier", "legacy_field": "序號barcode", "fallback_legacy_field": "bib_no"},
    {"folio_field": "copyNumber", "legacy_field": "編號copy"},
    {"folio_field": "materialTypeId", "legacy_field": "館藏類型itype"},
    {"folio_field": "permanentLoanTypeId", "legacy_field": "貸款狀態loantype"},
    {"folio_field": "volume", "legacy_field": "卷號volume"},
    {"folio_field": "status.name", "legacy_field": "Not mapped", "rules": {...}}
  ]
}
```

#### 3.7.2 holdings_mapping.json（館藏記錄映射）

```json
{
  "data": [
    {"folio_field": "callNumber", "legacy_field": "呼叫號碼call#"},
    {"folio_field": "legacyIdentifier", "legacy_field": "序號barcode", "fallback_legacy_field": "bib_no"},
    {"folio_field": "formerIds[0]", "legacy_field": "序號barcode"},
    {"folio_field": "formerIds[1]", "legacy_field": "bib_no"},
    {"folio_field": "instanceId", "legacy_field": "bib_no"},
    {"folio_field": "permanentLocationId", "legacy_field": "館藏室location"}
  ]
}
```

#### 3.7.3 user_mapping.json（讀者映射）

```json
{
  "data": [
    {"folio_field": "barcode", "legacy_field": "reader_code"},
    {"folio_field": "type", "legacy_field": "reader_code", "value": "patron"},
    {"folio_field": "externalSystemId", "legacy_field": "email", "fallback_legacy_field": "reader_code"},
    {"folio_field": "legacyIdentifier", "legacy_field": "reader_code"},
    {"folio_field": "patronGroup", "legacy_field": "readerTypeCode"},
    {"folio_field": "personal.firstName", "legacy_field": "Not mapped"},
    {"folio_field": "personal.lastName", "legacy_field": "reader_name"},
    {"folio_field": "personal.email", "legacy_field": "email", "rules": {"regexGetFirstMatchOrEmpty": "..."}},
    {"folio_field": "customFields.licenseid", "legacy_field": "license_id"},
    {"folio_field": "customFields.grade", "legacy_field": "grade"},
    {"folio_field": "customFields.sex", "legacy_field": "sex"}
  ]
}
```

#### 3.7.4 composite_order_mapping.json（訂單映射）

```json
{
  "data": [
    {"folio_field": "legacyIdentifier", "legacy_field": "RECORD #(Order)"},
    {"folio_field": "poNumber", "legacy_field": "RECORD #(Order)"},
    {"folio_field": "vendor", "legacy_field": "VENDOR"},
    {"folio_field": "orderType", "legacy_field": "ORD TYPE", "rules": {"replaceValues": {...}}},
    {"folio_field": "compositePoLines[0].titleOrPackage", "legacy_field": "TITLE"},
    {"folio_field": "compositePoLines[0].instanceId", "legacy_field": "RECORD #(Bibliographic)"},
    {"folio_field": "compositePoLines[0].source", "value": "API"},
    {"folio_field": "compositePoLines[0].cost.currency", "value": "USD"}
  ]
}
```

---

## 四、TSV Mapping Files 詳解

### 4.1 基本結構

TSV 檔案使用 Tab 分隔，第一行為標題行：

```
legacy_column1	legacy_column2	folio_code/folio_name
value1	value2	FOLIO_VALUE
*	*	DEFAULT_VALUE
```

### 4.2 欄位命名規則

| 目標欄位類型 | FOLIO 欄位名稱 |
|-------------|---------------|
| 依代碼查詢 | `folio_code` |
| 依名稱查詢 | `folio_name` |
| 讀者群組 | `folio_group` |
| 費用擁有者 | `folio_owner` |
| 費用類型 | `folio_feeFineType` |

### 4.3 萬用字元（*）使用

萬用字元 `*` 用於設定預設對應：

```tsv
folio_code	LOCATION
00AT	00AT
00AV	00AV
Migration	*
```

**規則：**
- 所有欄位都是 `*` = 預設映射（必須有）
- 部分欄位是 `*` = 混合映射（部分匹配）

### 4.4 多欄位對應

支援多個來源欄位組合對應：

```tsv
SUB_LIBRARY	PERM_LOCATION	legacy_code	folio_code
msl	infoOff	infoOff	InOFF
msl	jnlDesk	*	JOURDESK
*	maps	maps	MAPZ
*	maps	cd	CeeDee
*	*	*	migration
```

**匹配邏輯：**
1. 完全匹配優先
2. 混合匹配次之（帶 `*` 的欄位）
3. 預設映射最後（所有欄位都是 `*`）

### 4.5 各類 TSV Mapping Files

#### 4.5.1 locations.tsv（館藏地映射）

**範例（migration_example）：**
```tsv
SUB_LIBRARY	PERM_LOCATION	legacy_code	folio_code
msl	infoOff	infoOff	InOFF
msl	jnlDesk	*	JOURDESK
*	maps	maps	MAPZ
*	*	*	migration
```

**範例（migration_thu）：**
```tsv
folio_code	LOCATION
00AT	00AT
00AV	00AV
LB	LB
圖書館	圖書館
Migration	*
```

> **重要**：locations.tsv 第一欄必須是 `folio_code`（對應 FOLIO location 的 `code` 屬性），第二欄是來源資料的欄位名稱。通配符 `*` 放在來源值欄位（第二欄），表示預設對應。

#### 4.5.2 material_types.tsv（資料類型映射）

```tsv
folio_name	MATERIAL_TYPE
A	A
BOOK	BOOK
CD	CD
DVD	DVD
EB	EB
MIGRATION	*
```

#### 4.5.3 loan_types.tsv（借閱類型映射）

```tsv
folio_name	LOAN_TYPE
Reading room	33
Can circulate	42
Can circulate	*
```

#### 4.5.4 item_statuses.tsv（項目狀態映射）

```tsv
legacy_code	folio_name
checked_out	Checked out
available	Available
lost	Aged to lost
```

**注意：** 狀態映射不允許使用 `*` 作為預設，`Available` 是硬編碼的預設值。

#### 4.5.5 user_groups.tsv（讀者群組映射）

```tsv
readerTypeCode	folio_group
A	A
A1	A
B	B
C1	C1
*	error
```

#### 4.5.6 call_number_type_mapping.tsv（索書號類型映射）

```tsv
folio_name	Z30_CALL_NO_TYPE
Dewey Decimal classification	8
Other scheme	*
```

#### 4.5.7 statcodes.tsv（統計代碼映射）

```tsv
ITEM_STAT_CODE_DESC	folio_code
Gift	gift
Alumni	alumni
Faculty	faculty
Staff	staff
```

---

## 五、Mapping Files 與轉檔程式的對應

### 5.1 架構關係圖

```
TaskConfiguration (JSON)
    │
    ├─→ *MappingFileName (JSON mapping file path)
    │       ↓
    │   MappingFileMapperBase
    │       ├─→ ItemMapper
    │       ├─→ HoldingsMapper
    │       ├─→ UserMapper
    │       ├─→ OrganizationMapper
    │       └─→ OrderMapper
    │
    └─→ *MapFileName (TSV mapping file path)
            ↓
        RefDataMapping
            ├─→ LocationMapping
            ├─→ MaterialTypeMapping
            ├─→ LoanTypeMapping
            ├─→ CallNumberTypeMapping
            └─→ StatisticalCodesMapping
```

### 5.2 配置與程式碼對應

#### 5.2.1 ItemsTransformer

**Task Configuration：**
```json
{
  "name": "items",
  "migrationTaskType": "ItemsTransformer",
  "itemsMappingFileName": "item_mapping.json",
  "locationMapFileName": "locations.tsv",
  "materialTypesMapFileName": "material_types.tsv",
  "loanTypesMapFileName": "loan_types.tsv",
  "itemStatusesMapFileName": "item_statuses.tsv",
  "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
  "statisticalCodesMapFileName": "statcodes.tsv"
}
```

**程式碼（item_mapper.py:30-118）：**
```python
class ItemMapper(MappingFileMapperBase):
    def __init__(self, folio_client, items_map, material_type_map, loan_type_map,
                 location_map, call_number_type_map, holdings_id_map,
                 statistical_codes_map, item_statuses_map, ...):

        # JSON mapping file
        self.items_map = items_map

        # TSV mapping files → RefDataMapping
        self.material_type_mapping = RefDataMapping(
            folio_client, "/material-types", "mtypes",
            material_type_map, "name", "MaterialTypeMapping"
        )
        self.loan_type_mapping = RefDataMapping(
            folio_client, "/loan-types", "loantypes",
            loan_type_map, "name", "PermanentLoanTypeMapping"
        )
        self.location_mapping = RefDataMapping(
            folio_client, "/locations", "locations",
            location_map, "code", "LocationMapping"
        )
```

#### 5.2.2 UserTransformer

**Task Configuration：**
```json
{
  "name": "users",
  "migrationTaskType": "UserTransformer",
  "userMappingFileName": "user_mapping.json",
  "groupMapPath": "user_groups.tsv",
  "departmentsMapPath": "user_departments.tsv",
  "useGroupMap": true
}
```

#### 5.2.3 HoldingsCsvTransformer

**Task Configuration：**
```json
{
  "name": "holdings",
  "migrationTaskType": "HoldingsCsvTransformer",
  "holdingsMapFileName": "holdings_mapping.json",
  "locationMapFileName": "locations.tsv",
  "callNumberTypeMapFileName": "call_number_type_mapping.tsv"
}
```

### 5.3 RefDataMapping 處理流程

**程式碼（ref_data_mapping.py）：**

```python
class RefDataMapping:
    def __init__(self, folio_client, ref_data_path, array_name,
                 the_map, key_type, blurb_id):
        # 1. 從 FOLIO 取得參考資料
        self.ref_data = list(folio_client.folio_get_all(ref_data_path, array_name))

        # 2. 設定映射
        self.setup_mappings()

    def setup_mappings(self):
        for mapping in self.map:
            if self.is_default_mapping(mapping):  # 所有 *
                self.default_id = ...
            elif self.is_hybrid_default_mapping(mapping):  # 部分 *
                self.hybrid_mappings.append(mapping)
            else:  # 完全匹配
                self.regular_mappings.append(mapping)

    def get_ref_data_mapping(self, legacy_object):
        # 先查完全匹配
        for mapping in self.regular_mappings:
            if all_keys_match:
                return mapping
        return None  # 使用預設或混合匹配
```

### 5.4 MappingFileMapperBase 處理流程

**程式碼（mapping_file_mapper_base.py）：**

```python
class MappingFileMapperBase:
    def __init__(self, folio_client, schema, record_map, ...):
        # 1. 建立欄位映射
        self.field_map = self.setup_field_map()

        # 2. 提取有 value 的映射（預設值）
        self.mapped_from_values = {
            k["folio_field"]: k["value"]
            for k in record_map["data"]
            if k["value"] not in [None, ""]
        }

    def do_map(self, legacy_object, index_or_id, object_type):
        # 1. 建立 FOLIO 物件並生成 UUID
        folio_object, legacy_id = self.instantiate_record(legacy_object, ...)

        # 2. 遍歷 schema 屬性進行映射
        for property_name, property in self.schema["properties"].items():
            self.map_property(property_name, property, folio_object, ...)

        # 3. 驗證必要屬性
        return self.validate_required_properties(legacy_id, folio_object, ...)

    @staticmethod
    def get_legacy_value(legacy_object, mapping_file_entry, ...):
        # 1. 優先使用 value 欄位
        if mapping_file_entry.get("value"):
            return mapping_file_entry["value"]

        # 2. 從來源取值
        value = legacy_object.get(mapping_file_entry["legacy_field"], "")

        # 3. 應用 replaceValues 規則
        if value and mapping_file_entry.get("rules", {}).get("replaceValues"):
            value = mapping_file_entry["rules"]["replaceValues"].get(value, "")

        # 4. 應用 regex 規則
        if value and mapping_file_entry.get("rules", {}).get("regexGetFirstMatchOrEmpty"):
            value = re.findall(pattern, value)[0]

        # 5. 使用 fallback
        if not value and mapping_file_entry.get("fallback_legacy_field"):
            value = legacy_object.get(mapping_file_entry["fallback_legacy_field"], "")

        return value
```

---

## 六、兩個專案的差異比較

### 6.1 整體比較

| 特性 | migration_example | migration_thu |
|------|------------------|---------------|
| **用途** | 完整範例/測試 | 生產環境 |
| **檔案數量** | 34 個 | 10 個 |
| **涵蓋功能** | Orders, Organizations, Courses, FeeFines | Inventory, Users, Loans |
| **欄位命名** | 英文（Z30_BARCODE） | 中英混合（序號barcode） |
| **複雜度** | 高（多種變體） | 中等（精簡配置） |

### 6.2 JSON Mapping 差異

#### item_mapping 比較

**migration_example（較完整）：**
```json
{
  "folio_field": "barcode",
  "legacy_field": "Z30_BARCODE"
},
{
  "folio_field": "enumeration",
  "legacy_field": "Z30_ENUMERATION_A"
},
{
  "folio_field": "enumeration",
  "legacy_field": "Z30_ENUMERATION_B"
}
```

**migration_thu（較精簡）：**
```json
{
  "folio_field": "barcode",
  "legacy_field": "序號barcode"
},
{
  "folio_field": "volume",
  "legacy_field": "卷號volume"
}
```

**差異：**
- migration_example 使用 Aleph 欄位名稱（Z30_*）
- migration_thu 使用中文描述性欄位名稱
- migration_example 映射更多欄位（enumeration, chronology 等）

#### user_mapping 比較

**migration_example：**
```json
{
  "folio_field": "externalSystemId",
  "legacy_field": "USERNAME"
}
```

**migration_thu：**
```json
{
  "folio_field": "externalSystemId",
  "legacy_field": "email",
  "fallback_legacy_field": "reader_code"
},
{
  "folio_field": "customFields.licenseid",
  "legacy_field": "license_id"
},
{
  "folio_field": "customFields.grade",
  "legacy_field": "grade"
},
{
  "folio_field": "customFields.sex",
  "legacy_field": "sex"
}
```

**差異：**
- migration_thu 使用 fallback_legacy_field 處理空值
- migration_thu 映射 customFields（自訂欄位）
- migration_thu 使用 regex 規則提取 email 和 username

### 6.3 TSV Mapping 差異

#### locations.tsv 比較

**migration_example（多欄位對應）：**
```tsv
SUB_LIBRARY	PERM_LOCATION	legacy_code	folio_code
msl	infoOff	infoOff	InOFF
msl	jnlDesk	*	JOURDESK
*	maps	maps	MAPZ
```

**migration_thu（單欄位對應）：**
```tsv
folio_code	LOCATION
00AT	00AT
LB	LB
Migration	*
```

**差異：**
- migration_example 使用 3 個來源欄位組合對應
- migration_thu 使用單一欄位直接對應
- migration_thu 大部分值直接映射（相同代碼）

#### material_types.tsv 比較

**migration_example：**
```tsv
folio_name	ITEM_TYPE_ID
sound recording	33
video recording	42
book	*
```

**migration_thu：**
```tsv
folio_name	MATERIAL_TYPE
A	A
BOOK	BOOK
CD	CD
MIGRATION	*
```

**差異：**
- migration_example 使用數字代碼
- migration_thu 使用文字代碼，直接對應相同值

### 6.4 功能涵蓋差異

| 功能模組 | migration_example | migration_thu |
|----------|------------------|---------------|
| 書目轉換 | MARC rules | MARC rules |
| 館藏轉換 | MARC + CSV | CSV |
| 項目轉換 | 多種變體 | 單一配置 |
| 讀者轉換 | 基本欄位 | 含 customFields |
| 借閱遷移 | 有 | 有 |
| 預約遷移 | 有 | 無 |
| 課程遷移 | 有 | 無 |
| 訂單轉換 | 有 | 有（但未在 mapping 中） |
| 組織轉換 | 有 | 無 |
| 費用轉換 | 有 | 無 |

---

## 七、最佳實踐與建議

### 7.1 JSON Mapping Files

1. **必須包含 legacyIdentifier**
   ```json
   {
     "folio_field": "legacyIdentifier",
     "legacy_field": "primary_key",
     "fallback_legacy_field": "secondary_key"
   }
   ```

2. **善用 fallback 處理空值**
   ```json
   {
     "folio_field": "username",
     "legacy_field": "email",
     "fallback_legacy_field": "user_id",
     "fallback_value": "unknown"
   }
   ```

3. **使用 rules 進行資料清理**
   ```json
   {
     "folio_field": "personal.email",
     "legacy_field": "email_raw",
     "rules": {
       "regexGetFirstMatchOrEmpty": "([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})"
     }
   }
   ```

4. **固定值使用 value 欄位**
   ```json
   {
     "folio_field": "type",
     "legacy_field": "",
     "value": "patron"
   }
   ```

### 7.2 TSV Mapping Files

1. **必須有預設映射（所有 `*`）**
   ```tsv
   legacy_code	folio_code
   VALUE1	FOLIO1
   *	DEFAULT
   ```

2. **確保 folio_code/folio_name 在 FOLIO 中存在**
   - 程式會驗證映射值是否存在於 FOLIO
   - 不存在會導致錯誤

3. **使用 `*` 建立階層式匹配**
   ```tsv
   LIBRARY	LOCATION	folio_code
   LIB1	LOC1	SPECIFIC
   LIB1	*	LIB1_DEFAULT
   *	*	GLOBAL_DEFAULT
   ```

4. **避免空值**
   - 每個欄位都必須有值
   - 程式會驗證並報錯

### 7.3 命名建議

1. **JSON 檔案命名**
   - `{object_type}_mapping.json`
   - 例如：`item_mapping.json`, `holdings_mapping.json`

2. **TSV 檔案命名**
   - `{reference_type}.tsv` 或 `{reference_type}_mapping.tsv`
   - 例如：`locations.tsv`, `material_types.tsv`

3. **欄位命名**
   - 使用來源系統的原始欄位名
   - 或使用描述性名稱（如 `館藏類型itype`）

### 7.4 驗證清單

在執行遷移前確認：

- [ ] JSON mapping 包含 `legacyIdentifier`
- [ ] TSV mapping 包含預設映射（`*`）
- [ ] 所有 `folio_code`/`folio_name` 在 FOLIO 中存在
- [ ] TSV 檔案沒有空值
- [ ] 來源資料欄位名稱與 mapping 一致
- [ ] 必要的 mapping files 都已建立

---

## 附錄：參考檔案位置

| 檔案類型 | 路徑 |
|----------|------|
| migration_example mapping files | `migration_example/mapping_files/` |
| migration_thu mapping files | `migration_thu/mapping_files/` |
| MappingFileMapperBase | `folio_migration_tools/src/.../mapping_file_transformation/mapping_file_mapper_base.py` |
| RefDataMapping | `folio_migration_tools/src/.../mapping_file_transformation/ref_data_mapping.py` |
| ItemMapper | `folio_migration_tools/src/.../mapping_file_transformation/item_mapper.py` |

---

*文件產生日期：2025-01-26*
*最後更新日期：2026-02-23*
*分析工具：Claude Code*
