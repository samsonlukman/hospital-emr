import type { HTMLAttributes, ReactNode } from "react";
import "./Card.css";

interface CardProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode;
}

export function Card({ children, className = "", ...props }: CardProps) {
  return (
    <section className={`abikan-card ${className}`.trim()} {...props}>
      {children}
    </section>
  );
}
