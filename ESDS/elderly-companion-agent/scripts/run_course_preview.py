"""Run offline rules or an explicitly selected LLM in an isolated temporary database."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
import secrets
import sys
import tempfile

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="八课离线规则体验，不调用外部模型")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--policy", choices=("none", "per_turn", "per_task_step", "event_driven"), default="event_driven")
    parser.add_argument("--provider", choices=("preview", "deepseek", "dashscope", "azure"), default="preview")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    load_dotenv(project / ".env", encoding="utf-8-sig")
    required = {"preview": (), "deepseek": ("DEEPSEEK_API_KEY",), "dashscope": ("DASHSCOPE_API_KEY",),
                "azure": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")}[args.provider]
    missing = [name for name in required if not os.getenv(name) or os.getenv(name, "").startswith("replace-")]
    if args.provider == "azure" and not (os.getenv("AZURE_OPENAI_COURSE_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT")):
        missing.append("AZURE_OPENAI_COURSE_DEPLOYMENT / AZURE_OPENAI_DEPLOYMENT")
    if missing:
        parser.error("Missing configuration in the local .env: " + ", ".join(missing))
    with tempfile.TemporaryDirectory(prefix="cbt-course-preview-") as directory:
        os.environ.update({
            "APP_ENV": "development", "CBT_PREVIEW_MODE": "true" if args.provider == "preview" else "false", "CBT_COURSE_PROVIDER": args.provider,
            "DATABASE_URL": "sqlite:///" + (Path(directory) / "preview.db").as_posix(),
            "APP_SECRET": secrets.token_urlsafe(48), "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "INVITE_CODES": "course-preview:course-preview", "ADMIN_PASSWORD": secrets.token_urlsafe(32),
            "COOKIE_SECURE": "false", "VOICE_BRIDGE_ENABLED": "false", "VERCEL": "false",
            "CBT_REFLECTION_POLICY": args.policy,
            "CBT_DEMO_PROVIDER": "" if args.provider == "preview" else args.provider,
        })
        if args.provider == "preview":
            for name in ("DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
                os.environ[name] = ""
        import uvicorn
        mode = "离线规则体验" if args.provider == "preview" else "真实 LLM 体验：" + args.provider
        print(f"{mode}：http://127.0.0.1:{args.port}/；测试邀请码：course-preview。关闭服务后临时数据清除。", flush=True)
        try:
            uvicorn.run("webapp.main:app", host="127.0.0.1", port=args.port)
        finally:
            from webapp.database import engine
            engine.dispose()


if __name__ == "__main__":
    main()
