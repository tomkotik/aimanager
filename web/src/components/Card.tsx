"use client";

import { HTMLAttributes, PropsWithChildren } from "react";

type CardProps = PropsWithChildren<
  HTMLAttributes<HTMLDivElement> & {
    className?: string;
  }
>;

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      {...props}
      className={[
        "rounded-xl border border-border bg-bg-card p-4",
        "shadow-sm",
        className || "",
      ].join(" ")}
    >
      {children}
    </div>
  );
}
