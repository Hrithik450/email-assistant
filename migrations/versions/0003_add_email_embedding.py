"""Add email_embedding table (pgvector) for Gemini semantic search

Revision ID: 0003_add_email_embedding
Revises: 0002_separate_user_email_user
Create Date: 2026-08-26

Raw SQL is used deliberately: the pgvector extension, the `vector(3072)` column,
and the HNSW index over the `halfvec(3072)` cast can't be expressed by Alembic
autogenerate. pgvector caps the plain `vector` HNSW index at 2000 dims, so the
index (and every query) uses the half-precision `halfvec` cast, whose HNSW limit
is 4000. Requires pgvector >= 0.7 (shipped by `pgvector/pgvector:pg16`).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_add_email_embedding"
down_revision: Union[str, Sequence[str], None] = "0002_separate_user_email_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE email_embedding (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            gmail_email_id varchar(255),
            content        text NOT NULL,
            embedding      vector(3072) NOT NULL,
            metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        "CREATE INDEX ix_email_embedding_gmail_email_id "
        "ON email_embedding (gmail_email_id)"
    )

    # HNSW over the halfvec cast — the plain `vector` type is limited to 2000 dims.
    op.execute(
        """
        CREATE INDEX ix_email_embedding_hnsw ON email_embedding
        USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_embedding")
    # The `vector` extension is left installed; other objects may depend on it.
