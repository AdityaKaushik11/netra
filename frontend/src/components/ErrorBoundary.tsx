import { Component, type ErrorInfo, type ReactNode } from "react";

/** Last line of defence: a render error shows a recoverable message instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid h-full place-items-center p-6">
        <div className="panel max-w-md space-y-3 p-6 text-center">
          <h1 className="text-base font-semibold">Something went wrong in the console</h1>
          <p className="font-mono text-xs break-words text-ink-400">{this.state.error.message}</p>
          <div className="flex justify-center gap-2">
            <button className="btn" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
            <button className="btn btn-primary" onClick={() => location.reload()}>
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
