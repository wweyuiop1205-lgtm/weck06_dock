# FastAPI 後端

這個資料夾是獨立的 Python 建置上下文。`api/main.py` 提供 HTTP 路由、登入 session、權限檢查與 `/api/v1/ready`；`api/meeting_seed.py` 建立合成展示資料。`backend/` Python 套件包含供應鏈風險、新聞來源審查、What-if、採購提案、決策證據及 SQLite 存取邏輯。外層目錄與內層套件同名，是為了維持程式中的 `from backend...` 匯入路徑。

`Dockerfile` 只安裝 `requirements-api.txt` 並以非 root 使用者運行 FastAPI。資料庫在容器內 `/var/lib/erp/erp.db`，由 Compose 的 named volume 保存；原始碼 repo 不包含資料庫、金鑰或舊版 Streamlit 網站。

API 角色權限由 `backend/access_control.py` 管理。仍保留部分舊 ERP 領域函式作為現有風險與提案流程的依賴，但沒有納入舊 UI；無明確 API 權限上下文的舊入口採拒絕存取。
