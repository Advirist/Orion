#takes command from bot makes sure it can run the command then runs command
def call_tool(name, arguments, registry):
    if name not in registry:
        return {"error": f"'{name}' is not a recognized tool"}
    
    mutating = registry[name]['mutating']
    if mutating:
        while True:
            confirmation = input(f'are you sure you want to call {name} with {arguments} as arguments yes/no: ')
            if confirmation.lower() == 'yes':
                func = registry[name]['function']
                return func(**arguments)
            elif confirmation.lower() == 'no':
                return {'error' : 'user cancelled tool call for mutalble function please ask user to reclarify what they want you to do'}
            else:
                confirmation = input('Please enter yes or no: ')
    func = registry[name]['function']
    return func(**arguments)
    