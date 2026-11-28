"""Single-question interface for the DanceFlow AI knowledge API."""

import os
import re
from urllib.parse import urlsplit

import httpx
import streamlit as st


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
MAX_QUESTION_LENGTH = 2000
ERROR_MESSAGES = {
    422: "問題未通過驗證。請確認內容不為空，或縮短問題後再送出。",
    502: "問答服務未能取得完整有效的回答。",
    503: "問答服務尚未就緒，請確認後端設定與檢索服務。",
    504: "後端等候上游服務時逾時。",
}


def ask_backend(question):
    base_url = os.getenv("DANCEFLOW_API_BASE_URL", DEFAULT_API_BASE_URL).strip().rstrip("/")
    try:
        response = httpx.post(
            f"{base_url}/api/v1/knowledge/ask", json={"question": question}, timeout=120.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        raise ValueError("等待後端回應超過 120 秒，這次請求未自動重送。") from None
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        message = ERROR_MESSAGES.get(status, "後端回傳非預期的 HTTP 狀態。")
        raise ValueError(f"HTTP {status}｜{message}") from None
    except (httpx.RequestError, httpx.InvalidURL):
        raise ValueError("無法連線到問答 API，請確認後端已啟動及 API 位址正確。") from None
    except ValueError:
        raise ValueError("後端回傳的回答格式無法讀取。") from None


def video_time(milliseconds):
    seconds, millis = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def show_sources(sources, cited):
    for label, source in sources.items():
        st.text(f"[{label}] {source['title']}")
        url = source["source_url"]
        if urlsplit(url).scheme in {"http", "https"}:
            st.link_button(url, url)
        if source.get("heading_path"):
            st.caption("小節　" + " › ".join(source["heading_path"]))
        elif source.get("section_index") is not None and not source.get("time_range_ms"):
            st.caption(f"第 {source['section_index']} 節")
        if time_range := source.get("time_range_ms"):
            st.caption(f"影片時間　{video_time(time_range[0])}–{video_time(time_range[1])}")
    if not sources and cited:
        st.caption("回答未使用來源編號。")


def show_result(question, result):
    st.subheader("回答")
    st.caption(f"已送出　{question}")
    st.markdown(result["answer"])
    citations = set(re.findall(r"\[(S[0-9]+)\]", result["answer"]))
    sources = result["sources"]
    st.subheader("回答引用的來源")
    show_sources({key: value for key, value in sources.items() if key in citations}, cited=True)
    other_sources = {key: value for key, value in sources.items() if key not in citations}
    if other_sources:
        with st.expander("其他取回來源"):
            show_sources(other_sources, cited=False)

    with st.expander("執行資訊"):
        st.text(f"模型　{result['model']}")
        timings = result["timings_ms"]
        if timings.get("total") is not None:
            st.text(f"後端耗時　{timings['total'] / 1000:.3f} 秒")
        if usage := result.get("usage"):
            st.text(f"Token 用量　輸入 {usage['input_tokens']}／輸出 {usage['output_tokens']}／總計 {usage['total_tokens']}")
        else:
            st.caption("後端未回傳 token 用量。")


st.set_page_config(page_title="DanceFlow AI 舞蹈問答")
st.title("DanceFlow AI 舞蹈問答")

with st.form("knowledge_question"):
    question = st.text_area("你的舞蹈問題", placeholder="例如：我做 bounce 時看起來很僵硬，該怎麼練？")
    submitted = st.form_submit_button("送出問題", type="primary")

if submitted:
    st.session_state.pop("knowledge_result", None)
    st.session_state.pop("knowledge_error", None)
    question = question.strip()
    if not question:
        st.session_state["knowledge_error"] = "請先輸入問題。"
    elif len(question) > MAX_QUESTION_LENGTH:
        st.session_state["knowledge_error"] = f"問題最多 {MAX_QUESTION_LENGTH:,} 字元。"
    else:
        try:
            with st.spinner("正在搜尋教材並生成回答…"):
                result = ask_backend(question)
            st.session_state["knowledge_result"] = (question, result)
        except ValueError as error:
            st.session_state["knowledge_error"] = str(error)

if error := st.session_state.get("knowledge_error"):
    st.error(error)
if saved := st.session_state.get("knowledge_result"):
    show_result(*saved)
