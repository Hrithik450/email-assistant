import json
from lib.db import pool
from services.cache_service import CacheService


class ThreadService:

    @staticmethod
    def create_new_thread(user_id, title):
        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    INSERT INTO thread (user_id, title) 
                    VALUES (%s, %s) 
                    RETURNING id
                    """,
                    (user_id, title),
                )
                thread_id = curr.fetchone()[0]

            conn.commit()

        CacheService.delete(f"threads:{user_id}")

        return thread_id

    @staticmethod
    def update_thread_messages(thread_id, new_messages):
        """
        Insert one or many messages for a given thread.

        new_messages can be:
        • a dict: {"role": "...", "content": "..."}
        • a list of dicts: [{"role": "...", "content": "..."}, ...]
        """
        if isinstance(new_messages, dict):
            messages_to_insert = [new_messages]
        else:
            messages_to_insert = list(new_messages)

        with pool.connection() as conn:
            with conn.cursor() as curr:
                for msg in messages_to_insert:
                    curr.execute(
                        """
                        INSERT INTO thread_messages (thread_id, role, content)
                        VALUES (%s, %s, %s)
                        """,
                        (thread_id, msg["role"], msg["content"]),
                    )
            conn.commit()

        CacheService.delete(f"thread:{thread_id}:messages")
        CacheService.delete(f"thread:{thread_id}:recent_messages")

    @staticmethod
    def rename_thread(thread_id, new_title):
        """Renames a specific thread."""
        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    UPDATE thread SET title = %s WHERE id = %s
                    """,
                    (new_title, thread_id),
                )
            conn.commit()

    @staticmethod
    def get_threads(user_id):
        cache_key = f"threads:{user_id}"
        cached_value = CacheService.get(cache_key)
        if cached_value:
            return json.loads(cached_value)

        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    SELECT id, title, created_at 
                    FROM thread
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )

                rows = curr.fetchall()

        threads = [
            {
                "id": row[0],
                "title": row[1],
                "created_at": row[2].isoformat() if row[2] else None,
            }
            for row in rows
        ]

        CacheService.set(cache_key, json.dumps(threads), ex=3600)
        return threads

    @staticmethod
    def get_last_thread(user_id):

        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                SELECT id FROM thread
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                    (user_id,),
                )
                row = curr.fetchone()

        thread_id = row[0] if row else None

        return thread_id

    @staticmethod
    def get_thread_messages(thread_id):

        cache_key = f"thread:{thread_id}:messages"
        cached_value = CacheService.get(cache_key)
        if cached_value:
            return json.loads(cached_value)

        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    SELECT role, content 
                    FROM thread_messages
                    WHERE thread_id = %s 
                    ORDER BY created_at ASC
                    """,
                    (thread_id,),
                )

                rows = curr.fetchall()

        messages = [
            {
                "role": row[0],
                "content": row[1],
            }
            for row in rows
        ]

        result = {"messages": messages}

        CacheService.set(cache_key, json.dumps(result), 3600)
        return result

    @staticmethod
    def get_recent_thread_messages(thread_id):

        cache_key = f"thread:{thread_id}:recent_messages"
        cached_value = CacheService.get(cache_key)
        if cached_value:
            return json.loads(cached_value)

        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    SELECT role, content 
                    FROM thread_messages
                    WHERE thread_id = %s 
                    ORDER BY created_at DESC
                    LIMIT 6
                    """,
                    (thread_id,),
                )

                rows = curr.fetchall()

        messages = [{"role": r[0], "content": r[1]} for r in rows]

        # Reverse to maintain chronological order (oldest first)
        messages.reverse()

        result = {"messages": messages}

        CacheService.set(cache_key, json.dumps(result), 3600)
        return result

    @staticmethod
    def delete_thread(thread_id):
        """Deletes a specific thread and all its messages."""

        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    DELETE FROM thread WHERE id = %s
                    """,
                    (thread_id,),
                )
            conn.commit()

        CacheService.delete(f"thread:{thread_id}:messages")
        CacheService.delete(f"thread:{thread_id}:recent_messages")
