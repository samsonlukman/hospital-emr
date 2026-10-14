import { useEffect, useMemo, useState } from "react";
import { AppIcon } from "./icons";
import {
  acknowledgeAttention,
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
} from "../services/messaging";
import type { WorkspaceContext } from "../types";
import "./StaffTalkDock.css";

type Panel = "closed" | "chat" | "call";

function talkError(reason: unknown, fallback: string): string {
  return reason instanceof MessagingRequestError && reason.message ? reason.message : fallback;
}

function conversationKey(item: Conversation, username: string): string {
  if (item.type !== "direct") return item.id;
  const others = (item.participants || [])
    .filter((person) => person.type === "user" && person.username && person.username !== username)
    .map((person) => person.username.toLowerCase())
    .sort();
  if (others.length === 0) return item.id;
  return `direct:${others.join("|")}:${item.patientUuid || ""}`;
}

function clockTime(value: string): string {
  if (!value) return "";
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(value));
}

function PeopleColumns({
  workplaces,
  staff,
  online,
  busy,
  departmentAction,
  onDepartment,
  onStaff,
}: {
  workplaces: MessagingWorkplace[];
  staff: MessagingStaff[];
  online: number;
  busy: boolean;
  departmentAction: string;
  onDepartment: (id: string, label: string) => void;
  onStaff: (username: string, label: string) => void;
}) {
  return (
    <div className="staff-talk__columns">
      <div>
        <p className="staff-talk__label">Departments</p>
        <ul className="staff-talk__list">
          {workplaces.length === 0 ? <li className="staff-talk__muted">None</li> : null}
          {workplaces.map((item) => (
            <li key={item.id}>
              <button type="button" disabled={busy} onClick={() => onDepartment(item.id, item.label)}>
                <span>
                  <strong>{item.label}</strong>
                  <small>{departmentAction}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="staff-talk__label">Staff{online > 0 ? ` · ${online} online` : ""}</p>
        <ul className="staff-talk__list">
          {staff.length === 0 ? <li className="staff-talk__muted">None</li> : null}
          {staff.map((item) => (
            <li key={item.username}>
              <button type="button" disabled={busy} onClick={() => onStaff(item.username, item.displayName)}>
                <span>
                  <strong>{item.displayName}</strong>
                  <small className={item.online ? "is-online" : undefined}>
                    {item.online ? "Online" : "Offline"}
                  </small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ChatWindow({
  conversationId,
  username,
  onClose,
}: {
  conversationId: string;
  username: string;
  onClose: () => void;
}) {
  const [thread, setThread] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetchConversation(conversationId)
        .then(async (result) => {
          if (cancelled) return;
          const next = result.conversation;
          setThread(next);
          const latest = next.messages?.at(-1);
          if (latest) {
            await markConversationRead(conversationId, latest.id);
          }
        })
        .catch(() => {
          if (!cancelled) setError("This conversation could not be opened.");
        });
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [conversationId]);

  const send = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    setError("");
    try {
      await sendMessage(conversationId, draft.trim());
      setDraft("");
      const result = await fetchConversation(conversationId);
      setThread(result.conversation);
    } catch (reason) {
      setError(talkError(reason, "The message could not be sent."));
    } finally {
      setBusy(false);
    }
  };

  const acknowledge = async () => {
    if (!thread?.attention?.id) return;
    setBusy(true);
    try {
      await acknowledgeAttention(thread.attention.id);
      const result = await fetchConversation(conversationId);
      setThread(result.conversation);
    } catch (reason) {
      setError(talkError(reason, "The attention request could not be acknowledged."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="staff-talk__panel staff-talk__window" role="dialog" aria-label={thread?.label || "Chat"}>
      <header className="staff-talk__head">
        <strong>{thread?.label || "Chat"}</strong>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </header>
      {error ? <p className="staff-talk__error">{error}</p> : null}
      <div className="staff-talk__body">
        {thread?.attention?.status === "requested" ? (
          <p className="staff-talk__attention">
            {thread.attention.requesterUsername} needs your attention.
            <button type="button" disabled={busy} onClick={() => void acknowledge()}>
              Acknowledge
            </button>
          </p>
        ) : null}
        <div className="staff-talk__thread">
          {(thread?.messages || []).length === 0 ? <div className="staff-talk__muted">No messages yet.</div> : null}
          {(thread?.messages || []).map((message) => (
            <p key={message.id} className={message.senderUsername === username ? "is-mine" : undefined}>
              <strong>{message.senderUsername === username ? "You" : message.senderUsername}</strong>
              {message.body}
              <time>{clockTime(message.createdAt)}</time>
            </p>
          ))}
        </div>
        <form
          className="staff-talk__composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Type a message"
            aria-label="Type a message"
          />
          <button type="submit" className="is-primary" disabled={busy || !draft.trim()}>
            Send
          </button>
        </form>
      </div>
    </section>
  );
}

export function StaffTalkDock({ context }: { context: WorkspaceContext }) {
  const [panel, setPanel] = useState<Panel>("closed");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [workplaces, setWorkplaces] = useState<MessagingWorkplace[]>([]);
  const [staff, setStaff] = useState<MessagingStaff[]>([]);
  const [callQuery, setCallQuery] = useState("");
  const [sent, setSent] = useState("");

  const unread = conversations.reduce((sum, item) => sum + (item.unreadCount || 0), 0);
  const chats = useMemo(() => {
    const seen = new Set<string>();
    return conversations.filter((item) => {
      const key = conversationKey(item, context.username);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [conversations, context.username]);

  const loadList = () => {
    void fetchConversations()
      .then((result) => setConversations(result.conversations || []))
      .catch(() => undefined);
  };

  useEffect(() => {
    loadList();
    const timer = window.setInterval(loadList, panel === "closed" && openIds.length === 0 ? 15000 : 5000);
    return () => window.clearInterval(timer);
  }, [panel, openIds.length]);

  const loadPeople = () => {
    void fetchMessageWorkplaces()
      .then((result) => setWorkplaces(result.workplaces || []))
      .catch(() => setError("Departments could not be loaded."));
    void fetchMessageStaff()
      .then((result) => setStaff(result.staff || []))
      .catch(() => setError("Staff could not be loaded."));
  };

  const openWindow = (id: string) => {
    const selected = conversations.find((item) => item.id === id);
    const key = selected ? conversationKey(selected, context.username) : id;
    setOpenIds((current) => {
      const already = current.find((openId) => {
        if (openId === id) return true;
        const openItem = conversations.find((item) => item.id === openId);
        return Boolean(openItem && conversationKey(openItem, context.username) === key);
      });
      if (already === id) return current;
      if (already) return current.map((openId) => (openId === already ? id : openId));
      return [...current, id];
    });
  };

  const closeWindow = (id: string) => {
    setOpenIds((current) => current.filter((item) => item !== id));
  };

  const openChat = () => {
    setError("");
    setSent("");
    setStarting(false);
    setPanel((current) => (current === "chat" ? "closed" : "chat"));
  };

  const openCall = () => {
    setError("");
    setSent("");
    setCallQuery("");
    loadPeople();
    setPanel((current) => (current === "call" ? "closed" : "call"));
  };

  const beginNew = () => {
    setStarting(true);
    setCallQuery("");
    loadPeople();
  };

  const startConversation = async (type: ConversationType, recipient: string) => {
    if (!recipient) return;
    setBusy(true);
    setError("");
    try {
      const result = await createConversation({
        type,
        workplace: type === "department" ? recipient : undefined,
        username: type === "direct" ? recipient : undefined,
      });
      setStarting(false);
      setCallQuery("");
      openWindow(result.conversation.id);
      loadList();
    } catch (reason) {
      setError(talkError(reason, "The conversation could not be started."));
    } finally {
      setBusy(false);
    }
  };

  const callPerson = async (type: ConversationType, recipient: string, label: string) => {
    setBusy(true);
    setError("");
    setSent("");
    try {
      const conversation = await createConversation({
        type,
        workplace: type === "department" ? recipient : undefined,
        username: type === "direct" ? recipient : undefined,
      });
      await requestAttention(conversation.conversation.id);
      setSent(`${label} will see this now.`);
      openWindow(conversation.conversation.id);
      loadList();
    } catch (reason) {
      setError(talkError(reason, "The attention request could not be sent."));
    } finally {
      setBusy(false);
    }
  };

  const people = useMemo(() => {
    const needle = callQuery.trim().toLowerCase();
    const matchedStaff = staff
      .filter((item) => `${item.displayName} ${item.username}`.toLowerCase().includes(needle))
      .sort((left, right) => Number(right.online) - Number(left.online) || left.displayName.localeCompare(right.displayName));
    return {
      workplaces: workplaces.filter((item) => item.label.toLowerCase().includes(needle)),
      staff: matchedStaff,
      online: matchedStaff.filter((item) => item.online).length,
    };
  }, [callQuery, workplaces, staff]);

  return (
    <div className="staff-talk">
      {openIds.length > 0 ? (
        <div className="staff-talk__windows">
          {openIds.map((id) => (
            <ChatWindow key={id} conversationId={id} username={context.username} onClose={() => closeWindow(id)} />
          ))}
        </div>
      ) : null}

      <div className="staff-talk__stack">
        {panel === "chat" ? (
          <section
            className={`staff-talk__panel${starting ? " is-wide" : ""}`}
            role="dialog"
            aria-label="Chat"
          >
            <header className="staff-talk__head">
              <strong>Chat</strong>
              <button type="button" onClick={() => setPanel("closed")}>
                Close
              </button>
            </header>
            {error ? <p className="staff-talk__error">{error}</p> : null}
            {!starting ? (
              <div className="staff-talk__body">
                <button type="button" className="staff-talk__start" onClick={beginNew}>
                  + Start chat
                </button>
                {chats.length === 0 ? <p className="staff-talk__muted">No chats yet.</p> : null}
                <ul className="staff-talk__list">
                  {chats.map((item) => (
                    <li key={item.id}>
                      <button type="button" onClick={() => openWindow(item.id)}>
                        <span>
                          <strong>{item.label || "Conversation"}</strong>
                          <small>{item.latestMessage || "No messages yet"}</small>
                        </span>
                        {item.unreadCount > 0 ? <em>{item.unreadCount}</em> : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="staff-talk__body">
                <input
                  value={callQuery}
                  onChange={(event) => setCallQuery(event.target.value)}
                  placeholder="Search department or staff"
                  aria-label="Search department or staff"
                />
                <PeopleColumns
                  workplaces={people.workplaces}
                  staff={people.staff}
                  online={people.online}
                  busy={busy}
                  departmentAction="Chat"
                  onDepartment={(id) => void startConversation("department", id)}
                  onStaff={(username) => void startConversation("direct", username)}
                />
                <div className="staff-talk__actions">
                  <button type="button" onClick={() => setStarting(false)}>
                    Back
                  </button>
                </div>
              </div>
            )}
          </section>
        ) : null}

        {panel === "call" ? (
          <section className="staff-talk__panel is-wide" role="dialog" aria-label="Call attention">
            <header className="staff-talk__head">
              <strong>Call attention</strong>
              <button type="button" onClick={() => setPanel("closed")}>
                Close
              </button>
            </header>
            {error ? <p className="staff-talk__error">{error}</p> : null}
            <div className="staff-talk__body">
              {sent ? <p className="staff-talk__sent">{sent}</p> : null}
              <input
                value={callQuery}
                onChange={(event) => setCallQuery(event.target.value)}
                placeholder="Search department or staff"
                aria-label="Search department or staff"
              />
              <PeopleColumns
                workplaces={people.workplaces}
                staff={people.staff}
                online={people.online}
                busy={busy}
                departmentAction="Call"
                onDepartment={(id, label) => void callPerson("department", id, label)}
                onStaff={(username, label) => void callPerson("direct", username, label)}
              />
            </div>
          </section>
        ) : null}

        <div className="staff-talk__bar">
          <button type="button" className={panel === "chat" ? "is-open" : undefined} onClick={openChat}>
            <AppIcon name="message" size={16} />
            Chat
            {unread > 0 ? <em>{unread > 9 ? "9+" : unread}</em> : null}
          </button>
          <button type="button" className={panel === "call" ? "is-open" : undefined} onClick={openCall}>
            <AppIcon name="phoneCall" size={16} />
            Call attention
          </button>
        </div>
      </div>
    </div>
  );
}
