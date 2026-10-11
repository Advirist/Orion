import socket
import time
from datetime import datetime
import psutil
from ._common import parse_int

BYTES_PER_GB = 1024 ** 3
#virtual/temporary filesystems that aren't real drives
SKIPPED_FILESYSTEMS = {'squashfs', 'tmpfs', 'devtmpfs', 'overlay', 'efivarfs'}
MAX_PROCESSES = 25

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "cpu_memory_status",
            "description": "Reports the current CPU usage percentage and memory (RAM) usage of the system, including both the percentage used and the amount used versus total available, in gigabytes. Use this for any question about current RAM, memory, or CPU usage.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "disk_usage",
            "description": "Reports storage usage for each real drive/partition on the system: total, used, and free space in gigabytes, plus percent used.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "battery_status",
            "description": "Reports the battery charge percentage, whether the charger is plugged in, and estimated minutes remaining. Reports that no battery is present on desktops.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "network_status",
            "description": "Reports whether the internet is reachable, this machine's network interfaces and local IPv4 addresses, and whether a Tailscale network interface is up on this machine.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "running_processes",
            "description": "Lists the programs currently using the most memory or CPU, showing each one's name, process ID, and usage percentage. Read-only; it cannot stop or change any process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "enum": ["memory", "cpu"],
                        "description": "Rank processes by 'memory' or 'cpu' usage. Defaults to 'memory'. Note a single process's CPU percent can exceed 100 on multi-core machines."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many processes to show, from 1 to 25. Defaults to 10."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "uptime",
            "description": "Reports how long the system has been running since it was last booted, and when that boot happened.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]


def _gb(num_bytes):
    return round(num_bytes / BYTES_PER_GB, 1)


def _unexpected(e):
    return {"success": False, "error": "unexpected_error", "message": str(e)}


def cpu_memory_status():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        return {
            "success": True,
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": _gb(memory.used),
            "memory_total_gb": _gb(memory.total),
            "message": f"CPU is at {cpu_percent}% and memory is {memory.percent}% used ({_gb(memory.used)} of {_gb(memory.total)} GB)."
        }
    except Exception as e:
        return _unexpected(e)


def disk_usage():
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception as e:
        return _unexpected(e)

    drives = []
    seen_devices = set()
    for part in partitions:
        if part.fstype in SKIPPED_FILESYSTEMS or part.mountpoint.startswith('/snap'):
            continue
        #the same physical device can be mounted in several places; report it once
        if part.device in seen_devices:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        seen_devices.add(part.device)
        drives.append({
            "mountpoint": part.mountpoint,
            "filesystem": part.fstype,
            "total_gb": _gb(usage.total),
            "used_gb": _gb(usage.used),
            "free_gb": _gb(usage.free),
            "percent_used": usage.percent
        })

    return {
        "success": True,
        "drives": drives,
        "message": f"Found {len(drives)} drive(s)." if drives else "No real drives could be read."
    }


def battery_status():
    try:
        battery = psutil.sensors_battery()
    except Exception as e:
        return _unexpected(e)

    #no battery isn't a failure, it's a normal answer on a desktop
    if battery is None:
        return {
            "success": True,
            "battery_present": False,
            "message": "No battery was detected on this machine. This is normal for a desktop."
        }

    minutes_left = None
    if battery.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and battery.secsleft > 0:
        minutes_left = round(battery.secsleft / 60)

    percent = round(battery.percent)
    if battery.power_plugged:
        message = f"Battery is at {percent}% and plugged in."
    elif minutes_left is not None:
        message = f"Battery is at {percent}%, on battery power, about {minutes_left} minutes remaining."
    else:
        message = f"Battery is at {percent}%."

    return {
        "success": True,
        "battery_present": True,
        "percent": percent,
        "plugged_in": battery.power_plugged,
        "minutes_remaining": minutes_left,
        "message": message
    }


def _internet_reachable(timeout=3):
    #opens a plain TCP connection to a public DNS server; nothing is sent or downloaded
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False


def network_status():
    try:
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception as e:
        return _unexpected(e)

    interfaces = []
    for name, addrs in addresses.items():
        ipv4 = [a.address for a in addrs if a.family == socket.AF_INET and not a.address.startswith('127.')]
        if not ipv4:
            continue
        interfaces.append({
            "name": name,
            "ipv4": ipv4,
            "is_up": stats[name].isup if name in stats else None
        })

    tailscale = next((i for i in interfaces if 'tailscale' in i["name"].lower()), None)
    online = _internet_reachable()

    message = "The internet is reachable." if online else "The internet does not appear to be reachable."
    if tailscale and tailscale["is_up"]:
        message += " A Tailscale interface is up on this machine."
    else:
        message += " No active Tailscale interface was found on this machine."

    return {
        "success": True,
        "internet_reachable": online,
        "interfaces": interfaces,
        "tailscale_interface_up": bool(tailscale and tailscale["is_up"]),
        "message": message
    }


def running_processes(sort_by='memory', limit=10):
    sort_by = str(sort_by).strip().lower()
    if sort_by not in ('memory', 'cpu'):
        return {
            "success": False,
            "error": "invalid_argument",
            "message": f"sort_by must be 'memory' or 'cpu', but got '{sort_by}'."
        }
    limit, err = parse_int(limit, 'limit')
    if err:
        return err
    limit = max(1, min(limit, MAX_PROCESSES))

    try:
        processes = list(psutil.process_iter(['pid', 'name']))
    except Exception as e:
        return _unexpected(e)

    #a process's first cpu_percent() call always returns 0, because CPU usage is
    #measured between two calls. So prime every process, wait, then measure.
    if sort_by == 'cpu':
        for proc in processes:
            try:
                proc.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(0.5)

    rows = []
    for proc in processes:
        try:
            row = {
                "pid": proc.info['pid'],
                "name": proc.info['name'],
                "memory_percent": round(proc.memory_percent(), 1)
            }
            if sort_by == 'cpu':
                row["cpu_percent"] = round(proc.cpu_percent(None), 1)
            rows.append(row)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            #processes can exit or be off-limits mid-scan; skip them quietly
            continue

    key = 'cpu_percent' if sort_by == 'cpu' else 'memory_percent'
    rows.sort(key=lambda r: r[key], reverse=True)
    top = rows[:limit]

    return {
        "success": True,
        "sorted_by": sort_by,
        "processes": top,
        "message": f"Showing the top {len(top)} process(es) by {sort_by} usage."
    }


def uptime():
    try:
        boot_timestamp = psutil.boot_time()
    except Exception as e:
        return _unexpected(e)

    total_minutes = int((time.time() - boot_timestamp) // 60)
    days, remainder = divmod(total_minutes, 1440)
    hours, minutes = divmod(remainder, 60)

    return {
        "success": True,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "booted_at": datetime.fromtimestamp(boot_timestamp).astimezone().isoformat(timespec='minutes'),
        "message": f"The system has been running for {days} day(s), {hours} hour(s), and {minutes} minute(s)."
    }


TOOL_REGISTRY = {
    "cpu_memory_status": {'function': cpu_memory_status, 'mutating': False},
    "disk_usage": {'function': disk_usage, 'mutating': False},
    "battery_status": {'function': battery_status, 'mutating': False},
    "network_status": {'function': network_status, 'mutating': False},
    "running_processes": {'function': running_processes, 'mutating': False},
    "uptime": {'function': uptime, 'mutating': False},
}
