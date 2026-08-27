from src.lib.db import pool


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
                row = curr.fetchone()
                if row is None:
                    raise RuntimeError(
                        "Failed to create thread — INSERT RETURNING yielded no row"
                    )
                thread_id = row[0]

            conn.commit()

        return thread_id

    @staticmethod
    def update_thread_messages(thread_id, new_messages):
        """
        Insert one or many messages for a given thread.

        new_messages can be:
        - a dict: {"role": "...", "content": "..."}
        - a list of dicts: [{"role": "...", "content": "..."}, ...]
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
                        INSERT INTO thread_messages (thread_id, role, content, created_at)
                        VALUES (%s, %s, %s, clock_timestamp())
                        """,
                        (thread_id, msg["role"], msg["content"]),
                    )
            conn.commit()

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

        return result

    @staticmethod
    def get_recent_thread_messages(thread_id):

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

        messages.reverse()

        result = {"messages": messages}

        return result

    @staticmethod
    def delete_thread(thread_id):
        """Deletes a specific thread and all its messages (via CASCADE)."""

        with pool.connection() as conn:
            with conn.cursor() as curr:
                curr.execute(
                    """
                    DELETE FROM thread WHERE id = %s
                    """,
                    (thread_id,),
                )
            conn.commit()
