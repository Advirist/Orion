from settings.config import PIPER_VOICE_MODEL, MIC_DEVICE
import sounddevice as sd
import soundfile as sf
import numpy as np
import whisper
import subprocess
import tempfile
import os


# Loaded once, reused across calls — loading Whisper fresh every time would be slow
_whisper_model = whisper.load_model("small")

def listen(user_in) -> str:
    """Records audio via push-to-talk (Enter to start, Enter to stop) and returns transcribed text."""

    #returns string user typed if user chose to use keyboard instead of voice commands
    if user_in.strip():
        return user_in
    print("Recording... press Enter to stop.")
    
    mic_dict = sd.query_devices(MIC_DEVICE)
    mic_name = mic_dict['name']
    mic_sample_rate = int(mic_dict['default_samplerate'])
    recording = []
    stream = sd.InputStream(samplerate = mic_sample_rate, channels=1, callback=lambda indata, frames, time, status: recording.append(indata.copy()), device = mic_name)
    
    #starts recording
    with stream:
        input()  # blocks here until Enter is pressed again
    
    print("Processing...")
    
    if not recording:
        return "User tried to record but nothing came through alert them of this and ask them to type or try recording again"
    
    #makes recording into single array
    audio_data = np.concatenate(recording, axis=0)
    
    #creates a temporary .wav file to store audio data in
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, audio_data, mic_sample_rate)
        tmp_path = tmp.name
    
    #converts audio file to dict then returns string
    try:
        result = _whisper_model.transcribe(tmp_path)
        return result["text"].strip()
    #deletes temp file
    finally:
        os.remove(tmp_path)

def speak(text: str):
    """Converts text to speech using Piper and plays it aloud."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        piper_result = subprocess.run(
            ["piper", "--model", str(PIPER_VOICE_MODEL), "--output_file", tmp_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30
        )
        if piper_result.returncode != 0:
            print(f"[Piper failed: {piper_result.stderr.decode('utf-8', errors='replace')}]")
            return

        aplay_result = subprocess.run(["aplay", tmp_path], capture_output=True, timeout=60)
        if aplay_result.returncode != 0:
            print(f"[Playback failed: {aplay_result.stderr.decode('utf-8', errors='replace')}]")
    finally:
        os.remove(tmp_path)