-- Current sql file was generated after introspecting the database
-- If you want to run this migration please uncomment this code before executing migrations
/*
CREATE TABLE "alembic_version" (
	"version_num" varchar(32) PRIMARY KEY NOT NULL
);
--> statement-breakpoint
CREATE TABLE "user" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email" varchar(320) NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"username" varchar(255) NOT NULL,
	"role" varchar(50) DEFAULT 'user' NOT NULL,
	CONSTRAINT "uq_user_email" UNIQUE("email"),
	CONSTRAINT "uq_user_username" UNIQUE("username")
);
--> statement-breakpoint
CREATE TABLE "email_thread" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"gmail_thread_id" varchar(255) NOT NULL,
	"subject" text,
	"first_email_at" timestamp with time zone,
	"last_email_at" timestamp with time zone,
	"message_count" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_email_thread_gmail_thread_id" UNIQUE("gmail_thread_id")
);
--> statement-breakpoint
CREATE TABLE "email" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"gmail_email_id" varchar(255) NOT NULL,
	"thread_id" uuid NOT NULL,
	"sender_id" uuid NOT NULL,
	"subject" text,
	"snippet" text,
	"body" text,
	"sent_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_email_gmail_email_id" UNIQUE("gmail_email_id")
);
--> statement-breakpoint
CREATE TABLE "email_user" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"display_name" varchar(255) DEFAULT '' NOT NULL,
	"email" varchar(320) NOT NULL,
	"domain" varchar(255) DEFAULT '' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_email_user_email" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "recipient" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email_id" uuid NOT NULL,
	"person_id" uuid NOT NULL,
	"recipient_type" varchar(10) NOT NULL
);
--> statement-breakpoint
CREATE TABLE "attachment" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email_id" uuid NOT NULL,
	"gmail_attachment_id" varchar(512) NOT NULL,
	"filename" varchar(512),
	"mime_type" varchar(255),
	"size_bytes" bigint
);
--> statement-breakpoint
CREATE TABLE "email_label" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email_id" uuid NOT NULL,
	"label" varchar(100) NOT NULL
);
--> statement-breakpoint
CREATE TABLE "thread" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" uuid NOT NULL,
	"title" varchar(255) NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "thread_messages" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"thread_id" uuid NOT NULL,
	"role" varchar(10) NOT NULL,
	"content" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "email_embedding" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"gmail_email_id" varchar(255),
	"content" text NOT NULL,
	"embedding" vector(3072) NOT NULL,
	"metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "email" ADD CONSTRAINT "email_thread_id_fkey" FOREIGN KEY ("thread_id") REFERENCES "public"."email_thread"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "email" ADD CONSTRAINT "email_sender_id_fkey" FOREIGN KEY ("sender_id") REFERENCES "public"."email_user"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "recipient" ADD CONSTRAINT "recipient_email_id_fkey" FOREIGN KEY ("email_id") REFERENCES "public"."email"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "recipient" ADD CONSTRAINT "recipient_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "public"."email_user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "attachment" ADD CONSTRAINT "attachment_email_id_fkey" FOREIGN KEY ("email_id") REFERENCES "public"."email"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "email_label" ADD CONSTRAINT "email_label_email_id_fkey" FOREIGN KEY ("email_id") REFERENCES "public"."email"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "thread" ADD CONSTRAINT "thread_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "thread_messages" ADD CONSTRAINT "thread_messages_thread_id_fkey" FOREIGN KEY ("thread_id") REFERENCES "public"."thread"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "ix_user_email" ON "user" USING btree ("email" text_ops);--> statement-breakpoint
CREATE UNIQUE INDEX "ix_user_username" ON "user" USING btree ("username" text_ops);--> statement-breakpoint
CREATE UNIQUE INDEX "ix_email_thread_gmail_thread_id" ON "email_thread" USING btree ("gmail_thread_id" text_ops);--> statement-breakpoint
CREATE UNIQUE INDEX "ix_email_gmail_email_id" ON "email" USING btree ("gmail_email_id" text_ops);--> statement-breakpoint
CREATE UNIQUE INDEX "ix_email_user_email" ON "email_user" USING btree ("email" text_ops);--> statement-breakpoint
CREATE INDEX "ix_email_embedding_gmail_email_id" ON "email_embedding" USING btree ("gmail_email_id" text_ops);--> statement-breakpoint
CREATE INDEX "ix_email_embedding_hnsw" ON "email_embedding" USING hnsw (((embedding)::halfvec(3072)) halfvec_cosine_ops);
*/