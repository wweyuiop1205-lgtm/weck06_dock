# Docker Hub 已發布版本

這裡是私人倉庫 `weck06/erp-risk-demo` 的 Windows 啟停檔與 Compose 設定。GitHub 上的檔案公開，但 `api-bd37ee0`、`web-bd37ee0`、`launcher-bd37ee0` 三個 Docker 映像仍需 `weck06` 帳號權限才能拉取。完整下載步驟見[專案 README](../../README.md)。

若已從 GitHub 下載本 repo，也可在這個資料夾執行 `./start-hub.cmd`；腳本會登入 Hub、拉取映像、等待健康檢查，再列出本機與區網網址。結束時執行 `./stop-hub.cmd`。此模式與根目錄的原始碼建置模式使用不同的 Compose 專案名稱與資料 volume。

如需調整連接埠或 Docker Hub 命名空間，可將 `.env.example` 複製成 `.env` 後修改。不要把含金鑰的 `.env` 提交到 GitHub。
