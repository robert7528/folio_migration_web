# HyLib 使用者資料匯出成 TSV 指南（SQL Server）

本指南說明如何把 HyLib（SQL Server）的讀者資料正確匯出成 TSV，供 `UserTransformer` 使用。
重點是**在匯出階段就避開三個會讓 user transform 出錯或產生壞資料的坑**。

## 為什麼不直接 `SELECT *` 匯 CSV

THU 第一次匯出踩到的實際問題（2026-06-03）：

| 問題 | 症狀 | 根因 |
|------|------|------|
| **UTF-8 BOM** | transform 每筆 `Could not get a value ... ['reader_code']`，log 被撐到數 MB | CSV 第一行帶 BOM（`EF BB BF`），`csv.DictReader` 把第一欄 key 讀成 `﻿reader_code`，mapping 對不到 |
| **欄位錯位** | grade 欄混進 `note` 的內容（中文、結尾多一個 `"`） | `note` 等自由文字欄含**逗號**但沒用引號包，整列欄位往後位移 |
| **日期欄全毀** | `expired_date` 31695 筆全是 `00:00.0`，transform 把它當「今天」→ user 一灌進去就過期 | 匯出工具對日期欄套了「`分:秒.十分之一`」時間格式，**把日期整個丟掉只剩時間** |

> 三個坑裡，**日期欄全毀最嚴重**：原始日期在壞檔裡已經不存在、救不回來，只能從 SQL 重匯。
> 重新上傳同一支匯出程式產出的檔**沒有用** —— 問題在匯出端，要從 SQL 修。

## 正確做法：分兩步

### 步驟 1：在 SELECT 裡先把問題欄位處理乾淨

不要 `SELECT *`，把日期欄格式化、把自由文字欄的破壞字元清掉：

```sql
SELECT
    reader_code,
    reader_name,
    reader_sex,
    keepSiteId,
    readerTypeId,
    readerTypeCode,
    readerTypeName,
    address,
    address2,
    address3,
    tel,
    tel2,
    -- 日期欄：強制輸出 yyyy-MM-dd（style 23），解決 00:00.0 問題
    CONVERT(varchar(10), register_date, 23) AS register_date,
    CONVERT(varchar(10), expired_date, 23)  AS expired_date,
    email,
    id_license,
    -- note 等自由文字欄：清掉 tab/CR/LF（避免破壞 TSV 的列/欄結構）
    REPLACE(REPLACE(REPLACE(ISNULL(note, ''), CHAR(9), ' '), CHAR(13), ' '), CHAR(10), ' ') AS note,
    grade
FROM dbo.users_table
```

關鍵點：

- **日期欄一律 `CONVERT(varchar(10), 欄位, 23)`** → 輸出 `2026-06-03` 真實日期
  （要含時間用 style 120：`CONVERT(varchar(19), 欄位, 120)` → `2026-06-03 14:30:00`）
- **自由文字欄（note、address 等）用 `REPLACE` 清掉 `CHAR(9)`(tab)/`CHAR(13)`(CR)/`CHAR(10)`(LF)**
  —— 改匯 TSV 後，欄位內若還含 tab/換行一樣會錯位
- 欄位順序、欄名要跟 `user_mapping.json` 的 `legacy_field` 對得上
  （THU 已知對映：mapping 用 `reader_sex`、`id_license`，不是 `sex`、`license_id`）

### 步驟 2：匯出成 TSV（tab 分隔）

> 為什麼用 TSV 不用 CSV：`note` 欄含逗號會破壞 CSV 欄位對齊；改 tab 分隔（文字欄通常沒有 tab）直接繞掉這整類問題。
> THU 之前能正常用的 `users.tsv` 就是 tab 分隔。

> ⚠️ **查詢最前面加 `SET NOCOUNT ON;`** —— 否則 SQL Server 會在結果尾端印「(N 個資料列受到影響)」，
> SSMS Results to Text / sqlcmd 會把這行（外加空白行）一起存進 TSV。那種只有 1 欄的尾列會讓
> `csv.DictReader` 把其餘欄位填成 `None`，transform 最後 halt：
> `usergroups - folio_group (['readerTypeCode']) 'NoneType' object has no attribute 'strip'`。
> bcp 不會輸出 row-count 訊息，沒這問題。

#### 方法 A：bcp（推薦，UTF-8 無 BOM，可自動化）

```cmd
bcp "SELECT reader_code, ... FROM db.dbo.users_table" queryout users.tsv ^
    -c -t"\t" -r"\n" -C 65001 -S 伺服器名 -d 資料庫名 -T
```

- `-t"\t"`：欄位用 tab 分隔
- `-r"\n"`：列用換行分隔
- `-c`：字元模式
- `-C 65001`：UTF-8 **不帶 BOM**（剛好避開 BOM 坑）
- `-T`：Windows 整合驗證（用帳密改 `-U 帳號 -P 密碼`）
- 查詢太長：先建一個 View（把步驟 1 的 SELECT 包成 View），或把 SQL 存成 `.sql` 用 `bcp ... -i query.sql`
- bcp 不會自動輸出欄位標題，需要 header 時在前面手動補一行 tab 分隔的欄名

#### 方法 B：SSMS 介面（一次性、PM 最好操作）

1. SSMS → **工具 → 選項 → 查詢結果 → SQL Server → 以文字顯示結果**
2. 「輸出格式」選 **Tab 分隔（Tab delimited）**，勾「包含資料行標題」
3. **查詢最前面加 `SET NOCOUNT ON;`**（見上方警告）——
   這樣 SSMS 就不會在結尾多印「(N 個資料列受到影響)」那行垃圾，省掉事後濾檔
4. 回查詢視窗按 **Ctrl+T**（結果顯示為文字），執行步驟 1 的查詢
5. 結果區右鍵 → 另存，存成 `.tsv`，編碼選 **UTF-8**
6. ⚠️ 結果區右鍵「Save Results As」只給 CSV（逗號），要 tab **一定走這條 Results to Text**

> 備註：`SET NOCOUNT ON` 去掉「N 列受影響」訊息；SSMS 偶爾仍會在最後留一行空白行，
> 用驗收第 4 條（欄位數檢查）就能抓到，必要時 `awk -F'\t' 'NR==1{n=NF} NF==n'` 濾一下。

#### 方法 C：PowerShell（可自動化，但有兩個雷）

```powershell
Invoke-Sqlcmd -ServerInstance "伺服器名" -Database "資料庫名" -Query "SELECT ..." |
  Export-Csv -Path "users.tsv" -Delimiter "`t" -NoTypeInformation -Encoding UTF8
```

- ⚠️ Windows PowerShell 5.1 的 `-Encoding UTF8` **會加 BOM**
- ⚠️ `Export-Csv` **每個欄位都會包雙引號**（Python csv 讀得了，但不乾淨）
- → 自動化還是推**方法 A（bcp）**

## 驗收：匯出後在 Linux 上自我檢查

把 TSV 放到 `clients/{code}/iterations/{iter}/source_data/users/` 後，先跑這三條再 transform：

```bash
# 1. 檢查 BOM（開頭應該直接是欄名第一個字，不是 ef bb bf）
head -c 3 users.tsv | od -An -tx1
# 若是 ef bb bf → sed -i '1s/^\xEF\xBB\xBF//' users.tsv

# 2. 檢查 grade 欄（假設第 29 欄）值只剩乾淨代碼，沒有中文/結尾引號
awk -F'\t' 'NR>1{print $29}' users.tsv | sort | uniq -c

# 3. 檢查 expired_date 欄（假設第 19 欄）是真實日期，不是 00:00.0
awk -F'\t' 'NR>1{print $19}' users.tsv | sort | uniq -c | head

# 4. 檢查每列欄位數一致（揪出檔尾 row-count 訊息、空白行、被換行拆斷的列）
awk -F'\t' 'NR==1{n=NF; print "header 欄位數:", n} NF!=n{print "壞列 "NR": "NF" 欄"}' users.tsv | head
```

判讀：

- 第 1 條無 `ef bb bf`、第 2 條 grade 只剩代碼、第 3 條 expired_date 是 `yyyy-MM-dd`、第 4 條無壞列 → 乾淨可轉 ✅
- 任何一條不對 → 回 SQL 修匯出，不要硬轉（轉出來是壞資料）
- 第 4 條若只有檔尾幾列欄位數不對（row-count 訊息/空白行），臨時可濾掉：
  `awk -F'\t' 'NR==1{n=NF} NF==n' users.tsv > users.clean.tsv && mv users.clean.tsv users.tsv`

## FOLIO 端搭配設定（custom field）

mapping 把值寫進 `customFields.*` 時，**對應的 custom field 必須先在 FOLIO 建好，否則 post 階段整批退件**（`Total failed = 全部, created: 0`）。光「欄位存在」不夠，refId 跟型別/選項都要對：

- FOLIO → 設定 → 使用者 → 自訂欄位

#### 坑 1：refId 要剛好等於 mapping 的 `customFields.` 後面那段

`customFields.licenseid` 就要找 refId = `licenseid` 的欄位；**顯示名稱對不代表 refId 對**。
（THU 實例：FOLIO 欄位叫 `id_license`，但 mapping 寫 `customFields.licenseid` → 報 `Custom fields do not exist: [licenseid]`。修法是把 mapping 改成 `customFields.id_license` 對齊 FOLIO，或反過來改 FOLIO 欄位。）

#### 坑 2：select（下拉）型欄位 —— 送進去的值要「一字不差」等於選項文字

FOLIO 比對的是**選項的文字本身**（select 欄位沒有「值 vs 標籤」之分，顯示什麼、值就是什麼）。送的值不在選項清單 → 報 `Custom field's options do not exist: [refId = X, options: [送進去的值]]`。三種處理：

1. **改成 Text Field**：任何值都收，最省事（適合不需要固定選項的欄位）。
2. **保留下拉，把所有來源值補成選項**：來源有幾種值，FOLIO 下拉就要有對應幾個選項，且文字完全一致。
3. **在 SQL 端把代碼轉成選項文字**（想要 FOLIO 顯示好看的標籤時）：
   ```sql
   -- THU grade 實例：來源是代碼 0~7，FOLIO 下拉是「N年級 / 不分年級」
   CASE grade
       WHEN '0' THEN '不分年級'
       WHEN '1' THEN '1年級'
       WHEN '2' THEN '2年級'
       WHEN '3' THEN '3年級'
       WHEN '4' THEN '4年級'
       WHEN '5' THEN '5年級'
       WHEN '6' THEN '6年級'
       WHEN '7' THEN '7年級'
       ELSE ''
   END AS grade
   ```
   - ⚠️ 字串要跟 FOLIO 選項**完全一致**（全形/半形、數字位置：`1年級` ≠ `年級1`）。建議直接從 FOLIO 下拉複製文字貼進 CASE。
   - ⚠️ **先確認來源所有值在 FOLIO 都有對應選項**（用 `awk ... | sort | uniq -c` 列出來源有哪些值，逐一比對 FOLIO 下拉，缺的先補）。

- 若某欄 FOLIO 不需要 → 從 mapping 把那條 `customFields.*` 改 `Not mapped` 或刪掉

### post 前檢查 refId（兩個辦法）

mapping 送的 `customFields.<refId>`，那個 `<refId>` 必須剛好等於 FOLIO 裡 custom field 的 refId。post 前先確認，否則整批退件。

#### 辦法 1：curl 查 `/custom-fields`（Okapi-based FOLIO 適用）

先載入 FOLIO 環境變數（THU 用 `get_thu_env`，它只印不 export，要自己 eval 進 shell；輸出的 `✓` 會弄壞 `source <(...)`，故用 sed 換成 `export`）：

```bash
eval "$(get_thu_env | sed 's/^[^A-Z]*/export /')"
echo "$FOLIO_URL | $FOLIO_TENANT | ${FOLIO_TOKEN:0:20}..."   # 確認三個都有值
```

查 user custom fields 的 refId / 型別 / 選項：

```bash
curl -s "${FOLIO_URL}/custom-fields?limit=100" \
  -H "X-Okapi-Tenant: ${FOLIO_TENANT}" \
  -H "X-Okapi-Token: ${FOLIO_TOKEN}" \
  -H "x-okapi-module-id: mod-users" \
  | python3 -m json.tool | grep -E '"refId"|"name"|"type"|"value"'
```

判讀：看到 `"refId": "licenseid"` / `"grade"` / `"sex"` 都在、grade 若是 select 則 options 含 `0`~`7` → ✅。

> ⚠️ **EBSCO 託管的 FOLIO 走 Kong gateway，這條會回 404 `no Route matched`**（帶不帶 `x-okapi-module-id`、加不加版本都一樣）。判斷是「路徑沒開」而非 token 壞掉：同一組 env 打 `curl -i "${FOLIO_URL}/groups?limit=1" ...` 若回 200，就是 `/custom-fields` 這條沒對外開 → 改用辦法 2。

#### 辦法 2：看 post 錯誤訊息 / 小批 test post（EBSCO 等 API 沒開時）

post 的錯誤訊息就是最準的 ground truth：

- `Custom fields do not exist: [licenseid]` → 該 refId 的欄位不存在
- `Custom field's options do not exist: [refId = grade, options: [0]]` → 欄位存在但下拉沒這選項
- 某欄沒報錯 → 它存在且 refId 正確

用小批當試紙:取 header + 前 5 筆做迷你 TSV，把 `migration_config.json` 的 `userFile.file_name` 暫時指過去，transform → post：

- `created 5 / 0 failed` → 三個 custom field refId 全對，config 指回全量檔正式跑
- 仍報 `Custom fields do not exist: [X]` → UI 自動產的 refId 跟 mapping 不一致（如 `licenseid_1`），改 `user_mapping.json` 的 `customFields.X` 對齊 FOLIO 實際 refId
- 註：這 5 筆是真實讀者，post 進去即正式資料的一部分，不用刪

## 相關

- `docs/guides/migration_tasks_and_mapping_files_guide.md` — mapping 檔總覽
- memory `user_transform_bom_gotcha.md` — BOM / 欄名不符的快速診斷
