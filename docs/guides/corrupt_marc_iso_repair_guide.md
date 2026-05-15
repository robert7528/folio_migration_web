# 損壞 MARC ISO 修復流程指南

> 本文件說明當 HyLib 匯出的 MARC ISO 書目檔因 export tool 缺陷導致 folio_migration_tools 無法正常讀取時，如何用 `tools/one_off/` 的修復腳本救回絕大多數記錄，並處理少數需個案手術的超大記錄。

---

## 目錄

1. [適用情境](#適用情境)
2. [根本原因](#根本原因)
3. [整體流程圖](#整體流程圖)
4. [Step 1: preprocess_marc.py 修主檔](#step-1-preprocess_marcpy-修主檔)
5. [Step 2: synthesize_seg3.py 拆超大記錄](#step-2-synthesize_seg3py-拆超大記錄)
6. [Step 3: 合併成最終 ISO](#step-3-合併成最終-iso)
7. [Step 4: 後續轉檔](#step-4-後續轉檔)
8. [異常分類與處理對照](#異常分類與處理對照)
9. [工程師 ↔ PM 分工](#工程師--pm-分工)
10. [THU 2026-05-15 實例](#thu-2026-05-15-實例)

---

## 適用情境

- 來源是單一 MARC 書目檔（ISO 2709 格式）
- `transform_bibs` 跑出來的筆數遠少於預期（例：預期 11802 筆，pymarc 只讀到 4 筆）
- `reports/data_issues_log_*.tsv` 出現 `MARC parsing error`、`Unable to locate end of record marker`、`ascii codec can't decode` 之類訊息

---

## 根本原因

HyLib export tool 有兩個已知缺陷：

1. **Leader length overflow**：MARC21 的 record length 欄位只有 5 位數（上限 99999 byte）。當單筆記錄超過上限（通常是多卷期 serial 把所有卷期塞進同一筆的 095），export 把截位後的錯誤長度寫進 leader。pymarc 信任這個長度跳到下一筆，落在記錄中段，從此整個檔的 record framing 全亂。
2. **個別記錄編碼損壞**：少數記錄 leader 第一個 byte 不是 ASCII 數字，或 directory 不含 001 entry。

關鍵：`0x1D`（end-of-record marker）通常是完整的，所以可以重新用 `0x1D` 切割記錄、重算每筆 leader 長度，救回 ~99.97% 的記錄。

---

## 整體流程圖

```
202605151142-11802.iso (損壞主檔)
        │
        ├──> preprocess_marc.py ──> *_fixed.iso (11798 筆) + *_report.txt
        │                                  │
        └──> synthesize_seg3.py ──┐        │
             (處理 oversized 1 筆) │        │
                  thu_138131_bib.mrc       │
                  thu_138131_holdings.tsv  │
                  thu_138131_items.tsv     │
                                  │        │
                  cat fixed.iso + bib.mrc ─┴──> *_final.iso (11799 筆)
                                  │
                  transform_bibs / extract_095 / append seg3 TSV
                                  │
                  transform_holdings_csv / transform_items / post
```

---

## Step 1: preprocess_marc.py 修主檔

```bash
cd /folio/folio_migration_web/clients/<client>/iterations/<iter>/source_data/instances/
python /folio/folio_migration_web/tools/one_off/preprocess_marc.py 202605151142-11802.iso
```

產出：

- `202605151142-11802_fixed.iso` — 可正常解析的記錄（重算 leader 長度後）
- `202605151142-11802_fixed_report.txt` — 統計與被跳過記錄清單

預設行為：**跳過缺 001 的記錄**（folio_migration_tools 的 Voyager 來源要求 001）。若 PM 決定改用 035 當 legacy id（需另改 mapping rules），加 `--keep-no-001`：

```bash
python .../preprocess_marc.py 202605151142-11802.iso --keep-no-001
```

被跳過的記錄分四類，見 report：`oversized` / `unparseable` / `no_001` / `too_short`。

---

## Step 2: synthesize_seg3.py 拆超大記錄

`oversized`（>99999 byte）的記錄通常是一支多卷期 serial 把幾百個卷期塞進單一 bib 的 095。preprocess 無法處理（不能縮到限制以下），需個案拆解：

```bash
python /folio/folio_migration_web/tools/one_off/synthesize_seg3.py 202605151142-11802.iso --client <client>
```

預設自動偵測第一個 >99999 的 segment（也可 `--segment-index N` 指定）。產出 3 個檔（命名固定 `<client>_<bibid>_*`）：

- `<client>_<bibid>_bib.mrc` — 重建的乾淨 MARC bib（只有書目欄位，無 095，必定 <99999 byte）
- `<client>_<bibid>_holdings.tsv` — 與 `extract_095_standard.py` 同 schema
- `<client>_<bibid>_items.tsv` — 與 `extract_095_standard.py` 同 schema

預設會修 v.132 年份 typo（來源端 `20002` → `2002`）。若 PM 決定不在本地修（等源頭改），加 `--no-typo-patch`。

> ⚠️ synthesize_seg3.py 的書目欄位 tag 順序是**寫死**的（directory 損壞無法從中讀 tag），只針對已知記錄形狀。每次跑都會印出 round-trip 驗證 dump，**套用前務必人工核對**印出的書目欄位是否正確。

---

## Step 3: 合併成最終 ISO

```bash
cat 202605151142-11802_fixed.iso <client>_<bibid>_bib.mrc > 202605151142-11802_final.iso
```

驗證（應為 fixed 筆數 + 拆出的 bib 數）：

```bash
python -c "import pymarc; print(sum(1 for r in pymarc.MARCReader(open('202605151142-11802_final.iso','rb'), permissive=True) if r))"
```

---

## Step 4: 後續轉檔

1. `transform_bibs` 用 `*_final.iso` → 產 `results/instances_id_map.json`（含拆出的 bib id）
2. `extract_095_standard.py *_final.iso` → 產主 `holdings.tsv` / `items.tsv`（拆出的 bib 因無 095 會被略過，正常）
3. 把 seg3 的 holdings/items append 上去（跳 header）：
   ```bash
   tail -n +2 <client>_<bibid>_holdings.tsv >> ../holdings/holdings.tsv
   tail -n +2 <client>_<bibid>_items.tsv   >> ../items/items.tsv
   ```
4. `transform_holdings_csv` → `transform_items` → post

---

## 異常分類與處理對照

| 分類 | 意義 | 處理 |
|---|---|---|
| `ok` | 重算 leader 長度後可正常解析 | 自動寫入 fixed.iso |
| `oversized` | >99999 byte（多卷期塞單筆） | synthesize_seg3.py 個案拆解 |
| `unparseable` | leader / 編碼壞，無法救 | 通常放棄（筆數極少時可接受），或請來源端針對該筆重匯 |
| `no_001` | directory 無 001 entry | 預設跳過；或 `--keep-no-001` + 改 mapping rules 用 035 |
| `too_short` | 空段 / 截斷尾段 | 自動跳過 |

---

## 工程師 ↔ PM 分工

| 步驟 | 終態（web 工具就緒後） | 目前（一次性 script） |
|---|---|---|
| 健康檢查 | PM 在 web 看 ISO Health Check 報表 | 工程師跑 preprocess report，講給 PM |
| 一鍵修 99% | PM 點 autofix 按鈕 | 工程師跑 preprocess_marc.py |
| 異常筆決策 | PM 在 web 勾選處理方式 | PM 跟工程師確認 |
| 個案手術修復 | **永遠工程師做，UI 不出現** | 工程師跑 synthesize_seg3.py |
| 合併 + 轉檔 | PM 在 web 點執行 | PM 在 web 點 transform 流程 |

工程師交付物合約（命名固定）：`<client>_<bibid>_bib.mrc` / `_holdings.tsv` / `_items.tsv`。PM 永遠是同一動作：bib.mrc cat 進主 ISO，TSV append 進主 holdings/items。

---

## THU 2026-05-15 實例

檔案 `202605151142-11802.iso`（11802 筆）：

| 結果 | 筆數 |
|---|---:|
| 重算後可解析 | 11,798 |
| oversized | 1（seg 3 = bib 138131 俗文學叢刊，189378 byte，600 卷） |
| unparseable | 2（seg 0, seg 1，leader 0xef） |
| no_001 | 1（seg 2，有 035 `.b44660042` 可當 fallback） |
| 內含 U+FFFD | 12（中文字壞掉，結構 OK，可接受） |

seg 3 拆出：1 bib（138131）+ 600 items（LB4F 500 卷 v.1\~v.500 + AC 100 卷 v.201\~v.300）+ 6 holdings（依 location × 年份 dedup）。合併後 final.iso = 11799 筆，全部可解析、001 齊全。
