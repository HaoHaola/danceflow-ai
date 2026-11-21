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

## DF-005.1 共用 MySQL fixtures 已完成

- 集中 MySQL fixture、連線安全檢查和測試資料清理至 `backend/tests/conftest.py`。使用 `RUN_MYSQL_TESTS=1` 啟用，並用 `pytest -m mysql` 選取整合測試。
- CI 保留 API job，將兩組 MySQL matrix 合併為單一 MySQL 8.4 job，仍執行 Alembic upgrade/check 與 JUnit 檢查。
- 本機 API **64 passed**，預設 suite **64 passed、5 skipped**。全新隔離 MySQL 8.4 容器的 `upgrade head` 和 `alembic check` 通過。MySQL 合跑 **5 passed、0 skipped**，DF-003、DF-004 單獨執行分別 **1 passed**、**4 passed**。
- 驗證每輪測試寫入的資料皆已清理，事先放入的獨立 user、plan、session 均保留。未設定啟用 flag 時，5 個案例全部 skipped，JUnit 檢查回傳 exit 1。`actionlint` 與 `git diff --check` 通過。
- PR #2 已合併至 `main`（merge commit `d3f9ccf`）。API 與 MySQL jobs 在 PR 和合併後的 `main` CI 均通過。
- CD 待部署目標確定後再實作。

## Week 2 第一個最小交付已完成

- 自製 Markdown 與 WebVTT 已跑通讀取、清理與驗證，產生可回溯至原始行號的 clean JSON。文章有 5 個區塊，字幕有 3 個 cues 並保留時間戳。兩份樣本皆標記為 synthetic，排除於正式 RAG 品質評估。
- 新增測試 **13 passed**，預設 suite **77 passed、5 skipped**，以現有 CI 的篩選條件在本機執行為 **77 passed、5 deselected**。詳細指令與結果見 [RAG 實驗紀錄](../evaluations/rag/report.md)。
- 使用者已人工核對文章的 clean JSON，確認文字、標題階層、清單與 `raw_lines` 均與原始 Markdown 一致。字幕的文字、原始行範圍與時間戳仍待人工確認。
- 匯入 CLI 已支援 `synthetic: false`，並獨立記錄自動驗證、內容審核與評估資格。離線匯入測試 **18 passed**，非 MySQL suite **82 passed、5 deselected**。
- 第一批本機匯入 **3/3**。兩篇 STEEZY 文章以一般 HTTPS 取得 HTML 並擷取 Markdown，YouTube 影片取得原語言英文自動 VTT。三份 clean JSON 皆通過自動驗證，內容審核待確認，正式評估資格維持 `false`。OpenLearn 暫緩。實際檔案、條款與回溯範例見 [RAG 實驗紀錄](../evaluations/rag/report.md)。
- 本輪離線匯入測試 **22 passed**，非 MySQL suite **86 passed、5 deselected**。三份輸出與摘要重跑逐位元一致，原始檔 SHA-256 未變。正式 RAG 評估未執行。

## Week 2 字幕純文字與連續 transcript

- 新增 transcript 處理版本 `1`，保留 cue 原文與來源位置，另產生純文字。只移除具詞級時間或短過渡證據的相鄰重疊，並保存判定理由與字元／時間回溯。可疑重疊保留。
- 真實英文 VTT 的 339 個 cues 產生 18,177 個純文字字元，合併後為 6,145 個字元。移除 326 行副本，共 12,032 字元（含分隔空格），保留 8 處疑點。這些是處理統計，人工審核仍待確認。
- 離線匯入測試 **25 passed**，非 MySQL suite **89 passed、5 deselected**。兩次輸出逐位元一致，原始檔與 manifest SHA-256 未變。Chunking 留到下一輪，正式評估未執行。 [驗證與對照](../evaluations/rag/report.md)

- Transcript 規則版本 `2` 補上相接、恰為 10 ms 的單行滾動副本判定。使用者只確認 `cue-304` 是副本，原始 `1 atm` 保留。重跑新增 3 筆移除，疑點 8 → 5，整份字幕仍待人工審核。離線測試 **34 passed**，非 MySQL suite **98 passed、5 deselected**。 [規則及實測](../evaluations/rag/report.md)

- Transcript 規則版本 `3` 延續已辨識的 10 ms 過渡鏈。`cue-305` 首行 `atm` 併回 `cue-303`，三個 cues 都可回溯，第二行的新講解保留。真實字幕新增 3 筆移除，疑點 5 → 2。離線測試 **37 passed**，非 MySQL suite **101 passed、5 deselected**。整份字幕仍待人工審核。 [規則及實測](../evaluations/rag/report.md)

- Week 2 資料準備交付到 transcript v3。ASR 錯字保留，`cue-169`、`cue-243` 尚待影片抽查，整份字幕人工審核為 `pending`。最新本機產物在 `evaluations/rag/local/transcript-v3/`。遠端驗證見 [RAG 實驗紀錄](../evaluations/rag/report.md)。
- [PR #3](https://github.com/HaoHaola/danceflow-ai/pull/3) 的實作提交 `cb827e3` 已通過 [API 與 MySQL CI](https://github.com/HaoHaola/danceflow-ai/actions/runs/44914866078)。
