import "./ComingSoonMark.css";

interface ComingSoonMarkProps {
  label?: string;
}

export function ComingSoonMark({ label = "Coming soon" }: ComingSoonMarkProps) {
  return <span className="abikan-soon-mark">{label}</span>;
}
