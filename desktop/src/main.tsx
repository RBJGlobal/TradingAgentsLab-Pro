import React from 'react';
import ReactDOM from 'react-dom/client';
// Bundled variable fonts (offline, no external fetch) so the app renders with
// its intended type on every machine instead of falling back to system faces.
// Inter Variable for body/UI, JetBrains Mono Variable for the display + code
// surfaces. Both are wired into the --tal-font-* tokens.
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';
import App from './App';
import ConsentGate from './components/ConsentGate';
import ErrorBoundary from './components/ErrorBoundary';
import './styles/tokens.css';
import './styles/global.css';

// ConsentGate blocks App from mounting until the educational-use agreement is
// accepted, so none of App's startup effects (engine handshake, etc.) run
// behind the gate. Decline quits the app.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ConsentGate>
        <App />
      </ConsentGate>
    </ErrorBoundary>
  </React.StrictMode>,
);
