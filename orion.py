from ollama import chat
import json
from tools import TOOLS, call_tool
from history import history_load, history_save
from prompts import SYSTEM_PROMPT


#Loads history from past sessions
history = history_load()

if isinstance(history, list) and history:
    if history[0] != {'role': 'system', 'content': SYSTEM_PROMPT} and history[0]["role"] != "system":
        history.insert(0,{'role': 'system', 'content': SYSTEM_PROMPT})
    elif history[0] != {'role': 'system', 'content': SYSTEM_PROMPT}:
        history[0] = {'role': 'system', 'content': SYSTEM_PROMPT}

session_bool = True

#first user input to start session off
user_in = input('Ollama - type /e to end:')
if user_in.strip() == '/e': #ends session if user types /e
        session_bool = False
#adds first user input to history
history.append({'role': 'user', 'content': user_in})
history_save(history)

#While loop to keep the session going until user types /e
while session_bool:
    #Loads history from past sessions to feed to the model

    response = chat('qwen2.5:7b', messages = history, tools = TOOLS)
    
    message = response['message']

    # Check if the model wants to call a tool instead of just replying
    if message.get('tool_calls'):
        # Log the assistant's tool-call request itself into history
        history.append(message.model_dump())

        for tool_call in message['tool_calls']:
            name = tool_call['function']['name']
            arguments = tool_call['function']['arguments']

            print(f'\n[Orion wants to call: {name}({arguments})]')
            result = call_tool(name, arguments)

            # Tool results go back in as their own message, role='tool'
            history.append({
                'role': 'tool',
                'content': json.dumps(result)
            })

        history_save(history)
        continue  # loop back to the model WITHOUT asking user for input —
                  # the model needs to see the tool result before it can respond

    #prints the response from the model and adds it to the history
    print('\n' + response['message']['content'])
    history.append(response['message'].model_dump())
    history_save(history)

    #asks the user for input and adds it to the history
    user_in = input('\nOllama - type /e to end:')
    
    if user_in.strip() == '/e': #ends session if user types /e
        break
    
    history.append({'role': 'user', 'content': user_in})
    history_save(history) #saves the history to a json file


    

