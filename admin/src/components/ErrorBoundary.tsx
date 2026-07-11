import React from "react";
import { AlertOctagon, RefreshCw } from "lucide-react";

type State = { error: unknown | null; info: string | null };

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(err: unknown): State {
    return { error: err, info: null };
  }

  componentDidCatch(err: unknown, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[admin ErrorBoundary]", err, info?.componentStack);
    this.setState({ error: err, info: info?.componentStack || null });
  }

  reset = () => this.setState({ error: null, info: null });

  render() {
    if (!this.state.error) return this.props.children as any;
    const msg = (this.state.error as any)?.message || String(this.state.error);
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center p-8 gap-4">
        <div className="w-16 h-16 rounded-full bg-red-100 grid place-items-center">
          <AlertOctagon className="w-8 h-8 text-red-600" />
        </div>
        <h2 className="text-xl font-black">Something went wrong on this page</h2>
        <p className="text-sm text-slate-600 max-w-xl text-center">
          The rest of the admin app is still working. Use the sidebar to navigate away
          or reload this page. The error has been logged to the console.
        </p>
        <pre className="max-w-2xl overflow-x-auto text-[11px] bg-slate-50 border border-slate-200 rounded p-3">{msg}</pre>
        <div className="flex gap-2">
          <button onClick={this.reset} className="inline-flex items-center gap-1 px-3 py-2 rounded bg-brand-navy text-white text-sm font-bold">
            <RefreshCw className="w-4 h-4" /> Try again
          </button>
          <button onClick={() => (window.location.hash = "#/")} className="px-3 py-2 rounded bg-slate-200 text-slate-800 text-sm font-bold">Go to Dashboard</button>
        </div>
      </div>
    );
  }
}
