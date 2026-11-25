import type { ComponentProps } from "react";

type Props = Omit<ComponentProps<"a">, "href" | "onClick"> & {
  to: string;
  go: (to: string) => void;
  current?: boolean;
  /** Called after an in-app navigation (not for new-tab clicks). */
  onNavigate?: () => void;
};

/** Client-side link. Forwards className and data-* so it can sit under a shadcn `asChild` slot. */
export function Link({ to, go, children, current, onNavigate, ...rest }: Props) {
  return (
    <a
      {...rest}
      href={`/app${to}`}
      aria-current={current ? "page" : undefined}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        go(to);
        onNavigate?.();
      }}
    >
      {children}
    </a>
  );
}
