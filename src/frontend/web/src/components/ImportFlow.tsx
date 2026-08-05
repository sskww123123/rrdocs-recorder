import { useState, useRef, useCallback } from 'react';
import { getMqttClient, TOPIC_STATUS } from '../services/mqttService';

const ALLOWED_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.txt', '.pdf', '.md'];
const MAX_SIZE_MB = 500;
const UPLOAD_URL = 'http://localhost:8765/upload';

interface FileInfo { name: string; size: string; type: string; raw: File; }

export default function ImportFlow({ onFinish, onBack }: { onFinish: () => void, onBack: () => void }) {
  const [fileInfo, setFileInfo]       = useState<FileInfo | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isDragOver, setIsDragOver]   = useState(false);
  const [errorMsg, setErrorMsg]       = useState<string | null>(null);
  const [preset, setPreset]           = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<'IDLE' | 'UPLOADING' | 'TRANSCRIBING'>('IDLE');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fmt = (b: number) => b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;

  const validateAndSetFile = useCallback((file: File) => {
    setErrorMsg(null);
    setIsValidating(true);
    setTimeout(() => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setErrorMsg(`Formato no soportado: "${ext}". Usa: ${ALLOWED_EXTENSIONS.join(', ')}`);
        setIsValidating(false); return;
      }
      if (file.size / 1048576 > MAX_SIZE_MB) {
        setErrorMsg(`Archivo demasiado grande. Límite: ${MAX_SIZE_MB}MB`);
        setIsValidating(false); return;
      }
      if (file.size === 0) {
        setErrorMsg("El archivo está vacío o corrupto.");
        setIsValidating(false); return;
      }
      setFileInfo({ name: file.name, size: fmt(file.size), type: ext.toUpperCase().replace('.',''), raw: file });
      setIsValidating(false);
    }, 600);
  }, []);

  const onDragOver  = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragOver(true); }, []);
  const onDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragOver(false); }, []);
  const onDrop      = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragOver(false);
    const f = e.dataTransfer.files[0]; if (f) validateAndSetFile(f);
  }, [validateAndSetFile]);
  const onPick = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (f) validateAndSetFile(f);
  }, [validateAndSetFile]);

  const reset = () => { setFileInfo(null); setErrorMsg(null); setPreset(null); setUploadState('IDLE'); if (fileInputRef.current) fileInputRef.current.value = ''; };

  const handleSubmit = async () => {
    if (!fileInfo) return;
    setErrorMsg(null);
    setUploadState('UPLOADING');

    // 1. POST file to backend HTTP server
    const form = new FormData();
    form.append('file', fileInfo.raw, fileInfo.raw.name);
    try {
      const res = await fetch(UPLOAD_URL, { method: 'POST', body: form });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e: any) {
      setErrorMsg(`No se pudo conectar al backend (${e.message}). ¿Está corriendo el backend?`);
      setUploadState('IDLE'); return;
    }

    // 2. Wait for MQTT REPOSO signal (means transcription is done)
    setUploadState('TRANSCRIBING');
    const c = getMqttClient();
    c.subscribe(TOPIC_STATUS);
    const handler = (_topic: string, payload: Buffer) => {
      try {
        const data = JSON.parse(payload.toString());
        if (data.estado === 'REPOSO') {
          c.off('message', handler);
          onFinish(); // navigate to Dashboard which will send GENERATE_DOC
        } else if (data.estado === 'ERROR') {
          c.off('message', handler);
          setErrorMsg(`Error del backend: ${data.detalle}`);
          setUploadState('IDLE');
        }
      } catch { /* ignore */ }
    };
    c.on('message', handler);
  };

  return (
    <div className="bucm-card" style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--rr-blanco)', cursor: 'pointer', textAlign: 'left', padding: 0, opacity: 0.5, fontSize: '12pt' }}>← VOLVER</button>
      <h2 style={{ fontSize: '20pt', fontWeight: 'normal', margin: 0 }}>IMPORTAR ARCHIVO</h2>

      {errorMsg && (
        <div style={{ background: 'rgba(190,7,109,0.1)', border: '1px solid var(--rr-fucsia)', padding: '1rem', color: 'var(--rr-fucsia)', fontSize: '12pt' }}>
          <strong>ERROR:</strong> {errorMsg}
          <button onClick={reset} style={{ marginLeft: '1rem', background: 'none', border: '1px solid var(--rr-fucsia)', color: 'var(--rr-fucsia)', cursor: 'pointer', padding: '0.25rem 0.75rem' }}>REINTENTAR</button>
        </div>
      )}

      {!fileInfo && !isValidating && (
        <>
          <input ref={fileInputRef} type="file" accept=".mp3,.wav,.m4a,.txt,.pdf,.md" style={{ display: 'none' }} onChange={onPick} />
          <div
            onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{ border: `1px dashed ${isDragOver ? 'var(--rr-fucsia)' : 'rgba(255,255,243,0.3)'}`, padding: '4rem 2rem', textAlign: 'center', cursor: 'pointer', background: isDragOver ? 'rgba(190,7,109,0.05)' : 'transparent', transition: 'all 0.2s' }}
          >
            <p style={{ fontSize: '14pt', margin: 0, opacity: isDragOver ? 1 : 0.6 }}>{isDragOver ? 'SOLTAR ARCHIVO AQUÍ' : 'Arrastra un archivo o haz clic para seleccionar'}</p>
            <p style={{ fontSize: '10pt', margin: '1rem 0 0 0', opacity: 0.4 }}>MP3 / WAV / M4A / TXT / PDF / MD — máx {MAX_SIZE_MB}MB</p>
          </div>
        </>
      )}

      {isValidating && <p style={{ opacity: 0.6, fontSize: '12pt' }}>Validando archivo...</p>}

      {fileInfo && uploadState === 'IDLE' && (
        <div>
          <div style={{ border: '1px solid rgba(255,255,243,0.15)', padding: '1rem', marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="fucsia-text" style={{ fontWeight: 'bold', marginRight: '1rem' }}>{fileInfo.type}</span>
              <span style={{ fontSize: '12pt' }}>{fileInfo.name}</span>
            </div>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <span style={{ opacity: 0.5, fontSize: '11pt' }}>{fileInfo.size}</span>
              <button onClick={reset} style={{ background: 'none', border: 'none', color: 'var(--rr-blanco)', cursor: 'pointer', opacity: 0.4, fontSize: '14pt' }}>✕</button>
            </div>
          </div>
          <p style={{ fontSize: '11pt', opacity: 0.5, margin: '0 0 1rem 0' }}>PREAJUSTE DE ANÁLISIS</p>
          <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
            {['EJECUTIVO', 'LEGAL', 'CRÍTICA PROFUNDA'].map(p => (
              <button key={p} className="bucm-btn secondary" onClick={() => setPreset(p)}
                style={{ fontSize: '11pt', padding: '0.5rem 1rem', background: preset === p ? 'var(--rr-fucsia)' : 'transparent', border: preset === p ? '1px solid var(--rr-fucsia)' : '1px solid rgba(255,255,243,0.3)' }}>
                {p}
              </button>
            ))}
          </div>
          <button className="bucm-btn" style={{ fontSize: '12pt', padding: '0.75rem 1.5rem' }} onClick={handleSubmit}>
            INICIAR PIPELINE
          </button>
        </div>
      )}

      {(uploadState === 'UPLOADING' || uploadState === 'TRANSCRIBING') && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <p style={{ fontSize: '13pt', margin: 0, opacity: 0.8 }}>
            {uploadState === 'UPLOADING' ? 'Enviando archivo al backend...' : 'Transcribiendo con Whisper local...'}
          </p>
          <div style={{ width: '100%', height: '2px', background: 'rgba(255,255,243,0.1)', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: 0, left: '-50%', width: '50%', height: '100%', background: 'var(--rr-fucsia)', animation: 'slide 1.5s infinite linear' }} />
          </div>
          <style>{`@keyframes slide { from { left: -50%; } to { left: 100%; } }`}</style>
        </div>
      )}
    </div>
  );
}
