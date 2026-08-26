import { relations } from "drizzle-orm/relations";
import { emailThread, email, emailUser, recipient, attachment, emailLabel, user, thread, threadMessages } from "./schema";

export const emailRelations = relations(email, ({one, many}) => ({
	emailThread: one(emailThread, {
		fields: [email.threadId],
		references: [emailThread.id]
	}),
	emailUser: one(emailUser, {
		fields: [email.senderId],
		references: [emailUser.id]
	}),
	recipients: many(recipient),
	attachments: many(attachment),
	emailLabels: many(emailLabel),
}));

export const emailThreadRelations = relations(emailThread, ({many}) => ({
	emails: many(email),
}));

export const emailUserRelations = relations(emailUser, ({many}) => ({
	emails: many(email),
	recipients: many(recipient),
}));

export const recipientRelations = relations(recipient, ({one}) => ({
	email: one(email, {
		fields: [recipient.emailId],
		references: [email.id]
	}),
	emailUser: one(emailUser, {
		fields: [recipient.personId],
		references: [emailUser.id]
	}),
}));

export const attachmentRelations = relations(attachment, ({one}) => ({
	email: one(email, {
		fields: [attachment.emailId],
		references: [email.id]
	}),
}));

export const emailLabelRelations = relations(emailLabel, ({one}) => ({
	email: one(email, {
		fields: [emailLabel.emailId],
		references: [email.id]
	}),
}));

export const threadRelations = relations(thread, ({one, many}) => ({
	user: one(user, {
		fields: [thread.userId],
		references: [user.id]
	}),
	threadMessages: many(threadMessages),
}));

export const userRelations = relations(user, ({many}) => ({
	threads: many(thread),
}));

export const threadMessagesRelations = relations(threadMessages, ({one}) => ({
	thread: one(thread, {
		fields: [threadMessages.threadId],
		references: [thread.id]
	}),
}));