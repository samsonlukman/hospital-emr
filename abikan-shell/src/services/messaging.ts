export type ConversationType = "department" | "direct";
export const ACTIVE_MESSAGE_CONVERSATION_EVENT = "abikan:active-message-conversation";

export interface Message {
  id: string;
  conversationId: string;
  senderUsername: string;
  body: string;
  createdAt: string;
  editedAt: string;
  deletedAt: string;
}

export interface ConversationParticipant {
  type: "workplace" | "user";
  workplace: string;
  username: string;
  lastReadAt?: string;
}

export interface AttentionRequest {
  id: string;
  status: "requested" | "acknowledged";
  requesterUsername: string;
  recipientWorkplace: string;
  recipientUsername: string;
  createdAt: string;
  acknowledgedAt: string;
  acknowledgedByUsername: string;
}

export interface Conversation {
  id: string;
  type: ConversationType;
  createdByUsername: string;
  patientUuid: string;
  visitUuid: string;
  encounterUuid: string;
  createdAt: string;
  updatedAt: string;
  archivedAt: string;
  unreadCount: number;
  label?: string;
  latestMessage?: string;
  participants?: ConversationParticipant[];
  messages?: Message[];
  attention?: AttentionRequest | null;
  patient?: { uuid: string; name: string; mrn: string };
  hasPatientContext?: boolean;
}

export interface MessagingWorkplace {
  id: string;
  label: string;
}

export interface MessagingStaff {
  username: string;
  displayName: string;
  online: boolean;
}

export class MessagingRequestError extends Error {
  status?: number;
  code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = "MessagingRequestError";
    this.status = status;
    this.code = code;
  }
}

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = (await response.json().catch(() => ({}))) as {
    message?: string;
    code?: string;
  };
  if (!response.ok) {
    throw new MessagingRequestError(
      body.message || "The message could not be completed.",
      response.status,
      body.code,
    );
  }
  return body as T;
}

export function fetchConversations(query = ""): Promise<{ conversations: Conversation[] }> {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return readJson(`/openmrs/abikan-api/messages/conversations${suffix}`);
}

export function fetchConversation(id: string, before?: string, after?: string): Promise<{ conversation: Conversation }> {
  const params = new URLSearchParams();
  if (before) params.set("before", before);
  if (after) params.set("after", after);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson(`/openmrs/abikan-api/messages/conversations/${encodeURIComponent(id)}${suffix}`);
}

export function createConversation(input: {
  type: ConversationType;
  workplace?: string;
  username?: string;
  patientUuid?: string;
}): Promise<{ conversation: Conversation; duplicate: boolean }> {
  return readJson("/openmrs/abikan-api/messages/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function sendMessage(id: string, body: string): Promise<{ message: Message }> {
  return readJson(`/openmrs/abikan-api/messages/conversations/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
}

export function markConversationRead(id: string, messageId: string): Promise<{ changed: boolean }> {
  return readJson(`/openmrs/abikan-api/messages/conversations/${encodeURIComponent(id)}/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messageId }),
  });
}

export function requestAttention(id: string): Promise<{ attention: AttentionRequest }> {
  return readJson(`/openmrs/abikan-api/messages/conversations/${encodeURIComponent(id)}/attention`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

export function acknowledgeAttention(id: string): Promise<{ attention: AttentionRequest }> {
  return readJson(`/openmrs/abikan-api/messages/attention/${encodeURIComponent(id)}/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

export function fetchMessageWorkplaces(): Promise<{ workplaces: MessagingWorkplace[] }> {
  return readJson("/openmrs/abikan-api/messages/workplaces");
}

export function fetchMessageStaff(query = ""): Promise<{ staff: MessagingStaff[] }> {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return readJson(`/openmrs/abikan-api/messages/staff${suffix}`);
}

export function sendPresenceHeartbeat(): Promise<{ online: boolean }> {
  return readJson("/openmrs/abikan-api/messages/presence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}
