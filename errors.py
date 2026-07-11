import json

def log_error(tool_result, model_claim, verifier_verdict):
    try:
        with open('errors.json', 'r') as file:
            errors = json.load(file)
    except FileNotFoundError:
        errors = []
    
    errors.append({
        'tool_result': tool_result,
        'model_claim': model_claim,
        'verifier_verdict': verifier_verdict
    })
    
    with open('errors.json', 'w') as file:
        json.dump(errors, file, indent=2)