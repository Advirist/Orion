from .filesystem import TOOLS as FILESYSTEM_TOOLS, TOOL_REGISTRY as FILESYSTEM_REGISTRY
from .file_inspection import TOOLS as FILE_INSPECTION_TOOLS, TOOL_REGISTRY as FILE_INSPECTION_REGISTRY
from .git import TOOLS as GIT_TOOLS, TOOL_REGISTRY as GIT_REGISTRY
from .system import TOOLS as SYSTEM_TOOLS, TOOL_REGISTRY as SYSTEM_REGISTRY
from .code_inspection import TOOLS as CODE_TOOLS, TOOL_REGISTRY as CODE_REGISTRY
from .clock import TOOLS as CLOCK_TOOLS, TOOL_REGISTRY as CLOCK_REGISTRY
from .media import TOOLS as MEDIA_TOOLS, TOOL_REGISTRY as MEDIA_REGISTRY
from .weather import TOOLS as WEATHER_TOOLS, TOOL_REGISTRY as WEATHER_REGISTRY
from .dispatch import call_tool as _call_tool

#adding a new tool module = one import line above + one entry here
_MODULES = [
    (FILESYSTEM_TOOLS, FILESYSTEM_REGISTRY),
    (FILE_INSPECTION_TOOLS, FILE_INSPECTION_REGISTRY),
    (GIT_TOOLS, GIT_REGISTRY),
    (SYSTEM_TOOLS, SYSTEM_REGISTRY),
    (CODE_TOOLS, CODE_REGISTRY),
    (CLOCK_TOOLS, CLOCK_REGISTRY),
    (MEDIA_TOOLS, MEDIA_REGISTRY),
    (WEATHER_TOOLS, WEATHER_REGISTRY),
]

TOOLS = []
TOOL_REGISTRY = {}
for module_tools, module_registry in _MODULES:
    for name in module_registry:
        if name in TOOL_REGISTRY:
            raise RuntimeError(f"Two tool modules both register a tool named '{name}'.")
    TOOLS += module_tools
    TOOL_REGISTRY.update(module_registry)

#fail loudly at startup if a schema name and a registry key don't match
#(catches copy-paste bugs like a registry key still saying "git_status")
_schema_names = {tool["function"]["name"] for tool in TOOLS}
if _schema_names != set(TOOL_REGISTRY):
    raise RuntimeError(
        "Tool schemas and registry are out of sync. "
        f"In schemas only: {sorted(_schema_names - set(TOOL_REGISTRY))}. "
        f"In registry only: {sorted(set(TOOL_REGISTRY) - _schema_names)}."
    )

#Tools whose results describe LIVE state (the machine, the clock, the weather, git state,
#directory listings). These go out of date within seconds, so once the conversation moves
#on, llm/context.py replaces their old results with a short "stale" note before each model
#call. Tools that return content Jose may ask follow-up questions about (read_file,
#pdf_text_extract, file_diff, git_show, git_blame, image_info, lint_file) are deliberately
#NOT listed, so their results stay available.
VOLATILE_TOOLS = {
    'cpu_memory_status', 'disk_usage', 'battery_status', 'network_status',
    'running_processes', 'uptime', 'current_datetime', 'weather_check',
    'git_status', 'git_diff', 'git_log', 'git_branch', 'git_stash_list',
    'list_directory', 'directory_tree', 'search_files', 'find_duplicates',
    'file_stats', 'todo_scanner', 'list_dependencies',
}

#a typo in the set above would silently disable the protection for that tool
_unknown_volatile = VOLATILE_TOOLS - set(TOOL_REGISTRY)
if _unknown_volatile:
    raise RuntimeError(f"VOLATILE_TOOLS names tools that don't exist: {sorted(_unknown_volatile)}")


def call_tool(name, arguments):
    return _call_tool(name, arguments, TOOL_REGISTRY)