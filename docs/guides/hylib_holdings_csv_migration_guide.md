# HyLib 館藏/單冊 CSV 遷移指南（hold 表 → holdings + items）

本指南說明如何把 HyLib **`hold` 資料表**(join `marc`)匯出的 CSV，轉成 FOLIO 的
`holdings.tsv` + `items.tsv` 並載入。**取代舊的 MARC 095 抽取流程**
(`extract_095_standard.py`)——改由 HyLib SQL 直接匯出館藏，資料較完整、乾淨。

## 流程概覽

```
HyLib hold 表 CSV (可多檔:一般 + 期刊)
  → convert_hylib_holdings_csv.py  (Data Conversion 頁 or CLI)
  → holdings.tsv + items.tsv  (+ holdings.tsv 複製到 items/)
  → HoldingsCsvTransformer → folio_holdings_*.json → BatchPoster(Holdings)
  → ItemsTransformer        → folio_items_*.json    → BatchPoster(Items)
```

## 前置條件

- **Instances 必須先轉好,且 bib 同批**:holdings/items 透過 `BIB_ID`(= `marc_id`)
  連到 instance。bib MARC 匯出檔的 bib 必須**涵蓋 hold CSV 裡的 marc_id**,否則每筆
  報 `Bib id not in instance id map`。→ **從 HyLib 用同一組 bib 同時匯出 bib MARC + hold CSV**。
- 載入順序:**Instances → Holdings → Items**。

## HyLib 來源 CSV 欄位對照

`hold` 表(join `marc`)匯出。SQL Server CHAR 欄位會補尾空白、NULL 會匯成**文字
"NULL"** —— 轉換器自動 `strip()` 並把字面 `"NULL"` 當空。第一欄帶 UTF-8 BOM
(轉換器用 `utf-8-sig` 讀)。

### 使用到的欄位

| CSV 欄位 | 用途 / 去向 | 必要 |
|---------|-----------|:---:|
| `hold_id` | item 唯一值(`legacyIdentifier`/UUID 種子) | ✅ |
| `marc_id` | `BIB_ID`(連 instance)+ HOLDINGS_ID 第 1 段 | ✅ |
| `keeproom_code` | `LOCATION` + HOLDINGS_ID 第 2 段 | ✅ |
| `collection_code` | `MATERIAL_TYPE` + HOLDINGS_ID 第 3 段 | ✅ |
| `class_type` | `CALL_NUMBER_TYPE` | ✅ |
| `class_no` | 索書號第 1 段 + HOLDINGS_ID 索書號段 | ◐ |
| `author_no` | 索書號第 2 段 + HOLDINGS_ID 索書號段 | ◐ |
| `description3` | 索書號第 3 段 + HOLDINGS_ID 索書號段 | ◐ |
| `description2` | `COPY_NUMBER`(複本號) | ◐ |
| `description_final` | `ENUMERATION`(期數/卷號) | ◐ |
| `barcode` | `BARCODE`(共用碼會清空) | ◐ |
| `remark` | item note(type=Note) | ◐ |
| `annex` | circulation note(noteType=Check out) | ◐ |
| `price` | item note(type=Price;0/空跳過) | ◐ |

(✅ 必要、◐ 有就用沒有就空)

### 不使用的欄位(匯出可省略)

| CSV 欄位 | 為何不用 |
|---------|---------|
| `description4` | 已棄用:= `description_final` 重複或字面 "NULL",且本質是卷期非索書號 |
| `description` | 與 `description_final` 重複 |
| `holdcallNumber` | 改由 `class_no`+`author_no`+`description3` 組,不用原始欄 |
| `status` | item 狀態固定輸出 `Available`(不讀此欄) |
| `keepsite_id/code/name` | location 用 `keeproom_code`,不是 keepsite |
| `keeproom_id/name` | 用 `keeproom_code` 即可 |
| `collection_id/name` | 用 `collection_code` 即可 |
| `destinationdate`、`insert_*`、`update_*` | 目前不對映 |

## 欄位對映

### Holdings

| FOLIO 欄位 | 來源 | 說明 |
|-----------|------|------|
| Former holdings ID(`legacyIdentifier` / `formerIds[0]`) | `marc_id-keeproom_code-collection_code-{索書號}` | 分組鍵;索書號段用 `_` 接(例 `194422-LBSP-MA-830.51_8054_2006`)。無索書號時省略該段(例 `654196-PCC-PN`) |
| `instanceId` | `marc_id`(= 001) | 連 instance |
| `permanentLocationId` | `keeproom_code` | 經 `locations.tsv` |
| `callNumber` | `class_no + " " + author_no + " " + description3` | 見「索書號組成」 |
| `callNumberTypeId` | `class_type` | 經 `call_number_type_mapping.tsv`(CCL / DDC…) |

### Item

| FOLIO 欄位 | 來源 | 說明 |
|-----------|------|------|
| `legacyIdentifier`(item UUID 種子) | **`hold_id`** | **唯一且穩定**。**不可用 barcode**(barcode 不唯一,會 UUID 碰撞掉資料) |
| `barcode` | `barcode` | 共用碼會被清空(見下);期刊多半無 barcode |
| `holdingsRecordId` | 同 Holdings 的 Former holdings ID | 連到所屬 holdings |
| `materialTypeId` | `collection_code` | 經 `material_types.tsv`(BOOK/MA/S/R/PN…) |
| `permanentLoanTypeId` | (空) | 落 `defaultLoanTypeName`(Can circulate) |
| `permanentLocationId` | `keeproom_code` | 經 `locations.tsv` |
| `itemLevelCallNumber` | `class_no + " " + author_no + " " + description3` | item 層;空時**繼承 holdings 的索書號**(effective call number) |
| `copyNumber` | `description2` | 複本號(c.1/c.2) |
| `enumeration` | `description_final` | 期數/卷號(v.263、N.50…) |
| `status.name` | 固定 `Available` | 現有借閱另由 LoansMigrator 處理 |
| `notes[0]`(type=Note) | `remark` | 一般附註 |
| `notes[1]`(type=Price) | `price` | 價格;**0/空跳過**不建 note |
| `circulationNotes[0]`(noteType=Check out) | `annex` | 借閱/可用性附註(不是一般 note) |

> 空的 note(remark/price/annex 沒值)由 folio_migration_tools 的
> `validate_object_items_in_array` 自動丟棄(required 子欄不齊),不會產生空殼 note。

## 索書號 / HOLDINGS_ID 組成規則(重點)

1. **索書號 = `class_no` + `author_no` + `description3`**(非空部分用空格接),例 `830.51 8054 2006`。
   - **`class_no` 是必要條件:沒有分類號就沒有索書號(整個留空)**。孤立的 `author_no` 或
     年份不構成排架號,**不會拼湊**(早期 6 筆期刊 `author_no="2637"`、`class_no` 空,曾被
     錯填成索書號 `2637`,已修)。規則「跟著來源走」——來源無分類號(這些筆 `holdcallNumber`
     本身也空)就留空。
   - **C / J 兩檔同一條規則**,不分檔。
   - holdings 與 item 用**同一組**;item 層空時繼承 holdings(effective call number)。
2. **HOLDINGS_ID 的索書號段** = 同樣三段,但用 **`_`** 接(`830.51_8054_2006`)。
3. **`description4` 不使用** —— 它不是跟 `description_final` 重複(已是 enumeration)就是
   字面 `"NULL"`,且本質是卷期不是索書號。**早期曾把 desc4 接進索書號,導致期刊依卷號
   碎成大量單件 holdings;移除後正常**(test:1315 items 由 352→62 holdings)。
4. **字面 `"NULL"` 一律當空**(SQL 匯出把 NULL 寫成文字;`author_no="NULL"` 曾漏進索書號)。
5. **`class_no` 空(常見於期刊/期刊合訂本)** → 索書號留白、HOLDINGS_ID 省略索書號段
   (`654196-PCC-PN`),同刊同館藏地各期歸**一個 holdings**、各期當 item(enumeration)。

> **無索書號是正常的(全是期刊)**:某次 C+J 測試 2630 筆中有 917 筆無索書號 —— 全是連續
> 性出版品(J 的 PN 現期期刊 799 + C 的 S 期刊合訂本 118),`class_no` 都是真空值(0 筆字面
> "NULL"),**沒有「該有號的一般圖書卻缺號」**。FOLIO 容許 holdings/item 無 callNumber(期刊
> 靠刊名/題名排架)。若未來出現一般圖書無 class_no,那是來源資料缺漏,要從來源補,不是改轉換器。

## 期刊(現期期刊)的特性

期刊匯出檔(檔名常含 `_j_`)與一般館藏**不同批**:

- `collection_code` = `PN`(現期期刊);`hold_id` 帶 **`j_` 前綴**
- **多數無索書號**(class_no/author_no/holdcallNumber 空)→ holdings 索書號留白,
  靠 bib + keeproom 分組(一刊一 holdings)
- 各期靠 `description_final`(N.50、V.120 N.30…)當 **enumeration** 區分

## 多檔合併(一般 + 期刊一次轉)

一般批與期刊批可**一次轉成同一組** `holdings.tsv` + `items.tsv`:

- **Web UI**:Data Conversion 頁 →「館藏/單冊 CSV」型別 → 一次選/拖多個 CSV → 轉換
- **CLI**:`python tools/convert_hylib_holdings_csv.py 一般.csv 期刊.csv holdings.tsv items.tsv`
  (最後兩個參數是輸出,其餘都是輸入)

holdings 跨檔去重、共用 barcode 跨整個集合偵測。

## 匯入前補值與確認(非轉換器問題)

下列是「來源資料」或「目標欄位」層面,**不是轉換邏輯的 bug**,但匯入前要處理/確認:

| 項目 | 狀況 | 處理 |
|------|------|------|
| **BARCODE** | 來源 hold CSV 若**沒有 `barcode` 欄**,則 item 條碼全空(無法流通/掃描) | **一般圖書必補**:請匯出端在 SELECT 加 `barcode` 欄(欄名 `barcode`,轉換器自動帶);期刊常無條碼可空 |
| **LOAN_TYPE** | 來源無此欄,輸出全空 | **刻意** —— 落 `defaultLoanTypeName=Can circulate`(全可流通)。THU 已確認可接受;若要逐冊不同借閱規則才需另給來源欄 |
| **無索書號期刊** | 期刊(PN/S)無 callNumber | FOLIO 容許,**不用補**(見索書號規則的備註) |
| **同卷重複 item** | 同 holdings 下兩筆同 `description_final`、皆無 `COPY_NUMBER`(例 v.161:兩個 hold_id、PRICE 一有一空) | **來源資料問題**:回 HyLib 看兩筆的登錄號/建檔日/barcode —— 真兩本複本則補 `c.1`/`c.2`,重複登錄則刪一筆。轉換器忠實轉了來源 2 筆,非 bug |

## 對照表(沿用 095 流程那套,通常已涵蓋)

| 對照檔 | 對映 | 注意 |
|--------|------|------|
| `locations.tsv` | `keeproom_code` → FOLIO location | THU 已含 LBSP/PCC/JP/LM… |
| `material_types.tsv` | `collection_code` → 資料類型 | 含 BOOK/MA/S/R/PN… |
| `call_number_type_mapping.tsv` | `class_type` → call number type | 含 CCL/DDC(+ `*` fallback) |
| `item_statuses.tsv` | STATUS → 狀態 | 只需 `Available`(轉換器固定輸出 Available) |

custom item note type **"Price"** 需先在 FOLIO 建好(設定 → Inventory → Item note
types),`item_mapping.json` 用其 refId(UUID)。

## 已知坑 / 注意事項

- **barcode 唯一性**:HyLib 會把同一個佔位碼用在多本不同書(如 `20200423010`)。
  FOLIO 要求 barcode 唯一 → 轉換器**把被 >1 個 hold_id 共用的 barcode 清空**(item 仍靠
  hold_id 遷入,日後 FOLIO 補真碼)。
- **HoldingsCsvTransformer hardcoded path bug**:它讀 `source_data/items/`。轉換器/UI
  會**自動把 holdings.tsv 複製一份到 `source_data/items/`**。
- **item legacyIdentifier 必須是 hold_id**:`item_mapping.json` 的 legacyIdentifier
  要對 `ITEM_ID`(hold_id),**不可用 BARCODE**(否則碰撞)。
- **重跑會產生新 UUID**:re-transform 後要 re-post(冪等性靠穩定的 hold_id)。

## 執行步驟

1. (HyLib)用同一組 bib 匯出 bib MARC + hold CSV(一般 + 期刊)。
2. Data Conversion 頁「館藏/單冊 CSV」→ 上傳 hold CSV(可多檔)→ 得 holdings.tsv + items.tsv。
3. 確認 instances 已轉(bib 同批)。
4. 跑 `transform_holdings_csv` → `post_holdings_csv`。
5. 跑 `transform_items` → `post_items`。

## 相關

- `tools/convert_hylib_holdings_csv.py` — 轉換器
- `docs/guides/holdings_csv_transformer_guide.md` — HoldingsCsvTransformer 設定
- `docs/guides/items_transformer_guide.md` — ItemsTransformer 設定
- `docs/guides/hylib_user_export_to_tsv_guide.md` — 同類:user 從 SQL 匯出
