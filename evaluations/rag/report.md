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
- 提交前在本機重跑 RAG suite 為 **37 passed**，非 MySQL suite 為 **101 passed、5 deselected**。兩者各有一則既有 Starlette TestClient 棄用警告。遠端結果另依 PR 實際執行紀錄更新。
