# Dance Knowledge RAG 實驗紀錄

## 2026-11-21 — Synthetic corpus 匯入與驗證

- **狀態** 已執行。兩份樣本只用來驗證資料流程，明確排除於正式 RAG 品質評估。
- **輸入** `corpus/manifest.json` 記錄原始檔路徑、SHA-256、來源、作者、語言、字幕類型、使用條件與快照版本。兩份自製快照的版本均為 `1`。STEEZY 和 Dance With Ceech 仍是候選來源，尚未確認個別 URL 或取得資料。
- **決策** 用本機 Markdown 與 WebVTT 快照驗證兩種輸入結構，使用 Python 標準函式庫。日後若實際字幕軌需要更完整的格式支援，再依樣本決定是否引入 parser。
- **清理版本** `1`。原始檔先以位元組驗證 SHA-256，再讀取 UTF-8。清理會移除 BOM、統一換行、移除行尾空格與 tab，並以空行分隔區塊。文章支援一般段落、清單原文與 ATX 標題階層。輸出保留措辭和自 1 起算的原始行範圍，範圍包含首尾。
- **輸出** 每份文件各一個 UTF-8 JSON，包含 metadata、清理版本、區塊或 cue。輸出無執行時間，檔案自身的 SHA-256 與筆數列在 stdout 摘要。相同輸入與清理版本重跑時，輸出與摘要一致。

### WebVTT v1 支援範圍

支援不帶附加文字的 `WEBVTT` 標頭、標頭後的空行，以及空行分隔的 cues。Cue 可有一行由 ASCII 字母、數字、底線或連字號組成的來源 ID。時間接受 `MM:SS.mmm` 與 `HH:MM:SS.mmm`，輸出為整數毫秒。開始時間依序非遞減，結束須晚於開始；不同 cues 可以重疊。文字可有多行，保留重複字幕、數拍、`[Music]` 等提示。

附加標頭內容、`NOTE`、`STYLE`、`REGION`、cue 位置等 timing settings、HTML 或 WebVTT cue markup、文字實體及內嵌時間戳均超出這一版範圍。遇到不支援的語法或無效時間區間，程式回報檔名和行號，並以非零狀態結束。自動去重留作獨立實驗。

### 實際驗證

從 repository 根目錄執行：

```sh
out="$(mktemp -d)"
backend/.venv/bin/python evaluations/rag/prepare_corpus.py \
  --manifest evaluations/rag/corpus/manifest.json --output-dir "$out"
```

| Clean JSON | 筆數 | SHA-256 |
| --- | ---: | --- |
| `synthetic-groove.json` | 5 | `bf8121332259063cd329fbfd7a74787fa977131f49b5e993dd6f3fe92ba88b41` |
| `synthetic-counts.json` | 3 | `e20a70d0f8a3ec27536dd23c2c5effb1350bc7da81a018ef6fbbf9dfa60c678a` |

從 `backend/` 使用 Python 3.13.3 執行：

| 指令 | 觀察結果 |
| --- | --- |
| `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_preparation.py` | 13 passed，涵蓋輸出重現性、原始檔不變、回溯位置、重複 cue、邊界時間及錯誤診斷 |
| `.venv/bin/python -B -m pytest -p no:cacheprovider` | 77 passed，5 個需啟用的 MySQL 整合測試按預設跳過 |
| `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql' --collect-only` | 沿用現有 CI 的 marker 篩選，共收集 77 個案例，包含 13 個新案例 |
| `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` | 77 passed，5 deselected |

以上 pytest 各出現一則既有 Starlette TestClient 棄用警告。根目錄 `git diff --check` 無 whitespace 診斷。

### 人工核對

- 使用者已人工核對 `synthetic-groove.json`，確認文字、標題階層、清單與 `raw_lines` 均與原始 Markdown 一致。
- `synthetic-counts.json` 的文字、`raw_lines` 與 cue 起訖時間仍待人工確認。目前已有自動測試結果。

### 未執行

- 真實來源匯入、字幕自動去重及 chunking 比較均未執行。
- Dense baseline、檢索品質、延遲與任何正式 RAG 評估均未執行。

## 2026-11-21 — 第一批真實資料匯入規劃

已查核公開來源頁與平台條款。三筆皆為候選，授權與實際快照版本待確認。以下相容性來自閱讀清理版本 `1` 的程式，真實輸入的驗證尚未執行。

| 候選來源 | 教學主題與選取理由 | 取得方式與格式相容性 |
| --- | --- | --- |
| [The Ultimate Beginner Dance Guide](https://www.steezy.co/posts/how-to-be-a-good-dancer) · STEEZY，Charise Roberts | 音樂、基本 groove 與 freestyle 入門。編號清單和分節可驗證標題階層與清單原文保留。 | 經授權後向 STEEZY 取得文本，或依授權從公開頁手動整理正文為 UTF-8 Markdown。現有 parser 支援 ATX 標題、段落與清單文字，網頁 HTML 須先轉換。 |
| [How To Execute Movement For Beginner Dancers](https://www.steezy.co/posts/how-to-execute-movement) · STEEZY，Jessie Ma | Hitting、動作速度與質感。分節搭配練習要點，可驗證技術術語與項目清單的保留。 | 同樣經授權後取得 Markdown 快照，只整理正文，將導覽、促銷和嵌入媒體排除在快照正文之外。現有 parser 可處理整理後的 Markdown。 |
| [Dance Tutorial Basics: Hip Hop Bounce](https://www.youtube.com/watch?v=Aj34T435FAg) · Nustudios 上傳，影片說明標記 Dance With Ceech | 從 bounce、重心轉移練到手腳配合與八拍。影片章節可協助定位抽查區段。 | 先在播放器確認英文 CC 或 Show transcript、字幕語言與人工或自動類型，目前未確認。優先向權利人取得已授權且含起訖時間的 WebVTT。現有 parser 接受基本 WebVTT cues，含定位設定、markup 或內嵌時間戳的輸入會報錯。僅有畫面上的起始時間時，仍須取得 cue 結束時間。 |

- **文章使用條件** 兩篇共用 STEEZY 服務條款。條款將一般使用授權限於服務本身。匯入前取得涵蓋專案儲存與處理的事前書面許可，另記錄 Git 或公開展示的許可範圍。 [STEEZY Terms of Service](https://www.steezy.co/terms)
- **字幕使用條件** Show transcript 可用於平台內查看。匯入前確認字幕權利人允許專案儲存與處理，並確認取得方式符合平台條款。官方 `captions.download` 支援要求 VTT 格式，需有影片編輯權限，可由有權限的上傳者操作。 [YouTube 台灣服務條款](https://tw.youtube.com/t/terms) · [Show transcript](https://support.google.com/youtube/answer/15930243) · [Captions download](https://developers.google.com/youtube/data/reference/rest/v3/captions/download)
- **CLI 限制** `prepare_corpus.py` 目前要求 `synthetic: true` 和 `eligible_for_rag_quality_evaluation: false`。三筆真實資料都會被現有 CLI 拒絕，即使格式符合個別 parser。待另行核准後再調整 manifest 驗證，保留真實標記 `synthetic: false`，第一批的品質評估資格先設為 `false`。

### 最小匯入計畫

1. 逐筆記錄來源 URL、作者或頻道、使用範圍與授權證據。先確認影片字幕軌是否存在及其語言、類型。授權不明、字幕不可取得或格式不相容的項目先保留候選狀態。
2. 下一輪取得授權後，建立兩份 UTF-8 Markdown 與一份含起訖時間的 WebVTT 快照，使用獨立 manifest 記錄取得日期、快照版本、路徑、SHA-256 與字幕類型。若字幕需要格式整理，保留所取得的原檔與轉換紀錄。文章的 `raw_lines` 對應本機 Markdown 快照。
3. 待核准 CLI 支援真實 manifest 後，清理到暫存目錄。確認每筆非空、重跑 SHA-256 一致，抽查文章標題、清單及原始行範圍，並按影片章節抽查字幕文字與起訖時間。首批驗收止於 3 份可追溯的 clean JSON。

本輪只記錄選源與相容性，未下載全文或字幕檔，真實匯入與正式品質評估未執行。

## Week 2 — 真實 manifest 支援與來源取得結果

### 來源取得

| 來源 | 實際查核與結果 |
| --- | --- |
| [The Ultimate Beginner Dance Guide](https://www.steezy.co/posts/how-to-be-a-good-dancer) · Charise Roberts | 公開頁能查到英文正文、分節與清單。[STEEZY 條款](https://www.steezy.co/terms) 明確限制站外專案重製與儲存。未建立快照。 |
| [How To Execute Movement For Beginner Dancers](https://www.steezy.co/posts/how-to-execute-movement) · Jessie Ma | 公開頁能查到英文正文與練習要點。適用相同條款，未建立快照。 |
| [Dance Tutorial Basics: Hip Hop Bounce](https://www.youtube.com/watch?v=Aj34T435FAg) · Nustudios | 影片標題及說明可查。尚未確認字幕語言代碼、人工或自動類型、是否翻譯。[YouTube 台灣條款](https://tw.youtube.com/t/terms) 限制未經許可的自動存取及下載，本機也沒有 `yt-dlp`。未執行 `yt-dlp --list-subs` 或 `youtube-transcript-api`，未取得字幕、影片或音訊。可向上傳者索取原語言人工 VTT，其次為原語言自動 VTT，並確認可供本專案使用的範圍。 |
| [Posture, alignment and balance](https://www.open.edu/openlearn/education-development/dance-skills/content-section-2) 與 [Dance combinations](https://www.open.edu/openlearn/education-development/dance-skills/content-section-3) · OpenLearn / The Open University | 替代教材涵蓋對位、平衡及舞步組合。[課程致謝與授權](https://www.open.edu/openlearn/mod/oucontent/view.php?id=3140&printable=1) 標示課程自有文字為 CC BY-NC-SA 4.0，另列第三方材料。可用於本地非商業流程開發，需保留署名、授權與修改紀錄，分享衍生內容時遵守相同授權。以 curl 8.7.1 分別請求公開 HTML，初次 sandbox 環境發生 DNS 解析錯誤，授權重試後兩個 URL 均回傳 HTTP 403（curl exit 56）。未取得可雜湊的原始快照。 |

實際取得並匯入 **0 篇文章、0 支影片字幕**。沒有來源／快照版本、下載日期或雜湊可記錄。無實際字幕格式可供確認，WebVTT parser 維持 v1 支援範圍。

### 已實作的資料契約

- 第三方原始檔、衍生 Markdown／VTT、manifest、clean JSON 放在 Git 忽略的 `evaluations/rag/local/`。沿用既有欄位，真實來源另填 `acquisition_tool`（名稱與版本）。未知的來源資訊用 `unknown` 明記，`raw_sha256` 必須為文件實際雜湊。
- 網頁擷取與 Markdown 清理分兩步。取得可用的原始 HTML 後，保存於 `raw/` 並填 `original_path`、`original_sha256`。從正文標題起取到章節正文最後一段或清單，排除導覽、站點頁尾與第三方附件，將標題、段落、清單和原文轉成 UTF-8 Markdown，填寫 `extraction_method` 與 `extraction_boundary`。OpenLearn 可用章節 H1 至上一頁／下一頁導覽前作為邊界。第二步由 reader 驗證 HTML 與 Markdown 雜湊後，從 Markdown 產生可回溯至該快照的 `raw_lines`。HTML 到 Markdown 的保真度需由來源抽查驗證。
- 真實字幕記錄 `caption_type` 與 `caption_is_translation`。基本 VTT 可直接作為 reader 輸入。未來若以其他格式取得或需要轉換，保留原始快照與 SHA-256，記錄轉換方法及原始時間資訊。現有 reader 保留 cue 行號、起訖時間、重複文字與節拍提示。
- `validation_status` 由本次執行產生。檔案、metadata、時間或非空檢查失敗時，CLI 以非零退出，摘要與 clean JSON 不產出。可解析但文字與正規化來源對不起來時標記 `needs_review`。成功摘要包含輸入與輸出文字行數、行尾空白及 BOM／換行正規化紀錄。清理規則仍為 `1`，輸出 JSON 的 metadata 已擴充。
- `review_status` 預設 `pending`，`review_method` 預設空值。已有人工結果時可於 manifest 記錄 `reviewed`、`manual_full` 或 `manual_sample` 和輸出的 `review_fingerprint`。原始／reader 輸入雜湊、來源版本、取得／擷取方式或清理版本變化時，現有審核結果會回到待核對。首批真實資料的 `eligible_for_rag_quality_evaluation` 維持 `false`，synthetic fixture 亦排除於正式評估。

### 實測與抽查

- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_preparation.py`，**18 passed**。`.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'`，**82 passed、5 deselected**。各有一則既有 Starlette TestClient 棄用警告。真實 manifest 的測試使用自製位元組，CI 無須外部網站。
- 使用本節前述 `prepare_corpus.py` 指令輸出至兩個暫存目錄，`cmp` 確認各份 clean JSON 與摘要逐位元一致，執行前後原始檔 SHA-256 一致。`git check-ignore` 確認本機原始及衍生輸出路徑都被忽略。
- 真實來源對照待取得後執行。下表為自製樣本的抽查位置。字幕仍待人工確認。

| 位置 | 原始快照 | Clean JSON |
| --- | --- | --- |
| 文章段落 | 第 5 行 `Shift your weight slowly on counts 1 and 3.` | `block-3` 相同文字，`raw_lines: [5, 5]` |
| 字幕開頭 | 第 3–6 行，00:00.000–00:02.000，`[Music]` 與 `Count 5, 6, 7, 8.` | `cue-1`，0–2000 ms，兩行文字保留 |
| 字幕中段 | 第 8–9 行，00:01.500–00:03.000，`Count 5, 6, 7, 8.` | `cue-2`，1500–3000 ms，相同文字 |
| 字幕結尾 | 第 11–12 行，00:03.000–00:04.000，`Count 5, 6, 7, 8.` | `cue-3`，3000–4000 ms，重複文字保留 |

真實來源匯入、HTML 擷取驗證、真實字幕抽查、正式評估指標與 RAG 品質結果均未執行。

## 2026-11-21 — STEEZY 與 YouTube 第一批本機匯入

本輪依更新後的範圍完成 **3/3** 筆取得與本機匯入，OpenLearn 暫緩。以下路徑相對於 Git 忽略的 `evaluations/rag/local/`。三筆資料的授權均未確認，內容審核均為 `pending`，正式 RAG 評估資格均為 `false`。

| 來源 | 實際取得 | 快照與輸出 |
| --- | --- | --- |
| [The Ultimate Beginner Dance Guide](https://www.steezy.co/posts/how-to-be-a-good-dancer) · Charise Roberts | 一般 HTTPS GET 回傳 200，無登入或付費頁。 | `raw/steezy-how-to-be-a-good-dancer.html`、同名 `.md`、`clean/steezy-how-to-be-a-good-dancer.json`，100 blocks |
| [How To Execute Movement For Beginner Dancers](https://www.steezy.co/posts/how-to-execute-movement) · Jessie Ma | 一般 HTTPS GET 回傳 200，無登入或付費頁。 | `raw/steezy-how-to-execute-movement.html`、同名 `.md`、`clean/steezy-how-to-execute-movement.json`，27 blocks |
| [Dance Tutorial Basics: Hip Hop Bounce](https://www.youtube.com/watch?v=Aj34T435FAg) · Nustudios | `yt-dlp --list-subs` 列出自動字幕，人工字幕欄回報 `has no subtitles`。指定 `en-orig` 取得原語言英文（VTT `Language: en`），自動字幕，非翻譯。 | `raw/youtube-Aj34T435FAg.en-orig.vtt`、`clean/youtube-hip-hop-bounce.json`，339 cues |

- **工具與條件** 2026-11-21 以 curl 8.7.1 取得 HTML。依 `--skip-download --write-auto-subs --sub-langs '^en-orig$' --sub-format vtt` 取得 VTT。取得環境為 `local/.venv/`，安裝 yt-dlp 2026.10.26 與 Beautiful Soup 4.15.0。字幕查詢及下載都有 JavaScript runtime 警告，VTT 寫入另有無 impersonation target 的警告，查詢與寫入仍都以 exit 0 結束。原始輸出保存在 `acquisition/youtube-list-subs.log` 與 `acquisition/youtube-download.log`。本機僅有 VTT，沒有下載影片或音訊，未使用 youtube-transcript-api。
- **使用條件** STEEZY 條款限制服務外的重製與儲存，YouTube 台灣條款限制自動存取、下載與再利用。技術取得結果已記錄，專案專用許可未知，全文、衍生資料及取得紀錄僅留本機。 [STEEZY 條款](https://www.steezy.co/terms) · [YouTube 台灣條款](https://tw.youtube.com/t/terms)
- **正文擷取** 本機 `prepare_manifest.py` v1 使用 Beautiful Soup 的 `html.parser`，取 `h1.post-header` 與 `div.rich-text.w-richtext`。輸出保持 HTML 標題層級、分段、列表順序及正文文字，統一 HTML 空白，將連結及行內樣式保留為可見文字。省略無文字的媒體 figure、空元素與正文邊界外的版面。擷取時逐行比對去掉 Markdown 結構標記後的文字與 HTML 節點文字。既有 reader 只執行後段 Markdown 清理。
- **VTT 規則** 清理版本 2 僅用於這種帶 `Kind: captions` 與 `Language: en` 標頭的樣本。輸出保留標頭、cue 定位設定、行號、起訖時間，以及 `<時間戳><c>…</c>` 和 `&amp;` 原文。空白字幕行清為空字串並保留行位置，兩個純空白 cues 亦保留時間範圍。整份字幕仍需有非空文字，遇到未支援語法或不合法時間會報錯。Markdown 與基本 VTT 仍走版本 1。
- **雜湊與驗收** `manifest.json` 保存來源、取得日期、快照版本與 SHA-256，`acquisition/before.sha256` 和 `acquisition/validation-summary.json` 保存原始及輸出驗證結果。重跑擷取與清理後，原始 HTML、Markdown、VTT、manifest 的雜湊均相同，兩輪 clean JSON 與摘要亦逐位元相同。自動驗證三筆皆為 `passed`，文字行數清理前後依序為 115、46、678。

| 來源對照 | Clean JSON |
| --- | --- |
| Beginner Guide 正文第一個有序清單由「Get inspired」開始，Markdown 第 7–22 行 | `block-4`，`raw_lines: [7, 22]`，保留 16 個清單項目 |
| Execute Movement 文章的 Hitting 小節，Markdown 第 5 行 | `block-3`，`raw_lines: [5, 5]`，同一小節標題 |
| VTT 第 5–7 行，00:00:00.880–00:00:23.529，含 `[Music]` 與定位設定 | `cue-1`，880–23529 ms，`raw_lines: [5, 7]`，保留音樂提示及 `cue_settings` |

從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_preparation.py` 得 **22 passed**，執行 `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` 得 **86 passed、5 deselected**。兩次各有一則既有 Starlette TestClient 棄用警告。MySQL 測試與正式 RAG 品質評估未執行。

## 2026-11-21 — 字幕純文字、滾動去重與連續 transcript

- **輸入** 沿用 `local/raw/youtube-Aj34T435FAg.en-orig.vtt`，SHA-256 為 `70ed2782897d18b6f45ca216fce1246605133be1c7f2fb40c275a21075334c9a`，使用既有 manifest，無重新下載。保留舊版 `local/clean/`，本輪輸出為 `local/transcript-v1/youtube-hip-hop-bounce.json`，SHA-256 為 `6498b54eb1e3a2562b75e54c97aff3a3988ae2f7252bb7621e9caa060effd2aa`。
- **純文字** 保留 cue 的 `text`、兩種 ID、起訖時間、定位設定與 `raw_lines`。`plain_text` 移除已支援的 `<時間戳><c>…</c>` 標記，解碼有分號的已識別 HTML entities，將空白折成單一空格。未知顯示標記或 entity 會回報檔案與行號。純空白 cue 仍在來源記錄中，合併時不產生文字，並中斷相鄰重疊比對。
- **去重** 只比對時間相接或重疊的相鄰 cues，尋找前一 cue 尾端與下一 cue 開頭的相同整行。有相同的詞級時間標記，或已具詞級時間的同一行穿過相接且至多 10 ms 的過渡 cue，才移除副本。規則保留不同詞級時間的重複文字。只有部分詞重疊，或整行重疊但時間證據不足時，保留文字並列入 `doubts`。每次移除在 `removals` 記錄前一 cue、移除來源、保留來源、文字範圍與理由。
- **合併與回溯** 以單一空格串接保留下來的文字。沒有補標點或推斷教學邊界。獨立的 `[Music]` 類提示保留且標為 `hint`。每段 `char_range` 對應合併文字，每筆來源的 `plain_range` 對應該 cue 的 `plain_text`。兩者都是 Unicode code point、從 0 起算的半開區間 `[start, end)`。段間空格沒有來源範圍。段的時間覆蓋所有來源 cues 的最早開始至最晚結束，未推測詞級起訖。來源 cue ID 可再定位 `records` 的 VTT 行號。
- **決策與限制** 採整行比對，因本批自動字幕的過渡主要是整行搬移。若僅用文字後綴與前綴消除部分詞，可能刪掉老師實際重複數拍。全文件去重也會混淆不同時間的同一句練習。10 ms 是從本快照觀察到的格式特徵，遇到未見過的轉場或字幕切行方式時，仍可能留下副本。獨立提示的標記依方括號整行辨識。
- **版本與審核** `transcript.version=1` 已納入字幕審核指紋。既有文章的版本及審核指紋維持原樣。真實字幕已通過格式及來源驗證，人工審核維持 `pending`，正式評估資格仍為 `false`。

| 處理統計 | 實測 |
| --- | ---: |
| 原始 cues（含 2 個空白 cues） | 339 |
| 去重前純文字字元（非空 cues 以空格串接） | 18,177 |
| 合併後字元 | 6,145 |
| 移除的字元差（含分隔空格） | 12,032 |
| 移除的整行副本 | 326 |
| 保留並標記的疑點 | 8 |

326 次移除分別為 163 次進入短過渡，以及 163 次由短過渡延續到下一 cue。8 處疑點皆為整行相同但時間證據不足。這些數量只描述此規則的輸出，去重品質仍需依原始字幕與影片抽查。

- **移除範例** `cue-3` 的末行帶詞級時間，`cue-4` 是 27380–27390 ms 的短過渡，`cue-5` 的首行又包含同一句。合併文字留一份，來源指向三個 cues，`removals` 分別記錄 `cue-4` 與 `cue-5`。
- **保留範例** `cue-13` 的「left right right then left right left」在兩個 `right` 上有各自的詞級時間，兩個詞都保留。合併字元區間為 `[213, 250)`。
- **疑點範例** 開頭 `cue-1` 至 `cue-3` 都有 `[Music]`，缺少可證明同一個提示的詞級時間，因此保留三個 `hint` 並記兩個相鄰疑點。

從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_preparation.py` 為 **25 passed**，執行 `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` 為 **89 passed、5 deselected**。各有一則既有 Starlette TestClient 棄用警告。以相同 manifest 跑兩次 CLI，`diff -qr` 確認輸出 JSON 和摘要一致，`shasum -a 256 -c local/acquisition/before.sha256`（從 repo 根目錄以完整路徑執行）確認輸入未變。逐一核對所有真實字幕 spans 的字元切片及 cue 時間，並比對原 cue 欄位與舊版一致、兩篇文章 JSON 逐位元一致。

Chunking、MySQL 測試和正式 RAG 品質評估未執行。人工確認可先看 `transcript.removals[0:2]` 及 `transcript.doubts[0:2]`，再依 `cue_id` 和 `raw_lines` 回看原始 VTT。

## 字幕去重版本 2 — 精確 10 ms 單行過渡

使用者對照影片確認 `cue-303`（525580–526260 ms）的末行 `atm` 與 `cue-304`（526260–526270 ms）是同一次發聲。這是單一案例的人工判定。字幕原文的 `1 atm` 含 ASR 錯字，維持原樣。

既有詞級時間規則優先。若既有規則未判定，且當前 cue 緊接來源順序的前一 cue、恰為 10 ms、唯一非空正規化文字行與前一 cue 最後一行完全相同，且當前行沒有詞級時間或獨立方括號提示，就沿用既有來源映射，只在合併文字移除當前副本。去重理由記為 `single_line_exact_10ms_transition`。這項判定來自本批字幕的顯示過渡特徵，等文字、較長時間或局部重疊仍需原有的時間證據。

| 指標 | v1 | v2 |
| --- | ---: | ---: |
| 原始 cues | 339 | 339 |
| 去重前純文字字元 | 18,177 | 18,177 |
| 合併字元 | 6,145 | 6,131 |
| 移除字元（含空格） | 12,032 | 12,046 |
| 移除整行副本 | 326 | 329 |
| 疑點 | 8 | 5 |

- 新規則移除 `cue-168`（278219–278229 ms，`okay`）、`cue-242`（390570–390580 ms，`good`）及 `cue-304`。前兩筆是規則判定，尚未經影片人工核對。疑點數是處理統計，去重正確率未評估。
- `cue-304` 的原始記錄仍存在，`removals` 指向保留的 `cue-303`。合併 `[5499, 5502)` 的 `atm` 可回溯到 `cue-303` 和 `cue-304`，共同覆蓋 525580–526270 ms。下一個 `cue-305` 也攜帶 `atm`，因時間證據不足保留在 `[5503, 5506)` 並標為疑點，可由 `cue-304` 的移除紀錄回查前一份來源。
- 沿用同一份已保存的 VTT 和 manifest，兩次輸出逐位元相同，原始快照雜湊與 cue 記錄一致。新輸出是 `local/transcript-v2/youtube-hip-hop-bounce.json`，SHA-256 為 `e206051dde032e86c986b3dd97c149250a3607a1818169641437c36f0d19022a`。規則版本納入字幕審核指紋，已確認和 v1 不同。字幕整體仍為 `pending`，正式評估資格為 `false`。

從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_preparation.py` 為 **34 passed**，`.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` 為 **98 passed、5 deselected**。各有一則既有 Starlette TestClient 棄用警告。正式 RAG 評估未執行。

## 字幕去重版本 3 — 延續已辨識的 10 ms 過渡

- 使用者確認 `cue-305` 的 `atm` 是 `cue-303` 經 `cue-304` 過渡後繼續顯示的副本，第二行才是新講解。v3 沿用原始快照與正規化。當前兩行 cue 必須緊接上一個已被 `single_line_exact_10ms_transition` 移除的 cue，首行完全相同且沒有新詞級時間，第二行須有詞級時間。只有首行可標記為 `single_line_carried_through_10ms_transition`。較長的鏈、時間間隔或首行新詞級時間不觸發本次規則。
- v2 的個案合併文字為 `… go 1 atm atm right leg …`，v3 為 `… go 1 atm right leg …`。`atm` 的合併字元範圍為 `[5489, 5492)`，來源包含 `cue-303`、`cue-304`、`cue-305`。第二行在 `[5493, 5520)`，僅指向 `cue-305`。原始 cue payload 和 ASR 文字保留。
- 真實重跑同時識別 `cue-169` 的 `okay` 與 `cue-243` 的 `good`，這兩筆仍待影片抽查。總移除整行 329 → 332，合併字元 6,131 → 6,117，疑點 5 → 2，兩筆剩餘疑點均為開頭的 `[Music]`。原始 339 cues、去重前 18,177 字元維持一致。統計只描述規則輸出。
- 輸出在 `local/transcript-v3/youtube-hip-hop-bounce.json`，SHA-256 為 `d8d7c5fb034c631b0dbfcbe0903946961eee5a83d977abde1d53d4f59d011cd0`。兩次輸出及摘要逐位元一致，原始檔與 manifest 雜湊一致，cue 記錄與 v2 一致。字幕審核指紋已隨版本更新，整份字幕仍為 `pending`。

從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_preparation.py` 為 **37 passed**，`.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` 為 **101 passed、5 deselected**。各有一則既有 Starlette TestClient 棄用警告。正式 RAG 評估未執行。

## Week 2 資料準備交付驗證

- 交付範圍涵蓋本機快照匯入、來源回溯與 transcript v3。Git 保留程式、離線測試、自製 fixtures 與文件。第三方快照、衍生全文、真實 manifest 及取得工具環境留在忽略的 `local/`；目前本機輸出為 `local/transcript-v3/`。
- ASR 措辭維持原樣，`cue-169`、`cue-243` 尚待影片抽查，真實字幕的整體人工審核為 `pending`。正式 RAG 評估未執行。
- GitHub Actions 的 `CI` 在目標為 `main` 的 PR 上執行，沒有路徑篩選。`API tests` 從 `backend/` 執行 `python -m pytest -m "not mysql"`，RAG tests 只使用版本庫內的自製 fixtures 和暫存目錄。沿用既有 workflow 與 MySQL job。
- 提交前在本機重跑 RAG suite 為 **37 passed**，非 MySQL suite 為 **101 passed、5 deselected**。兩者各有一則既有 Starlette TestClient 棄用警告。另從 `git archive cb827e3` 匯出的快照重跑相同非 MySQL 指令，仍為 **101 passed、5 deselected**，該快照無 `evaluations/rag/local/`。
- 遠端 [PR #3](https://github.com/HaoHaola/danceflow-ai/pull/3) 的實作提交 `cb827e32a3e1d44b7d6f1ccdfe401c9ae331624d` 觸發 [CI run 44914866078](https://github.com/HaoHaola/danceflow-ai/actions/runs/44914866078)，API tests 與 MySQL integration tests 均為 `success`。

## Week 2.1 — 第一批語料收集與清理

2026-11-22 完成 10 篇 STEEZY 文章、5 支 Ceech 教學影片的本機匯入。基準為 PR #3 合併提交 `9c6464c`。沿用 2026-11-21 保存的兩份 HTML 和一份 VTT，當日新增 8 份 HTML、4 份 VTT。下列雜湊前綴識別原始快照版本，完整 SHA-256 及清理輸入檔雜湊保存在本機 manifest。

### STEEZY 文章

| 公開來源 | 作者 | Clean blocks | 原始 HTML SHA-256 前綴 |
| --- | --- | ---: | --- |
| [The Ultimate Beginner Dance Guide](https://www.steezy.co/posts/how-to-be-a-good-dancer) | Charise Roberts | 93 | `7ec9e3db2e6c` |
| [How To Execute Movement For Beginner Dancers](https://www.steezy.co/posts/how-to-execute-movement) | Jessie Ma | 26 | `5866fc036fe0` |
| [Basics of Dance Musicality](https://www.steezy.co/posts/basics-dance-musicality) | Charise Roberts | 56 | `b243fd70c55b` |
| [How To Freestyle Dance](https://www.steezy.co/posts/how-to-freestyle-dance-2) | Charise Roberts | 60 | `d591f228079d` |
| [How To Learn Popping – The Ultimate Popping Training Guide](https://www.steezy.co/posts/how-to-learn-popping) | Charise Roberts | 144 | `18af92d0058f` |
| [How To Take A Dance Class](https://www.steezy.co/posts/how-to-take-a-dance-class-2) | Charise Roberts | 100 | `9ee7edc033ed` |
| [How To Train Your Foundation / Fundamentals](https://www.steezy.co/posts/how-to-train-your-foundation-fundamentals-2) | Charise Roberts | 63 | `0ea96c4fd82d` |
| [How To Train Your Musicality As A Dancer](https://www.steezy.co/posts/how-to-train-your-musicality-as-a-dancer) | Evan Zhou | 23 | `e34dd5913062` |
| [What Is House Dance?](https://www.steezy.co/posts/what-is-house-dance) | Charise Roberts | 132 | `f3efcac5414d` |
| [What Is Popping? (Popping Dance)](https://www.steezy.co/posts/what-is-popping-dance) | Charise Roberts | 99 | `fd1f15b33680` |

### Nustudios 上傳的 Ceech 教學

| 公開來源 | Cues | 合併字元 | 去除副本 | 保留疑點 | 原始 VTT SHA-256 前綴 |
| --- | ---: | ---: | ---: | ---: | --- |
| [Dance Tutorial Basics: Hip Hop Bounce](https://www.youtube.com/watch?v=Aj34T435FAg) | 339 | 6117 | 332 | 2 | `70ed2782897d` |
| [Dance Drills Basics - Arm Waves Inside Out](https://www.youtube.com/watch?v=Y1yURow9_4Q) | 533 | 9394 | 504 | 2 | `ffecd7b47c97` |
| [Learn Hip-Hop Dance for Beginners and Intermediate Dancers \| Step-by-Step Tutorial](https://www.youtube.com/watch?v=okd4X8fVn80) | 353 | 6119 | 339 | 3 | `9b829243814e` |
| [Locking Fundamentals - The Lock (in 4k)](https://www.youtube.com/watch?v=U_x-AxjcfNE) | 299 | 4310 | 198 | 20 | `3764799de324` |
| [Hip-Hop Dance Tutorial: Learn Locking, Running Man and Skeeter Rabbit in Less Than 10 Minutes](https://www.youtube.com/watch?v=-0AVDqDu2As) | 409 | 6397 | 373 | 1 | `dd37bb090cd7` |

- 五支影片使用 `yt-dlp 2026.10.26` 的原語言英文自動字幕 `en-orig`，格式 VTT。影片說明為授課者證據。Arm Waves Inside Out 與 Hip Hop Bounce 的說明使用 Dance With Ceech 署名，The Lock 自我介紹為 Ceech，另外兩支明列 Ceech 為授課者。
- 候選 [Shuffle aka Running Man](https://www.youtube.com/watch?v=7TQahj_DQ2I) 由 Margarita 教授，排除。替代項 [Locking, Running Man and Skeeter Rabbit](https://www.youtube.com/watch?v=-0AVDqDu2As) 保留 Running Man 主題，另有動作組合，與專講 The Lock 的來源用途不同。
- 舞風及程度依本文、標題或影片說明標記，例如 House 歷史的舞風為 `house`，程度為 `unknown`。所有來源的內容審核為 `pending`，正式 RAG 評估資格為 `false`。

### 處理與回溯

- 原始 HTML 以 curl 8.7.1 取得。Beautiful Soup 擷取 `h1.post-header` 和 `div.rich-text.w-richtext`，排除無文字 figure、內嵌促銷和純導覽段落。保留原文標題、段落、清單及 House 文章的引述文字。每篇正文排除位置由 manifest 的 `extraction_boundary` 記錄為原始正文直接元素的零起算索引。重新清理舊文章時沿用原 HTML 和取得日期。
- 兩支字幕的相鄰詞級標籤各有重複時間值。將同一時間值下的相鄰標籤合成一組，原始 VTT、文字、cue 時間和行號均保留。`caption_review_lines` 記錄 Hip-Hop Fundamentals 第 935、1247、1375 行，及 Locking / Running Man / Skeeter Rabbit 第 303、751、911、1191 行。這些位置的重複發聲仍待人工檢查。
- `prepare_corpus.py` 沿用 transcript v3 移除格式標籤和有時間證據的滾動副本。`transcript.doubts` 保留其餘 28 筆重疊疑點。既有 Bounce 的去重規則移除位置 `cue-169`、`cue-243` 亦待人工抽查。ASR 辨識錯字保留原樣，包含已知的 `1 atm`。
- 第三方全文、VTT、manifest、clean JSON 和兩支本機腳本保存在 Git 忽略的 `evaluations/rag/local/week2.1/`。網站內容的專案使用授權仍待確認。本次 Git 交付為來源與驗證紀錄。

### 實測

- 本機 `prepare_batch.py` 產生對應快照與 manifest。從 repo 根目錄執行 `backend/.venv/bin/python -B evaluations/rag/prepare_corpus.py --manifest evaluations/rag/local/week2.1/manifest.json --output-dir evaluations/rag/local/week2.1/clean`，15/15 為 `passed`。重跑至 `repeat/`，`diff -qr` 和摘要 `cmp` 均一致。
- `python3 -B evaluations/rag/local/week2.1/verify_batch.py` 通過 10/5 筆數、唯一 URL／ID／雜湊、輸入 SHA-256、metadata 一致、非空內容、文章與 VTT 行號回溯、字幕起訖與起始時間順序、合併文字的來源切片、七行修正前後的去標籤文字一致性。十篇文章之間無完全相同的正規化 paragraph record，五支影片兩兩共有的八詞序列最高占較短一方約 1.22%。此檢查可辨識明顯重複，字幕文字與畫面仍待完整人工抽查。
- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider`，**101 passed、5 skipped**，含 37 個離線語料測試。5 個 MySQL 測試因預設未啟用而跳過，另有一則既有 Starlette TestClient 棄用警告。`git diff --check` 通過。
- Chunking、embedding、Qdrant ingestion、retrieval、RAG baseline 與正式 RAG 品質評估未執行。

### Week 2.1 — 字幕滾動重疊人工審查清單

- 沿用上述 2026-11-22 批次的 manifest、VTT 與 transcript v3。從五份字幕 clean JSON 的 `transcript.doubts` 讀取原有疑點，按報告的影片順序及檔內順序編號，使用 cue 時間與 `raw_lines` 提供影片和快照定位。本機清單位於 Git 忽略的 `local/week2.1/subtitle-overlap-review.md`，共 28 筆，分布為 2、2、3、20、1。
- 從 repo 根目錄執行 `python3 -B evaluations/rag/local/week2.1/verify_batch.py`，檢查通過。另以 Python 核對 15 份 clean JSON 的 SHA-256 均與既有 `validation-summary.json` 一致，確認 28 筆的相鄰 cue、時間及吻合文字切片均能對應來源紀錄。
- 清單僅記錄文字與時間的初判，28 筆均為 `needs_review`。音訊審查、chunking、embedding、Qdrant ingestion、retrieval 與正式 RAG 評估均未執行。

### Week 2.1 — Transcript v4 滾動去重與數拍待校對

- 沿用同一批 manifest、原始快照與 WebVTT parser。v4 移除以整行相同及 10 ms 過渡為基礎的無詞級時間規則及其延續規則。相鄰 cue 必須有整行後綴／前綴延續，並有重疊且一致的詞級時間，或由帶有詞級時間的原行經無縫短過渡延續，才合併來源。證據不足的吻合內容保留並標記。
- `transcript.chunking_input` 由合併後的 spans 投影，僅排除整行 `[Music]`、`[Applause]`。其 spans 的字元位置對應衍生文字。排除項記錄原 transcript 的 span 與來源。原始 VTT、cue 文字、時間和 `raw_lines` 均保留。
- 使用者聽音回報數拍漏字。RO-05、RO-06、RO-07、RO-28 的記錄為「疑似滾動重複，且使用者聽音發現數拍漏字；精確轉寫待確認。」三段範圍與現有 cue 文字保存在 Git 忽略的 `local/week2.1/count-transcription-review.md`。四筆仍保留文字與疑點。ASR 內容未校對，整份字幕的人工審核狀態仍為 `pending`。
- 從 repo 根目錄執行 `backend/.venv/bin/python -B evaluations/rag/prepare_corpus.py --manifest evaluations/rag/local/week2.1/manifest.json --output-dir evaluations/rag/local/week2.1/clean-v4`，15 份通過自動驗證。另輸出至暫存目錄，`diff -qr` 和摘要 `cmp` 一致。`python3 -B evaluations/rag/local/week2.1/verify_batch.py` 通過。以 Python 核對既有 15 份 clean JSON SHA-256、v4 的 cue records、10 份文章輸出及字幕 span 的文字／時間回溯。
- 五支影片合計去重 1,690 次，較 v3 少 56 次。疑點由 28 增至 84，原有 28 筆均保留。衍生輸入排除 78 個非語音 marker spans，數量獨立於滾動去重。
- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider`，102 passed、5 skipped，另有一則既有 Starlette TestClient 棄用警告。`git diff --check` 通過。Chunking、embedding、檢索與正式 RAG 評估未執行。

### Week 2.1 — 選定 transcript v3 作為 baseline

- 採用既有 transcript v3 規則，保守的 v4 結果只作歷史比較。v3 優先減少相鄰滾動字幕的重複顯示，接受短過渡等啟發式判定可能誤刪真實重複口令。規則仍限制在相鄰 cue 的後綴／前綴與時間關係，沒有全域單字去重。
- baseline 輸出位於 Git 忽略的 `local/week2.1/clean-v3-baseline/`。僅新增 `transcript.chunking_input`，從 v3 spans 排除整行 `[Music]`、`[Applause]`，保留同 cue 口語行。衍生文字的 spans 使用重算的字元區間，並保留原 cue、時間與原始行號回溯。排除清單的字元區間對應原 transcript。
- 沿用同一 manifest、5 支影片與 10 篇文章。ASR 內容未校對，未補寫漏字或修正錯字。人工審核維持 `pending`，沿用三段數拍待校對紀錄。
- 從 repo 根目錄執行 `backend/.venv/bin/python -B evaluations/rag/prepare_corpus.py --manifest evaluations/rag/local/week2.1/manifest.json --output-dir evaluations/rag/local/week2.1/clean-v3-baseline`。同一輸入再跑至暫存目錄，`diff -qr` 和摘要 `cmp` 一致。`python3 -B evaluations/rag/local/week2.1/verify_batch.py` 通過，原始快照與清理輸入雜湊一致。
- 15 份輸出完整。以 Python 比對，10 份文章逐位元一致，5 份字幕除新增衍生欄位外與既有 v3 完全相同，既有 15 份檔案 SHA-256 仍與原摘要一致。v3 共去重 1,746 次、保留 28 筆疑點，另從衍生文字排除 78 個標記 spans。衍生文字的切片和來源映射均核對通過。
- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider`，102 passed、5 skipped，含一則既有 Starlette TestClient 棄用警告。`git diff --check` 通過。Chunking、embedding、檢索與正式 RAG 評估未執行。

### Week 2.1 — Embedding 選型與本機 smoke test

官方模型卡查核日期為 2026-11-22（Asia/Taipei）。DanceFlow 需要接受中文、英文提問，檢索英文舞蹈文章與影片字幕。本輪採用 **Qwen/Qwen3-Embedding-0.6B**。官方支援多語言及跨語言檢索、可直接沿用 SentenceTransformers，0.6B 規模適合先在本機驗證，權重採 Apache-2.0。模型提供 32K context，使用完整 1024 維 dense 向量。以下成本比較依參數量、向量維度與整合需求推估，候選未做本機效能比較。DanceFlow retrieval 評估尚未執行，選型不代表此模型在專案語料上效果最佳。[Qwen 0.6B 官方模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)

| 候選 | 功能、成本與授權取捨 | 官方來源 |
| --- | --- | --- |
| Qwen3-Embedding-4B | 同系列，多語、32K、最高 2560 維，可用同一個 SentenceTransformers 介面。4B 權重預期需要更多下載空間、記憶體與運算，若使用完整維度，每筆向量也較大。Apache-2.0。 | [Qwen 模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-4B) |
| BGE-M3 | 多語、8192 tokens、1024 維 dense，也提供 sparse 與 ColBERT multi-vector。Dense 可沿用 SentenceTransformers，後兩種輸出若納入實驗，會增加整合、索引和查詢成本。MIT。 | [BAAI 模型卡](https://huggingface.co/BAAI/bge-m3) |
| Jina v5-text-small | 677M、32768 tokens、最高 1024 維。與選用模型規模接近，支援 retrieval、matching、clustering、classification，官方本機用法另列 PEFT。CC BY-NC 4.0，商用需洽 Jina。 | [Jina small 模型卡](https://huggingface.co/jinaai/jina-embeddings-v5-text-small) |
| Jina v5-text-nano | 239M、8192 tokens、最高 768 維，支援同系列四種任務。權重較小，完整向量占用較少空間，輸入長度上限較短。CC BY-NC 4.0，商用需洽 Jina。 | [Jina nano 模型卡](https://huggingface.co/jinaai/jina-embeddings-v5-text-nano) |

本機為 Apple M4 Pro（arm64、12 CPU cores、24 GiB RAM），backend Python 3.13.3，既有 backend 依賴沒有 PyTorch、Transformers 或 SentenceTransformers。本輪在 Git 忽略的 `evaluations/rag/local/.embedding-venv/` 安裝 embedding 套件。CI 繼續使用既有離線 fixtures，真實模型 smoke test 由本機指令手動執行。

#### 重現方式

從 repo 根目錄執行。前兩步安裝套件，接著將官方固定 revision 的模型下載至 Git 忽略的快取。最後一行可在離線環境重跑。

```sh
backend/.venv/bin/python -m venv evaluations/rag/local/.embedding-venv
evaluations/rag/local/.embedding-venv/bin/python -m pip install -r evaluations/rag/requirements-embedding.txt
HF_HUB_CACHE=evaluations/rag/local/hf-cache evaluations/rag/local/.embedding-venv/bin/hf download \
  Qwen/Qwen3-Embedding-0.6B --revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1 \
  evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/smoke_embedding.py
```

本次權重及設定檔透過 Hugging Face 的固定 revision URL 下載，權重為 1,191,586,416 bytes，本機 SHA-256 與官方回應的權重雜湊一致（`0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`）。[官方模型快照](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/tree/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3)

完整 query prefix 如下。第二行冒號後有一個空格，再接上原始 query。格式採官方 instruction 模式，指令以英文描述 DanceFlow 的檢索任務。兩段測試文件以原文編碼，呼叫 `encode(..., prompt="")` 明確使用空 prompt。

```text
Instruct: Given a street dance question, retrieve relevant English passages from dance articles and instructional video transcripts that answer it.
Query: <query>
```

#### 實測結果

- 固定 revision 為 `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`。Python 3.13.3、macOS 26.6.2、PyTorch 2.8.0、Transformers 4.57.6、SentenceTransformers 5.1.2、huggingface-hub 0.36.2、tokenizers 0.22.2、safetensors 0.8.0、NumPy 2.5.5。
- 離線 smoke 指令 exit 0。模型與 tokenizer 均成功載入。裝置為 CPU，PyTorch 使用 4 個 intra-op threads，權重與輸出皆為 float32。Smoke 的 `max_seq_length=512`，與後續 chunking 設定分開。兩個帶 instruction 的 query 和兩段原文文件的 token 數依序為 38、36、20、16，均低於截斷上限。
- `normalize_embeddings=True`。Query 和文件各為 `(2, 1024)`，所有分量有限，四個向量的 L2 norm 實測均為 1.0，通過絕對誤差 `1e-6` 檢查。單次本機快取載入模型和 tokenizer 為 **1.456 s**，不含下載與 Python 套件 import。首批 2 個 query encode 為 **0.180 s**，接續一批 2 段文件 encode 為 **0.074 s**。每批 encode 時間含 tokenizer、模型推論及正規化，無另外 warm-up。
- 使用兩個自製英文文件，一段描述手臂波浪從手指到肩膀的動作傳遞，一段描述番茄澆水。單位向量的 dot product 即為 cosine similarity。這些短句只用於功能檢查，排除於正式 RAG 品質評估。

| Query | 手臂波浪文件 | 番茄澆水文件 |
| --- | ---: | ---: |
| 初學者怎麼練習手臂波浪？ | 0.711089 | 0.242114 |
| How can a beginner practice an arm wave? | 0.740947 | 0.224636 |

- `evaluations/rag/local/.embedding-venv/bin/python -m pip check` 回報 `No broken requirements found.` 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'`，**102 passed、5 deselected**，含一則既有 Starlette TestClient 棄用警告。 `git diff --check` 通過。
- Chunking、15 份語料的批次 embedding、Qdrant ingestion、retrieval 與正式 RAG 評估均未執行。

### Week 2.2 — Chunking pilot，兩份來源

本輪使用 `local/week2.1/clean-v3-baseline/` 的兩份 clean JSON。輸入雜湊是 clean JSON 原始位元組的 SHA-256，產物另保留原始快照的 `raw_sha256`。影片的 cue records 及既有 transcript v3 與舊版快照相同，`chunking_input` 排除 4 個整行非語音 marker，保留 168 個去重後 spans。ASR 文字未修改，人工審核仍為 pending。

| 來源 | Cleaning / transcript 版本 | Clean JSON SHA-256 |
| --- | --- | --- |
| How To Execute Movement For Beginner Dancers | 1 / 不適用 | `95091b1ed122de1d26765d7d09b4a412a9b58a025c48578e658958a63d507424` |
| Dance Tutorial Basics: Hip Hop Bounce | 2 / 3 | `479bdef40d5ff5292b3c36bfb67e838a3deacb6fb1ea441e6d24057ed6d1702b` |

設定版本 `week2.2-pilot-1`。Tokenizer 使用上一輪同一個 Qwen revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，Transformers 4.57.6、tokenizers 0.22.2。本機快取離線載入 tokenizer，未載入模型權重。每段 `embedding_text` 由來源標題、文章可用的小節路徑、空行和正文組成。保留原樣的 `text` 支援精確回溯，`embedding_text` 依 SentenceTransformers 的輸入處理移除外側空白。完整輸入以 `add_special_tokens=True`、`truncation=False` 計數，硬上限 512。Overlap 以重複正文單獨計數，最多 64 tokens，且納入完整輸入的 512 tokens 上限。本文未使用 LLM 轉寫。

- 文章按相鄰的 `heading_path` 分區，以完整清理區塊合併。過長區塊先依標點加空白判定句界，最後才以 tokenizer 字元 offsets 切分。保留 heading record，並保留 `block_range` 與原始行範圍。
- 影片依 v3 span 順序合併相鄰 cue，使用每個 span 首次保留的 cue 決定邊界，仍保留其他滾動副本的來源指標。超長 cue 才用 tokenizer offsets 續切。因時間粒度沿用來源 cue，拆分後的字元位置可精確回到 cue 的 `plain_text`，時間仍指向整個 cue。
- 每段先確認可容納新增單位，才保留前段末尾的完整句子、區塊或 cue 作 overlap。以 `new_body_range` 串回每個來源或小節，應逐字等於清理後正文。句界是啟發式規則，縮寫或無標點長文可能落到 token 切分。Pilot 的長段／長 cue fallback 由離線 fixtures 驗證。512／64 目前是 pilot 設定，尚無標註查詢結果可據以調整。

| 來源 | Chunk 數 | Token 數（依輸出順序） | 最小／中位／最大 | Overlap tokens |
| --- | ---: | --- | --- | --- |
| How To Execute Movement For Beginner Dancers | 5 | 119, 284, 261, 134, 218 | 119 / 218 / 284 | 0, 0, 0, 0, 0 |
| Dance Tutorial Basics: Hip Hop Bounce | 4 | 508, 506, 511, 90 | 90 / 507 / 511 | 0, 60, 60, 57 |

完整 JSON 位於 Git 忽略的 `local/week2.2/chunks/`。`local/week2.2/boundary-preview.md` 列出文章 #2–4 和影片 #1–3 的完整正文，分別標記 overlap 與新增正文。文章這三段在各自小節內就能容納，因此 overlap 均為 0。影片 #2、#3 各有 60 tokens 來自前一 chunk。

從 repo 根目錄執行：

```sh
export HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/chunk_pilot.py \
  --input-dir evaluations/rag/local/week2.1/clean-v3-baseline \
  --output-dir evaluations/rag/local/week2.2/chunks
```

- 同指令輸出至獨立暫存目錄後用 `diff -qr` 比較，兩份 JSON 逐位元一致，包含 chunk IDs。另以固定 tokenizer 重算每段完整輸入及 overlap 的 token 數，驗證預算、非空與新增正文，以及每筆區塊或 cue 的字元位置、時間與原始行範圍。串接無 overlap 的新增正文後與原輸入逐字一致。
- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_rag_chunk_pilot.py` 為 **4 passed**。執行 `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` 為 **106 passed、5 deselected**。兩輪各有一則既有 Starlette TestClient 棄用警告。測試使用自製 fixture 和 token 計數替身，CI 無 tokenizer 或模型下載。`git diff --check` 通過。
- 其餘語料未切分。批次 embedding、Qdrant ingestion、retrieval 與正式 RAG 評估均未執行。

### Week 2.2 — 選定的 15 份來源完成批次 chunking

輸入使用 `local/week2.1/manifest.json`、`validation-summary-v3-baseline.json` 及 `clean-v3-baseline/`。批次入口只依固定的 15 個來源 ID 開檔，核對 manifest、驗證摘要中的 clean JSON SHA-256、原始來源雜湊與網址。5 支影片均使用 v3 投影，仍只排除整行 `[Music]`、`[Applause]`，ASR 原文維持。逐來源輸入 SHA-256 與完整 token 序列保存在本機 `local/week2.2/batch/summary.json`。

沿用 `week2.2-pilot-1` 和 Qwen tokenizer revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`。文章分小節並合併完整區塊，字幕沿用連續保留 cue。完整 `embedding_text` 使用原 tokenizer 計數，含來源標題、小節及特殊 tokens，最多 512；重複正文的 overlap 預算為 64 tokens，每段須有新增正文。本輪維持相同規則，讓批次結果可直接與兩份 pilot 輸出比對。

| 來源 ID | Chunks | 最小／中位／最大 tokens | 有 overlap 的 chunk 序號及 token 數 |
| --- | ---: | --- | --- |
| `steezy-how-to-be-a-good-dancer` | 18 | 23／118.5／278 | 全 0 |
| `steezy-how-to-execute-movement` | 5 | 119／218／284 | 全 0 |
| `steezy-basics-dance-musicality` | 8 | 14／109.5／494 | #5 57 |
| `steezy-how-to-freestyle-dance-2` | 9 | 82／157／275 | 全 0 |
| `steezy-how-to-learn-popping` | 55 | 23／63／269 | 全 0 |
| `steezy-how-to-take-a-dance-class-2` | 9 | 55／267／500 | #6 53、#9 48 |
| `steezy-how-to-train-your-foundation-fundamentals-2` | 9 | 42／193／254 | 全 0 |
| `steezy-how-to-train-your-musicality-as-a-dancer` | 6 | 78／201／474 | 全 0 |
| `steezy-what-is-house-dance` | 17 | 44／175／438 | 全 0 |
| `steezy-what-is-popping-dance` | 25 | 25／65／347 | 全 0 |
| `youtube-hip-hop-bounce` | 4 | 90／507／511 | #2 60、#3 60、#4 57 |
| `youtube-arm-waves-inside-out` | 5 | 369／510／512 | #2 61、#3 64、#4 62、#5 60 |
| `youtube-hip-hop-fundamentals` | 3 | 501／504／512 | #2 60、#3 58 |
| `youtube-locking-the-lock` | 2 | 381／444／507 | #2 62 |
| `youtube-locking-running-man-skeeter-rabbit` | 4 | 223／505.5／512 | #2 64、#3 64、#4 62 |

共 **179 個 chunks**（文章 161、影片 18），實際 overlap 為 0–64 tokens，16 個 chunks 有 overlap。沒有觀察到單一文章區塊或單一保留 cue 被拆成多段。23 個文章 chunks 只含標題區塊，集中在 4 篇文章，其中 19 個來自 *How To Learn Popping*。依現有規則保留標題區塊，之後可檢查這些短 chunks 是否擠掉含動作說明的搜尋結果。

代表性邊界的完整正文與 overlap 分開顯示在 Git 忽略的 `local/week2.2/batch/boundary-preview.md`。

- *Basics of Dance Musicality* #4 → #5 在同一小節內切分。#4 為 494 tokens，#5 為 99 tokens。#5 沿用原文第 63、65、67 行（57 tokens），新增第 69 行。同篇 #1 為 14 tokens，只含標題。
- *Dance Tutorial Basics: Hip Hop Bounce* #3 → #4 在 cue 邊界切分。#3 為 511 tokens，尾段 #4 為 90 tokens，沿用 cue-319 到 cue-331 之間的 7 個保留 cue（57 tokens），新增保留 cue-333、cue-335、cue-337。#4 可回溯至 09:08.980–09:41.140，時間涵蓋 overlap 和所有相關來源 cue。

從 repo 根目錄執行：

```sh
export HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/chunk_batch.py \
  --baseline-root evaluations/rag/local/week2.1 \
  --output-dir evaluations/rag/local/week2.2/batch
```

- 179 段均通過非空、每段新增正文、完整輸入 token 上限、overlap 預算、文字覆蓋與來源回溯檢查。重跑至獨立暫存目錄，以 `diff -qr` 和 `cmp` 得到逐位元相同的 15 份 JSON 和 summary，包含 chunk IDs。兩份 pilot JSON 也與批次對應檔案逐位元相同。原始檔及 15 份 clean JSON 執行前後 SHA-256 清單一致。
- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'` 為 **108 passed、5 deselected**，含既有 Starlette TestClient 棄用警告。測試使用本機 fixtures 與 token 計數替身。 `git diff --check` 通過。
- 尚未執行批次 embedding、Qdrant ingestion、retrieval 或正式 RAG 品質評估。

### Week 2.2 — 文章標題改為正文的階層前綴

原批次有 23 個只含標題的 chunks。新版讓文章標題在完整 `embedding_text` 中提供小節脈絡，`text` 與其正文範圍只放非 heading records。按清理資料的 heading path 建立節點，每遇到同層標題便開始新的同層分支。每篇的 `article-structure/` JSON 保存所有標題的原文、path、父標題 block ID、原始行號與直接所屬正文 block IDs。無直接正文的父標題仍可作為下層祖先，無正文也無適用下層的標題只保存在結構。正文 chunks 使用 `heading_block_ids` 對回這些節點。即使小節只有短句，也保留。

文章設定版本為 `week2.2-article-headings-2`。用同一固定 Qwen tokenizer revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` 重算含階層前綴的完整輸入，仍採 512 tokens 硬上限和 64 tokens overlap 預算。字幕輸出及 chunk IDs 逐位元一致，繼續使用 v3。

| 範圍 | Chunks 前 → 後 | 最小／中位／最大 tokens 前 → 後 |
| --- | ---: | --- |
| 全部 15 份 | 179 → 154 | 14／119／512 → 32／139／512 |
| 10 篇文章 | 161 → 136 | 14／105／500 → 32／122.5／507 |
| 5 支影片 | 18 → 18 | 向量輸入逐位元一致 |

| 文章來源 ID | Chunks 前 → 後 | 最小／中位／最大 tokens 前 → 後 |
| --- | ---: | --- |
| `steezy-how-to-be-a-good-dancer` | 18 → 17 | 23／118.5／278 → 61／112／268 |
| `steezy-how-to-execute-movement` | 5 → 5 | 119／218／284 → 109／208／274 |
| `steezy-basics-dance-musicality` | 8 → 6 | 14／109.5／494 → 40／164.5／504 |
| `steezy-how-to-freestyle-dance-2` | 9 → 9 | 82／157／275 → 73／147／267 |
| `steezy-how-to-learn-popping` | 55 → 36 | 23／63／269 → 37／80／263 |
| `steezy-how-to-take-a-dance-class-2` | 9 → 8 | 55／267／500 → 47／260.5／507 |
| `steezy-how-to-train-your-foundation-fundamentals-2` | 9 → 9 | 42／193／254 → 32／190／250 |
| `steezy-how-to-train-your-musicality-as-a-dancer` | 6 → 6 | 78／201／474 → 66／191／457 |
| `steezy-what-is-house-dance` | 17 → 17 | 44／175／438 → 38／166／431 |
| `steezy-what-is-popping-dance` | 25 → 23 | 25／65／347 → 40／62／330 |

- *How To Learn Popping* 舊 #3 的 Hitting 標題（第 31 行）獨立成段。新版保存在結構；第 35、37 行正文歸到新版 #2，前綴保留原本的 `WEEK 1 > Learn how to hit:`（第 29、33 行標題）。第 31、33 行在來源同為二級標題，因此第 31 行的技術名維持同層節點。來源中的泛用標題（例如 `Things to remember:`）仍沿用原本的週次路徑，未推定其所屬技巧。
- *What Is Popping Dance* 原本獨立成段的 `Key moves in Popping Dance`（第 21 行）仍是 `Animation`（第 23 行）和 `The Boogaloo`（第 29 行）的父標題。兩段正文各自保留在新版 #3（第 25–27 行）和 #4（第 31–33 行），前綴共享父標題並各帶自身小節名。同層的 `Notable Poppers and Popping crews` 與 `Boogaloo Sam` 保留為獨立節點。
- Heading-only chunks 從 23 降至 0。移除正文內重複的標題後，另有兩處同小節正文可各少用一個 chunk。所有正文 block 的 heading path 與舊批次及 clean records 一致，完整覆蓋檢查逐字通過。

新版將 15 份 chunks、10 份標題結構、逐來源 summary 存在 Git 忽略的 `local/week2.2/batch-headings-v2/`；新版 pilot 在 `local/week2.2/pilot-headings-v2/`。原 `batch/` 與 `chunks/` 保存修改前的實驗產物。重跑新版時使用新版輸出路徑：

```sh
export HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/chunk_batch.py \
  --baseline-root evaluations/rag/local/week2.1 \
  --output-dir evaluations/rag/local/week2.2/batch-headings-v2
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/chunk_pilot.py \
  --input-dir evaluations/rag/local/week2.1/clean-v3-baseline \
  --output-dir evaluations/rag/local/week2.2/pilot-headings-v2
```

- 新批次在獨立目錄重跑，chunks、標題結構與 summary 以 `diff -qr` 核對逐位元一致。新版 pilot 的兩份 chunks 及文章標題結構與新版批次相應檔案以 `cmp` 核對一致。所有輸入雜湊仍與原批次相同。核對全部 heading records 可從標題結構找回，正文來源、含前綴的 token 上限與新增內容驗證均通過。
- 從 `backend/` 執行 `.venv/bin/python -B -m pytest -p no:cacheprovider -m 'not mysql'`，**109 passed、5 deselected**，含一則既有 Starlette TestClient 棄用警告。`git diff --check` 通過。
- 批次 embedding、Qdrant ingestion、retrieval 與正式品質評估尚未執行。這輪觀察是結構及覆蓋驗證，retrieval 是否改善仍未驗證。

### 本輪交接與後續評估範圍

- 本輪採用 v3 去重及其 `chunking_input`，排除整行 `[Music]`、`[Applause]`。ASR 漏字與錯字維持原樣；數拍疑點留有追蹤記錄，逐支影片完整聽音不是這次 baseline 的前置步驟。
- 模型使用 Qwen/Qwen3-Embedding-0.6B 的固定 revision 及隔離環境。CPU／float32 的 1024 維正規化 smoke test 已驗證中英 query instruction 和英文文件編碼流程。其自製短句與相似度紀錄只用於功能驗證。
- **目前批次為 `local/week2.2/batch-headings-v2/` 的 154 段**，其中 136 段文章、18 段影片，沒有 heading-only chunks。前面的 179 段及其執行結果是舊版實驗，重跑請使用新版段落中的輸出路徑。第三方文本、字幕、模型快取與本機產物均維持本機保存。
- 下次先準備並審查 retrieval 評估集，再依序執行批次 embedding、Qdrant ingestion 和 retrieval baseline。這些步驟與正式 retrieval 品質評估均未執行。
