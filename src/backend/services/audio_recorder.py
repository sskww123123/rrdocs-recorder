import threading
import queue
import tempfile
import os
import sys
import re

# Add NVIDIA DLL directories to PATH for Windows (CUDA 12)
if os.name == 'nt':
    site_packages = os.path.join(sys.prefix, 'Lib', 'site-packages')
    for lib in ['cublas', 'cuda_nvrtc', 'cudnn', 'cuda_runtime']:
        bin_dir = os.path.join(site_packages, 'nvidia', lib, 'bin')
        if os.path.isdir(bin_dir):
            try:
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                print(f"[AUDIORECORDER] Added DLL dir: {bin_dir}")
            except Exception as e:
                print(f"[AUDIORECORDER] Error adding DLL dir {bin_dir}: {e}")

from faster_whisper import WhisperModel
import speech_recognition as sr
from difflib import SequenceMatcher

class MicRecorder:
    def __init__(self, device: str = "cpu", compute_type: str = "int8"):
        """
        Initializes the recorder, loads the AI model using faster-whisper.
        device:       'cpu' or 'cuda'
        compute_type: 'int8' (cpu) or 'float16' (cuda)
        """
        self.last_transcript = ""
        self._device = device
        self._compute_type = compute_type

        print(f"[AUDIORECORDER] Loading Faster-Whisper model ('small') on {device.upper()} ({compute_type})...")
        self.model = WhisperModel("small", device=device, compute_type=compute_type)
        
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        # 2. One-time Calibration
        self.initialize_recorder()
        
        # Control events for the recording thread
        self._stop_event = threading.Event()
        self._audio_queue = queue.Queue()
        
        # Ensure it starts in a stopped but ready state
        self._stop_event.set()
        print("[AUDIORECORDER] System ready for instant recording.")

    def reload_model(self, device: str, compute_type: str):
        """Hot-swaps the Whisper model to a different device without restarting."""
        print(f"[AUDIORECORDER] Reloading model on {device.upper()} ({compute_type})...")
        self._device = device
        self._compute_type = compute_type
        self.model = WhisperModel("small", device=device, compute_type=compute_type)
        print(f"[AUDIORECORDER] Model reloaded on {device.upper()}.")

    def initialize_recorder(self):
        """Runs ambient noise adjustment ONLY ONCE."""
        print("[AUDIORECORDER] Calibrating ambient noise (2s)...")
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            self.recognizer.dynamic_energy_threshold = False
            print(f"[AUDIORECORDER] Calibration complete. Energy threshold: {self.recognizer.energy_threshold:.2f}")

    def sanitize_text(self, text: str) -> str:
        """
        Regex sanitization: Keeps only alphanumeric characters and basic Spanish punctuation.
        Prevents hallucinated garbage characters from polluting the output.
        """
        # Pattern: letters, numbers, Spanish vowels/accents, spaces, and .,!?
        pattern = r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s.,!?]"
        sanitized = re.sub(pattern, "", text)
        # Collapse multiple spaces
        return re.sub(r"\s+", " ", sanitized).strip()

    def _deduplicar_texto(self, texto_nuevo: str) -> str:
        """Compares new text with previous text to avoid phrase repetition."""
        if not self.last_transcript: 
            return texto_nuevo
            
        matcher = SequenceMatcher(None, self.last_transcript[-50:], texto_nuevo[:50])
        match = matcher.find_longest_match(0, len(self.last_transcript[-50:]), 0, len(texto_nuevo[:50]))        
        
        if match.size > 10:
            return texto_nuevo[match.size:]
        return texto_nuevo

    def start(self):
        """Prepares the recorder."""
        self._stop_event.clear()
        with self._audio_queue.mutex:
            self._audio_queue.queue.clear()
        print("[AUDIORECORDER] Ready signal received.")

    def stop(self):
        """Signals the producer thread to stop."""
        self._stop_event.set()

    def _audio_producer(self):
        """Optimized Producer: Captures audio without re-calibration."""
        print("[AUDIORECORDER] Producer thread active.")
        with self.microphone as source:
            while not self._stop_event.is_set():
                try:
                    audio = self.recognizer.listen(source, timeout=2.0, phrase_time_limit=None)
                    self._audio_queue.put(audio)
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    print(f"[AUDIORECORDER] Producer Error: {e}")
                    break
        print("[AUDIORECORDER] Producer thread closed.")

    def record_chunks(self):
        """
        Main Generator: Transcribes chunks using faster-whisper with 
        pre-processing and sanitization.
        """
        self._stop_event.clear()
        producer = threading.Thread(target=self._audio_producer, daemon=True)
        producer.start()

        while not self._stop_event.is_set() or not self._audio_queue.empty():
            try:
                audio = self._audio_queue.get(timeout=0.5)
                
                # --- Speech Pre-processing (Silence Threshold Check) ---
                # speech_recognition captures audio based on energy_threshold.
                # However, for an extra layer of robustness, we check the raw data.
                raw_data = audio.get_raw_data()
                if not raw_data or len(raw_data) < 1000: # Ignore tiny/empty buffers
                    continue

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(audio.get_wav_data())
                    tmp_path = tmp.name

                # --- AI Inference using faster-whisper (Advanced Settings) ---
                # beam_size=5: Better accuracy via broader search
                # temperature=0.0: Deterministic output, prevents hallucination
                # no_speech_threshold=0.6: Filters out non-speech segments
                segments, info = self.model.transcribe(
                    tmp_path, 
                    language="es", 
                    beam_size=5, 
                    temperature=0.0,
                    no_speech_threshold=0.6,
                    vad_filter=True
                )
                
                raw_text = " ".join([segment.text for segment in segments]).strip()
                
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

                if not raw_text:
                    continue

                # --- Text Sanitization & Deduplication ---
                clean_text = self.sanitize_text(raw_text)
                text_final = self._deduplicar_texto(clean_text)
                
                self.last_transcript = clean_text

                if text_final:
                    yield text_final

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[AUDIORECORDER] Transcription Error: {e}")

if __name__ == "__main__":
    print("[TEST] Initializing Robust Faster-MicRecorder...")
    recorder = MicRecorder()
    recorder.start()
    
    print("[TEST] Recording started. Accuracy and Sanitization enabled. Speak now...")
    try:
        for text in recorder.record_chunks():
            print(f"[DETECTED]: {text}")
    except KeyboardInterrupt:
        recorder.stop()
    print("[TEST] Finished.")
