from settings.config import PIPER_VOICE_MODEL, DEFAULT_MIC_DEVICE
import sounddevice as sd
import soundfile as sf
import numpy as np
import whisper
import subprocess
import tempfile
import os
import json


# Loaded once, reused across calls — loading Whisper fresh every time would be slow
_whisper_model = whisper.load_model("small")

def listen(user_in) -> str:
    """Records audio via push-to-talk (Enter to start, Enter to stop) and returns transcribed text."""

    #returns string user typed if user chose to use keyboard instead of voice commands
    if user_in.strip():
        return user_in
    print("Recording... press Enter to stop.")

    last_mic_name = load_mic_name()

    if last_mic_name:

        mic_name, mic_sample_rate = get_mic(last_mic_name)

    else:
        mic_name, mic_sample_rate = get_mic(DEFAULT_MIC_DEVICE)

    #mic_dict = sd.query_devices(DEFAULT_MIC_DEVICE)
    #mic_name = mic_dict['name']
    #mic_sample_rate = int(mic_dict['default_samplerate'])
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

#mic defaults to system default unless specified otherwise program will remeber the last mic you used
def get_mic(chosen_mic): 
    if  chosen_mic:
        try:
            mic_dict = sd.query_devices(chosen_mic)
            mic_name = mic_dict['name']

            with open('storage/mic.json', 'w') as file:
                    json.dump({'last_microphone': mic_name}, file, indent = 2)

            return mic_name, int(mic_dict['default_samplerate'])
        except ValueError:
            print(f"[Configured mic '{chosen_mic}' not found — falling back to system default.]")

    mic_dict = sd.query_devices(kind='input')
    mic_name = mic_dict['name']

    with open('storage/mic.json', 'w') as file:
        json.dump({'last_microphone': mic_name}, file, indent = 2)

    return mic_name, int(mic_dict['default_samplerate'])

def load_mic_name():
    if os.path.exists('storage/mic.json'):
        with open('storage/mic.json', "r") as f:
            data = json.load(f)
            return data.get('last_microphone')
    return None