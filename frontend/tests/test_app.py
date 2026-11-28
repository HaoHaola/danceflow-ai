from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"
RESULT = {
    "answer": "先做雙膝屈伸。[S1]",
    "sources": {
        "S1": {"title": "Bounce 教學", "source_url": "https://example.test/video",
               "time_range_ms": [1000, 62500]},
        "S2": {"title": "節奏筆記", "source_url": "https://example.test/article",
               "heading_path": ["律動", "練習"]},
    },
    "model": "test-model",
    "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    "timings_ms": {"total": 1234.0},
}


@pytest.fixture
def post(monkeypatch):
    request = httpx.Request("POST", "http://example.test/api/v1/knowledge/ask")
    post = Mock(return_value=httpx.Response(200, json=RESULT, request=request))
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.delenv("DANCEFLOW_API_BASE_URL", raising=False)
    return post


def submit(app, question):
    app.text_area[0].set_value(question)
    app.button[0].click().run()
    assert not app.exception
    return app


def test_success_and_rerun(post, monkeypatch):
    monkeypatch.setenv("DANCEFLOW_API_BASE_URL", "http://example.test/")
    app = AppTest.from_file(APP).run()
    post.assert_not_called()
    submit(app, "  How do I bounce?  ")
    post.assert_called_once_with("http://example.test/api/v1/knowledge/ask",
                                 json={"question": "How do I bounce?"}, timeout=120.0)
    assert app.markdown[0].value == RESULT["answer"]
    assert "[S1] Bounce 教學" in [x.value for x in app.text]
    assert {link.proto.url for link in app.get("link_button")} == {
        "https://example.test/video", "https://example.test/article",
    }
    assert any("00:01.000–01:02.500" in x.value for x in app.caption)
    others, execution = app.expander
    assert others.label == "其他取回來源"
    assert others.text[0].value == "[S2] 節奏筆記"
    assert others.caption[0].value == "小節　律動 › 練習"
    assert execution.label == "執行資訊"
    assert any("總計 15" in x.value for x in execution.text)
    app.run()
    assert app.markdown[0].value == RESULT["answer"]
    post.assert_called_once()


@pytest.mark.parametrize(("question", "message"), [(" \n ", "請先輸入"), ("x" * 2001, "2,000")])
def test_invalid_input_does_not_post(post, question, message):
    app = submit(AppTest.from_file(APP).run(), question)
    assert message in app.error[0].value
    post.assert_not_called()


@pytest.mark.parametrize("status", [422, 502, 503, 504])
def test_new_api_failure_clears_previous_result(post, status):
    app = AppTest.from_file(APP).run()
    submit(app, "First question")
    post.return_value = httpx.Response(status, request=post.return_value.request)
    submit(app, "New question")
    assert f"HTTP {status}" in app.error[0].value
    assert not app.markdown
    assert post.call_count == 2
    app.run()
    assert f"HTTP {status}" in app.error[0].value
    assert post.call_count == 2


@pytest.mark.parametrize(("error", "message"), [
    (httpx.ReadTimeout("timeout"), "120 秒"),
    (httpx.ConnectError("connection refused"), "無法連線"),
])
def test_network_errors_are_not_retried(post, error, message):
    post.side_effect = error
    app = submit(AppTest.from_file(APP).run(), "What is bounce?")
    assert message in app.error[0].value
    post.assert_called_once_with("http://127.0.0.1:8765/api/v1/knowledge/ask",
                                 json={"question": "What is bounce?"}, timeout=120.0)
