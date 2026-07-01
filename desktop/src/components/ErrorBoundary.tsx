import React from 'react';

/**
 * App-wide error boundary.
 *
 * Without this, any exception thrown during render unmounts the entire React
 * tree and the window goes blank with no recovery path (the class of bug seen
 * with the dev-mode "Settings goes blank" report). This catches render-phase
 * throws below it and shows a recoverable fallback with a Reload button
 * instead of a dead window.
 *
 * Styles are inline on purpose: if a stylesheet failed to load, a fallback
 * that depends on CSS classes could itself render blank. The palette mirrors
 * the app theme (dark base + warm amber accent) so it still feels in-product.
 */

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Local-only log for diagnosis (no remote reporting — zero data
    // collection posture). Surfaces in the DevTools console + the Electron
    // renderer log.
    console.error('[ErrorBoundary] render error:', error, info.componentStack);
  }

  private handleReload = (): void => {
    // Full reload rebuilds the renderer from a clean slate. window.location
    // works in both the Vite dev server and the packaged file:// renderer.
    window.location.reload();
  };

  render(): React.ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    return (
      <div
        role="alert"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 18,
          padding: 40,
          background: '#0d1117',
          color: '#e6edf3',
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, monospace',
            fontSize: 12,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: '#f0a830',
          }}
        >
          Something went wrong
        </div>
        <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>
          The view hit an unexpected error
        </h1>
        <p style={{ maxWidth: 460, fontSize: 14, lineHeight: 1.6, color: '#9da7b3', margin: 0 }}>
          Your data and settings are safe. Reload to get back to a working
          screen. If it keeps happening on the same page, note what you were
          doing so it can be reproduced.
        </p>
        <button
          type="button"
          onClick={this.handleReload}
          style={{
            marginTop: 6,
            padding: '9px 20px',
            background: '#f0a830',
            color: '#0d1117',
            border: 'none',
            borderRadius: 6,
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Reload
        </button>
        <pre
          style={{
            marginTop: 14,
            maxWidth: 560,
            maxHeight: 160,
            overflow: 'auto',
            padding: '10px 14px',
            background: '#161b22',
            border: '1px solid #30363d',
            borderRadius: 6,
            fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, monospace',
            fontSize: 11,
            lineHeight: 1.5,
            color: '#9da7b3',
            textAlign: 'left',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {error.name}: {error.message}
        </pre>
      </div>
    );
  }
}
