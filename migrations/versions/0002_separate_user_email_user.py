"""Separate application user from email participants (email_user)

Revision ID: 0002_separate_user_email_user
Revises: 0001_initial_schema
Create Date: 2026-07-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_separate_user_email_user"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. Clear all existing data — dev migration; no production data to preserve
    # ------------------------------------------------------------------
    op.execute('DELETE FROM email_label')
    op.execute('DELETE FROM attachment')
    op.execute('DELETE FROM recipient')
    op.execute('DELETE FROM email')
    op.execute('DELETE FROM email_thread')
    op.execute('DELETE FROM thread_messages')
    op.execute('DELETE FROM thread')
    op.execute('DELETE FROM "user"')

    # ------------------------------------------------------------------
    # 1. Drop all tables that depend on "user" (FK chains, leaf-first)
    # ------------------------------------------------------------------
    op.drop_table("email_label")
    op.drop_table("attachment")
    op.drop_table("recipient")
    op.drop_table("email")
    op.drop_table("email_thread")
    op.drop_table("thread_messages")
    op.drop_table("thread")

    # ------------------------------------------------------------------
    # 2. Reshape "user" into an app-authentication-only table
    # ------------------------------------------------------------------
    op.drop_index("ix_user_email", table_name="user")
    op.drop_constraint("uq_user_email", "user", type_="unique")

    op.drop_column("user", "user_name")
    op.drop_column("user", "domain")

    op.add_column(
        "user",
        sa.Column("username", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "user",
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
            server_default="user",
        ),
    )
    # Remove the server defaults used only to satisfy the NOT NULL during ALTER
    op.alter_column("user", "username", server_default=None)

    op.create_unique_constraint("uq_user_username", "user", ["username"])
    op.create_unique_constraint("uq_user_email", "user", ["email"])
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_user_username", "user", ["username"], unique=True)

    # ------------------------------------------------------------------
    # 3. Create email_user — people extracted from email headers only
    # ------------------------------------------------------------------
    op.create_table(
        "email_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_email_user_email"),
    )
    op.create_index("ix_email_user_email", "email_user", ["email"], unique=True)

    # ------------------------------------------------------------------
    # 4. Recreate email_thread
    # ------------------------------------------------------------------
    op.create_table(
        "email_thread",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("gmail_thread_id", sa.String(255), nullable=False),
        sa.Column("subject", sa.Text()),
        sa.Column("first_email_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_email_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_thread_id", name="uq_email_thread_gmail_thread_id"),
    )
    op.create_index(
        "ix_email_thread_gmail_thread_id", "email_thread", ["gmail_thread_id"], unique=True
    )

    # ------------------------------------------------------------------
    # 5. Recreate email — sender_id now FK → email_user
    # ------------------------------------------------------------------
    op.create_table(
        "email",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("gmail_email_id", sa.String(255), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.Text()),
        sa.Column("snippet", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["email_thread.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["email_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_email_id", name="uq_email_gmail_email_id"),
    )
    op.create_index("ix_email_gmail_email_id", "email", ["gmail_email_id"], unique=True)

    # ------------------------------------------------------------------
    # 6. Recreate recipient — person_id now FK → email_user
    # ------------------------------------------------------------------
    op.create_table(
        "recipient",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_type", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["email.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["email_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # 7. Recreate attachment
    # ------------------------------------------------------------------
    op.create_table(
        "attachment",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gmail_attachment_id", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(512)),
        sa.Column("mime_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.ForeignKeyConstraint(["email_id"], ["email.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # 8. Recreate email_label
    # ------------------------------------------------------------------
    op.create_table(
        "email_label",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["email.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # 9. Recreate thread + thread_messages (FK → user unchanged)
    # ------------------------------------------------------------------
    op.create_table(
        "thread",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "thread_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["thread.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("thread_messages")
    op.drop_table("thread")
    op.drop_table("email_label")
    op.drop_table("attachment")
    op.drop_table("recipient")
    op.drop_table("email")
    op.drop_index("ix_email_thread_gmail_thread_id", table_name="email_thread")
    op.drop_table("email_thread")
    op.drop_index("ix_email_user_email", table_name="email_user")
    op.drop_table("email_user")

    op.drop_index("ix_user_username", table_name="user")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_constraint("uq_user_username", "user", type_="unique")
    op.drop_constraint("uq_user_email", "user", type_="unique")
    op.drop_column("user", "role")
    op.drop_column("user", "username")

    op.add_column("user", sa.Column("user_name", sa.String(255), nullable=False, server_default=""))
    op.add_column("user", sa.Column("domain", sa.String(255), nullable=False, server_default=""))
    op.create_unique_constraint("uq_user_email", "user", ["email"])
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "email_thread",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gmail_thread_id", sa.String(255), nullable=False),
        sa.Column("subject", sa.Text()),
        sa.Column("first_email_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_email_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_thread_id", name="uq_email_thread_gmail_thread_id"),
    )
    op.create_index("ix_email_thread_gmail_thread_id", "email_thread", ["gmail_thread_id"], unique=True)
    op.create_table(
        "email",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gmail_email_id", sa.String(255), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.Text()),
        sa.Column("snippet", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["email_thread.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_email_id", name="uq_email_gmail_email_id"),
    )
    op.create_index("ix_email_gmail_email_id", "email", ["gmail_email_id"], unique=True)
    op.create_table(
        "recipient",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_type", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["email.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "attachment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gmail_attachment_id", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(512)),
        sa.Column("mime_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.ForeignKeyConstraint(["email_id"], ["email.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "email_label",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], ["email.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "thread",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "thread_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["thread.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
