import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


def create_db_engine() -> Engine:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    required = ("MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(f"Missing database settings: {', '.join(missing)}.")
    if os.environ["MYSQL_USER"].lower() == "root":
        raise ValueError("Set MYSQL_USER to a non-root application account.")

    try:
        port = int(os.getenv("MYSQL_HOST_PORT") or "3307")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("MYSQL_HOST_PORT must be an integer from 1 to 65535.") from None

    url = URL.create(
        "mysql+pymysql",
        username=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        host="127.0.0.1",
        port=port,
        database=os.environ["MYSQL_DATABASE"],
        query={"charset": "utf8mb4"},
    )
    return create_engine(
        url,
        connect_args={
            "connect_timeout": 5,
            "read_timeout": 5,
            "write_timeout": 5,
            "init_command": "SET SESSION time_zone = '+00:00'",
        },
    )


def main() -> int:
    try:
        engine = create_db_engine()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        print(
            "Database check failed. Verify MySQL is ready and check the application settings.",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()

    if result != 1:
        print("Database check failed. SELECT 1 returned an unexpected result.", file=sys.stderr)
        return 1
    print("Database check passed. SELECT 1 returned 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
