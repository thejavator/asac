export function Link({
  to, go, children, current,
}: { to: string; go: (to: string) => void; children: React.ReactNode; current?: boolean }) {
  return (
    <a
      href={`/app${to}`}
      aria-current={current ? "page" : undefined}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        go(to);
      }}
    >
      {children}
    </a>
  );
}
