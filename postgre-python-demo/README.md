以下の構成で作るのが一番シンプルです。

```text
postgres-python-demo/
├─ docker-compose.yml
├─ requirements.txt
└─ insert_sample.py
```

Docker Desktop は Windows では WSL2 backend を使う構成が標準的です。Docker Desktop の公式手順でも、Windows では Docker Desktop を起動し、Settings から WSL 2 based engine を有効にする流れが案内されています。([Docker Documentation][1])
PostgreSQL の公式 Docker image では、`POSTGRES_PASSWORD` などの環境変数で初期ユーザー・DB・パスワードを設定します。([Docker Hub][2])
Python 側は PostgreSQL 接続用ライブラリとして `psycopg` を使います。([Psycopg][3])

---

## 1. Docker Desktop の確認

PowerShell で確認します。

```powershell
docker --version
docker compose version
```

Docker Desktop を起動して、右下の Docker アイコンが動いていればOKです。

もしうまく動かない場合は Docker Desktop で以下を確認してください。

```text
Settings
  → General
    → Use the WSL 2 based engine を ON
```

---

## 2. 作業フォルダ作成

PowerShell で実行します。

```powershell
mkdir postgres-python-demo
cd postgres-python-demo
```

---

## 3. docker-compose.yml を作成

`docker-compose.yml` を作成します。

```yaml
services:
  postgres:
    image: postgres:17
    container_name: local-postgres
    restart: unless-stopped

    environment:
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: app_password
      POSTGRES_DB: app_db
      TZ: Asia/Tokyo

    ports:
      - "5432:5432"

    volumes:
      - postgres_data:/var/lib/postgresql/data

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d app_db"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  postgres_data:
```

ポイントはここです。

```yaml
ports:
  - "5432:5432"
```

これは、

```text
Windows PC の localhost:5432
      ↓
Docker内 PostgreSQL の 5432
```

につなげる設定です。

---

## 4. PostgreSQL コンテナを起動

```powershell
docker compose up -d
```

起動確認します。

```powershell
docker ps
```

`local-postgres` が表示されればOKです。

ログ確認はこちら。

```powershell
docker logs local-postgres
```

DBに直接入る場合はこれです。

```powershell
docker exec -it local-postgres psql -U app_user -d app_db
```

入れたら、PostgreSQL の中で以下を実行できます。

```sql
\dt
```

終了は、

```sql
\q
```

---

## 5. Python環境を作成

PowerShell で実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

`requirements.txt` を作成します。

```txt
psycopg[binary]
```

インストールします。

```powershell
pip install -r requirements.txt
```

---

## 6. PythonからDBに書き込むスクリプト

`insert_sample.py` を作成します。

```python
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
```

実行します。

```powershell
python insert_sample.py
```

以下のように表示されれば成功です。

```text
=== 最新データ ===
(1, '搬送ロボットA', 'running', 45, datetime.datetime(...))
```

---

## 7. DBの中身をPostgreSQL側から確認

```powershell
docker exec -it local-postgres psql -U app_user -d app_db
```

PostgreSQLに入ったら、

```sql
SELECT * FROM equipment_logs;
```

---

## 8. よく使うDockerコマンド

### 起動

```powershell
docker compose up -d
```

### 停止

```powershell
docker compose down
```

### 停止してもDBデータは残す

```powershell
docker compose down
```

### DBデータも完全削除

これは注意です。DBの中身が消えます。

```powershell
docker compose down -v
```

### ログ確認

```powershell
docker logs local-postgres
```

### コンテナ再起動

```powershell
docker restart local-postgres
```

---

## まずはこの状態でOKです

この構成ができると、次にすぐ以下へ発展できます。

```text
Pythonスクリプト
  ↓
PostgreSQL
  ↓
Streamlit / FastAPI / Pygame / 工場シミュレーションUI
```

今回のDBは、工場シミュレーションPoCなら例えばこういうテーブルに育てられます。

```text
machines
workers
parts
process_routes
simulation_logs
takt_time_results
```

最初は今回の `equipment_logs` で接続確認してから、次に「機器マスタ」「作業者マスタ」「部品投入ログ」あたりを作るのが良いです。

[1]: https://docs.docker.com/desktop/features/wsl/?utm_source=chatgpt.com "Docker Desktop WSL 2 backend on Windows"
[2]: https://hub.docker.com/_/postgres?utm_source=chatgpt.com "postgres - Official Image"
[3]: https://www.psycopg.org/docs/?utm_source=chatgpt.com "Psycopg – PostgreSQL database adapter for Python"
