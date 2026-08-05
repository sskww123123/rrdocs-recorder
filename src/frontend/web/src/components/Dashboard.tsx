import { useState, useEffect } from 'react';
import { getMqttClient, sendCommand, TOPIC_STATUS } from '../services/mqttService';

interface AnalysisResults {
  resumen_ejecutivo:     string[];
  conceptos_principales: string[];
  sesgos_cognitivos:     string[];
  tareas_acciones:       string[];
  texto_corregido:       string[];
  sentiment:             number;
  subjectivity:          number;
  total_phrases:         number;
  texto_original:        string;
}

type Tab = 'RESUMEN' | 'CONCEPTOS' | 'SESGOS' | 'TAREAS' | 'TRANSCRIPCIÓN';

export default function Dashboard({ onBack }: { onBack: () => void }) {
  const [tab, setTab]           = useState<Tab>('RESUMEN');
  const [status, setStatus]     = useState<'WAITING' | 'PROCESSING' | 'DONE' | 'ERROR'>('WAITING');
  const [progress, setProgress] = useState<string>('Enviando comando al motor de análisis...');
  const [results, setResults]   = useState<AnalysisResults | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    // 1. Send GENERATE_DOC command to backend
    try {
      sendCommand('GENERATE_DOC');
      setStatus('PROCESSING');
      setProgress('Procesando con Ollama...');
    } catch (e) {
      setErrorMsg('No se pudo conectar al broker MQTT. Verifica que el backend esté corriendo.');
      setStatus('ERROR');
      return;
    }

    // 2. Subscribe to status topic and wait for COMPLETO or ERROR
    const c = getMqttClient();
    c.subscribe(TOPIC_STATUS);

    const handler = (_topic: string, payload: Buffer) => {
      try {
        const data = JSON.parse(payload.toString());
        const estado: string = data.estado ?? '';
        const detalle: string = data.detalle ?? '';

        if (estado === 'PROCESANDO') {
          setProgress(detalle);
        } else if (estado === 'COMPLETO') {
          // detalle contains the JSON analysis result
          try {
            const parsed: AnalysisResults = JSON.parse(detalle);
            setResults(parsed);
            setStatus('DONE');
          } catch {
            setErrorMsg('El motor devolvió un resultado malformado.');
            setStatus('ERROR');
          }
        } else if (estado === 'DOC_GENERADO') {
          // Word doc is ready — just a confirmation, we already have results
          setProgress(detalle);
        } else if (estado === 'ERROR') {
          setErrorMsg(detalle || 'Error desconocido en el backend.');
          setStatus('ERROR');
        }
      } catch { /* ignore malformed packets */ }
    };

    c.on('message', handler);
    return () => { c.off('message', handler); };
  }, []);

  const TABS: Tab[] = ['RESUMEN', 'CONCEPTOS', 'SESGOS', 'TAREAS', 'TRANSCRIPCIÓN'];

  if (status === 'ERROR') {
    return (
      <div className="bucm-card" style={{ maxWidth: '800px', margin: '0 auto', width: '100%' }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--rr-blanco)', cursor: 'pointer', padding: 0, opacity: 0.5, fontSize: '12pt' }}>← VOLVER</button>
        <div style={{ marginTop: '2rem', background: 'rgba(190,7,109,0.1)', border: '1px solid var(--rr-fucsia)', padding: '1.5rem', color: 'var(--rr-fucsia)' }}>
          <strong>ERROR DE ANÁLISIS:</strong> {errorMsg}
        </div>
      </div>
    );
  }

  if (status !== 'DONE') {
    return (
      <div className="bucm-card" style={{ maxWidth: '800px', margin: '0 auto', width: '100%', minHeight: '300px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '2rem' }}>
        <h2 style={{ fontSize: '18pt', fontWeight: 'normal', margin: 0 }} className="mostaza-text">PROCESANDO</h2>
        <p style={{ opacity: 0.6, fontSize: '12pt', margin: 0 }}>{progress}</p>
        <div style={{ width: '100%', height: '2px', background: 'rgba(255,255,243,0.1)', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 0, left: '-50%', width: '50%', height: '100%', background: 'var(--rr-fucsia)', animation: 'slide 1.5s infinite linear' }} />
        </div>
        <style>{`@keyframes slide { from { left: -50%; } to { left: 100%; } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '900px', margin: '0 auto', width: '100%' }}>
      <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--rr-blanco)', cursor: 'pointer', textAlign: 'left', padding: 0, opacity: 0.5, fontSize: '12pt' }}>← VOLVER</button>

      {/* Metrics strip */}
      <div style={{ display: 'flex', gap: '2rem', borderBottom: '1px solid rgba(255,255,243,0.15)', paddingBottom: '1.5rem' }}>
        <div><span style={{ opacity: 0.5, fontSize: '10pt' }}>SENTIMIENTO</span><br/><span style={{ fontSize: '18pt' }} className={results!.sentiment >= 0 ? 'mostaza-text' : 'fucsia-text'}>{results!.sentiment >= 0 ? '+' : ''}{results!.sentiment.toFixed(2)}</span></div>
        <div><span style={{ opacity: 0.5, fontSize: '10pt' }}>SUBJETIVIDAD</span><br/><span style={{ fontSize: '18pt' }}>{(results!.subjectivity * 100).toFixed(0)}%</span></div>
        <div><span style={{ opacity: 0.5, fontSize: '10pt' }}>FRASES</span><br/><span style={{ fontSize: '18pt' }}>{results!.total_phrases}</span></div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: 'none', border: 'none', padding: '0.5rem 0', cursor: 'pointer',
            fontSize: '11pt', fontFamily: 'var(--rr-font-heading)', letterSpacing: '0.05em',
            color: tab === t ? 'var(--rr-fucsia)' : 'var(--rr-blanco)',
            opacity: tab === t ? 1 : 0.4,
            borderBottom: tab === t ? '2px solid var(--rr-fucsia)' : '2px solid transparent',
            transition: 'all 0.15s ease',
          }}>{t}</button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bucm-card">
        {tab === 'RESUMEN' && (
          results!.resumen_ejecutivo.length > 0
            ? <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {results!.resumen_ejecutivo.map((p, i) => (
                  <li key={i} style={{ display: 'flex', gap: '1rem', fontSize: '13pt', lineHeight: 1.5 }}>
                    <span className="fucsia-text" style={{ flexShrink: 0 }}>{String(i + 1).padStart(2, '0')}.</span>
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            : <p style={{ opacity: 0.5 }}>Sin resumen disponible.</p>
        )}
        {tab === 'CONCEPTOS' && (
          results!.conceptos_principales.length > 0
            ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
                {results!.conceptos_principales.map((c, i) => (
                  <span key={i} style={{ border: '1px solid var(--rr-orquidea)', color: 'var(--rr-orquidea)', padding: '0.4rem 1rem', fontSize: '12pt' }}>{c}</span>
                ))}
              </div>
            : <p style={{ opacity: 0.5 }}>Sin conceptos identificados.</p>
        )}
        {tab === 'SESGOS' && (
          results!.sesgos_cognitivos.length > 0
            ? <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {results!.sesgos_cognitivos.map((s, i) => (
                  <li key={i} style={{ display: 'flex', gap: '1rem', fontSize: '13pt' }}>
                    <span className="mostaza-text" style={{ flexShrink: 0 }}>▸</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            : <p style={{ opacity: 0.5 }}>No se detectaron sesgos cognitivos.</p>
        )}
        {tab === 'TAREAS' && (
          results!.tareas_acciones && results!.tareas_acciones.length > 0
            ? <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {results!.tareas_acciones.map((t, i) => (
                  <li key={i} style={{ display: 'flex', gap: '1rem', fontSize: '13pt', borderLeft: '3px solid var(--rr-naranja)', paddingLeft: '1rem' }}>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            : <p style={{ opacity: 0.5 }}>No se detectaron tareas ni acciones.</p>
        )}
        {tab === 'TRANSCRIPCIÓN' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div>
              <h3 style={{ color: 'var(--rr-mostaza-acido)', fontSize: '11pt', letterSpacing: '0.1em', marginTop: 0 }}>VERSIÓN CORREGIDA POR IA</h3>
              {results!.texto_corregido && results!.texto_corregido.length > 0 ? (
                results!.texto_corregido.map((p, i) => (
                  <p key={i} style={{ fontSize: '12pt', lineHeight: 1.7, opacity: 0.9, margin: '0 0 1rem 0' }}>{p}</p>
                ))
              ) : <p style={{ opacity: 0.5 }}>No hay corrección disponible.</p>}
            </div>
            <div style={{ borderTop: '1px solid rgba(255,255,243,0.1)', paddingTop: '1.5rem' }}>
              <h3 style={{ color: 'var(--rr-blanco)', opacity: 0.5, fontSize: '10pt', letterSpacing: '0.1em', marginTop: 0 }}>TRANSCRIPCIÓN CRUDA (WHISPER)</h3>
              <p style={{ fontSize: '11pt', lineHeight: 1.7, opacity: 0.4, whiteSpace: 'pre-wrap', margin: 0 }}>
                {results!.texto_original || 'Sin transcripción.'}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
