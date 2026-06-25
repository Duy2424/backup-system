"""
Backup va restore system state tren Windows:
- Network adapter (IP, DNS, gateway, mode: Host-only/NAT/Bridged)
- Windows Firewall (Domain/Private/Public profiles)
- Windows Defender (Real-time protection)

Chu y: Module nay dung subprocess goi PowerShell va netsh.
Cac lenh duoc viet de tuong thich Windows Server 2012 R2 va moi hon.
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import subprocess
import json
import sys
import os
import platform
import re


IS_WINDOWS = platform.system() == "Windows"


def _run_ps(script, timeout=30):
    """Chay PowerShell script va tra ve stdout"""
    if not IS_WINDOWS:
        return ""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout
    except Exception as e:
        print(f"[system_state] PowerShell error: {e}")
        return ""


def _run_cmd(args, timeout=30):
    """Chay lenh cmd"""
    if not IS_WINDOWS:
        return ""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, shell=True
        )
        return result.stdout
    except Exception as e:
        print(f"[system_state] cmd error: {e}")
        return ""


# ===== NETWORK ADAPTER =====

def detect_network_mode(ip_address):
    """
    Phat hien che do network adapter dua tren dai IP:
    - VMware Host-only (theo cau hinh do an): 192.168.10.x
    - VMware Host-only mac dinh khac: 192.168.146.x, 192.168.137.x
    - VMware NAT: 192.168.x.x (gateway co .2)
    - Bridged: dai IP cua mang vat ly
    Day la heuristic - co the tinh chinh theo cau hinh thuc te
    """
    if not ip_address:
        return "Unknown"

    parts = ip_address.split(".")
    if len(parts) != 4:
        return "Unknown"

    # Dai Host-only dung trong do an nay (192.168.10.0/24) va cac dai
    # Host-only mac dinh pho bien cua VMware
    if (ip_address.startswith("192.168.10.")
            or ip_address.startswith("192.168.146.")
            or ip_address.startswith("192.168.137.")):
        return "Host-only"
    # VMnet8 (NAT) mac dinh
    if ip_address.startswith("192.168.") and parts[2] in ["80", "100", "110", "44"]:
        return "NAT"
    # Mac dinh: doan theo subnet phoi bien
    return "Unknown"


def get_network_adapters():
    """
    Lay thong tin tat ca network adapter active.
    Ho tro DAY DU ca IPv4 va IPv6:
    - IPv4: dia chi, prefix, gateway, DNS, DHCP
    - IPv6: dia chi, prefix, gateway, DNS, autoconfig
    """
    if not IS_WINDOWS:
        return [{
            "name": "demo", "mac": "00:0C:29:00:00:00", "status": "Up",
            "index": 1, "mode": "Host-only",
            "ipv4": {
                "ip": "192.168.10.2", "prefix": 24,
                "subnet_mask": "255.255.255.0",
                "gateway": "192.168.10.1", "dns": ["8.8.8.8"], "dhcp": False
            },
            "ipv6": {
                "ip": "fe80::20c:29ff:fe00:0", "prefix": 64,
                "subnet_mask": None,
                "gateway": None, "dns": ["2001:4860:4860::8888"], "dhcp": True
            },
            # Tuong thich nguoc voi code cu
            "ip": "192.168.10.2", "prefix": 24,
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.10.1", "dns": ["8.8.8.8"], "dhcp": False
        }]

    script = """
    $adapters = Get-NetIPConfiguration -Detailed -ErrorAction SilentlyContinue
    $result = @()
    foreach ($a in $adapters) {
        $idx = $a.InterfaceIndex
        # ----- IPv4 -----
        $ipv4 = $a.IPv4Address | Select-Object -First 1
        $dns4 = ($a.DNSServer | Where-Object {$_.AddressFamily -eq 2}).ServerAddresses
        $dhcp4 = (Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue).Dhcp
        # ----- IPv6 -----
        $ipv6 = $a.IPv6Address | Select-Object -First 1
        $dns6 = ($a.DNSServer | Where-Object {$_.AddressFamily -eq 23}).ServerAddresses
        $v6if = Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv6 -ErrorAction SilentlyContinue
        $dhcp6 = $v6if.Dhcp
        $autocfg6 = $v6if.AddressFamily
        $obj = @{
            name = $a.InterfaceAlias
            mac = (Get-NetAdapter -InterfaceIndex $idx -ErrorAction SilentlyContinue).MacAddress
            status = (Get-NetAdapter -InterfaceIndex $idx -ErrorAction SilentlyContinue).Status
            index = $idx
            v4_ip = if ($ipv4) { $ipv4.IPAddress } else { $null }
            v4_prefix = if ($ipv4) { $ipv4.PrefixLength } else { $null }
            v4_gateway = if ($a.IPv4DefaultGateway) { $a.IPv4DefaultGateway.NextHop } else { $null }
            v4_dns = $dns4
            v4_dhcp = "$dhcp4"
            v6_ip = if ($ipv6) { $ipv6.IPAddress } else { $null }
            v6_prefix = if ($ipv6) { $ipv6.PrefixLength } else { $null }
            v6_gateway = if ($a.IPv6DefaultGateway) { $a.IPv6DefaultGateway.NextHop } else { $null }
            v6_dns = $dns6
            v6_dhcp = "$dhcp6"
        }
        $result += New-Object PSObject -Property $obj
    }
    $result | ConvertTo-Json -Depth 5 -Compress
    """
    out = _run_ps(script)
    try:
        data = json.loads(out) if out.strip() else []
        if isinstance(data, dict):
            data = [data]
        adapters = []
        for a in data:
            v4_ip = a.get("v4_ip")
            v6_ip = a.get("v6_ip")
            # Bo qua adapter khong co IP nao
            if not v4_ip and not v6_ip:
                continue

            def _as_list(x):
                if isinstance(x, list):
                    return x
                return [x] if x else []

            mode = detect_network_mode(v4_ip or "")
            v4_prefix = a.get("v4_prefix")
            ipv4 = {
                "ip": v4_ip,
                "prefix": v4_prefix,
                "subnet_mask": _prefix_to_mask(v4_prefix) if v4_prefix else None,
                "gateway": a.get("v4_gateway"),
                "dns": _as_list(a.get("v4_dns")),
                "dhcp": "Enabled" in str(a.get("v4_dhcp", "")),
            }
            ipv6 = {
                "ip": v6_ip,
                "prefix": a.get("v6_prefix"),
                "subnet_mask": None,  # IPv6 dung prefix length, khong dung subnet mask
                "gateway": a.get("v6_gateway"),
                "dns": _as_list(a.get("v6_dns")),
                "dhcp": "Enabled" in str(a.get("v6_dhcp", "")),
            }
            adapters.append({
                "name": a.get("name"),
                "mac": a.get("mac"),
                "status": a.get("status"),
                "index": a.get("index"),
                "mode": mode,
                "ipv4": ipv4,
                "ipv6": ipv6,
                # Tuong thich nguoc voi code cu (compare_system_state cu)
                "ip": ipv4["ip"],
                "prefix": ipv4["prefix"],
                "subnet_mask": ipv4["subnet_mask"],
                "gateway": ipv4["gateway"],
                "dns": ipv4["dns"],
                "dhcp": ipv4["dhcp"],
            })
        return adapters
    except json.JSONDecodeError as e:
        print(f"[system_state] JSON parse error: {e}, raw: {out[:200]}")
        return []


def restore_network_adapter(adapter_info):
    """
    Khoi phuc cau hinh network adapter ve trang thai luc backup.
    Khoi phuc DAY DU ca IPv4 va IPv6.
    Su dung netsh de tuong thich nhieu phien ban Windows.
    """
    if not IS_WINDOWS:
        print(f"[system_state] (Skip - non-Windows) Restore adapter: {adapter_info.get('name')}")
        return True

    name = adapter_info.get("name")
    if not name:
        return False

    # Lay cau hinh IPv4 / IPv6 (ho tro ca format cu va moi)
    ipv4 = adapter_info.get("ipv4")
    ipv6 = adapter_info.get("ipv6")
    if ipv4 is None:
        # Format cu - chi co IPv4 o cap goc
        ipv4 = {
            "ip": adapter_info.get("ip"),
            "prefix": adapter_info.get("prefix"),
            "gateway": adapter_info.get("gateway"),
            "dns": adapter_info.get("dns") or [],
            "dhcp": adapter_info.get("dhcp", False),
        }

    # ===== KHOI PHUC IPv4 =====
    if ipv4 and ipv4.get("ip"):
        _restore_ipv4(name, ipv4)
    elif ipv4 and ipv4.get("dhcp"):
        _restore_ipv4(name, ipv4)

    # ===== KHOI PHUC IPv6 =====
    if ipv6 and (ipv6.get("ip") or ipv6.get("dhcp")):
        _restore_ipv6(name, ipv6)

    return True


def _restore_ipv4(name, ipv4):
    """Khoi phuc cau hinh IPv4 cho adapter (IP, subnet mask, default gateway, DNS)"""
    dhcp = ipv4.get("dhcp", False)
    ip = ipv4.get("ip")
    prefix = ipv4.get("prefix") or 24
    gateway = ipv4.get("gateway")
    dns = ipv4.get("dns") or []

    if dhcp:
        _run_cmd(f'netsh interface ipv4 set address name="{name}" source=dhcp')
        _run_cmd(f'netsh interface ipv4 set dnsservers name="{name}" source=dhcp')
        print(f"[system_state] {name} IPv4 -> DHCP")
        return

    if not ip:
        return

    # Uu tien subnet_mask da luu trong backup, neu khong co thi tinh tu prefix
    mask = ipv4.get("subnet_mask") or _prefix_to_mask(prefix)

    # netsh: set address static <IP> <SUBNET_MASK> <DEFAULT_GATEWAY> <gateway_metric>
    cmd = f'netsh interface ipv4 set address name="{name}" static {ip} {mask}'
    if gateway:
        cmd += f" {gateway} 1"
    _run_cmd(cmd)
    print(f"[system_state] {name} IPv4 -> IP={ip} | Subnet mask={mask} | Default gateway={gateway}")

    if dns:
        _run_cmd(f'netsh interface ipv4 set dnsservers name="{name}" static {dns[0]} primary')
        for i, d in enumerate(dns[1:], 2):
            _run_cmd(f'netsh interface ipv4 add dnsservers name="{name}" {d} index={i}')
        print(f"[system_state] {name} IPv4 DNS -> {dns}")


def _restore_ipv6(name, ipv6):
    """Khoi phuc cau hinh IPv6 cho adapter"""
    dhcp = ipv6.get("dhcp", False)
    ip = ipv6.get("ip")
    prefix = ipv6.get("prefix") or 64
    gateway = ipv6.get("gateway")
    dns = ipv6.get("dns") or []

    if dhcp:
        # IPv6 dung DHCPv6 / autoconfig
        _run_cmd(f'netsh interface ipv6 set interface "{name}" routerdiscovery=enabled')
        _run_cmd(f'netsh interface ipv6 set dnsservers name="{name}" source=dhcp')
        print(f"[system_state] {name} IPv6 -> DHCP/Autoconfig")
        return

    if not ip:
        return

    # Bo qua link-local (fe80::) - dia chi nay tu sinh, khong can restore
    if ip.lower().startswith("fe80"):
        print(f"[system_state] {name} IPv6 {ip} la link-local, bo qua")
        return

    # Static IPv6
    cmd = f'netsh interface ipv6 set address interface="{name}" address={ip}/{prefix}'
    _run_cmd(cmd)
    print(f"[system_state] {name} IPv6 -> {ip}/{prefix}")

    if gateway:
        _run_cmd(f'netsh interface ipv6 add route ::/0 "{name}" {gateway}')
        print(f"[system_state] {name} IPv6 gateway -> {gateway}")

    if dns:
        _run_cmd(f'netsh interface ipv6 set dnsservers name="{name}" static {dns[0]} primary')
        for i, d in enumerate(dns[1:], 2):
            _run_cmd(f'netsh interface ipv6 add dnsservers name="{name}" {d} index={i}')


def _prefix_to_mask(prefix):
    """Doi prefix length sang subnet mask"""
    try:
        prefix = int(prefix)
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        return f"{(mask >> 24) & 0xFF}.{(mask >> 16) & 0xFF}.{(mask >> 8) & 0xFF}.{mask & 0xFF}"
    except Exception:
        return "255.255.255.0"


# ===== WINDOWS FIREWALL =====

def get_firewall_state():
    """
    Lay trang thai Windows Firewall cho 3 profile.
    Dung netsh lam nguon chinh (chinh xac hon PowerShell tren Server 2012).
    """
    if not IS_WINDOWS:
        return {
            "Domain": {"enabled": True, "inbound": "Block", "outbound": "Allow"},
            "Private": {"enabled": False, "inbound": "Block", "outbound": "Allow"},
            "Public": {"enabled": True, "inbound": "Block", "outbound": "Allow"}
        }

    result = {
        "Domain":  {"enabled": False, "inbound": "Block", "outbound": "Allow"},
        "Private": {"enabled": False, "inbound": "Block", "outbound": "Allow"},
        "Public":  {"enabled": False, "inbound": "Block", "outbound": "Allow"}
    }

    # === PHUONG PHAP 1: netsh (chinh xac nhat tren Server 2012) ===
    try:
        out = _run_cmd("netsh advfirewall show allprofiles")
        if out:
            current_prof = None
            for line in out.splitlines():
                line = line.strip()
                if "Domain Profile" in line:
                    current_prof = "Domain"
                elif "Private Profile" in line:
                    current_prof = "Private"
                elif "Public Profile" in line:
                    current_prof = "Public"
                elif current_prof and line.lower().startswith("state"):
                    parts = line.split()
                    if len(parts) >= 2:
                        state_val = parts[-1].upper()
                        result[current_prof]["enabled"] = (state_val == "ON")
                        print(f"[system_state] Firewall {current_prof}: State={state_val} -> enabled={result[current_prof]['enabled']}")
                elif current_prof and ("firewall policy" in line.lower() or "firewallpolicy" in line.lower()):
                    parts = line.split()
                    if parts:
                        policy = parts[-1].lower()
                        if "blockinbound" in policy:
                            result[current_prof]["inbound"] = "Block"
                        elif "allowinbound" in policy:
                            result[current_prof]["inbound"] = "Allow"
                        if "blockoutbound" in policy:
                            result[current_prof]["outbound"] = "Block"
                        elif "allowoutbound" in policy:
                            result[current_prof]["outbound"] = "Allow"

            if any(result[p].get("enabled") is not None for p in result):
                return result
    except Exception as e:
        print(f"[system_state] netsh firewall error: {e}")

    # === PHUONG PHAP 2: PowerShell fallback ===
    try:
        script = r"""
        $profiles = Get-NetFirewallProfile -ErrorAction SilentlyContinue
        $out = @()
        foreach ($p in $profiles) {
            $enabled = ($p.Enabled -eq $true) -or ($p.Enabled -eq 1) -or ([string]$p.Enabled -eq 'True')
            $out += "$($p.Name)|$enabled|$($p.DefaultInboundAction)|$($p.DefaultOutboundAction)"
        }
        $out -join "`n"
        """
        ps_out = _run_ps(script)
        if ps_out.strip():
            for line in ps_out.strip().splitlines():
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    enabled = parts[1].strip().lower() == "true"
                    if name in result:
                        result[name]["enabled"] = enabled
                        print(f"[system_state] PS Firewall {name}: enabled={enabled}")
    except Exception as e:
        print(f"[system_state] PowerShell firewall error: {e}")

    return result


def restore_firewall_state(fw_state):
    """Khoi phuc Windows Firewall ve trang thai luc backup"""
    if not IS_WINDOWS:
        print(f"[system_state] (Skip - non-Windows) Restore firewall: {fw_state}")
        return True

    profile_map = {"Domain": "domain", "Private": "private", "Public": "public"}
    for prof_name, settings in fw_state.items():
        netsh_prof = profile_map.get(prof_name)
        if not netsh_prof:
            continue
        state = "on" if settings.get("enabled") else "off"
        _run_cmd(f"netsh advfirewall set {netsh_prof}profile state {state}")
        print(f"[system_state] Firewall {prof_name} -> {state}")

        inbound = settings.get("inbound", "Block").lower()
        outbound = settings.get("outbound", "Allow").lower()
        _run_cmd(f"netsh advfirewall set {netsh_prof}profile firewallpolicy {inbound}inbound,{outbound}outbound")

    return True


# ===== WINDOWS DEFENDER =====

def get_defender_state():
    """Lay trang thai Windows Defender"""
    if not IS_WINDOWS:
        return {"realtime_enabled": True, "available": False}

    script = """
    try {
        $pref = Get-MpPreference -ErrorAction Stop
        @{
            realtime_enabled = -not $pref.DisableRealtimeMonitoring
            behavior_enabled = -not $pref.DisableBehaviorMonitoring
            ioav_enabled = -not $pref.DisableIOAVProtection
            available = $true
        } | ConvertTo-Json -Compress
    } catch {
        @{ available = $false } | ConvertTo-Json -Compress
    }
    """
    out = _run_ps(script)
    try:
        return json.loads(out) if out.strip() else {"available": False}
    except json.JSONDecodeError:
        return {"available": False}


def restore_defender_state(def_state):
    """Khoi phuc Windows Defender ve trang thai luc backup"""
    if not IS_WINDOWS:
        print(f"[system_state] (Skip - non-Windows) Restore defender: {def_state}")
        return True

    if not def_state.get("available"):
        print("[system_state] Defender khong kha dung, bo qua")
        return True

    rt = "$false" if def_state.get("realtime_enabled") else "$true"
    bh = "$false" if def_state.get("behavior_enabled") else "$true"
    io = "$false" if def_state.get("ioav_enabled") else "$true"

    script = f"""
    try {{
        Set-MpPreference -DisableRealtimeMonitoring {rt} -ErrorAction SilentlyContinue
        Set-MpPreference -DisableBehaviorMonitoring {bh} -ErrorAction SilentlyContinue
        Set-MpPreference -DisableIOAVProtection {io} -ErrorAction SilentlyContinue
        Write-Output "OK"
    }} catch {{
        Write-Output "FAIL: $_"
    }}
    """
    out = _run_ps(script)
    print(f"[system_state] Defender restore: {out.strip()}")
    return True


# ===== TONG HOP =====

def capture_system_state():
    """Capture toan bo system state"""
    state = {
        "platform": platform.platform(),
        "hostname": platform.node(),
        "adapters": get_network_adapters(),
        "firewall": get_firewall_state(),
        "defender": get_defender_state()
    }
    # Cau hinh mang nang cao: routing, hosts, firewall rules, shares, port proxy
    try:
        import network_advanced
        state["network_advanced"] = network_advanced.capture_network_advanced()
    except Exception as e:
        print(f"[system_state] Khong capture duoc network_advanced: {e}")
        state["network_advanced"] = {}
    return state


def restore_system_state(state):
    """Khoi phuc system state.
    Chi khoi phuc thanh phan CO trong backup (ho tro backup chon loc:
    tick muc nao thi chi muc do co trong state -> chi muc do duoc restore).
    """
    if "adapters" in state:
        print("[system_state] Restoring network adapters...")
        for adapter in state.get("adapters", []):
            try:
                restore_network_adapter(adapter)
            except Exception as e:
                print(f"  Error restoring {adapter.get('name')}: {e}")

    if "firewall" in state:
        print("[system_state] Restoring firewall...")
        try:
            restore_firewall_state(state.get("firewall", {}))
        except Exception as e:
            print(f"  Error: {e}")

    if "defender" in state:
        print("[system_state] Restoring defender...")
        try:
            restore_defender_state(state.get("defender", {}))
        except Exception as e:
            print(f"  Error: {e}")

    # Khoi phuc cau hinh mang nang cao (routing/hosts/shares/portproxy/firewall rules)
    if state.get("network_advanced"):
        try:
            import network_advanced
            network_advanced.restore_network_advanced(state["network_advanced"])
        except Exception as e:
            print(f"[system_state] Loi restore network_advanced: {e}")


def compare_system_state(backup_state, current_state):
    """So sanh system state luc backup vs hien tai"""
    diffs = []

    # Network adapter
    backup_adapters = {a["name"]: a for a in backup_state.get("adapters", [])}
    current_adapters = {a["name"]: a for a in current_state.get("adapters", [])}

    for name, b_adapter in backup_adapters.items():
        c_adapter = current_adapters.get(name)
        if not c_adapter:
            diffs.append(f"Adapter '{name}' khong ton tai luc restore")
            continue
        if b_adapter.get("mode") != c_adapter.get("mode"):
            diffs.append(f"Adapter '{name}': mode {c_adapter.get('mode')} -> {b_adapter.get('mode')}")

        # So sanh IPv4
        b_v4 = b_adapter.get("ipv4") or {
            "ip": b_adapter.get("ip"), "dhcp": b_adapter.get("dhcp")}
        c_v4 = c_adapter.get("ipv4") or {
            "ip": c_adapter.get("ip"), "dhcp": c_adapter.get("dhcp")}
        if b_v4.get("ip") != c_v4.get("ip"):
            diffs.append(f"Adapter '{name}': IPv4 dia chi {c_v4.get('ip')} -> {b_v4.get('ip')}")
        if b_v4.get("subnet_mask") != c_v4.get("subnet_mask"):
            diffs.append(f"Adapter '{name}': IPv4 subnet mask {c_v4.get('subnet_mask')} -> {b_v4.get('subnet_mask')}")
        if b_v4.get("dhcp") != c_v4.get("dhcp"):
            diffs.append(f"Adapter '{name}': IPv4 DHCP {c_v4.get('dhcp')} -> {b_v4.get('dhcp')}")
        if b_v4.get("gateway") != c_v4.get("gateway"):
            diffs.append(f"Adapter '{name}': IPv4 default gateway {c_v4.get('gateway')} -> {b_v4.get('gateway')}")

        # So sanh IPv6
        b_v6 = b_adapter.get("ipv6") or {}
        c_v6 = c_adapter.get("ipv6") or {}
        if b_v6.get("ip") != c_v6.get("ip"):
            diffs.append(f"Adapter '{name}': IPv6 dia chi {c_v6.get('ip')} -> {b_v6.get('ip')}")
        if b_v6.get("gateway") != c_v6.get("gateway"):
            diffs.append(f"Adapter '{name}': IPv6 default gateway {c_v6.get('gateway')} -> {b_v6.get('gateway')}")
        if b_v6.get("dhcp") != c_v6.get("dhcp"):
            diffs.append(f"Adapter '{name}': IPv6 DHCP {c_v6.get('dhcp')} -> {b_v6.get('dhcp')}")

    # Firewall
    for prof in ["Domain", "Private", "Public"]:
        b_fw = backup_state.get("firewall", {}).get(prof, {})
        c_fw = current_state.get("firewall", {}).get(prof, {})
        if b_fw.get("enabled") != c_fw.get("enabled"):
            diffs.append(f"Firewall {prof}: {c_fw.get('enabled')} -> {b_fw.get('enabled')}")

    # Defender
    b_def = backup_state.get("defender", {})
    c_def = current_state.get("defender", {})
    if b_def.get("realtime_enabled") != c_def.get("realtime_enabled"):
        diffs.append(f"Defender realtime: {c_def.get('realtime_enabled')} -> {b_def.get('realtime_enabled')}")

    # Network advanced
    if backup_state.get("network_advanced") and current_state.get("network_advanced"):
        try:
            import network_advanced
            na_diffs = network_advanced.compare_network_advanced(
                backup_state["network_advanced"],
                current_state["network_advanced"]
            )
            diffs.extend(na_diffs)
        except Exception as e:
            print(f"[system_state] Loi compare network_advanced: {e}")

    return diffs


if __name__ == "__main__":
    state = capture_system_state()
    print(json.dumps(state, indent=2, default=str))
