import psycopg
from datetime import datetime


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "app_db",
    "user": "app_user",
    "password": "app_password",
}


def main():
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # テーブル作成
            cur.execute("""
                CREATE TABLE IF NOT EXISTS equipment_logs (
                    id SERIAL PRIMARY KEY,
                    equipment_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    takt_time_sec INTEGER,
                    created_at TIMESTAMP NOT NULL
                );
            """)

            # データ書き込み
            cur.execute("""
                INSERT INTO equipment_logs (
                    equipment_name,
                    status,
                    takt_time_sec,
                    created_at
                )
                VALUES (%s, %s, %s, %s);
            """, (
                "搬送ロボットA",
                "running",
                45,
                datetime.now()
            ))

            # データ確認
            cur.execute("""
                SELECT
                    id,
                    equipment_name,
                    status,
                    takt_time_sec,
                    created_at
                FROM equipment_logs
                ORDER BY id DESC
                LIMIT 5;
            """)

            rows = cur.fetchall()

            print("=== 最新データ ===")
            for row in rows:
                print(row)


if __name__ == "__main__":
    main()