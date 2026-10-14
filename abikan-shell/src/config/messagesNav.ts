import type { NavGroup } from "../types";

export const MESSAGES_NAV: NavGroup = {
  id: "messages",
  label: "Communication",
  items: [
    { id: "messages", label: "Messages", kind: "route", href: "#/messages", icon: "message" },
    {
      id: "message-calls",
      label: "Call attention",
      kind: "route",
      href: "#/messages/call",
      icon: "phoneCall",
    },
  ],
};
