# DanceFlow AI 開發進度

## 已完成與提交

| 項目 | 實際完成 | Git |
| --- | --- | --- |
| DF-001 | FastAPI 基礎、`GET /health` 和具輸入驗證的訓練計畫 draft placeholder。 | `59fa7b9`，已推送至 `origin/main` |
| DF-002 | MySQL Compose、named volume、`SELECT 1` CLI、UTC session、User ORM model 和首份 Alembic revision。`472cb4adbf8b` 已套用到本機開發庫，並驗證 email 唯一限制。 | `c680eb3`，已推送至 `origin/main` |
| DF-003 | 使用者建立與查詢 API。已在 Swagger UI 確認建立回 201、依 ID 查詢回 200 且資料一致、重複 email 回 409。 | `225c314`，已推送至 `origin/main` |

DF-003 提交前的預設測試為 **33 passed、1 skipped**，隔離 MySQL 測試為 **1 passed**。

## DF-004 已完成

- 新增每週訓練計畫的建立、單筆查詢與依使用者分頁列表。列表以 `id DESC` 排序，`limit` 預設 10、最大 20，回傳完整計畫與 sessions。
- 計畫與所有 sessions 在同一個 transaction 內保存。Sessions 依 `position` 保留輸入順序，支援同一天多筆。既有 draft contract 維持原樣。
- Alembic revision `10f04d5c9b21` 新增 `training_plans` 和 `training_sessions`。隔離測試庫與日常開發庫均從 `472cb4adbf8b` 升級至此 revision，並確認既有使用者資料保留。
- 目前提供本機建立與讀取。 `user_id` 指定資料擁有者，尚未驗證呼叫者身分。

## DF-004 驗證結果

- 從 `backend/` 執行 `.venv/bin/python -m pytest`，結果為 **64 passed、5 skipped**。
- 在隔離 MySQL 測試庫執行 `RUN_DF004_MYSQL_TESTS=1 .venv/bin/python -m pytest tests/test_training_plans_mysql.py`，結果為 **4 passed**。
- Swagger UI `/docs` 手動驗證通過，DF-004 review 已完成。

## DF-005 CI 已完成（Week 1.5）

- `.github/workflows/ci.yml` 已透過 PR #1 合併至 `main`（merge commit `5316e36`）。Workflow 執行 API tests，以及使用獨立 MySQL 8.4 service 的 DF-003、DF-004 matrix jobs。
- 兩組 MySQL jobs 執行 `alembic upgrade head` 和 `alembic check`，再執行對應的整合測試。JUnit 檢查要求至少有一項測試且沒有 skipped。
- 本機驗證通過。API **64 passed**、DF-003 MySQL **1 passed**、DF-004 MySQL **4 passed**，`actionlint 1.7.12` 無診斷。兩組 MySQL 測試在未設定啟用 flag 時全部 skipped，JUnit 檢查如預期回傳 exit 1。

| GitHub Actions 觸發方式 | API tests | MySQL DF-003 | MySQL DF-004 |
| --- | --- | --- | --- |
| `pull_request`（目標 `main`） | 通過 | 通過 | 通過 |
| `push`（`main`） | 通過 | 通過 | 通過 |
| `workflow_dispatch` | 通過 | 通過 | 通過 |

### 後續待辦

- 待部署目標確定後再實作 CD。
- 整理 DF-003 與 DF-004 的共用 MySQL fixtures，保留專用測試庫的隔離檢查。
