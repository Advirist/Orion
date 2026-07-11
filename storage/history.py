import json
from settings.prompts import SYSTEM_PROMPT

#Functions to load and save history
def history_load():
    try:
        with open('storage/history.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return [{'role': 'system', 'content': SYSTEM_PROMPT}]

def history_save(history):
    with open('storage/history.json', 'w') as file:
        json.dump(history, file, indent = 2)