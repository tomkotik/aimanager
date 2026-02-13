"use client";

import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

function variantClasses(variant: Variant): string {
  switch (variant) {
    case "primary":
      return "bg-accent text-black hover:bg-accent-hover";
    case "secondary":
      return "bg-bg-hover text-text hover:bg-[#242428]";
    case "danger":
      return "bg-danger text-white hover:bg-[#dc2626]";
    case "ghost":
      return "bg-transparent text-text-muted hover:text-text hover:bg-bg-hover";
    default:
      return "bg-accent text-black hover:bg-accent-hover";
  }
}

export function Button({ variant = "secondary", className, ...props }: Props) {
  return (
    <button
      {...props}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm transition-colors",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variantClasses(variant),
        className || "",
      ].join(" ")}
    />
  );
}

