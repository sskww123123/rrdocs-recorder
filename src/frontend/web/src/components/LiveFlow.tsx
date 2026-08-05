import { useState, useEffect, useRef } from 'react';

export default function LiveFlow({ onFinish, onBack }: { onFinish: () => void, onBack: () => void }) {
  const [step, setStep] = useState<'VERIFY' | 'RECORD' | 'REVIEW'>('VERIFY');
  const [isRecording, setIsRecording] = useState(false);
  const [time, setTime] = useState(0);
  const [transcript, setTranscript] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  // Refs for audio context and recognition
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const animationFrameRef = useRef<number>();
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    if (step === 'VERIFY') {
      const timer = setTimeout(() => setStep('RECORD'), 1000);
      return () => clearTimeout(timer);
    }
    
    let interval: any;
    if (step === 'RECORD' && isRecording) {
      interval = setInterval(() => setTime(t => t + 1), 1000);
    }
    return () => clearInterval(interval);
  }, [step, isRecording]);

  // Text Sanitization (Spanish only)
  const sanitizeText = (text: string) => {
    // Keep only alphanumeric characters and basic Spanish punctuation
    const pattern = /[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s.,!?]/g;
    let sanitized = text.replace(pattern, "");
    // Collapse multiple spaces
    return sanitized.replace(/\s+/g, " ").trim();
  };

  useEffect(() => {
    if (isRecording) {
      setErrorMsg(null);
      navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        const analyser = audioCtx.createAnalyser();
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        analyser.fftSize = 2048;
        
        audioContextRef.current = audioCtx;
        analyserRef.current = analyser;
        sourceRef.current = source;
        
        drawWaveform();

        // Live transcript comes from the backend Whisper engine via MQTT.
        // The Web Speech API is NOT used because it requires Google's servers (network error).
        // Instead, the backend streams recognized text chunks to the rrdocs/transcript topic.
        setTranscript(""); // clear previous
        setErrorMsg(null);

        try {
          // Try to connect to the MQTT broker over WebSocket (backend must have WS port open, default 9001)
          const mqttClient = (window as any).mqtt?.connect?.('ws://localhost:9001', { clientId: 'rrdocs-web-' + Date.now() });

          if (mqttClient) {
            mqttClient.on('connect', () => {
              mqttClient.subscribe('rrdocs/transcript');
            });

            mqttClient.on('message', (_topic: string, payload: Buffer) => {
              try {
                const data = JSON.parse(payload.toString());
                const chunk: string = data.detalle ?? data.text ?? '';
                if (chunk) {
                  const clean = sanitizeText(chunk);
                  setTranscript(prev => {
                    const combined = prev + (prev ? ' ' : '') + clean;
                    return combined.length > 300 ? '...' + combined.slice(-300) : combined;
                  });
                }
              } catch (_) { /* ignore malformed packets */ }
            });

            mqttClient.on('error', () => {
              // MQTT not available — show an informational message, waveform still works
              setTranscript("Transcripción en tiempo real no disponible. El audio se procesará con Whisper al detener.");
            });

            recognitionRef.current = { mqttClient };
          } else {
            // mqtt.js library not loaded in browser — graceful info message
            setTranscript("Grabando audio. La transcripción completa estará disponible al finalizar la sesión.");
          }
        } catch (_) {
          setTranscript("Grabando audio. La transcripción completa estará disponible al finalizar la sesión.");
        }
      }).catch(err => {
        console.error("Microphone error:", err);
        setErrorMsg(`Acceso al micrófono denegado o dispositivo no encontrado. (${err.message})`);
        setIsRecording(false);
      });
    } else {
      // Cleanup
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      if (sourceRef.current) sourceRef.current.disconnect();
      if (audioContextRef.current) audioContextRef.current.close();
      if (recognitionRef.current) {
        if (recognitionRef.current.stop) recognitionRef.current.stop();
      }
    }
    
    return () => {
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      if (recognitionRef.current && recognitionRef.current.stop) recognitionRef.current.stop();
    };
  }, [isRecording]);

  const drawWaveform = () => {
    if (!canvasRef.current || !analyserRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const analyser = analyserRef.current;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animationFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(dataArray);

      ctx.fillStyle = '#070001'; 
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 1.5;
      ctx.strokeStyle = '#be076d'; 
      ctx.beginPath();

      const sliceWidth = canvas.width * 1.0 / bufferLength;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = v * (canvas.height / 2);

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
        x += sliceWidth;
      }
      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };
    draw();
  };

  return (
    <div className="bucm-card" style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--rr-blanco)', cursor: 'pointer', textAlign: 'left', padding: 0, opacity: 0.5, fontSize: '12pt' }}>← VOLVER</button>
      
      {errorMsg && (
        <div style={{ background: 'rgba(190, 7, 109, 0.1)', border: '1px solid var(--rr-fucsia)', padding: '1rem', color: 'var(--rr-fucsia)' }}>
          <strong>ERROR DE SISTEMA:</strong> {errorMsg}
        </div>
      )}

      {step === 'VERIFY' && (
        <div>
          <h2 style={{ fontSize: '20pt', fontWeight: 'normal', opacity: 0.8 }}>VERIFICANDO SISTEMA...</h2>
        </div>
      )}

      {step === 'RECORD' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
             <h2 style={{ margin: 0, fontSize: '20pt', fontWeight: 'normal' }}>CAPTURA EN VIVO</h2>
             <div style={{ fontSize: '20pt', fontFamily: 'var(--rr-font-heading)', color: 'var(--rr-blanco)', opacity: 0.8 }}>
               {isRecording ? <span className="fucsia-text" style={{marginRight: '1rem'}}>REC</span> : <span style={{opacity: 0.5, marginRight: '1rem'}}>STANDBY</span>}
               {Math.floor(time / 60).toString().padStart(2, '0')}:{(time % 60).toString().padStart(2, '0')}
             </div>
          </div>
          
          <div style={{ 
            minHeight: '100px', 
            padding: '1.5rem',
            margin: '2rem 0',
            border: '1px solid rgba(255, 255, 243, 0.1)',
            color: 'var(--rr-blanco)',
            fontSize: '14pt',
            fontFamily: 'var(--rr-font-body)',
            lineHeight: '1.6',
            opacity: 0.8
          }}>
            {transcript || (isRecording ? "Escuchando..." : "Presione INICIAR para capturar.")}
          </div>

          <div style={{ height: '60px', margin: '1rem 0', position: 'relative' }}>
            <canvas 
              ref={canvasRef} 
              width={800} 
              height={60} 
              style={{ width: '100%', height: '100%', display: isRecording ? 'block' : 'none', border: '1px solid rgba(255, 255, 243, 0.1)' }} 
            />
            {!isRecording && (
               <div style={{ width: '100%', height: '100%', border: '1px solid rgba(255, 255, 243, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.3 }}>
                 <span style={{ fontSize: '10pt', letterSpacing: '0.1em' }}>WAVEFORM OFFLINE</span>
               </div>
            )}
          </div>
          
          <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
            <button className="bucm-btn" style={{ fontSize: '12pt', padding: '0.75rem 1.5rem' }} onClick={() => setIsRecording(!isRecording)}>
              {isRecording ? 'PAUSAR' : 'INICIAR GRABACIÓN'}
            </button>
            <button className="bucm-btn secondary" style={{ fontSize: '12pt', padding: '0.75rem 1.5rem' }} onClick={() => { setIsRecording(false); setStep('REVIEW'); }}>
              DETENER & REVISAR
            </button>
          </div>
        </div>
      )}

      {step === 'REVIEW' && (
        <div>
          <h2 style={{ fontSize: '20pt', fontWeight: 'normal' }}>REVISIÓN DE ANÁLISIS</h2>
          <p style={{ opacity: 0.6, fontSize: '12pt' }}>Audio capturado exitosamente. Seleccione la profundidad de análisis.</p>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
            <button className="bucm-btn" style={{ fontSize: '12pt' }} onClick={onFinish}>INICIAR INFERENCIA</button>
          </div>
        </div>
      )}
    </div>
  );
}
