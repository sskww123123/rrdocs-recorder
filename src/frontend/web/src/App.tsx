import { useState } from 'react';
import './index.css';
import LiveFlow from './components/LiveFlow';
import ImportFlow from './components/ImportFlow';
import Dashboard from './components/Dashboard';
import { sendCommand } from './services/mqttService';

function App() {
  const [view, setView] = useState<'WELCOME' | 'HOME' | 'LIVE_FLOW' | 'IMPORT_FLOW' | 'DASHBOARD'>('WELCOME');
  const [device, setDevice] = useState<'cpu' | 'cuda'>('cpu');

  const toggleDevice = (next: 'cpu' | 'cuda') => {
    setDevice(next);
    const compute_type = next === 'cuda' ? 'float16' : 'int8';
    sendCommand('SET_DEVICE', { device: next, compute_type });
  };

  return (
    <div className="bucm-container">
      {view !== 'WELCOME' && (
        <header style={{ borderBottom: '1px solid rgba(255, 255, 243, 0.15)', paddingBottom: '1.5rem', marginBottom: '4rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 style={{ margin: 0, fontSize: '20pt', fontWeight: '500', letterSpacing: '0.05em' }}>RR ALIADOS <span className="fucsia-text" style={{ margin: '0 0.5rem' }}>//</span> TERMINAL</h1>
          <div style={{ color: 'var(--rr-blanco)', fontFamily: 'var(--rr-font-heading)', fontSize: '10pt', opacity: 0.4 }}>STATUS: ONLINE</div>
        </header>
      )}

      {view === 'WELCOME' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
          <h1 style={{ fontSize: '7vw', margin: 0, lineHeight: 1 }}>RR ALIADOS</h1>
          <h2 style={{ fontSize: '2vw', color: 'var(--rr-blanco)', opacity: 0.5, fontWeight: 'normal', letterSpacing: '0.2em', marginTop: '1rem' }}>GROWTH PARTNER OS</h2>
          <button 
            className="bucm-btn" 
            style={{ marginTop: '5rem', padding: '1rem 3rem', fontSize: '14pt' }}
            onClick={() => setView('HOME')}
          >
            INGRESAR
          </button>
        </div>
      )}

      {view === 'HOME' && (
        <div className="bucm-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', alignItems: 'flex-start', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
          <h2 style={{ fontSize: '28pt', margin: 0, fontWeight: 'normal' }}>VECTOR DE DESPLIEGUE</h2>
          <p style={{ fontSize: '14pt', margin: 0, opacity: 0.6, lineHeight: 1.5 }}>
            Inicialice Growth Partner OS. Seleccione su modalidad de entrada para análisis multicapa.
          </p>

          {/* Device toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '0.5rem' }}>
            <span style={{ fontSize: '10pt', opacity: 0.4, letterSpacing: '0.1em' }}>MOTOR WHISPER</span>
            <div style={{ display: 'flex', border: '1px solid rgba(255,255,243,0.2)', overflow: 'hidden' }}>
              {(['cpu', 'cuda'] as const).map(d => (
                <button key={d} onClick={() => toggleDevice(d)} style={{
                  background: device === d ? 'var(--rr-fucsia)' : 'transparent',
                  color: 'var(--rr-blanco)',
                  border: 'none',
                  padding: '0.35rem 1rem',
                  cursor: 'pointer',
                  fontSize: '11pt',
                  fontFamily: 'var(--rr-font-heading)',
                  opacity: device === d ? 1 : 0.4,
                  transition: 'all 0.2s',
                }}>{d.toUpperCase()} {d === 'cuda' ? '(GPU)' : ''}</button>
              ))}
            </div>
            {device === 'cuda' && <span style={{ fontSize: '10pt', color: 'var(--rr-mostaza-acido)' }}>RTX 3050 Ti — float16</span>}
          </div>

          <div style={{ display: 'flex', gap: '1.5rem', marginTop: '1rem', width: '100%' }}>
            <button className="bucm-btn" style={{ flex: 1, fontSize: '14pt', padding: '1rem' }} onClick={() => setView('LIVE_FLOW')}>
              [1] CAPTURA EN VIVO
            </button>
            <button className="bucm-btn secondary" style={{ flex: 1, fontSize: '14pt', padding: '1rem' }} onClick={() => setView('IMPORT_FLOW')}>
              [2] IMPORTAR ARCHIVO
            </button>
          </div>
        </div>
      )}

      {view === 'LIVE_FLOW' && (
        <LiveFlow onFinish={() => setView('DASHBOARD')} onBack={() => setView('HOME')} />
      )}

      {view === 'IMPORT_FLOW' && (
        <ImportFlow onFinish={() => setView('DASHBOARD')} onBack={() => setView('HOME')} />
      )}

      {view === 'DASHBOARD' && (
        <Dashboard onBack={() => setView('HOME')} />
      )}
    </div>
  );
}

export default App;
