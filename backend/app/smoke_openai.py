import os
import sys
from time import perf_counter

from openai import APIError, APIStatusError, OpenAI

from app.config import load_local_env


def main() -> int:
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("請在專案根目錄的 .env 設定 OPENAI_API_KEY。", file=sys.stderr)
        return 1

    model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-6.1-terra"
    try:
        with OpenAI(api_key=api_key, timeout=30.0, max_retries=0) as client:
            started_at = perf_counter()
            response = client.responses.create(
                model=model,
                input="請用繁體中文回答：API 連線成功。",
                reasoning={"effort": "none"},
                max_output_tokens=256,
            )
            elapsed = perf_counter() - started_at
    except APIError as error:
        http_status = error.status_code if isinstance(error, APIStatusError) else "無"
        print(f"OpenAI API 錯誤｜HTTP {http_status}｜{type(error).__name__}", file=sys.stderr)
        return 1

    print(f"模型：{response.model}")
    print(f"回答：{response.output_text}")
    print(f"耗時：{elapsed:.3f} 秒")
    print(f"Token usage：{response.usage.model_dump_json() if response.usage else '未回傳'}")
    if response.status != "completed" or not response.output_text.strip():
        print(f"未取得完整文字回覆｜Responses 狀態：{response.status}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
