import { useEffect, useState } from "react";
import "./SectionIndex.css";

export interface SectionIndexItem {
  id: string;
  label: string;
}

interface SectionIndexProps {
  items: readonly SectionIndexItem[];
  label?: string;
}

export function SectionIndex({ items, label = "Sections" }: SectionIndexProps) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const signature = items.map((item) => item.id).join("|");

  useEffect(() => {
    const nodes = items
      .map((item) => document.getElementById(item.id))
      .filter((node): node is HTMLElement => Boolean(node));
    if (nodes.length === 0) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible?.target.id) {
          setActiveId(visible.target.id);
        }
      },
      { rootMargin: "-15% 0px -60% 0px", threshold: [0.15, 0.4] },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [signature]);

  if (items.length < 2) {
    return null;
  }

  return (
    <nav className="abikan-index" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={activeId === item.id ? "is-active" : undefined}
          onClick={() => {
            setActiveId(item.id);
            document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
