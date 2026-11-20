import { useEffect, useState } from "react";

const BASE = "/app";

export function useRoute(): [string[], (to: string) => void] {
  const read = () =>
    window.location.pathname.slice(BASE.length).split("/").filter(Boolean).map(decodeURIComponent);
  const [parts, setParts] = useState<string[]>(read);
  useEffect(() => {
    const on = () => setParts(read());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  const go = (to: string) => {
    window.history.pushState({}, "", BASE + to);
    setParts(read());
  };
  return [parts, go];
}
