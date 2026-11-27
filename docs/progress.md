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

- PR #3 已合併至 `main`，merge commit 為 `9c6464c`。Week 2.1 從此提交開始。

## Week 2.1 第一批語料已完成本機收集與清理

- 本機共 **10 篇 STEEZY 文章、5 支 Ceech 教學影片**，含先前的 2 篇文章和 1 支影片。Margarita 教授的候選影片改用 Ceech 教授的 Nustudios 教學。
- 15 份非空 clean JSON 均通過自動驗證。原始快照、manifest 與衍生檔位於 Git 忽略的 `evaluations/rag/local/week2.1/`。五支影片皆為原語言英文自動字幕，內容人工審核待確認。
- Backend 預設 suite **101 passed、5 skipped**。來源、快照識別、去重疑點、驗證指令與限制見 [RAG 實驗紀錄](../evaluations/rag/report.md#week-21--第一批語料收集與清理)。Chunking、embedding、Qdrant ingestion、retrieval 與 RAG baseline 均未執行。

## Week 2.2 Chunking pilot 與原始批次（歷史紀錄）

- 使用 Week 2.1 選定的 10 篇文章和 5 支 v3 字幕，沿用 pilot 的固定 Qwen tokenizer revision、512 tokens 完整輸入上限及 64 tokens overlap 預算。文章依小節與區塊，字幕依 cue 邊界切分。
- Pilot 先完成 1 篇文章與 1 支影片，原始批次再產出 179 個 chunks（文章 161、影片 18），全數通過正文覆蓋、token 上限、每段新增內容及來源回溯驗證。獨立重跑逐位元一致，兩份 pilot 輸出也一致。當時將批次 JSON、summary 和邊界預覽寫入 Git 忽略的 `evaluations/rag/local/week2.2/batch/`。
- 離線測試 **108 passed、5 deselected**，`git diff --check` 通過。逐來源分布、實際 overlap、標題單獨成塊及短尾段見 [RAG 實驗紀錄](../evaluations/rag/report.md#week-22--選定的-15-份來源完成批次-chunking)。批次 embedding、Qdrant ingestion 和 retrieval 品質評估尚未執行。

### Week 2.2 文章標題處理修正

- 新版 15 份來源共 **154 個 chunks**（文章 136、影片 18）。文章標題進入正文 chunks 的階層前綴，無正文標題保存於標題結構，僅含標題的 chunks 由 23 降至 0。5 份字幕 chunks 與舊批次逐位元一致。
- 新版在 Git 忽略的 `evaluations/rag/local/week2.2/batch-headings-v2/`。正文與標題回溯、token 預算、重跑一致性通過，離線測試 **109 passed、5 deselected**。批次 embedding 與 retrieval 品質尚未評估。[前後比較與重跑指令](../evaluations/rag/report.md#week-22--文章標題改為正文的階層前綴)

### 本輪結案與下次接續

- 採用 transcript v3 去除相鄰滾動字幕重複，衍生輸入只排除整行 `[Music]`、`[Applause]`。保留 ASR 的漏字與錯字，本輪 baseline 不以逐支影片聽音為前提。
- 選用 Qwen/Qwen3-Embedding-0.6B，考量中英跨語言檢索、0.6B 規模、SentenceTransformers 支援及 Apache-2.0。模型選型、候選比較和完整 query instruction 見 [embedding 紀錄](../evaluations/rag/report.md#week-21--embedding-選型與本機-smoke-test)。固定 revision 的 CPU／float32 本機 smoke test 通過，產生 1024 維 L2 正規化向量。檢索品質仍待評估。
- **目前採用 `batch-headings-v2` 的 154 個 chunks**。舊版 179 段的本機批次已刪除，實驗結果仍見 RAG 實驗紀錄。
- **Week 2.2 已完成**。Retrieval 評估集固定為 `week2.2-retrieval-set-v1`，共 **30 題（繁中 15、英文 15）與 61 筆證據**，全部於 2026-11-24 獲使用者確認並標為 `approved`。Q1 下拍時機和 Q2 的兩段 12-point 證據維持 `partial`。
- 本機資料集與預覽位於 `evaluations/rag/local/week2.2/retrieval-pilot-v1/`。Git 追蹤 `evaluations/rag/retrieval-set-v1.lock.json`，記錄版本及 SHA-256；原文摘錄留在本機。完整標註驗證與固定 Qwen tokenizer 的 154 段計數驗證均通過。[RAG 實驗紀錄](../evaluations/rag/report.md#week-22-收尾與版本鎖定)
- **Week 2.3 第一階段已驗收**。用鎖定批次離線產出 154 筆 1024 維文件向量，核對 chunk ID 映射、512-token 輸入上限、64-token overlap 預算、有限數值與 L2 norm。重跑通過產物驗證並重用向量。
- **Week 2.3 第二階段已驗收**。既有 Compose 新增 Qdrant 1.16.3。以固定 client 1.16.2 匯入既有向量，首次、重跑與單獨重啟 Qdrant 後均通過 154 筆 exact count、UUID、向量及來源 payload 驗證。真實 Qdrant synthetic suite 6 passed，非 MySQL suite 120 passed。
- **Week 2.3 第三階段已驗收**。30 題 exact top-5 全數通過本機 dot product 對照。充分方案成員命中與最小充分方案完成均為 29/30，繁中 15/15、英文 14/15。唯一未完成題只命中 partial。離線 suite 131 passed，真實 Qdrant suite 7 passed、零 skip。Qdrant CI workflow 步驟已本機驗證，遠端結果見下方 Week 2.3 分支交接。

### Week 2.3 分支交接

- 將已在本機驗收的三階段交付與 Qdrant CI job 整理至 `feature/week2.3-dense-baseline`，供後續審查。現行 workflow 只在 push 到 `main`、以 `main` 為目標的 PR，或手動觸發時執行。單獨推送此 feature branch 不會觸發 CI。

- [PR #6](https://github.com/HaoHaola/danceflow-ai/pull/6) 已用 merge commit `76a0b3e4deaab5469e8bb8a0d9d5eae54c28e7e6` 合併至 `main`，保留 `a845ed9` 的提交歷史。[PR CI](https://github.com/HaoHaola/danceflow-ai/actions/runs/45862328146) 的 API、MySQL、Qdrant 三個 jobs 均通過。Week 2.5 分支已一般合併該版本的 `origin/main`。

## Week 2.4 Reranker 開發評估

- **探索診斷已完成**。固定資料及模型，比較同一次 exact top-10 的 `k=3 / 5 / 10` 前綴。兩項指標均為 28/30、29/30、30/30。Arm Wave 的充分段排第 6，原始 top-5 baseline 已保留。離線 suite 133 passed。
- **Reranker 開發評估已完成**。Qwen3-Reranker-0.6B 以 MPS／float32 重排固定 top-10。Rerank top-5 的充分方案仍為 29/30，Arm Wave 仍排第 6。Rerank top-3 為 28/30，較同 k dense 救回一題、退步一題。完整流程 P50／P95 為 1.46／2.38 s，保留原 dense baseline。離線 suite 136 passed，結果與回歸案例見 [RAG report](../evaluations/rag/report.md)。
- **Evidence-v1 instruction 對照已完成**。固定候選與模型，top-3 充分方案由 default 的 28/30 升為 29/30，top-5 維持 29/30。兩種 k 都沒有退步題，Arm Wave 充分段仍第 6。90 筆 rerank P50／P95 為 1.52／2.42 s，尚未重測完整流程。保留原 baseline。
- **Evidence-v2 簡測**。加入部位與動作順序提醒後，開發集 top-5 完成升為 30/30，Arm Wave 取回充分段。Top-3 降為 28/30，Dime Stop 定義掉到第 4。結果另存，保留 baseline。
- **BGE 對照已完成**。同批 30 題，top-3 與 top-5 完成均 29/30。單輪 rerank P50／P95 約 0.62／1.08 s，較既有 Qwen 觀測短，選出文字較多。保留現有預設。
- **Evidence-v3 簡測**。比較題補充單側概念證據提示，在這批題目與 evidence-v2 持平。保留 evidence-v2。
- **目前採用**。Exact dense top-10 → Qwen3-Reranker-0.6B（`evidence-v2`）→ top-5。開發集取回 Arm Wave 充分段，top-5 兩項指標 30/30，歷史 dense top-5 為 29/30。Evidence-v2 的 rerank P50／P95 為 1.628／2.372 秒，平均選出 5,229.1 字元／1,203.7 代理 tokens。BGE 為 0.624／1.076 秒、5,585.6 字元／1,289.8 代理 tokens，top-5 完成少一題。比較基於同一批開發題及分開的計時輪次。新題 retrieval 尚未驗證。 [指標和決策](../evaluations/rag/report.md#week-24-檢索決策)

Week 2.3 的交付檔案如下。

| 範圍 | 檔案 |
| --- | --- |
| 批次 embedding | `evaluations/rag/embed_batch.py`、`backend/tests/test_rag_embed_batch.py` |
| Qdrant 部署、匯入與 CI | `compose.yaml`、`evaluations/rag/requirements-qdrant.txt`、`evaluations/rag/ingest_qdrant.py`、`backend/tests/test_rag_qdrant_artifact.py`、`.github/workflows/ci.yml` |
| Dense retrieval 與測試 | `evaluations/rag/evaluate_dense.py`、`backend/tests/test_rag_dense_evaluation.py`、`evaluations/rag/integration/test_qdrant_ingestion.py`（亦涵蓋匯入） |
| 文件與實驗記錄 | `README.md`、`docs/progress.md`、`docs/development-roadmap.md`、`evaluations/rag/report.md` |

## Week 2.5 單題 RAG CLI

- 使用者已確認 OpenAI smoke test 成功。單題 CLI 沿用鎖定的 154 段和既有 Qdrant collection，以 exact dense top-10、Qwen reranker 的 `evidence-v2` instruction 取 top-5。生成使用 Responses API 和 `week2.5-generation-v1`。
- 指定 bounce 問題先完成 dry-run，再完成一筆真實請求。兩次來源完全一致，API 回傳 `gpt-6.1-terra`、`completed`、2,798 tokens，CLI 量測總耗時 14.597 秒。引用 [S1]、[S2] 均存在。未執行 30 題生成評估。 [設定、實測與限制](../evaluations/rag/report.md#week-25-單題-rag-cli)
- API CI job 明確停用 dotenv。以相同 pytest 篩選條件並移除 API key 的本機驗證為 **148 passed、5 deselected**，GitHub Actions 尚待遠端執行。

- **五題 generation 評估已鎖定**。使用者於 2026-11-27 確認 `week2.5-generation-pilot-v1-approved.1`。共用品質分與 RAG 引用檢查各自記錄。
- **成對生成完成**。五題各跑一次 RAG 與 LLM-only，10 筆均 completed，共 13,354 tokens。逐題原始回答、完整來源、使用量及耗時保存在 `evaluations/rag/local/week2.5/generation-pairs-v1-approved.1/`，人工對照從該目錄的 `review.md` 開始。
- **目前離線驗證**。API job 同條件為 151 passed、5 MySQL 測試 deselected。這批變更的遠端 CI 尚未執行。
- **五題評分完成**。ChatGPT 協助審查，使用者於對話確認。兩種模式各五題，三項全部 2／2／2。這批 pilot 分數未呈現 RAG 品質提升。RAG 提供可追溯依據，補充例子仍需核對歸屬。評分與理由另存同目錄的 `scores-v1.json` 及 `review.md`。
- **FastAPI 問答 endpoint 已驗證**。`POST /api/v1/knowledge/ask` 共用 CLI 的 RAG service，首個有效請求驗證並載入模型，後續在同一程序重用。Swagger 與 OpenAPI 路由已確認。一次真實 HTTP 請求回 200，使用 2,850 tokens，客戶端耗時 23.099 秒。獨立結果在 `evaluations/rag/local/week2.5/api-smoke-v1.json`。
- **Endpoint 離線驗證**。167 passed、5 MySQL 測試 deselected。當時未量測真實 warm request，後續 Streamlit 驗證見下方。完整 30 題 generation 與此分支遠端 CI 仍待執行。
- **Knowledge API schema 歸位**。四個問答 Pydantic models 移至 `backend/app/schemas.py`，路由與 runtime 維持在 `knowledge.py`。搬移前後 OpenAPI 一致。離線回歸 167 passed、5 MySQL 測試 deselected，無 key 時 `/health` 回 200、問答回 503，且未載入 RAG runtime。

- **Streamlit 單題問答介面已完成**。繁中介面接受中英文題目，表單提交後透過 HTTP 呼叫既有問答 API。回答引用與其他取回來源分開，執行資訊可展開，Session State 保存成功結果。
- **Streamlit 離線與本機驗證**。前端 AppTest 9 passed，backend 非 MySQL 167 passed、5 deselected。獨立前端 CI job 已配置，遠端未執行。Streamlit 頁面及 backend health 回 200。AppTest 經真實 HTTP 對同一 backend 程序送兩筆問答，首筆與後續的 HTTP 耗時為 21.645／8.932 秒，均回 200 並確認完整回答與五筆來源可顯示。未操作瀏覽器 UI。完整結果在 `evaluations/rag/local/week2.5/streamlit-smoke-v1.json`。

### Week 2.5 本機串接 checkpoint

五題 pilot 評分、真實 FastAPI HTTP smoke，以及 Streamlit AppTest 連真實 backend 的冷／熱請求驗證均已完成。這批 pilot 的兩種模式三項皆為 2／2／2，未呈現 RAG 的品質分數提升。瀏覽器 UI 操作與完整 30 題 generation 評估待完成。原始評估與 smoke 產物留在 Git 忽略的本機目錄。
