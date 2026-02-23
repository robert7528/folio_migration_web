# 測試 MCP Servers 和 Slash Commands 指南

## 一、測試 MCP Servers

**1. 列出已配置的 servers：**

```bash
claude mcp list
```

**2. 在互動模式中檢查狀態：**

```
/mcp
```

會顯示所有 MCP servers 的連接狀態、可用工具和認證狀態。

**3. 查詢特定 server：**

```bash
claude mcp get <server-name>
```

**4. 實際測試工具：** 直接在對話中使用 MCP 提供的工具，例如：

- GitHub MCP → 試著問「列出我的 GitHub repositories」
- Fetch MCP → 試著說「Fetch https://example.com 的內容」

---

## 二、測試 Slash Commands（自訂 Skills）

**1. 查看所有可用 commands：** 在互動模式中輸入 `/` 然後按 Tab

**2. 直接調用測試：**

```
/deploy
/add-api users
/add-page dashboard
```

**3. 確認 skill 檔案存在：** 檢查 `.claude/` 目錄下的設定。

---

## 三、除錯技巧

| 問題 | 排查方式 |
|------|----------|
| MCP Server 無法連接 | 檢查環境變數、token 是否有效、網路是否通 |
| Slash Command 無法觸發 | 確認 skill 設定檔格式正確，用 `/` + Tab 確認是否出現 |
| 權限問題 | 用 `/permissions` 查看，確認 MCP tools 沒被 blocked |

**查看設定檔位置：**

- 專案級：`.claude/settings.local.json`
- 使用者級：`~/.claude.json`（Windows 在 `%USERPROFILE%\.claude.json`）

**啟用除錯模式：**

```bash
claude --debug
```

---

## 四、專案的 Slash Commands

根據 CLAUDE.md，已設定的 commands：

- `/deploy` — 檢視改動、commit 並 push 到 GitHub
- `/add-api <name>` — 新增 API endpoint
- `/add-page <name>` — 新增前端頁面

直接在 Claude Code 中輸入這些命令即可測試。如果有錯誤，Claude 會顯示相關的錯誤訊息幫助你排查。
