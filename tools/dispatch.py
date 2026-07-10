#takes command from bot makes sure it can run the command then runs command
def call_tool(name, arguments, registry):
    if name not in registry:
        return {"error": f"'{name}' is not a recognized tool"}
    
    mutating = registry[name]['mutating']
    if mutating:
        confirmation = input(f'are you sure you want to call {name} with {arguments} as arguments yes/no: ')
        if confirmation.lower() == 'yes':
            func = registry[name]['function']
            return func(**arguments)
        else:
            return {'error' : 'user cancelled tool call for mutalble function please ask user to reclarify what they want you to do'}
    func = registry[name]['function']
    return func(**arguments)
    