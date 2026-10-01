# 供應鏈風險展示系統｜Vue + FastAPI + Docker

這是供應鏈風險工作台的**公開原始碼**與 Docker 部署說明。Vue 前端和 FastAPI 後端在 Docker Compose 中各自運行。舊版 Streamlit 網站、`app.py`、LINE Bot 與本機資料庫均未收入此 repo。

本 repo 提供兩種啟動方式：有 `weck06` Docker Hub 私人倉庫權限的人可直接拉取已驗證映像；其他人可從公開原始碼自行建置。**GitHub repo 公開，但 Docker Hub 的 `weck06/erp-risk-demo` 仍是私人倉庫**，公開原始碼不會讓其他帳號自動取得私人映像。

要在會議上介紹元件、資料流、L1→L2→L3 流程及設計理由，請看[系統架構與流程說明（會議版）](docs/ARCHITECTURE.zh.md)。

## 資料夾

| 路徑 | 用途 |
| --- | --- |
| [`frontend/`](frontend/) | Vue 3、Vite、Nginx。`src/App.vue` 是工作台，`src/api.ts` 呼叫 FastAPI；`public/` 存放離線地圖與照片。 |
| [`backend/api/`](backend/api/) | FastAPI 路由、登入 session、健康檢查與 Demo 資料初始化。入口是 `api.main:app`。 |
| [`backend/backend/`](backend/backend/) | 供應鏈風險、新聞審查、What-if、採購提案、證據與資料庫等領域邏輯。內層套件沿用 `backend` 名稱，以保持既有 Python 匯入路徑。 |
| [`backend/Dockerfile`](backend/Dockerfile) | 建置 FastAPI 映像；只安裝 API 所需依賴，不安裝 Streamlit。 |
| [`compose.yaml`](compose.yaml) | 從公開原始碼建置並啟動前後端。 |
| [`deploy/docker-hub/`](deploy/docker-hub/) | 已發布私人 Docker Hub 映像的 Compose 設定與 Windows 啟停檔。 |

## 方式 A：在另一台 Windows 電腦直接從 Docker Hub 下載

先安裝並啟動 Docker Desktop，確定 Docker Engine 運作中。開 PowerShell，以有權存取私人倉庫的 `weck06` 帳號登入，依序執行：

```powershell
docker login
docker pull weck06/erp-risk-demo:launcher-bd37ee0
$launcherContainer = docker create weck06/erp-risk-demo:launcher-bd37ee0
docker cp "${launcherContainer}:/launcher/." .\erp-risk-demo
docker rm $launcherContainer
cd .\erp-risk-demo
.\start-hub.cmd
```

`launcher-bd37ee0` 保存 Compose 與啟停檔；腳本接著下載 `web-bd37ee0` 與 `api-bd37ee0`，啟動兩個獨立容器。此流程不需 GitHub 原始碼，也不需在另一台電腦建置。腳本會等待健康檢查並列出網址。結束後在同一資料夾執行 `./stop-hub.cmd`；Docker named volume 中的 Demo 資料會保留。[Docker Hub 倉庫](https://hub.docker.com/repository/docker/weck06/erp-risk-demo/general)須登入才能存取。

## 方式 B：從這份公開原始碼建置

安裝 Git 與 Docker Desktop，複製本 repo 後在專案根目錄執行：

```powershell
git clone https://github.com/wweyuiop1205-lgtm/weck06_dock.git
cd .\weck06_dock
docker compose up --build --detach --wait
```

開啟 <http://localhost:8080>。根目錄 `compose.yaml` 預設只綁定本機 `127.0.0.1`。若要讓同一網路的成員觀看，複製 [`.env.example`](.env.example) 為 `.env`，將 `ERP_WEB_BIND` 改成 `0.0.0.0`，再執行 `docker compose up --detach --wait`。成員使用 `http://<執行電腦的區網 IPv4>:8080`；若無法連線，檢查網路隔離與該電腦的 8080/TCP 防火牆規則。

停止服務：`docker compose down`。這會保留 Docker named volume；不要用 `down --volumes`，除非確定要清空展示資料。

### 區網登入一直顯示「登入中」

在使用者的電腦，先開啟 `http://<執行 Docker 電腦的區網 IPv4>:8080/api/v1/ready`；正常應看到 `{"status":"ready"}`。若打不開，確認 Docker 主機的 `.env` 已設定 `ERP_WEB_BIND=0.0.0.0`、8080 埠沒有被占用，且 Windows 防火牆允許區網連入 TCP 8080。若看到 502/504，請在 Docker 主機的專案根目錄執行 `docker compose ps` 和 `docker compose logs --tail 80 web api`，查看 API 啟動錯誤。若 ready 正常但仍卡在登入，請在瀏覽器開發者工具的「Network／網路」檢查 `POST /api/v1/session` 的狀態；新版前端會在 15 秒後顯示逾時訊息，不會無限轉圈。更新公開原始碼後須重新執行 `docker compose up --build --detach --wait`，讓 Web 容器載入新版本。

## 展示資料與登入

第一次啟動會建立明確標示為「DEMO 合成資料」的供應鏈風險範例，用於展示風險地圖、新聞審查、What-if、提案與證據流程。展示帳號為 `viewer / viewer`、`planner / planner`、`approver / approver`。這些簡單帳密只適合可信任的展示網路，不適合直接對公網開放。

新聞和 AI 服務不是基本展示的必要條件。若要啟用，僅在執行電腦的 `.env` 中設定模型或新聞來源金鑰；`.env` 已被 Git 忽略，請勿提交金鑰、真實 ERP 資料或資料庫。啟用外部 AI 時，What-if 的供應商、採購單與庫存內容可能送往所設定的模型服務。

## 驗證範圍

API 與 Web 映像已從 Docker Hub 推送、回拉，並在來源電腦透過 Hub 啟動檔健康啟動。公開原始碼也已從 `frontend/`、`backend/` 重新建置並啟動：Web 回傳 200、API ready 回傳 `ready`，`planner` 可登入並讀取 8 個供應據點。另一台電腦的實際拉取、瀏覽器開啟及同網路第二台裝置連線，仍需現場驗收。

程式碼採 [MIT License](LICENSE)。港口照片來源：[CHUTTERSNAP / Unsplash](https://unsplash.com/photos/assorted-shipping-containers-in-dock-Q4bmoSPJM18)；地圖採 Natural Earth 公開地理資料。
