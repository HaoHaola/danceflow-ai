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
