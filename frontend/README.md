# Vue 前端

這個資料夾是獨立的 Vue 3 + Vite 專案。`src/App.vue` 實作供應鏈風險工作台；`src/api.ts` 使用相對路徑 `/api/` 呼叫 FastAPI。`Dockerfile` 先在 Node 建置靜態檔，再由 Nginx 提供頁面；`nginx.conf` 把 `/api/` 轉送到 Compose 內名為 `api` 的後端服務。

`public/images/` 隨 Web 映像打包，因此地圖與港口照片在展示環境不依賴外網。一般部署請在 repo 根目錄執行 `docker compose up --build --detach --wait`，不需要在主機安裝 Node。
