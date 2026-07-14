"""Initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user — email participants and app users
    op.create_table(
        "user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    # thread — conversation threads for the chat UI
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

    # thread_messages — chat messages within a thread
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

    # email_thread — Gmail thread grouping
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

    # email — individual emails
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
        sa.ForeignKeyConstraint(["sender_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gmail_email_id", name="uq_email_gmail_email_id"),
    )
    op.create_index(
        "ix_email_gmail_email_id", "email", ["gmail_email_id"], unique=True
    )

    # recipient — TO / CC / BCC recipients of each email
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
        sa.ForeignKeyConstraint(["person_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # attachment — files attached to emails
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

    # email_label — labels applied to emails (INBOX, IMPORTANT, etc.)
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


def downgrade() -> None:
    op.drop_table("email_label")
    op.drop_table("attachment")
    op.drop_table("recipient")
    op.drop_table("email")
    op.drop_index("ix_email_thread_gmail_thread_id", table_name="email_thread")
    op.drop_table("email_thread")
    op.drop_table("thread_messages")
    op.drop_table("thread")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")
