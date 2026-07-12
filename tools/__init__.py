from .filesystem import TOOLS as FILESYSTEM_TOOLS, TOOL_REGISTRY as FILESYSTEM_REGISTRY
from .git import TOOLS as GIT_TOOLS, TOOL_REGISTRY as GIT_REGISTRY
from .dispatch import call_tool as _call_tool

# Combine every module's TOOLS list into one
TOOLS = FILESYSTEM_TOOLS + GIT_TOOLS  # later: + STATUS_TOOLS + ...

# Combine every module's registry dict into one
TOOL_REGISTRY = {**FILESYSTEM_REGISTRY, **GIT_REGISTRY}  # later: {**FILESYSTEM_REGISTRY, **STATUS_REGISTRY, ...}

def call_tool(name, arguments):
    return _call_tool(name, arguments, TOOL_REGISTRY)