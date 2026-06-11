from db import pool, redis_client

try:
    with pool.connection() as conn:
        with conn.cursor() as curr:
            curr.execute("SELECT version();")
            print(curr.fetchone())
except Exception as e:
    print(f"DB Error: {e}")

print(redis_client.ping())
