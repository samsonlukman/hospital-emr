import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { PatientSearch } from "../../components/PatientSearch";
import { AppIcon } from "../../components/icons";
import {
  acknowledgeAttention,
  ACTIVE_MESSAGE_CONVERSATION_EVENT,
  createConversation,
  fetchConversation,
  fetchConversations,
  fetchMessageStaff,
  fetchMessageWorkplaces,
  markConversationRead,
  MessagingRequestError,
  requestAttention,
  sendMessage,
  type Conversation,
  type ConversationType,
  type MessagingStaff,
  type MessagingWorkplace,
} from "../../services/messaging";
import type { WorkspaceContext } from "../../types";
import { playMessageBeep } from "../../utils/patientCallSpeech";
import "./MessagesWorkspace.css";

type Filter = "all" | "unread" | "departments" | "direct";

function timeLabel(value: string): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(
    new Date(value),
  );
}

interface MessagesWorkspaceProps {
  context: WorkspaceContext;
  callOnly?: boolean;
  conversationId?: string;
}

function actionError(reason: unknown, fallback: string): string {
  return reason instanceof MessagingRequestError && reason.message ? reason.message : fallback;
}

export function MessagesWorkspace({
  context,
  callOnly = false,
  conversationId = "",
}: MessagesWorkspaceProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [newType, setNewType] = useState<ConversationType>("department");
  const [workplaces, setWorkplaces] = useState<MessagingWorkplace[]>([]);
  const [staff, setStaff] = useState<MessagingStaff[]>([]);
  const [workplacesLoading, setWorkplacesLoading] = useState(false);
  const [targetWorkplace, setTargetWorkplace] = useState("");
  const [targetUser, setTargetUser] = useState("");
  const [callSearch, setCallSearch] = useState("");
  const [requestSentOpen, setRequestSentOpen] = useState(false);
  const [patientUuid, setPatientUuid] = useState("");
  const selectedRef = useRef<Conversation | null>(null);
  selectedRef.current = selected;

  useEffect(() => {
    if (callOnly) {
      loadRecipients();
    }
  }, [callOnly]);

  const loadList = async () => {
    try {
      const result = await fetchConversations(search);
      const nextConversations = result.conversations || [];
      setConversations((current) => {
        const unchanged =
          current.length === nextConversations.length &&
          current.every((item, index) => {
            const next = nextConversations[index];
            return (
              item.id === next.id &&
              item.updatedAt === next.updatedAt &&
              item.unreadCount === next.unreadCount &&
              item.latestMessage === next.latestMessage
            );
          });
        return unchanged ? current : nextConversations;
      });
      setSelected((current) => {
        const requested = conversationId
          ? nextConversations.find((item) => item.id === conversationId)
          : undefined;
        if (requested) {
          return current?.id === requested.id ? current : requested;
        }
        if (current) return current;
        return nextConversations[0] || null;
      });
      setError(null);
    } catch {
      setError("Messages could not be loaded. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const loadSelected = async (id: string, incremental = false) => {
    try {
      const cursor = incremental ? selectedRef.current?.messages?.at(-1)?.createdAt : undefined;
      const result = await fetchConversation(id, undefined, cursor ? String(Date.parse(cursor) / 1000) : undefined);
      const next = result.conversation;
      const knownIds = new Set((selectedRef.current?.messages || []).map((message) => message.id));
      const incomingMessages = incremental
        ? (next.messages || []).filter(
            (message) => !knownIds.has(message.id) && message.senderUsername !== context.username,
          )
        : [];
      if (incomingMessages.length > 0) {
        playMessageBeep();
      }
      setSelected((current) => {
        if (!incremental || !current || current.id !== id) return next;
        if (incomingMessages.length === 0) return current;
        return {
          ...next,
          messages: [
            ...(current.messages || []),
            ...(next.messages || []).filter((message) => !knownIds.has(message.id)),
          ],
        };
      });
      const latest = next.messages?.at(-1);
      const previousLatest = selectedRef.current?.messages?.at(-1)?.id;
      if (latest && (!incremental || latest.id !== previousLatest)) {
        await markConversationRead(id, latest.id);
      }
    } catch {
      setError("This conversation could not be opened.");
    }
  };

  useEffect(() => {
    if (callOnly) {
      setLoading(false);
      return;
    }
    void loadList();
    const timer = window.setInterval(() => void loadList(), 5000);
    return () => window.clearInterval(timer);
  }, [callOnly, search, conversationId]);

  useEffect(() => {
    if (callOnly || !selected?.id) return;
    window.dispatchEvent(
      new CustomEvent(ACTIVE_MESSAGE_CONVERSATION_EVENT, { detail: selected.id }),
    );
    void loadSelected(selected.id);
    const timer = window.setInterval(() => void loadSelected(selected.id, true), 5000);
    return () => {
      window.clearInterval(timer);
      window.dispatchEvent(
        new CustomEvent(ACTIVE_MESSAGE_CONVERSATION_EVENT, { detail: "" }),
      );
    };
  }, [selected?.id]);

  const visible = useMemo(
    () =>
      conversations.filter((item) => {
        if (filter === "unread") return item.unreadCount > 0;
        if (filter === "departments") return item.type === "department";
        if (filter === "direct") return item.type === "direct";
        return true;
      }),
    [conversations, filter],
  );

  const loadRecipients = () => {
    setWorkplaces([]);
    setStaff([]);
    setError(null);
    setWorkplacesLoading(true);
    void fetchMessageWorkplaces()
      .then((result) => setWorkplaces(result.workplaces || []))
      .catch(() => setError("Departments could not be loaded. Please try again."))
      .finally(() => setWorkplacesLoading(false));
    void fetchMessageStaff()
      .then((result) => setStaff(result.staff || []))
      .catch(() => setError("Staff members could not be loaded. Please try again."));
  };

  const openNew = () => {
    setNewOpen(true);
    loadRecipients();
  };

  const create = async () => {
    setSaving(true);
    try {
      const result = await createConversation({
        type: newType,
        workplace: newType === "department" ? targetWorkplace : undefined,
        username: newType === "direct" ? targetUser : undefined,
        patientUuid: patientUuid || undefined,
      });
      setNewOpen(false);
      setTargetWorkplace("");
      setTargetUser("");
      setPatientUuid("");
      await loadList();
      await loadSelected(result.conversation.id);
    } catch (reason) {
      setError(actionError(reason, "The conversation could not be started."));
    } finally {
      setSaving(false);
    }
  };

  const startCall = async (type: ConversationType, recipient: string) => {
    setSaving(true);
    setRequestSentOpen(false);
    try {
      const conversation = await createConversation({
        type,
        workplace: type === "department" ? recipient : undefined,
        username: type === "direct" ? recipient : undefined,
      });
      await requestAttention(conversation.conversation.id);
      setRequestSentOpen(true);
      if (!callOnly) {
        await loadList();
      }
    } catch (reason) {
      setError(actionError(reason, "The attention request could not be sent."));
    } finally {
      setSaving(false);
    }
  };

  const send = async () => {
    if (!selected || !draft.trim()) return;
    setSaving(true);
    try {
      await sendMessage(selected.id, draft.trim());
      setDraft("");
      await loadSelected(selected.id);
      await loadList();
    } catch (reason) {
      setError(actionError(reason, "The message could not be sent."));
    } finally {
      setSaving(false);
    }
  };

  const call = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await requestAttention(selected.id);
      await loadSelected(selected.id);
    } catch (reason) {
      setError(actionError(reason, "The attention request could not be sent."));
    } finally {
      setSaving(false);
    }
  };

  const acknowledge = async () => {
    if (!selected?.attention?.id) return;
    setSaving(true);
    try {
      await acknowledgeAttention(selected.attention.id);
      await loadSelected(selected.id);
    } catch (reason) {
      setError(actionError(reason, "The attention request could not be acknowledged."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="messages-workspace">
      <PageHeader
        title={callOnly ? "Call attention" : "Messages"}
        description={
          callOnly
            ? undefined
            : `Internal communication · ${context.displayName}`
        }
      >
        {!callOnly ? <Button onClick={() => void openNew()}>New message</Button> : null}
      </PageHeader>
      {error ? <p className="messages-error" role="alert">{error}</p> : null}
      {callOnly ? (
        <section className="call-attention-screen" aria-label="Call attention">
          <div className="call-attention-screen__toolbar">
            <input
              className="messages-search"
              aria-label="Search departments and staff"
              placeholder="Search departments and staff"
              value={callSearch}
              onChange={(event) => setCallSearch(event.target.value)}
            />
          </div>
          <div className="call-attention-screen__grid">
            <Card>
              <h2>Departments</h2>
              <div className="call-attention-screen__list">
                {workplacesLoading ? <p className="messages-muted">Loading departments…</p> : null}
                {!workplacesLoading && workplaces.length === 0 ? (
                  <p className="messages-muted">No other departments are available to call.</p>
                ) : null}
                {workplaces
                  .filter((item) => item.label.toLowerCase().includes(callSearch.toLowerCase()))
                  .map((item) => (
                    <button
                      type="button"
                      disabled={saving}
                      className={`call-recipient${targetWorkplace === item.id ? " is-selected" : ""}`}
                      key={item.id}
                      onClick={() => {
                        void startCall("department", item.id);
                      }}
                    >
                      <span className="call-recipient__call">
                        <AppIcon name="phoneCall" size={16} />
                        Call
                      </span>
                      <span>
                        <strong>{item.label}</strong>
                        <small>Department</small>
                      </span>
                    </button>
                  ))}
              </div>
            </Card>
            <Card>
              <h2>Staff</h2>
              <div className="call-attention-screen__list">
                {staff
                  .filter((item) =>
                    `${item.displayName} ${item.username}`.toLowerCase().includes(callSearch.toLowerCase()),
                  )
                  .sort(
                    (left, right) =>
                      Number(right.online) - Number(left.online) ||
                      left.displayName.localeCompare(right.displayName),
                  )
                  .map((item) => (
                    <button
                      type="button"
                      disabled={saving}
                      className={`call-recipient${targetUser === item.username ? " is-selected" : ""}`}
                      key={item.username}
                      onClick={() => {
                        void startCall("direct", item.username);
                      }}
                    >
                      <span className="call-recipient__call">
                        <AppIcon name="phoneCall" size={16} />
                        Call
                      </span>
                      <span>
                        <strong>{item.displayName}</strong>
                        <small className={item.online ? "staff-status is-online" : "staff-status"}>
                          <i aria-hidden="true" />
                          {item.online ? "Online" : "Offline"} · {item.username}
                        </small>
                      </span>
                    </button>
                  ))}
              </div>
            </Card>
          </div>
        </section>
      ) : null}
      {!callOnly ? <div className="messages-layout">
        <Card className="messages-sidebar">
          <div className="messages-filters">
            {(["all", "unread", "departments", "direct"] as Filter[]).map((item) => (
              <button
                type="button"
                key={item}
                className={filter === item ? "is-active" : ""}
                onClick={() => setFilter(item)}
              >
                {item === "all" ? "All" : item === "unread" ? "Unread" : item === "departments" ? "Departments" : "Direct"}
              </button>
            ))}
          </div>
          <input
            className="messages-search"
            aria-label="Search messages"
            placeholder="Search conversations"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {loading ? <p className="messages-muted">Loading messages…</p> : null}
          {!loading && visible.length === 0 ? <EmptyState title="No messages yet" /> : null}
          <div className="conversation-list">
            {visible.map((conversation) => (
              <button
                type="button"
                key={conversation.id}
                className={`conversation-row ${selected?.id === conversation.id ? "is-selected" : ""}`}
                onClick={() => setSelected(conversation)}
              >
                <span className="conversation-row__top">
                  <strong>{conversation.label || "Conversation"}</strong>
                  <small>{timeLabel(conversation.updatedAt)}</small>
                </span>
                <span className="conversation-row__message">{conversation.latestMessage || "No messages yet"}</span>
                {conversation.unreadCount > 0 ? <span className="conversation-row__badge">{conversation.unreadCount} unread</span> : null}
              </button>
            ))}
          </div>
        </Card>

        <Card className="messages-thread">
          {!selected ? (
            <EmptyState title="Choose a conversation" description="Select a conversation or start a new message." />
          ) : (
            <>
              <header className="messages-thread__header">
                <div>
                  <p className="messages-eyebrow">{selected.type === "department" ? "Department" : "Direct message"}</p>
                  <h2>{selected.label || "Conversation"}</h2>
                  {selected.patient ? (
                    <p className="messages-patient">
                      Patient: <strong>{selected.patient.mrn}</strong> · {selected.patient.name}
                    </p>
                  ) : null}
                </div>
                {selected.type === "department" ? (
                  <Button variant="secondary" busy={saving} onClick={() => void call()}>
                    Call / attention
                  </Button>
                ) : null}
              </header>
              {selected.attention?.status === "requested" ? (
                <div className="messages-attention">
                  <strong>Incoming attention request</strong>
                  <span>{selected.attention.requesterUsername} needs your attention.</span>
                  <Button variant="primary" busy={saving} onClick={() => void acknowledge()}>Acknowledge</Button>
                </div>
              ) : null}
              {selected.attention?.status === "acknowledged" ? (
                <p className="messages-acknowledged">✓ Acknowledged by {selected.attention.acknowledgedByUsername}</p>
              ) : null}
              <div className="messages-history">
                {(selected.messages || []).map((message) => (
                  <article className={`message-bubble ${message.senderUsername === context.username ? "is-mine" : ""}`} key={message.id}>
                    <span className="message-bubble__sender">{message.senderUsername === context.username ? "You" : message.senderUsername}</span>
                    <p>{message.body}</p>
                    <time>{timeLabel(message.createdAt)}</time>
                  </article>
                ))}
              </div>
              <div className="messages-composer">
                <textarea
                  aria-label="Type a message"
                  placeholder="Type a message…"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                />
                <Button busy={saving} onClick={() => void send()}>Send</Button>
              </div>
            </>
          )}
        </Card>
      </div> : null}

      {newOpen ? (
        <div className="messages-dialog-backdrop">
          <Card className="messages-dialog">
            <h2>New message</h2>
            <div className="messages-type-toggle">
              <Button variant={newType === "department" ? "primary" : "secondary"} onClick={() => setNewType("department")}>Department</Button>
              <Button variant={newType === "direct" ? "primary" : "secondary"} onClick={() => setNewType("direct")}>Staff member</Button>
            </div>
            {newType === "department" ? (
              <select value={targetWorkplace} onChange={(event) => setTargetWorkplace(event.target.value)}>
                <option value="">
                  {workplacesLoading ? "Loading departments…" : "Choose a department"}
                </option>
                {workplaces.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
              </select>
            ) : (
              <select value={targetUser} onChange={(event) => setTargetUser(event.target.value)}>
                <option value="">Choose a staff member</option>
                {staff.map((item) => (
                  <option value={item.username} key={item.username}>
                    {item.displayName} · {item.online ? "Online" : "Offline"}
                  </option>
                ))}
              </select>
            )}
            <label className="messages-patient-label">
              Optional patient context
              <PatientSearch onSelect={setPatientUuid} />
            </label>
            {patientUuid ? <p className="messages-muted">Patient selected.</p> : null}
            <div className="messages-dialog__actions">
              <Button variant="secondary" onClick={() => setNewOpen(false)}>Cancel</Button>
              <Button
                busy={saving}
                disabled={newType === "department" ? !targetWorkplace : !targetUser}
                onClick={() => void create()}
              >
                Start conversation
              </Button>
            </div>
          </Card>
        </div>
      ) : null}
      {callOnly && requestSentOpen ? (
        <div className="messages-dialog-backdrop" role="dialog" aria-modal="true" aria-label="Request sent">
          <Card className="request-sent-dialog">
            <AppIcon name="phoneCall" size={24} />
            <h2>Request sent</h2>
            <p>The other department will see and hear this call now.</p>
            <Button onClick={() => setRequestSentOpen(false)}>Done</Button>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
