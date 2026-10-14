import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  BedDouble,
  Bell,
  Calendar,
  CalendarPlus,
  ClipboardList,
  ClipboardPlus,
  CreditCard,
  FileText,
  FlaskConical,
  FolderOpen,
  Image,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircle,
  Pill,
  PhoneCall,
  Receipt,
  Search,
  Settings,
  Stethoscope,
  User,
  UserPlus,
  Users,
} from "lucide-react";
import type { AppIconName } from "../types";

export type { AppIconName };

const ICONS: Record<Exclude<AppIconName, "naira">, LucideIcon> = {
  dashboard: LayoutDashboard,
  search: Search,
  userPlus: UserPlus,
  user: User,
  users: Users,
  calendar: Calendar,
  calendarPlus: CalendarPlus,
  clipboardPlus: ClipboardPlus,
  clipboardList: ClipboardList,
  creditCard: CreditCard,
  receipt: Receipt,
  chart: BarChart3,
  fileText: FileText,
  settings: Settings,
  bell: Bell,
  menu: Menu,
  logOut: LogOut,
  activity: Activity,
  stethoscope: Stethoscope,
  bed: BedDouble,
  image: Image,
  folder: FolderOpen,
  flask: FlaskConical,
  pill: Pill,
  message: MessageCircle,
  phoneCall: PhoneCall,
};

const STROKE = 1.75;

function NairaIcon({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M7 4v16" />
      <path d="M17 4v16" />
      <path d="M7 8h10" />
      <path d="M7 16h10" />
      <path d="M8 20 16 4" />
    </svg>
  );
}

interface AppIconProps {
  name: AppIconName;
  size?: number;
  className?: string;
}

export function AppIcon({ name, size = 20, className }: AppIconProps) {
  if (name === "naira") {
    return <NairaIcon size={size} className={className} />;
  }
  const Icon = ICONS[name];
  return <Icon size={size} strokeWidth={STROKE} className={className} aria-hidden="true" />;
}
