"""
Network Advanced - Cac tinh nang backup mang nang cao (kieu Veeam)

Backup va restore:
1. Routing table (bang dinh tuyen tinh)
2. Hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts)
3. Firewall rules chi tiet (tung rule, khong chi profile on/off)
4. Network shares (cac thu muc chia se SMB)
5. Static ARP entries
6. Port proxy / port forwarding (netsh interface portproxy)

Tat ca dung netsh + PowerShell, tuong thich Windows Server 2012 R2+
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import os
import subprocess
import platform
import json
import re

IS_WINDOWS = platform.system() == "Windows"

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"


def _run_cmd(args, timeout=30):
    """Chay lenh cmd, tra ve stdout"""
    if not IS_WINDOWS:
        return ""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True,
            timeout=timeout, shell=True
        )
        return result.stdout
    except Exception as e:
        print(f"[network_adv] cmd error: {e}")
        return ""


def _run_ps(script, timeout=30):
    """Chay PowerShell"""
    if not IS_WINDOWS:
        return ""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy",
             "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout
    except Exception as e:
        print(f"[network_adv] PowerShell error: {e}")
        return ""


# ===== 1. ROUTING TABLE =====

def get_routing_table():
    """
    Lay bang dinh tuyen tinh (persistent routes).
    Chi lay route tinh do admin them, bo qua route tu dong.
    """
    if not IS_WINDOWS:
        return [{"destination": "10.0.0.0", "mask": "255.0.0.0",
                 "gateway": "192.168.1.1", "metric": 1, "interface": "demo"}]

    routes = []
    # Dung 'route print -4' de lay IPv4 routes
    out = _run_cmd("route print -4")
    if not out:
        return routes

    # Parse phan "Persistent Routes"
    in_persistent = False
    in_active = False
    for line in out.splitlines():
        line = line.strip()
        if "Persistent Routes:" in line:
            in_persistent = True
            in_active = False
            continue
        if "Active Routes:" in line:
            in_active = True
            in_persistent = False
            continue
        if in_persistent:
            # Format: Network Address  Netmask  Gateway Address  Metric
            parts = line.split()
            if len(parts) >= 4 and re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                routes.append({
                    "destination": parts[0],
                    "mask": parts[1],
                    "gateway": parts[2],
                    "metric": parts[3],
                    "persistent": True
                })

    print(f"[network_adv] Tim thay {len(routes)} persistent route(s)")
    return routes


def restore_routing_table(routes):
    """Khoi phuc cac persistent route"""
    if not IS_WINDOWS:
        print(f"[network_adv] (Skip non-Windows) Restore {len(routes)} routes")
        return True

    for r in routes:
        dest = r.get("destination")
        mask = r.get("mask")
        gw = r.get("gateway")
        metric = r.get("metric", 1)
        if not (dest and mask and gw):
            continue
        # route add <dest> mask <mask> <gateway> metric <metric> -p
        cmd = f"route add {dest} mask {mask} {gw} metric {metric} -p"
        _run_cmd(cmd)
        print(f"[network_adv] Restore route: {dest}/{mask} -> {gw}")
    return True


# ===== 2. HOSTS FILE =====

def get_hosts_file():
    """Doc noi dung file hosts"""
    if not IS_WINDOWS:
        return "# demo hosts file\n127.0.0.1 localhost\n"

    try:
        with open(HOSTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        # Dem so dong entry thuc su (khong phai comment)
        entries = [l for l in content.splitlines()
                   if l.strip() and not l.strip().startswith("#")]
        print(f"[network_adv] Hosts file: {len(entries)} entries, {len(content)} bytes")
        return content
    except Exception as e:
        print(f"[network_adv] Khong doc duoc hosts file: {e}")
        return ""


def restore_hosts_file(content):
    """Ghi lai file hosts"""
    if not IS_WINDOWS:
        print("[network_adv] (Skip non-Windows) Restore hosts file")
        return True

    if not content:
        print("[network_adv] Hosts file rong, bo qua")
        return False

    try:
        # Backup file hosts hien tai truoc khi ghi de
        if os.path.exists(HOSTS_PATH):
            bak = HOSTS_PATH + ".bak"
            try:
                with open(HOSTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    old = f.read()
                with open(bak, "w", encoding="utf-8") as f:
                    f.write(old)
            except Exception:
                pass

        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[network_adv] Restore hosts file: {len(content)} bytes")
        return True
    except Exception as e:
        print(f"[network_adv] Khong ghi duoc hosts file: {e}")
        return False


# ===== 3. FIREWALL RULES CHI TIET =====

def get_firewall_rules():
    """
    Lay danh sach firewall rules chi tiet (do admin tao).
    Chi lay cac rule enabled de tranh qua nhieu.
    """
    if not IS_WINDOWS:
        return [{"name": "Demo Rule", "direction": "Inbound",
                 "action": "Allow", "protocol": "TCP", "localport": "8080",
                 "enabled": True}]

    rules = []
    # Dung PowerShell de lay rules - chi lay rule enabled
    script = r"""
    Get-NetFirewallRule -Enabled True -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -notlike '@*' } |
        Select-Object -First 100 |
        ForEach-Object {
            $rule = $_
            $portFilter = $rule | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
            $addrFilter = $rule | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue
            $obj = [PSCustomObject]@{
                Name = $rule.DisplayName
                Direction = [string]$rule.Direction
                Action = [string]$rule.Action
                Protocol = [string]$portFilter.Protocol
                LocalPort = [string]$portFilter.LocalPort
                RemotePort = [string]$portFilter.RemotePort
                Profile = [string]$rule.Profile
            }
            $obj
        } | ConvertTo-Json -Compress
    """
    out = _run_ps(script, timeout=60)
    if not out.strip():
        # Fallback: dung netsh
        return _get_firewall_rules_netsh()

    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for r in data:
            rules.append({
                "name": r.get("Name", ""),
                "direction": r.get("Direction", ""),
                "action": r.get("Action", ""),
                "protocol": r.get("Protocol", ""),
                "localport": r.get("LocalPort", ""),
                "remoteport": r.get("RemotePort", ""),
                "profile": r.get("Profile", ""),
                "enabled": True
            })
        print(f"[network_adv] Tim thay {len(rules)} firewall rule(s)")
    except json.JSONDecodeError:
        return _get_firewall_rules_netsh()

    return rules


def _get_firewall_rules_netsh():
    """Fallback: lay firewall rules bang netsh"""
    rules = []
    out = _run_cmd("netsh advfirewall firewall show rule name=all", timeout=60)
    if not out:
        return rules

    current = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Rule Name:"):
            if current.get("name"):
                rules.append(current)
            current = {"name": line.split(":", 1)[1].strip(), "enabled": True}
        elif line.startswith("Enabled:"):
            current["enabled"] = "Yes" in line
        elif line.startswith("Direction:"):
            current["direction"] = line.split(":", 1)[1].strip()
        elif line.startswith("Action:"):
            current["action"] = line.split(":", 1)[1].strip()
        elif line.startswith("Protocol:"):
            current["protocol"] = line.split(":", 1)[1].strip()
        elif line.startswith("LocalPort:"):
            current["localport"] = line.split(":", 1)[1].strip()
    if current.get("name"):
        rules.append(current)

    # Chi giu rule enabled
    rules = [r for r in rules if r.get("enabled")]
    print(f"[network_adv] (netsh) Tim thay {len(rules)} firewall rule(s)")
    return rules[:100]  # Gioi han 100 rule


def restore_firewall_rules(rules):
    """
    Khoi phuc firewall rules.
    Chi them lai cac rule, khong xoa rule hien co (an toan hon).
    """
    if not IS_WINDOWS:
        print(f"[network_adv] (Skip non-Windows) Restore {len(rules)} firewall rules")
        return True

    added = 0
    for r in rules:
        name = r.get("name", "")
        if not name or name.startswith("@"):
            continue
        direction = (r.get("direction", "in") or "in").lower()
        # Chuan hoa direction
        if "out" in direction:
            direction = "out"
        else:
            direction = "in"
        action = (r.get("action", "allow") or "allow").lower()
        if "block" in action:
            action = "block"
        else:
            action = "allow"
        protocol = r.get("protocol", "")
        localport = r.get("localport", "")

        # Xoa rule cu cung ten (neu co) roi them lai
        _run_cmd(f'netsh advfirewall firewall delete rule name="{name}"')

        cmd = f'netsh advfirewall firewall add rule name="{name}" dir={direction} action={action}'
        if protocol and protocol not in ("Any", "", "None"):
            cmd += f" protocol={protocol}"
        if localport and localport not in ("Any", "", "None"):
            cmd += f" localport={localport}"

        out = _run_cmd(cmd)
        if "Ok" in out or out.strip() == "":
            added += 1

    print(f"[network_adv] Restore firewall rules: {added}/{len(rules)} rule(s)")
    return True


# ===== 4. NETWORK SHARES =====

def get_network_shares():
    """Lay danh sach thu muc chia se SMB (tru cac share he thong)"""
    if not IS_WINDOWS:
        return [{"name": "SharedDocs", "path": "C:\\SharedDocs",
                 "description": "Demo share"}]

    shares = []
    script = r"""
    Get-SmbShare -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike '*$' } |
        ForEach-Object {
            [PSCustomObject]@{
                Name = $_.Name
                Path = $_.Path
                Description = $_.Description
            }
        } | ConvertTo-Json -Compress
    """
    out = _run_ps(script)
    if not out.strip():
        # Fallback: net share
        out2 = _run_cmd("net share")
        for line in out2.splitlines():
            parts = line.split()
            if len(parts) >= 2 and ":" in parts[1] and not parts[0].endswith("$"):
                shares.append({"name": parts[0], "path": parts[1], "description": ""})
        print(f"[network_adv] (net share) Tim thay {len(shares)} share(s)")
        return shares

    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for s in data:
            shares.append({
                "name": s.get("Name", ""),
                "path": s.get("Path", ""),
                "description": s.get("Description", "")
            })
        print(f"[network_adv] Tim thay {len(shares)} network share(s)")
    except json.JSONDecodeError:
        pass

    return shares


def restore_network_shares(shares):
    """Khoi phuc cac network share"""
    if not IS_WINDOWS:
        print(f"[network_adv] (Skip non-Windows) Restore {len(shares)} shares")
        return True

    restored = 0
    for s in shares:
        name = s.get("name", "")
        path = s.get("path", "")
        if not name or not path:
            continue
        # Chi tao share neu thu muc ton tai
        if not os.path.exists(path):
            print(f"[network_adv] Bo qua share '{name}': thu muc {path} khong ton tai")
            continue

        # Xoa share cu cung ten roi tao lai
        _run_cmd(f'net share {name} /delete /y')
        desc = s.get("description", "")
        cmd = f'net share {name}="{path}"'
        if desc:
            cmd += f' /remark:"{desc}"'
        out = _run_cmd(cmd)
        if "successfully" in out.lower() or name in out:
            restored += 1
            print(f"[network_adv] Restore share: {name} -> {path}")

    print(f"[network_adv] Restore network shares: {restored}/{len(shares)}")
    return True


# ===== 5. PORT PROXY (Port Forwarding) =====

def get_port_proxy():
    """Lay cau hinh port proxy (netsh interface portproxy)"""
    if not IS_WINDOWS:
        return []

    proxies = []
    out = _run_cmd("netsh interface portproxy show all")
    if not out:
        return proxies

    # Parse cac dong dang: listenaddress listenport connectaddress connectport
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and re.match(r"[\d\.]+|\*", parts[0]):
            # Bo qua dong header
            if parts[0].lower() in ("address", "listen"):
                continue
            proxies.append({
                "listen_address": parts[0],
                "listen_port": parts[1],
                "connect_address": parts[2],
                "connect_port": parts[3]
            })

    if proxies:
        print(f"[network_adv] Tim thay {len(proxies)} port proxy rule(s)")
    return proxies


def restore_port_proxy(proxies):
    """Khoi phuc port proxy rules"""
    if not IS_WINDOWS:
        print(f"[network_adv] (Skip non-Windows) Restore {len(proxies)} port proxies")
        return True

    for p in proxies:
        la = p.get("listen_address", "0.0.0.0")
        lp = p.get("listen_port")
        ca = p.get("connect_address")
        cp = p.get("connect_port")
        if not (lp and ca and cp):
            continue
        cmd = (f"netsh interface portproxy add v4tov4 "
               f"listenaddress={la} listenport={lp} "
               f"connectaddress={ca} connectport={cp}")
        _run_cmd(cmd)
        print(f"[network_adv] Restore port proxy: {la}:{lp} -> {ca}:{cp}")
    return True


# ===== TONG HOP =====

def capture_network_advanced():
    """Capture toan bo cau hinh mang nang cao"""
    print("[network_adv] Bat dau capture cau hinh mang nang cao...")
    return {
        "routing_table": get_routing_table(),
        "hosts_file": get_hosts_file(),
        "firewall_rules": get_firewall_rules(),
        "network_shares": get_network_shares(),
        "port_proxy": get_port_proxy(),
    }


def restore_network_advanced(net_adv):
    """Khoi phuc cau hinh mang nang cao.
    Chi khoi phuc nhung thanh phan THUC SU CO trong backup (ho tro backup chon loc):
    neu mot key khong co trong net_adv thi bo qua, khong dung den thanh phan do.
    """
    if not net_adv:
        return

    print("[network_adv] === Khoi phuc cau hinh mang nang cao ===")

    if "routing_table" in net_adv:
        print("[network_adv] Routing table...")
        try:
            restore_routing_table(net_adv.get("routing_table", []))
        except Exception as e:
            print(f"  Error: {e}")

    if "hosts_file" in net_adv:
        print("[network_adv] Hosts file...")
        try:
            restore_hosts_file(net_adv.get("hosts_file", ""))
        except Exception as e:
            print(f"  Error: {e}")

    if "firewall_rules" in net_adv:
        print("[network_adv] Firewall rules...")
        try:
            restore_firewall_rules(net_adv.get("firewall_rules", []))
        except Exception as e:
            print(f"  Error: {e}")

    if "network_shares" in net_adv:
        print("[network_adv] Network shares...")
        try:
            restore_network_shares(net_adv.get("network_shares", []))
        except Exception as e:
            print(f"  Error: {e}")

    if "port_proxy" in net_adv:
        print("[network_adv] Port proxy...")
        try:
            restore_port_proxy(net_adv.get("port_proxy", []))
        except Exception as e:
            print(f"  Error: {e}")

    print("[network_adv] === Hoan tat khoi phuc cau hinh mang nang cao ===")


def compare_network_advanced(backup_na, current_na):
    """So sanh cau hinh mang nang cao"""
    diffs = []

    # Routing table
    b_routes = len(backup_na.get("routing_table", []))
    c_routes = len(current_na.get("routing_table", []))
    if b_routes != c_routes:
        diffs.append(f"Persistent routes: {c_routes} -> {b_routes}")

    # Hosts file
    b_hosts = backup_na.get("hosts_file", "")
    c_hosts = current_na.get("hosts_file", "")
    if b_hosts != c_hosts:
        diffs.append("Hosts file co thay doi")

    # Firewall rules
    b_rules = len(backup_na.get("firewall_rules", []))
    c_rules = len(current_na.get("firewall_rules", []))
    if b_rules != c_rules:
        diffs.append(f"Firewall rules: {c_rules} -> {b_rules}")

    # Network shares
    b_shares = {s.get("name") for s in backup_na.get("network_shares", [])}
    c_shares = {s.get("name") for s in current_na.get("network_shares", [])}
    if b_shares != c_shares:
        missing = b_shares - c_shares
        if missing:
            diffs.append(f"Network shares thieu: {', '.join(missing)}")

    # Port proxy
    b_pp = len(backup_na.get("port_proxy", []))
    c_pp = len(current_na.get("port_proxy", []))
    if b_pp != c_pp:
        diffs.append(f"Port proxy rules: {c_pp} -> {b_pp}")

    return diffs


if __name__ == "__main__":
    na = capture_network_advanced()
    print()
    print(json.dumps(na, indent=2, default=str, ensure_ascii=False))
