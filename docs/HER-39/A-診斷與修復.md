# HER-39 階段 A：LabPro 無法使用 — 診斷與修復

作者：claude-code（Sonnet）；日期：2026-11-18

## 一句話根因
正式 Web 實例所在的部署目錄 `~/orca/workspaces/labpro-dev/labpro-d1-deploy`（含 venv、`desktop/dist`）已被刪除（Orca 工作區清理，父目錄 mtime 11/18 04:52），仍在跑的舊程序（pid 78074，11/09 起）只剩記憶體中的 index.html，所有 `/lab-pro/assets/*.js|css` 皆 404，頁面白屏。

## 使用者平常怎麼用
- 現役是 **D 輪部署的 Web 版**（非 w2／w3 桌面版）：`engine.web --port 8765`，由 Hermes `control_web.py`（47900，`/lab-pro/` 反向代理，`labpro_proxy.py`）經 Tailscale serve 對外：`https://stevenmac-studio.tailea0f1c.ts.net:47900/lab-pro/`。
- 證據：記憶 `labpro-web-deploy`、`Trading Agents Lab Web-backup-D72/deploy.log`（`D72: started pid 78074 head ef7572f`）、`tailscale serve status`、`lsof` 8765/47900 在聽。

## 重現
- `curl https://…:47900/lab-pro/` → 200（HTML 在記憶體）；`/lab-pro/assets/index-C3wkLKkx.js`、`.css` → **404**；`web-bridge.js` 200。
- `lsof -a -p 78074 -d cwd` → 指向已不存在的 `labpro-d1-deploy`；`ls` 該目錄 → No such file；分支 `her30/d1-deploy` 也已不在。
- 資料庫 `sessions.db` 完好（runs 44 completed／4 failed，batches 11 completed，無執行中）。

## 修復（未改任何程式碼）
1. 備份：`Trading Agents Lab Web-backup-HER39A/`（sessions.db 以 sqlite backup、launch-env.sh）。
2. 新部署樹放在 Orca 清理不到的位置：`git worktree add --detach ~/.local/share/her30/labpro-prod ef7572f`（與原部署同一 commit）。
3. 重建 venv：`uv venv --python 3.12 engine/.venv`，`uv pip install -r requirements.txt -r engine/requirements.txt`（原 requirements.txt 不含 fastapi/uvicorn，需另裝 engine/requirements.txt）。
4. `cd desktop && npm ci && npm run build`，產出 `dist/`（bundle 名稱 index-C3wkLKkx.js，與原部署相同）。
5. 確認無 queued/running 後，停舊程序，用原 `launch-env.sh`（代理模式、secret 檔案路徑；不讀出任何值）啟動：`engine.web --port 8765`（新 pid 43439）。

## 驗證
- 經 Tailscale 網址：`/lab-pro/` 200、`assets/index-C3wkLKkx.js` 200、`web-bridge.js` 200、`web/consent` 已同意、`web/secrets/availability` available（Keychain）、`web/handshake` `{port:8765, proxy:true}`。

## 未驗證
- **尚未實際跑一檔股票分析**（會用到使用者的 LLM 登入／額度，且需瀏覽器 WebSocket＋CSRF）。請使用者開頁面跑一檔最省設定確認；若失敗再看 `Trading Agents Lab Web-backup-HER39A/server-her39a.log`。
- 沒有重啟 launchd 化：這個 LabPro 沒有 launchd plist，是手動啟動；重開機後不會自動起來（維持原狀）。

## 使用者怎麼開
開 `https://stevenmac-studio.tailea0f1c.ts.net:47900/lab-pro/`（需在 Tailnet 內並以擁有者身分登入）。

## 預防與待決
- 部署樹現為 `~/.local/share/her30/labpro-prod`（detached ef7572f）；後續部署請在這裡 checkout 新 commit、build 到 `desktop/dist-next` 再換，不要放在會被 Orca 清理的 workspaces 下。
- 待使用者決定：是否要把 LabPro 做成 launchd 服務（改排程屬主控授權範圍，本階段未做）。
