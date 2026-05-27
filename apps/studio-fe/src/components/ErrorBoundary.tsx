import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("[ErrorBoundary] Uncaught error:", error, info.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-neutral-950 text-neutral-300">
          <AlertTriangle size={40} className="text-amber-400" />
          <h1 className="text-lg font-semibold text-neutral-100">
            Something went wrong
          </h1>
          {this.state.error && (
            <p className="max-w-sm text-center text-sm text-neutral-500">
              {this.state.error.message}
            </p>
          )}
          <button
            onClick={this.handleReload}
            className="mt-2 flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500"
          >
            <RefreshCw size={14} />
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
