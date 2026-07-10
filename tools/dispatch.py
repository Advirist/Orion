#takes command from bot makes sure it can run the command then runs command
def call_tool(name, arguments, registry):
    if name not in registry:
        return {"error": f"'{name}' is not a recognized tool"}
    func = registry[name]
    return func(**arguments)