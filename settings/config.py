from pathlib import Path
import os
from dotenv import load_dotenv
from ollama import Client
load_dotenv()
CLIENT = Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
PROJ_DIR = Path(__file__).parent.parent
TESTING_DIR = (PROJ_DIR / 'playground').resolve()
MODEL_NAME = 'qwen2.5:7b'
VERIFIER_MODEL_NAME = 'qwen3:8b'
PIPER_VOICE_MODEL = PROJ_DIR / 'voice' / 'models' / 'en_GB-northern_english_male-medium.onnx'
MIC_DEVICE = 'Blue Microphone'