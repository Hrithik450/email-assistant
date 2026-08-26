from sqlalchemy import (
    Column,
    String,
    Text,
    ForeignKey,
    TIMESTAMP,
    func,
    Integer,
    BigInteger,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
import uuid

Base = declarative_base()


class User(Base):
    """Authenticated application user. Never used for email sender/recipient data."""

    __tablename__ = "user"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    role = Column(String(50), nullable=False, server_default="user")
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    conversation_threads = relationship(
        "ConversationThread",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ConversationThread(Base):
    """Chat thread owned by an app user."""

    __tablename__ = "thread"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(255), nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="conversation_threads")
    messages = relationship(
        "ConversationMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
    )


class ConversationMessage(Base):
    """Single message inside a chat thread."""

    __tablename__ = "thread_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(
        UUID(as_uuid=True), ForeignKey("thread.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(10), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    thread = relationship("ConversationThread", back_populates="messages")


class EmailUser(Base):
    """
    Person extracted from email headers (From / To / CC / BCC).
    Completely separate from the User table; never used for authentication.
    """

    __tablename__ = "email_user"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name = Column(String(255), nullable=False, server_default="")
    email = Column(String(320), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=False, server_default="")
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    sent_emails = relationship(
        "Email",
        back_populates="sender",
        foreign_keys="Email.sender_id",
    )
    received_emails = relationship(
        "Recipient",
        back_populates="person",
        foreign_keys="Recipient.person_id",
    )


class EmailThread(Base):
    """Groups a chain of emails sharing the same Gmail threadId."""

    __tablename__ = "email_thread"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_thread_id = Column(String(255), unique=True, nullable=False, index=True)
    subject = Column(Text)
    first_email_at = Column(TIMESTAMP(timezone=True))
    last_email_at = Column(TIMESTAMP(timezone=True))
    message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    emails = relationship(
        "Email", back_populates="thread", cascade="all, delete-orphan"
    )


class Email(Base):
    """Individual email message. sender_id references email_user, not user."""

    __tablename__ = "email"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_email_id = Column(String(255), unique=True, nullable=False, index=True)
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("email_thread.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("email_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject = Column(Text)
    snippet = Column(Text)
    body = Column(Text)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    thread = relationship("EmailThread", back_populates="emails")
    sender = relationship(
        "EmailUser", back_populates="sent_emails", foreign_keys=[sender_id]
    )
    recipients = relationship(
        "Recipient", back_populates="email", cascade="all, delete-orphan"
    )
    attachments = relationship(
        "Attachment", back_populates="email", cascade="all, delete-orphan"
    )
    labels = relationship(
        "EmailLabel", back_populates="email", cascade="all, delete-orphan"
    )


class Recipient(Base):
    """TO / CC / BCC recipients of an email. person_id references email_user."""

    __tablename__ = "recipient"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(
        UUID(as_uuid=True), ForeignKey("email.id", ondelete="CASCADE"), nullable=False
    )
    person_id = Column(
        UUID(as_uuid=True),
        ForeignKey("email_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_type = Column(String(10), nullable=False)  # TO / CC / BCC

    email = relationship("Email", back_populates="recipients")
    person = relationship(
        "EmailUser", back_populates="received_emails", foreign_keys=[person_id]
    )


class Attachment(Base):
    """File attached to an email."""

    __tablename__ = "attachment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(
        UUID(as_uuid=True), ForeignKey("email.id", ondelete="CASCADE"), nullable=False
    )
    gmail_attachment_id = Column(String(512), nullable=False)
    filename = Column(String(512))
    mime_type = Column(String(255))
    size_bytes = Column(BigInteger)

    email = relationship("Email", back_populates="attachments")


class EmailLabel(Base):
    """Label applied to an email (INBOX, IMPORTANT, CATEGORY_PERSONAL, …)."""

    __tablename__ = "email_label"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(
        UUID(as_uuid=True), ForeignKey("email.id", ondelete="CASCADE"), nullable=False
    )
    label = Column(String(100), nullable=False)

    email = relationship("Email", back_populates="labels")


class EmailEmbedding(Base):
    """Vector embedding of an email/thread summary for semantic search (pgvector).

    One row per indexed document. `embedding` is a Gemini `gemini-embedding-001`
    vector (3072-d, kept in sync with `src.lib.utils.EMBEDDING_DIM`). The HNSW
    index over its `halfvec(3072)` cast lives in the Alembic migration — an
    expression index can't be declared on the model, and pgvector caps the plain
    `vector` HNSW index at 2000 dims. The `metadata` JSONB holds the source
    document's original metadata plus a `source_id` used to make index rebuilds
    idempotent and resumable.
    """

    __tablename__ = "email_embedding"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Best-effort link to email.gmail_email_id (used for source attribution).
    gmail_email_id = Column(String(255), index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(3072), nullable=False)
    meta = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
