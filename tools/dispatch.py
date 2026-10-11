import inspect


def _error(error, message):
    return {"success": False, "error": error, "message": message}


#checks a model-supplied argument dict against the function's real signature
#returns None if the call is fine, or an error dict explaining what to fix
def _validate_arguments(name, func, arguments):
    parameters = inspect.signature(func).parameters.values()
    accepts_anything = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters)
    named = [p for p in parameters
             if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)]
    accepted_names = [p.name for p in named]

    #unknown arguments are rejected, never silently dropped: dropping them would run the
    #tool without something the model thinks it asked for, and the model could then
    #describe an outcome that never happened
    unknown = sorted(set(arguments) - set(accepted_names))
    if unknown and not accepts_anything:
        accepted_text = ", ".join(accepted_names) if accepted_names else "none (it takes no arguments)"
        return _error(
            "unknown_argument",
            f"'{name}' does not accept the argument(s): {', '.join(unknown)}. "
            f"Accepted arguments: {accepted_text}. Retry using only those."
        )

    missing = [p.name for p in named if p.default is inspect.Parameter.empty and p.name not in arguments]
    if missing:
        return _error(
            "missing_argument",
            f"'{name}' requires the argument(s): {', '.join(missing)}. Retry with them included."
        )
    return None


#takes a tool name and arguments from the model, validates them, asks for confirmation if the
#tool is mutating, then runs it
def call_tool(name, arguments, registry):
    if name not in registry:
        return _error(
            "unknown_tool",
            f"'{name}' is not a recognized tool. Available tools: {', '.join(sorted(registry))}."
        )

    entry = registry[name]
    func = entry['function']

    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _error("invalid_arguments", f"Arguments for '{name}' must be a set of named values.")

    #validated BEFORE any confirmation prompt, so the user is never asked to approve a call
    #that would be rejected anyway
    problem = _validate_arguments(name, func, arguments)
    if problem:
        return problem

    if entry['mutating']:
        confirmation = input(f'Are you sure you want to call {name} with {arguments} as arguments? (yes/no): ')
        if confirmation.strip().lower() != 'yes':
            return _error(
                "user_cancelled",
                f"The user declined to run '{name}'. Let them know it was not run and ask how they'd like to proceed."
            )

    return func(**arguments)