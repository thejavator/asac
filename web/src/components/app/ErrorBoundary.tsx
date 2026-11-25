import { Component, type ReactNode } from "react";
import { ErrorAlert } from "./Page";

/** Keeps the shell usable when one page throws while rendering. Reset by changing `resetKey` (the route). */
export class PageErrorBoundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }
  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-3xl">
          <ErrorAlert title="This page could not be displayed">
            {this.state.error.message}. Other pages still work: use the navigation on the left.
          </ErrorAlert>
        </div>
      );
    }
    return this.props.children;
  }
}
