"""Generate isolated rehearsal configuration without starting any services."""

import argparse
import os
import secrets
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / ".env.rehearsal"


def init_config(path: Path, *, port: int = 3100) -> Path:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("port must be an integer between 1024 and 65535")
    values = {
        "REHEARSAL_PORT": str(port),
        "POSTGRES_USER": "devdocs_rehearsal",
        "POSTGRES_DB": "devdocs_rehearsal",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "SILICONFLOW_API_KEY": "",
        "CHAT_MODEL": "deepseek-ai/DeepSeek-V4-Flash",
        "DAILY_CHAT_LIMIT": "50",
        "DAILY_INDEX_LIMIT": "20",
    }
    content = "# Local rehearsal credentials. Do not share or commit.\n"
    content += "".join(f"{key}={value}\n" for key, value in values.items())
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="只生成独立演练配置，不启动任何服务")
    parser.add_argument("--port", type=int, default=3100)
    args = parser.parse_args(argv)
    try:
        init_config(DEFAULT_PATH, port=args.port)
    except FileExistsError:
        print("配置已存在，保留原文件，未覆盖。")
        return 0
    except (OSError, ValueError):
        print("配置生成失败，请检查端口范围与目录权限；不会自动删除或覆盖文件。")
        return 1
    print("已生成 infra/deploy/.env.rehearsal（数据库密码已随机生成，不显示）。")
    print("模型密钥保持为空；未启动容器，未连接数据库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
