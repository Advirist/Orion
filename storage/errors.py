import json

#logs errors from subprocess
def subprocess_log_error(stdout,stderr, error, message):
    try:
        with open('storage/subprocess_errors.json', 'r') as file:
            errors = json.load(file)
    except FileNotFoundError:
        errors = []
    
    errors.append({
        'error' : error,
        'stdout' : stdout,
        'stderr' : stderr,
        'message' : message
    })
    
    with open('storage/subprocess_errors.json', 'w') as file:
        json.dump(errors, file, indent=2)

#logs errors caught by the verifier
def log_error_from_verifier(tool_result, model_claim, verifier_verdict):
    try:
        with open('storage/verifier_errors.json', 'r') as file:
            errors = json.load(file)
    except FileNotFoundError:
        errors = []
    
    errors.append({
        'error' : 'verifier_error',
        'tool_result': tool_result,
        'model_claim': model_claim,
        'verifier_verdict': verifier_verdict
    })
    
    with open('storage/verifier_errors.json', 'w') as file:
        json.dump(errors, file, indent=2)
