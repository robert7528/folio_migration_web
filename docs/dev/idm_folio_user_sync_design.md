# IDM ↔ FOLIO 讀者檔同步設計

> 設計文件(尚未實作)。描述一個外部 IDM(身分管理系統)如何與 FOLIO 做讀者
> (user / patron)記錄的異動同步,選用哪些 FOLIO API、以什麼鍵對應、同步策略與待確認項。

## 1. 目標與範圍

- IDM 作為**讀者身分的主檔(source of truth)**,當讀者新增/異動/離校時,把變更同步到 FOLIO。
- 範圍:user 記錄本體(姓名、聯絡、patronGroup、有效期、自訂欄)。**不含**借閱/罰款等交易資料。
- 可選的反向回流:FOLIO 端人工改動的 user 變更,拉回 IDM 對帳。

## 2. 同步方向與角色

```
[IDM 主檔] --(推送異動)--> [FOLIO]      ← 主要方向
[IDM]      <--(增量拉回)-- [FOLIO]      ← 選配,對帳/回填
```

以 **IDM 推送到 FOLIO** 為主軸;FOLIO 不是讀者主檔。

## 3. 對應鍵(最關鍵的設計決定)

**`externalSystemId`** 作為兩邊的身分對應鍵 —— 填 IDM 端**穩定不變**的 user id。

- 同步、比對、upsert 全靠它。一旦選定**不可變動**。
- ⚠️ 現況需確認:THU 遷移時 `externalSystemId` 目前對映的是 `email`(fallback `reader_code`)。
  若 IDM 要用別的 id 當鍵,**上線前要先對齊**(改 IDM 用同一個值,或在 FOLIO 端統一回填)。
- 其他識別碼:`username`(登入帳號)、`barcode`(借書證號)—— 視需要一併維護,但**對應鍵只用一個**。

## 4. API 選用

### 4.1 IDM → FOLIO(推送):`POST /user-import`(首選)

`mod-user-import` 專為「從外部系統同步使用者」設計(SIS/AD/LDAP 場景):

- 以 `externalSystemId` 比對做 **upsert**(有則更新、無則新建)
- 一次批次多筆
- 重要參數:
  - `deactivateMissingUsers`:此次批次未出現的既有 user → 停用(處理離校/離職)
  - `updateOnlyPresentFields`:只更新 payload 有給的欄,不覆蓋未給欄(增量更新建議開)
  - `sourceType`:給 externalSystemId 加前綴命名空間(多來源時用)
- 支援 `customFields`、`patronGroup`(用**名稱**,模組自動解析成 UUID)、`personal.addresses`、`expirationDate` 等

> 註:讀者遷移時 BatchPoster `objectType: Users` 走的就是這支,已驗證可用。

**Payload 結構(範例)**:
```json
{
  "users": [
    {
      "externalSystemId": "<IDM 穩定 id>",
      "username": "...",
      "barcode": "...",
      "active": true,
      "patronGroup": "undergrad",
      "personal": { "lastName": "...", "firstName": "...", "email": "...",
                    "addresses": [ ... ] },
      "expirationDate": "2027-07-31T00:00:00.000Z",
      "customFields": { "grade": "...", "sex": "...", "id_license": "..." }
    }
  ],
  "totalRecords": 1,
  "deactivateMissingUsers": false,
  "updateOnlyPresentFields": true
}
```

### 4.2 IDM → FOLIO(逐筆替代)

量小或要精細控制時:
```
GET  /users?query=externalSystemId=="<id>"      # 查是否存在
PUT  /users/{id}                                 # 更新
POST /users                                      # 新建
```

### 4.3 FOLIO → IDM(反向回流)

FOLIO **無對外 webhook**。兩條路:

1. **增量輪詢(實務首選)**:
   ```
   GET /users?query=metadata.updatedDate > "<上次同步時間>"&limit=...&offset=...
   ```
   IDM 端記住上次同步時間戳,定時增量抓、分頁處理。
2. **Kafka domain events(進階,不建議外部用)**:新版 mod-users 會發 user 變更事件到
   Kafka,但 EBSCO 託管環境通常不對外開放 Kafka,外部 IDM 難取用。

## 5. 認證

- 走 gateway:`X-Okapi-Tenant` + `X-Okapi-Token`(與遷移工具相同)。
- Token 動態、約 1 小時到期 → **IDM 端要自動取得/續用 token**(login 端點換 token,快取到期前刷新)。
- THU tenant:`fs00001280`、gateway `https://api-thu.folio.ebsco.com`。

## 6. 密碼與權限(若 IDM 也管登入)

user 記錄本身**不含密碼**。若 IDM 要連登入一起管:

- 密碼:`POST /authn/credentials`(`{ userId, password }`)
- 權限:`/perms/users`
- 複合操作:`/bl-users`(`mod-users-bl`)可一次處理 user + 權限 + 憑證
- 若改用 SSO/SAML/OIDC,密碼通常不落 FOLIO,只同步身分。

## 7. 同步策略

| 模式 | 時機 | 做法 |
|------|------|------|
| **全量** | 初始載入 / 定期校正 | IDM 匯出全部 → `/user-import`(可開 `deactivateMissingUsers` 清掉已不存在的) |
| **增量** | 日常異動 | 只送有變動的 user;`updateOnlyPresentFields: true` |
| **離校/停用** | 學期末等 | 全量批次 + `deactivateMissingUsers`,或逐筆 `active: false` |

- **批次大小**:依規模分批(數百~數千/批),避免單次過大逾時。
- **排程**:近即時(分鐘級觸發)或定時(每小時/每日)依需求。

## 8. 冪等、衝突、錯誤處理

- **冪等**:upsert 以 externalSystemId 為準,重送同筆不會產生重複。
- **欄位衝突**:`updateOnlyPresentFields` 避免 IDM 沒管的欄被清空(例 FOLIO 端的 barcode 若由館員維護,IDM 不要送該欄覆蓋)。明確劃分「哪些欄由 IDM 管、哪些由 FOLIO 管」。
- **patronGroup / customFields / addressType**:用名稱,需先在 FOLIO 建好對應項(自訂欄
  select 的選項也要齊),否則退件 —— 同遷移時踩過的坑。
- **錯誤回報**:`/user-import` 回傳建立/更新/失敗統計與失敗清單,IDM 端要記錄、重試或告警。

## 9. 待確認 / 前置

1. **`externalSystemId` 對應鍵**:IDM 用什麼當穩定 id?跟 FOLIO 現況(email/reader_code)如何對齊?
2. **SCIM 2.0**:THU tenant 有沒有開 SCIM 佈建端點(IdP 標準對接)?有的話可考慮走標準路;
   沒有就用 `/user-import`。向 EBSCO 確認。
3. **欄位責任劃分**:哪些 user 欄由 IDM 主導、哪些保留給 FOLIO 館員。
4. **密碼/SSO**:登入由 IDM 管還是走 SSO?決定要不要碰 `/authn/credentials`。
5. **token 續用**:IDM 端的 token 取得/刷新機制。

## 10. 參考端點

| 用途 | 端點 |
|------|------|
| 批次 upsert 使用者 | `POST /user-import` |
| 查/改/建單筆 | `GET/PUT/POST /users`、`GET /users/{id}` |
| 增量拉回 | `GET /users?query=metadata.updatedDate > "..."` |
| patronGroup 清單 | `GET /groups` |
| 自訂欄定義 | `GET /custom-fields`(EBSCO gateway 可能未開,改用 UI/UI DevTools 查) |
| 密碼 | `POST /authn/credentials` |
| 複合 user 操作 | `/bl-users` |
