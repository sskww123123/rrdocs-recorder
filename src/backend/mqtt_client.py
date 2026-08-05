"""
mqtt_client.py
BackendController – RRDOCS persistent-buffer recording orchestrator.

State machine
-------------
  STANDBY  ──[START_RECORDING]──► RUNNING   (mic loop active, buffer grows)
  RUNNING  ──[PAUSE_RECORDING]──► REPOSO    (mic stops, buffer preserved)
  REPOSO   ──[START_RECORDING]──► RUNNING   (mic resumes, same buffer)
  RUNNING  ──[CANCEL]──────────► REPOSO    (mic stops, buffer cleared)
  REPOSO   ──[CANCEL]──────────► REPOSO    (buffer cleared in place)
  REPOSO   ──[GENERATE_DOC]───► PROCESANDO ► COMPLETO ► DOC_GENERADO
"""

import json
import queue
import threading
import os
import sys
import types
import tempfile
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

import paho.mqtt.client as paho

from src.backend.services.analyzer import MeetingAnalyzer
from src.backend.services.audio_recorder import MicRecorder
from src.backend.services.documenter import MeetingDocumenter

# ---------------------------------------------------------------------------
# cgi shim – keeps googletrans happy on Python 3.11+ where cgi was removed
# ---------------------------------------------------------------------------
if "cgi" not in sys.modules:
    _cgi = types.ModuleType("cgi")

    def _parse_header(line):
        parts = [p.strip() for p in line.split(";")]
        key = parts[0]
        pdict = {}
        for part in parts[1:]:
            if "=" in part:
                name, value = part.split("=", 1)
                pdict[name.strip().lower()] = value.strip().strip('"')
        return key, pdict

    _cgi.parse_header = _parse_header #type: ignore
    sys.modules["cgi"] = _cgi


# ---------------------------------------------------------------------------
# HTTP Upload Handler (port 8765) – receives imported audio files from the
# web UI, saves them to a temp file, and triggers Whisper transcription.
# ---------------------------------------------------------------------------

class _UploadHandler(BaseHTTPRequestHandler):
    controller = None  # set by BackendController.start()

    def do_OPTIONS(self):
        """Handle CORS preflight from the browser."""
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/upload":
            self.send_response(404)
            self.end_headers()
            return

        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Parse multipart boundary
        boundary_match = re.search(r"boundary=(.+)", content_type)
        if not boundary_match:
            self._respond(400, "No boundary found")
            return

        boundary = boundary_match.group(1).strip().encode()
        file_data = None
        original_filename = "upload.m4a"

        for part in body.split(b"--" + boundary):
            if b"Content-Disposition" not in part:
                continue
            # Extract filename
            fn_match = re.search(rb'filename="([^"]+)"', part)
            if fn_match:
                original_filename = fn_match.group(1).decode(errors="replace")
            # File bytes are after the double CRLF
            header_end = part.find(b"\r\n\r\n")
            if header_end != -1 and b"filename" in part:
                file_data = part[header_end + 4:].rstrip(b"\r\n")
                break

        if not file_data:
            self._respond(400, "No file data found")
            return

        ext = os.path.splitext(original_filename)[1] or ".m4a"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        # Transcribe in a background thread (non-blocking)
        threading.Thread(
            target=self.controller._transcribe_file,
            args=(tmp_path, ext),
            daemon=True,
            name="file-transcriber",
        ).start()

        self._respond(200, "OK")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond(self, code: int, msg: str):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode())

    def log_message(self, *_):
        pass  # silence HTTP request logs


# ---------------------------------------------------------------------------
# BackendController
# ---------------------------------------------------------------------------


    """Orchestrates MQTT communication, audio capture, analysis, and doc export.

    Public recording buffer
    -----------------------
    ``self.recording_buffer`` accumulates all transcribed text chunks during a
    session.  It is preserved across PAUSE/RESUME cycles and only cleared on
    an explicit CANCEL command.  When GENERATE_DOC is received the full buffer
    is joined with a single space and sent to the analyzer + documenter.
    """
class BackendController:
    def __init__(self):
        # --- AQUÍ VA EL BLOQUE QUE CORREGIMOS ---
        def get_config_path():
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                base_path = os.path.abspath(os.path.join(script_dir, '..', '..'))
            return os.path.join(base_path, 'config.json')

        
        config_path = get_config_path()
        #BLOQUE DIAGNOSTICO
        if not os.path.exists(config_path):
            print(f"\n[ERROR DE RUTA] No encuentro el archivo de configuración.")
            print(f"El programa intentó buscar aquí: {config_path}")
            print(f"¿Existe realmente el archivo en esa ruta? Verifica los archivos en esa carpeta.")
            input("Presiona Enter para cerrar...")
            sys.exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        # ── Persistent recording buffer ──────────────────────────────────────
        self.recording_buffer: list[str] = []
        self.recording_buffer.clear()
        self._buffer_lock = threading.Lock()
        # ── State ────────────────────────────────────────────────────────────
        self._estado = "STANDBY"

        # ── MQTT ─────────────────────────────────────────────────────────────
        self._cmd_queue: queue.Queue = queue.Queue()
        # Ajuste de robustez: protocolo especificado explícitamente
        self.client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2, #type: ignore
            protocol=paho.MQTTv5  # O MQTTv311 si tu broker es antiguo
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.enable_logger()
        # ── Services ─────────────────────────────────────────────────────────
        self.recorder   = MicRecorder()
        self.analyzer   = MeetingAnalyzer()
        self.documenter = MeetingDocumenter()

        # ── Recording thread handle ──────────────────────────────────────────
        self._rec_thread: threading.Thread | None = None

    # ── MQTT callbacks ───────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._log("¡CONEXIÓN EXITOSA AL BROKER!")
            self.client.subscribe("rrdocs/reunion/comandos") # Asegúrate de que esto exista
        else:
            self._log(f"FALLO DE CONEXIÓN. Código de error: {rc}")
            # rc=1: Versión de protocolo incorrecta
            # rc=2: Identificador de cliente rechazado
            # rc=3: Servidor no disponible
            # rc=4: Usuario/Contraseña incorrectos
            # rc=5: No autorizado
            
    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            self._cmd_queue.put(data)
        except Exception as exc:
            self._log(f"ERROR parsing command: {exc}")

    # ── Transport helpers ─────────────────────────────────────────────────────

    def _log(self, msg: str):
        """Imprime en la terminal y transmite el log a la consola de la UI."""
        print(f"[Backend] {msg}")
        
        # Si el cliente MQTT ya está conectado, transmitimos el log a la UI
        if hasattr(self, 'client') and self.client:
            payload = {
                "estado": "",  # Lo dejamos vacío para no dañar los colores de la UI
                "detalle": f"[SYS] {msg}"
            }
            try:
                self.client.publish(
                    self.config["mqtt"]["topic_status"], 
                    json.dumps(payload, ensure_ascii=False)
                )
            except Exception:
                pass

    def _word_count(self) -> int:
        with self._buffer_lock:
            return len(" ".join(self.recording_buffer).split()) if self.recording_buffer else 0

    def enviar_estado(self, estado: str, detalle: str, **extra):
        """Publishes a JSON status packet to the MQTT status topic.

        Args:
            estado:  State code string (RUNNING, REPOSO, COMPLETO, …).
            detalle: Human-readable description or embedded JSON payload.
            **extra: Optional extra fields merged into the packet
                     (e.g. ``word_count=42``).
        """
        packet = {"estado": estado, "detalle": detalle}
        packet.update(extra)
        self.client.publish(
            self.config["mqtt"]["topic_status"],
            json.dumps(packet, ensure_ascii=False),
        )
        self._log(f"[{estado}] {detalle[:120]}")

    # ── MQTT transport lifecycle ──────────────────────────────────────────────

    def start(self):
        """Connects to the broker, starts MQTT loop, and starts HTTP upload server."""
        broker = "127.0.0.1"
        port   = 1883
        try:
            self.client.connect(broker, port, 60)
            self.client.loop_start()
            self._log(f"Connected to LOCAL broker {broker}:{port}")
        except Exception as e:
            print(f"[DEBUG] ERROR EN START: {e}")

        # Start HTTP file upload server on port 8765
        _UploadHandler.controller = self
        http_server = HTTPServer(("127.0.0.1", 8765), _UploadHandler)
        threading.Thread(target=http_server.serve_forever, daemon=True, name="upload-server").start()
        self._log("Upload server listening on http://127.0.0.1:8765")
    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        self._log("Disconnected from broker.")

    # ── Recording control ─────────────────────────────────────────────────────

    def _start_recording(self):
        """Launches the recording background thread."""
        if self._rec_thread and self._rec_thread.is_alive():
            self._log("Recording already active – ignoring START_RECORDING.")
            return
        
        self._log("Debug: Llamando a self.recorder.start()...")
        self.recorder.start()
        
        self._log("Debug: Lanzando hilo de grabación...")
        self._rec_thread = threading.Thread(
            target=self._recording_loop, daemon=True, name="rec-loop"
        )
        self._rec_thread.start()

    def _recording_loop(self):
        """Background thread: drives record_chunks() and appends to buffer."""
        self._estado = "RUNNING"
        self._log("Debug: Entrando al bucle de grabación...") # <-- NUEVO LOG
        
        # Obtenemos el generador
        chunks = self.recorder.record_chunks()
        
        try:
            # Iteramos
            for chunk_text in chunks:
                self._log(f"Debug: ¡Fragmento recibido!: {chunk_text}") # <-- NUEVO LOG
                if chunk_text:
                    with self._buffer_lock:
                        self.recording_buffer.append(chunk_text)
                    
                    wc = self._word_count()
                    self.enviar_estado("RUNNING", chunk_text, word_count=wc)

        except Exception as exc: # Cambiado de RuntimeError a Exception para atrapar todo
            self._log(f"Fatal recording error: {exc}")
            self.enviar_estado("ERROR", str(exc), word_count=self._word_count())
        finally:
            self._estado = "REPOSO"
            with self._buffer_lock:
                actual_len = len(self.recording_buffer)
            wc = self._word_count()
            self.enviar_estado(
                "REPOSO",
                f"Grabacion pausada. Buffer: {actual_len} segmentos / {wc} palabras.",
                word_count=wc,
            )
            self._log("Recording thread exited -> REPOSO.")

    def _pause_recording(self):
        """Signals the recording generator to stop; buffer is preserved."""
        if self._rec_thread and self._rec_thread.is_alive():
            self._log("PAUSE_RECORDING signal sent to recorder.")
            # Avisamos a la interfaz que se está vaciando la cola ANTES de detener
            wc = self._word_count()
            self.enviar_estado(
                "PROCESANDO",
                "Drenando audios pendientes en cola...",
                word_count=wc,
            )
            self.recorder.stop()
        else:
            self._log("PAUSE_RECORDING received but no active recording.")
            wc = self._word_count()
            self.enviar_estado(
                "REPOSO",
                f"Sin grabacion activa. Buffer: {wc} palabras.",
                word_count=wc,
            )

    def _cancel_recording(self):
        """Stops recording AND clears the entire buffer, resets to REPOSO."""
        self.recorder.stop()                
        with self._buffer_lock:  # <── AÑADE EL LOCK AQUÍ
            self.recording_buffer.clear()
        self._estado = "REPOSO"
        self.enviar_estado(
            "REPOSO",
            "Grabacion cancelada. Buffer limpiado.",
            word_count=0,
        )
        self._log("CANCELLED: buffer cleared.")

    # ── File import transcription ─────────────────────────────────────────────

    def _transcribe_file(self, tmp_path: str, original_ext: str):
        """Transcribes an imported audio file with Whisper, loads result into buffer."""
        self.enviar_estado("PROCESANDO", "Transcribiendo archivo con Whisper local...")
        
        fallback_done = False
        while True:
            try:
                segments, _ = self.recorder.model.transcribe(
                    tmp_path,
                    language="es",
                    beam_size=5,
                    temperature=0.0,
                    no_speech_threshold=0.6,
                    vad_filter=True,
                )
                raw_text = " ".join(seg.text for seg in segments).strip()
                if not raw_text:
                    self.enviar_estado("ERROR", "No se detectó habla en el archivo importado.")
                    break
                
                clean = self.recorder.sanitize_text(raw_text)
                with self._buffer_lock:
                    self.recording_buffer.clear()
                    self.recording_buffer.append(clean)
                wc = self._word_count()
                
                self.enviar_estado(
                    "REPOSO",
                    f"Archivo transcrito en {self.recorder._device.upper()}. {wc} palabras listas para análisis.",
                    word_count=wc,
                )
                self._log(f"File transcription complete: {wc} words in buffer.")
                break
                
            except Exception as exc:
                self._log(f"Transcription error: {exc}")
                if getattr(self.recorder, '_device', 'cpu') == 'cuda' and not fallback_done:
                    self._log("CUDA failed, falling back to CPU...")
                    self.enviar_estado("PROCESANDO", "Falta librería CUDA. Cayendo a CPU (más lento)...")
                    try:
                        self.recorder.reload_model("cpu", "int8")
                        fallback_done = True
                        continue
                    except Exception as reload_exc:
                        self.enviar_estado("ERROR", f"Error al recargar CPU: {reload_exc}")
                        break
                else:
                    self.enviar_estado("ERROR", f"Error al transcribir archivo: {exc}")
                    break
                    
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    def _set_device(self, device: str, compute_type: str):
        """Hot-reloads the Whisper model on the requested device (CPU or CUDA)."""
        self.enviar_estado("PROCESANDO", f"Cargando modelo en {device.upper()}...")
        try:
            self.recorder.reload_model(device, compute_type)
            self.enviar_estado("STANDBY", f"Motor Whisper activo en {device.upper()} ({compute_type}).")
        except Exception as exc:
            self._log(f"SET_DEVICE error: {exc}")
            self.enviar_estado("ERROR", f"No se pudo cargar en {device.upper()}: {exc}")

    # ── Document generation ───────────────────────────────────────────────────

    def _generate_doc(self):
        """Joins the entire buffer, runs analysis, and generates the Word report."""
        with self._buffer_lock:
            if not self.recording_buffer:
                self.enviar_estado(
                    "ERROR",
                    "Buffer vacio – no hay texto para generar el reporte.",
                    word_count=0,
                )
                return
            texto_completo = " ".join(self.recording_buffer)
            total_chunks = len(self.recording_buffer)

        wc = len(texto_completo.split())
        self._log(f"GENERATE_DOC: joining {total_chunks} chunks ({wc} words).")
        self.enviar_estado("PROCESANDO", f"Analizando {wc} palabras...", word_count=wc)

        # METEMOS TODO EL PROCESAMIENTO CRÍTICO DENTRO DEL TRY
        try:
            # 1. Intentar analizar con la IA
            results = self.analyzer.analizar_reunion(texto_completo)
            results["texto_original"] = texto_completo

            # 2. Publicar resultados del análisis a la UI
            self.enviar_estado(
                "COMPLETO",
                json.dumps(results, ensure_ascii=False),
                word_count=wc,
            )

            # 3. Intentar generar el reporte físico en Word
            filepath = self.documenter.generar_reporte(results)
            self.enviar_estado(
                "DOC_GENERADO",
                f"Reporte guardado: {filepath}",
                word_count=wc,
            )
            
        except Exception as exc:
            # Si Ollama da Out-Of-Memory o cualquier cosa falla, cae aquí de forma segura
            self._log(f"Error en el procesamiento del reporte: {exc}")
            self.enviar_estado("ERROR", f"Error al generar reporte: {exc}", word_count=wc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    controller = BackendController()
    controller.start()
    print("[Backend] Controller started. Waiting for commands. Press Ctrl+C to stop.")

    try:
        while True:
            try:
                command = controller._cmd_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            action = command.get("action")
            controller._log(f"Command received: {action}")

            if action == "START_RECORDING":
                controller._start_recording()

            elif action == "PAUSE_RECORDING":
                controller._pause_recording()

            elif action == "SET_DEVICE":
                device       = command.get("device", "cpu")
                compute_type = command.get("compute_type", "int8")
                threading.Thread(
                    target=controller._set_device,
                    args=(device, compute_type),
                    daemon=True, name="set-device"
                ).start()

            elif action == "CANCEL":
                controller._cancel_recording()

            elif action == "GENERATE_DOC":
                # Run doc generation in a thread so we don't block the command queue
                threading.Thread(
                    target=controller._generate_doc, daemon=True, name="doc-gen"
                ).start()

            else:
                controller._log(f"Unknown action ignored: {action}")

            controller._cmd_queue.task_done()

    except KeyboardInterrupt:
        print("\n[Backend] Ctrl+C received – shutting down.")
    finally:
        controller.recorder.stop()
        controller.stop()
        print("[Backend] BackendController stopped.")
