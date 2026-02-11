# folio_migration_tools Task Configuration 參數說明

本文件基於 folio_migration_tools 的 JSON Schema 產生，涵蓋 `taskConfig.json` 中所有參數的完整說明。

---

## 目錄

- [libraryInformation（全域設定）](#libraryinformation全域設定)
- [FileDefinition（檔案定義，共用）](#filedefinition檔案定義共用)
- [BibsTransformer（書目轉換）](#bibstransformer書目轉換)
- [HoldingsMarcTransformer（MARC 館藏轉換）](#holdingsmarctransformermarc-館藏轉換)
- [HoldingsCsvTransformer（CSV 館藏轉換）](#holdingscsvtransformercsv-館藏轉換)
- [ItemsTransformer（館藏項目轉換）](#itemstransformer館藏項目轉換)
- [UserTransformer（讀者轉換）](#usertransformer讀者轉換)
- [OrdersTransformer（採購訂單轉換）](#orderstransformer採購訂單轉換)
- [BatchPoster（批次匯入）](#batchposter批次匯入)
- [LoansMigrator（流通借閱遷移）](#loansmigrator流通借閱遷移)

---

## libraryInformation（全域設定）

整個遷移專案的全域配置，所有 task 共用。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `tenantId` | string | 是 | - | FOLIO 租戶 ID。可在 Settings > Software versions 中找到。ECS 環境下為中央租戶 ID |
| `okapiUrl` | string | 是 | - | FOLIO API Gateway URL |
| `okapiUsername` | string | 是 | - | FOLIO 帳號，需有完整管理員權限 |
| `libraryName` | string | 是 | - | 圖書館名稱，用於產出檔案命名和識別 |
| `folioRelease` | enum | 是 | - | FOLIO 版本。可選值：`ramsons`、`sunflower`、`trillium`、`umbrellaleaf` |
| `iterationIdentifier` | string | 是 | - | 迭代目錄名稱，對應 `base_folder/iterations/` 下的子目錄 |
| `logLevelDebug` | boolean | 否 | `false` | 啟用 debug 級別日誌 |
| `multiFieldDelimiter` | string | 否 | `"<delimiter>"` | 多值欄位分隔符，用於 CSV/TSV 中一個欄位包含多個值的情況 |
| `addTimeStampToFileNames` | boolean | 否 | `false` | 是否在產出檔案名稱加上時間戳記 |
| `failedPercentageThreshold` | integer | 否 | `20` | 失敗記錄百分比上限，超過此比例時程序會終止 |
| `failedRecordsThreshold` | integer | 否 | `5000` | 失敗記錄數量上限 |
| `genericExceptionThreshold` | integer | 否 | `50` | 通用例外數量上限 |

---

## FileDefinition（檔案定義，共用）

每個 task 的 `files` 陣列中的檔案物件定義。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `file_name` | string | 是 | `""` | 要處理的檔案名稱 |
| `discovery_suppressed` | boolean | 否 | `false` | 是否在 OPAC 中隱藏（discovery suppressed） |
| `staff_suppressed` | boolean | 否 | `false` | 是否對館員隱藏（staff suppressed） |
| `service_point_id` | string | 否 | `""` | 服務點 UUID（僅用於 Loans） |
| `statistical_code` | string | 否 | `""` | 統計代碼，用於 Inventory 記錄。多個代碼使用 `multiFieldDelimiter` 分隔 |
| `create_source_records` | boolean | 否 | `true` | 是否在 SRS（Source Record Storage）中保留 MARC 記錄。僅適用 MARC 類轉換 |

---

## BibsTransformer（書目轉換）

將 MARC21 書目記錄轉換為 FOLIO Instance 記錄。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱，用於識別和呼叫特定任務 |
| `migrationTaskType` | string | 是 | - | 固定為 `"BibsTransformer"` |
| `files` | FileDefinition[] | 是 | - | MARC21 書目檔案列表 |
| `ilsFlavour` | enum | 是 | - | 來源 ILS 類型，影響 legacy ID 的提取方式。可選值：`aleph`、`voyager`、`sierra`、`millennium`、`koha`、`tag907y`、`tag001`、`tagf990a`、`custom`、`none` |
| `hridHandling` | enum | 否 | `"default"` | HRID 處理方式。`default`：由 FOLIO 自動產生序號 HRID（如 `in00001...`），原 001 移至 035。`preserve001`：保留 MARC 001 值作為 HRID |
| `useTenantMappingRules` | boolean | 否 | `false` | 是否使用 FOLIO 租戶的 MARC-to-Instance mapping rules（而非工具內建規則） |
| `createSourceRecords` | boolean | 否 | `false` | 是否在 SRS 中保留 MARC 來源記錄 |
| `deactivate035From001` | boolean | 否 | `false` | 停用「將 001 連同 003 前綴移到 035」的預設行為 |
| `tagsToDelete` | string[] | 否 | `[]` | 轉換前要從 MARC 記錄中刪除的欄位標籤列表。這些欄位的資料仍會用於轉換，但刪除後不會出現在 SRS 記錄中 |
| `addAdministrativeNotesWithLegacyIds` | boolean | 否 | `true` | 是否在記錄中加入包含 legacy ID 的管理備註（`"Identifier(s) from previous system: XXX"`） |
| `customBibIdField` | string | 否 | `"001"` | 自訂 legacy Bib ID 的 MARC 欄位路徑（如 `"991$a"`）。需搭配 `ilsFlavour: "custom"` 使用 |
| `dataImportMarc` | boolean | 否 | `true` | 是否產生二進位 MARC 檔案，供 FOLIO Data Import 介面匯入使用 |
| `parseCatalogedDate` | boolean | 否 | `false` | 是否解析 catalogedDate 欄位為 FOLIO 接受的日期格式 |
| `resetHridSettings` | boolean | 否 | `false` | 是否在執行結束時重置該記錄類型的 HRID 計數器 |
| `updateHridSettings` | boolean | 否 | `true` | 是否在執行結束時更新 FOLIO 的 HRID 設定 |
| `statisticalCodesMapFileName` | string | 否 | `""` | 統計代碼對應檔（TSV 格式，含 `legacy_stat_code` 和 `folio_code` 欄位） |
| `statisticalCodeMappingFields` | string[] | 否 | `[]` | 用於統計代碼對應的 MARC 欄位列表（如 `["907$a"]`） |

---

## HoldingsMarcTransformer（MARC 館藏轉換）

將 MARC21 館藏記錄（MFHD）轉換為 FOLIO Holdings 記錄。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"HoldingsMarcTransformer"` |
| `files` | FileDefinition[] | 是 | - | MARC21 館藏（MFHD）檔案列表 |
| `legacyIdMarcPath` | string | 是 | - | Legacy ID 在 MARC 記錄中的路徑（如 `"001"` 或 `"951$c"`） |
| `locationMapFileName` | string | 是 | - | 館藏地對應檔（TSV 格式） |
| `defaultCallNumberTypeName` | string | 是 | - | 預設索書號類型名稱（如 `"Library of Congress classification"`、`"Dewey Decimal classification"`） |
| `fallbackHoldingsTypeId` | string (UUID) | 是 | - | 備用 Holdings Type UUID。當無法從來源資料判斷時使用。可從 FOLIO API `/holdings-types` 查詢 |
| `hridHandling` | enum | 否 | `"default"` | HRID 處理方式，同 BibsTransformer |
| `createSourceRecords` | boolean | 否 | `false` | 是否在 SRS 中保留 MARC 來源記錄 |
| `deactivate035From001` | boolean | 否 | `false` | 停用「將 001 連同 003 前綴移到 035」的預設行為 |
| `useTenantMappingRules` | boolean | 否 | `false` | 是否使用租戶的 MARC mapping rules |
| `updateHridSettings` | boolean | 否 | `true` | 是否在執行結束時更新 FOLIO 的 HRID 設定 |
| `resetHridSettings` | boolean | 否 | `false` | 是否重置 HRID 計數器 |
| `holdingsTypeUuidForBoundwiths` | string (UUID) | 否 | `""` | 合訂本（Bound-with）的 Holdings Type UUID |
| `boundwithRelationshipFilePath` | string | 否 | `""` | 合訂本關係檔案路徑（TSV 格式，含 `MFHD_ID` 和 `BIB_ID`） |
| `supplementalMfhdMappingRulesFile` | string | 否 | `""` | 補充 MFHD mapping rules 的檔案名稱 |
| `deduplicateHoldingsStatements` | boolean | 否 | `true` | 是否去除重複的 holdings statements |
| `includeMrkStatements` | boolean | 否 | `false` | 是否將 MARC statements 以 MRK 格式加入 Holdings 備註 |
| `mrkHoldingsNoteType` | string | 否 | `"Original MARC holdings statements"` | MRK statements 的備註類型名稱 |
| `includeMfhdMrkAsNote` | boolean | 否 | `false` | 是否將完整 MFHD 以 MRK 格式加入備註 |
| `mfhdMrkNoteType` | string | 否 | `"Original MFHD Record"` | MFHD MRK 備註的類型名稱 |
| `includeMfhdMrcAsNote` | boolean | 否 | `false` | 是否將 MARC21 二進位記錄解碼後加入備註 |
| `mfhdMrcNoteType` | string | 否 | `"Original MFHD (MARC21)"` | MARC21 解碼備註的類型名稱 |
| `statisticalCodesMapFileName` | string | 否 | `""` | 統計代碼對應檔 |
| `statisticalCodeMappingFields` | string[] | 否 | `[]` | 統計代碼對應的 MARC 欄位列表 |

---

## HoldingsCsvTransformer（CSV 館藏轉換）

從 CSV/TSV 表格資料轉換為 FOLIO Holdings 記錄。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"HoldingsCsvTransformer"` |
| `files` | FileDefinition[] | 是 | - | CSV/TSV 檔案列表 |
| `holdingsMapFileName` | string | 是 | - | Holdings 欄位對應檔（JSON 格式） |
| `locationMapFileName` | string | 是 | - | 館藏地對應檔（TSV 格式） |
| `defaultCallNumberTypeName` | string | 是 | - | 預設索書號類型名稱 |
| `fallbackHoldingsTypeId` | string (UUID) | 是 | - | 備用 Holdings Type UUID（查詢：`/holdings-types`） |
| `callNumberTypeMapFileName` | string | 是 | - | 索書號類型對應檔（TSV 格式） |
| `hridHandling` | enum | 是 | - | HRID 處理方式：`"default"` 或 `"preserve001"` |
| `holdingsMergeCriteria` | string[] | 否 | `["instanceId", "permanentLocationId", "callNumber"]` | Holdings 合併條件。具有相同值的 Holdings 會被合併為一筆 |
| `previouslyGeneratedHoldingsFiles` | string[] | 否 | `[]` | 之前已產生的 Holdings 檔案列表，用於避免重複 |
| `holdingsTypeUuidForBoundwiths` | string (UUID) | 否 | `""` | 合訂本的 Holdings Type UUID |
| `resetHridSettings` | boolean | 否 | `false` | 是否重置 HRID 計數器 |
| `updateHridSettings` | boolean | 否 | `true` | 是否更新 FOLIO HRID 設定 |
| `statisticalCodesMapFileName` | string | 否 | `""` | 統計代碼對應檔 |

---

## ItemsTransformer（館藏項目轉換）

從 CSV/TSV 表格資料轉換為 FOLIO Item 記錄。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"ItemsTransformer"` |
| `files` | FileDefinition[] | 是 | - | CSV/TSV 檔案列表 |
| `itemsMappingFileName` | string | 是 | - | Item 欄位對應檔（JSON 格式） |
| `locationMapFileName` | string | 是 | - | 永久館藏地對應檔（TSV 格式） |
| `defaultCallNumberTypeName` | string | 是 | - | 預設索書號類型名稱 |
| `materialTypesMapFileName` | string | 是 | - | 資料類型對應檔（TSV 格式，查詢：`/material-types`） |
| `loanTypesMapFileName` | string | 是 | - | 借閱類型對應檔（TSV 格式，查詢：`/loan-types`） |
| `itemStatusesMapFileName` | string | 是 | - | 館藏狀態對應檔（TSV 格式） |
| `callNumberTypeMapFileName` | string | 是 | - | 索書號類型對應檔（TSV 格式） |
| `hridHandling` | enum | 是 | - | HRID 處理方式 |
| `tempLocationMapFileName` | string | 否 | `""` | 臨時館藏地對應檔（TSV 格式） |
| `tempLoanTypesMapFileName` | string | 否 | `""` | 臨時借閱類型對應檔 |
| `defaultLoanTypeName` | string | 否 | - | 預設借閱類型名稱（當對應不到時使用） |
| `statisticalCodesMapFileName` | string | 否 | `""` | 統計代碼對應檔 |
| `resetHridSettings` | boolean | 否 | `false` | 是否重置 HRID 計數器 |
| `updateHridSettings` | boolean | 否 | `true` | 是否更新 FOLIO HRID 設定 |
| `boundwithRelationshipFilePath` | string | 否 | `""` | 合訂本關係檔案路徑 |
| `preventPermanentLocationMapDefault` | boolean | 否 | `false` | 防止永久館藏地使用預設值對應 |

---

## UserTransformer（讀者轉換）

從 CSV/TSV 表格資料轉換為 FOLIO User 記錄。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"UserTransformer"` |
| `userFile` | FileDefinition | 是 | - | 讀者資料檔案（注意：此處為單一物件，不是陣列） |
| `userMappingFileName` | string | 是 | - | 讀者欄位對應檔（JSON 格式） |
| `groupMapPath` | string | 是 | - | 讀者群組對應檔（TSV 格式，查詢：`/groups`） |
| `departmentsMapPath` | string | 否 | `""` | 部門對應檔（TSV 格式） |
| `useGroupMap` | boolean | 否 | `true` | 是否使用群組對應檔 |
| `removeIdAndRequestPreferences` | boolean | 否 | `false` | 是否移除 User ID 和借閱偏好 |
| `removeRequestPreferences` | boolean | 否 | `false` | 是否移除借閱偏好 |

---

## OrdersTransformer（採購訂單轉換）

從 CSV/TSV 表格資料轉換為 FOLIO Composite Purchase Order 記錄。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"OrdersTransformer"` |
| `files` | FileDefinition[] | 是 | - | CSV/TSV 檔案列表 |
| `ordersMappingFileName` | string | 是 | - | 訂單欄位對應檔（JSON 格式） |
| `organizationsCodeMapFileName` | string | 是 | - | 供應商組織代碼對應檔（TSV 格式） |
| `acquisitionMethodMapFileName` | string | 是 | - | 採購方式對應檔（TSV 格式） |
| `objectType` | string | 否 | - | 物件類型（通常為 `"Orders"`） |
| `locationMapFileName` | string | 否 | `""` | 館藏地對應檔 |
| `paymentStatusMapFileName` | string | 否 | `""` | 付款狀態對應檔 |
| `receiptStatusMapFileName` | string | 否 | `""` | 收貨狀態對應檔 |
| `workflowStatusMapFileName` | string | 否 | `""` | 工作流程狀態對應檔 |
| `fundsMapFileName` | string | 否 | `""` | 基金對應檔 |
| `fundsExpenseClassMapFileName` | string | 否 | `""` | 基金費用類別對應檔 |

---

## BatchPoster（批次匯入）

將 Transformer 產出的 JSON 記錄批次匯入 FOLIO。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"BatchPoster"` |
| `objectType` | string | 是 | - | 物件類型。可選值：`"Instances"`、`"Holdings"`、`"Items"`、`"Users"`、`"Orders"`、`"Extradata"`、`"SRS"` |
| `files` | FileDefinition[] | 是 | - | 要匯入的 JSON 檔案列表（通常是 Transformer 的產出檔案） |
| `batchSize` | integer | 是 | - | 每批次的記錄數量。建議值：Instances 500、Holdings/Items 1000、Users 250、Orders/Extradata 1 |
| `rerunFailedRecords` | boolean | 否 | `true` | 是否自動重試失敗的批次 |
| `useSafeInventoryEndpoints` | boolean | 否 | `true` | 使用安全的 Inventory 端點（支援 Optimistic Locking）。設為 `false` 會繞過鎖定機制 |
| `upsert` | boolean | 否 | `false` | 啟用 upsert 模式（存在時更新，不存在時新增） |
| `patchExistingRecords` | boolean | 否 | `false` | 在 upsert 時使用 patch（部分更新）而非完整替換 |
| `patchPaths` | string[] | 否 | `[]` | patch 時要更新的欄位路徑列表（JSON Path 格式，省略 `$`）。空陣列 = 更新所有欄位。例：`["statisticalCodeIds", "administrativeNotes"]` |
| `preserveStatisticalCodes` | boolean | 否 | `false` | upsert 時是否保留現有統計代碼 |
| `preserveAdministrativeNotes` | boolean | 否 | `false` | upsert 時是否保留現有管理備註 |
| `preserveTemporaryLocations` | boolean | 否 | `false` | upsert 時是否保留 item 的臨時館藏地 |
| `preserveTemporaryLoanTypes` | boolean | 否 | `false` | upsert 時是否保留 item 的臨時借閱類型 |
| `preserveItemStatus` | boolean | 否 | `true` | upsert 時是否保留 item 狀態 |
| `extradataEndpoints` | object | 否 | `{}` | Extradata 自訂端點字典 |

---

## LoansMigrator（流通借閱遷移）

將未歸還的借閱記錄遷移到 FOLIO。

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱 |
| `migrationTaskType` | string | 是 | - | 固定為 `"LoansMigrator"` |
| `openLoansFiles` | FileDefinition[] | 是 | - | 開放借閱（未歸還）資料檔案列表 |
| `fallbackServicePointId` | string (UUID) | 是 | - | 備用服務點 UUID。當記錄未指定服務點時使用（查詢：`/service-points`） |
| `startingRow` | integer | 否 | `1` | 資料處理的起始行 |
| `utcDifference` | integer | 否 | - | UTC 時區差異（小時），用於日期時間轉換 |
| `itemFiles` | FileDefinition[] | 否 | `[]` | 館藏項目資料檔案列表 |
| `patronFiles` | FileDefinition[] | 否 | `[]` | 讀者資料檔案列表 |

---

## hridHandling 詳細說明

HRID（Human-Readable ID）是 FOLIO 中每筆 Inventory 記錄的人類可讀識別碼。

| 選項 | 行為 | 適用場景 |
|------|------|---------|
| `default` | FOLIO 自動產生序號 HRID（如 `in00001...`、`ho00001...`、`it00001...`）。原 MARC 001 會被移至 035 欄位（除非設定 `deactivate035From001: true`） | 不需要保留原始 ID 作為 HRID 的場景 |
| `preserve001` | 保留 MARC 001 值作為 HRID | 需要保留原始編號方便查詢的場景。注意：001 值必須在 FOLIO 中唯一 |

**影響**：
- `default` 模式下，本地產出的 JSON 不會包含 `hrid` 欄位，需使用 `id_map.json` 反查 legacy ID
- `preserve001` 模式下，HRID 即為原始系統的 ID，驗證和查詢更直觀

---

## UUID 參數對照表

以下參數需要填入 FOLIO 參考資料的 UUID，可透過 web portal 的「Lookup UUID」工具查詢。

| 參數 | 所在 Task | FOLIO API 端點 | 說明 |
|------|-----------|---------------|------|
| `fallbackHoldingsTypeId` | HoldingsMarcTransformer / HoldingsCsvTransformer | `/holdings-types` | 備用 Holdings 類型（如 Monograph） |
| `fallbackServicePointId` | LoansMigrator | `/service-points` | 備用服務點 |

---

## Mapping File 中的 UUID

以下 UUID 出現在 mapping JSON 檔案的 `value` 欄位中：

| 欄位 | 所在檔案 | FOLIO API 端點 | 說明 |
|------|---------|---------------|------|
| `notes[].itemNoteTypeId` | item_mapping.json | `/item-note-types` | Item 備註類型 |
| `notes[].holdingsNoteTypeId` | holdings_mapping.json | `/holdings-note-types` | Holdings 備註類型 |
| `personal.addresses[].addressTypeId` | user_mapping.json | `/addresstypes` | 地址類型 |
| `notes[].typeId` | user_mapping.json | `/note-types` | User 備註類型 |

---

*本文件由 folio_migration_tools generated_schemas 自動分析產生*
