import { useInfiniteQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Link } from "../components/Link";

export function AuditPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const q = useInfiniteQuery({
    queryKey: ["audit", pid],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/projects/{pid}/audit", { params: { path: { pid }, query: { cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / Audit trail</p>
      <div className="page-head"><div><h1>Audit trail</h1><p>Every decision, change and denial, newest first. Entries cannot be edited.</p></div><a className="btn" href={`/api/v1/projects/${encodeURIComponent(pid)}/audit.csv`} download>Export CSV</a></div>
      {q.isError && <p role="alert">Could not load the audit trail: {q.error.message}</p>}
      {q.data && items.length === 0 && <p className="soft">Nothing recorded yet.</p>}
      {items.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th className="hide-sm">When</th><th>Who</th><th>Action</th><th className="hide-sm">Run</th><th>Detail</th></tr></thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.seq} data-state={a.action === "gate.denied" ? "bad" : undefined}>
                  <td className="mono hide-sm">{a.at}</td><td>{a.actor}</td><td className="mono">{a.action}</td>
                  <td className="mono hide-sm">{a.run_id ?? ""}</td><td>{a.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.hasNextPage && <p><button className="btn" type="button" disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Load more</button></p>}
    </>
  );
}
