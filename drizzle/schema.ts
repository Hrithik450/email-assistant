import { pgTable, varchar, uniqueIndex, unique, uuid, timestamp, text, integer, foreignKey, bigint, index, vector, jsonb } from "drizzle-orm/pg-core"
import { sql } from "drizzle-orm"



export const alembicVersion = pgTable("alembic_version", {
	versionNum: varchar("version_num", { length: 32 }).primaryKey().notNull(),
});

export const user = pgTable("user", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	email: varchar({ length: 320 }).notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
	username: varchar({ length: 255 }).notNull(),
	role: varchar({ length: 50 }).default('user').notNull(),
}, (table) => [
	uniqueIndex("ix_user_email").using("btree", table.email.asc().nullsLast().op("text_ops")),
	uniqueIndex("ix_user_username").using("btree", table.username.asc().nullsLast().op("text_ops")),
	unique("uq_user_email").on(table.email),
	unique("uq_user_username").on(table.username),
]);

export const emailThread = pgTable("email_thread", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	gmailThreadId: varchar("gmail_thread_id", { length: 255 }).notNull(),
	subject: text(),
	firstEmailAt: timestamp("first_email_at", { withTimezone: true, mode: 'string' }),
	lastEmailAt: timestamp("last_email_at", { withTimezone: true, mode: 'string' }),
	messageCount: integer("message_count").default(0).notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	uniqueIndex("ix_email_thread_gmail_thread_id").using("btree", table.gmailThreadId.asc().nullsLast().op("text_ops")),
	unique("uq_email_thread_gmail_thread_id").on(table.gmailThreadId),
]);

export const email = pgTable("email", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	gmailEmailId: varchar("gmail_email_id", { length: 255 }).notNull(),
	threadId: uuid("thread_id").notNull(),
	senderId: uuid("sender_id").notNull(),
	subject: text(),
	snippet: text(),
	body: text(),
	sentAt: timestamp("sent_at", { withTimezone: true, mode: 'string' }).notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	uniqueIndex("ix_email_gmail_email_id").using("btree", table.gmailEmailId.asc().nullsLast().op("text_ops")),
	foreignKey({
			columns: [table.threadId],
			foreignColumns: [emailThread.id],
			name: "email_thread_id_fkey"
		}).onDelete("cascade"),
	foreignKey({
			columns: [table.senderId],
			foreignColumns: [emailUser.id],
			name: "email_sender_id_fkey"
		}).onDelete("restrict"),
	unique("uq_email_gmail_email_id").on(table.gmailEmailId),
]);

export const emailUser = pgTable("email_user", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	displayName: varchar("display_name", { length: 255 }).default('').notNull(),
	email: varchar({ length: 320 }).notNull(),
	domain: varchar({ length: 255 }).default('').notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	uniqueIndex("ix_email_user_email").using("btree", table.email.asc().nullsLast().op("text_ops")),
	unique("uq_email_user_email").on(table.email),
]);

export const recipient = pgTable("recipient", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	emailId: uuid("email_id").notNull(),
	personId: uuid("person_id").notNull(),
	recipientType: varchar("recipient_type", { length: 10 }).notNull(),
}, (table) => [
	foreignKey({
			columns: [table.emailId],
			foreignColumns: [email.id],
			name: "recipient_email_id_fkey"
		}).onDelete("cascade"),
	foreignKey({
			columns: [table.personId],
			foreignColumns: [emailUser.id],
			name: "recipient_person_id_fkey"
		}).onDelete("cascade"),
]);

export const attachment = pgTable("attachment", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	emailId: uuid("email_id").notNull(),
	gmailAttachmentId: varchar("gmail_attachment_id", { length: 512 }).notNull(),
	filename: varchar({ length: 512 }),
	mimeType: varchar("mime_type", { length: 255 }),
	// You can use { mode: "bigint" } if numbers are exceeding js number limitations
	sizeBytes: bigint("size_bytes", { mode: "number" }),
}, (table) => [
	foreignKey({
			columns: [table.emailId],
			foreignColumns: [email.id],
			name: "attachment_email_id_fkey"
		}).onDelete("cascade"),
]);

export const emailLabel = pgTable("email_label", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	emailId: uuid("email_id").notNull(),
	label: varchar({ length: 100 }).notNull(),
}, (table) => [
	foreignKey({
			columns: [table.emailId],
			foreignColumns: [email.id],
			name: "email_label_email_id_fkey"
		}).onDelete("cascade"),
]);

export const thread = pgTable("thread", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	userId: uuid("user_id").notNull(),
	title: varchar({ length: 255 }).notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	foreignKey({
			columns: [table.userId],
			foreignColumns: [user.id],
			name: "thread_user_id_fkey"
		}).onDelete("cascade"),
]);

export const threadMessages = pgTable("thread_messages", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	threadId: uuid("thread_id").notNull(),
	role: varchar({ length: 10 }).notNull(),
	content: text().notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	foreignKey({
			columns: [table.threadId],
			foreignColumns: [thread.id],
			name: "thread_messages_thread_id_fkey"
		}).onDelete("cascade"),
]);

export const emailEmbedding = pgTable("email_embedding", {
	id: uuid().defaultRandom().primaryKey().notNull(),
	gmailEmailId: varchar("gmail_email_id", { length: 255 }),
	content: text().notNull(),
	embedding: vector({ dimensions: 3072 }).notNull(),
	metadata: jsonb().default({}).notNull(),
	createdAt: timestamp("created_at", { withTimezone: true, mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	index("ix_email_embedding_gmail_email_id").using("btree", table.gmailEmailId.asc().nullsLast().op("text_ops")),
	index("ix_email_embedding_hnsw").using("hnsw", sql`((embedding)::halfvec(3072))`),
]);
