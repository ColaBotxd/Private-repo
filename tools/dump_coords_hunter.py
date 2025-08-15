# tools/dump_coords_hunter.py
# Offline dump analyzer: find X/Y/Heading floats and try to derive pointer chains from a WoW minidump.

import argparse, struct, sys
from collections import defaultdict

# Works across minidump versions
from minidump.minidumpfile import MinidumpFile

def f32(b): return struct.unpack("<f", b)[0]
def f64(b): return struct.unpack("<d", b)[0]
def u64(b): return struct.unpack("<Q", b)[0]

def within(v, t, tol):
    try: return abs(float(v) - float(t)) <= tol
    except: return False

def scan_for_values(mem_ranges, want_val, tol, kind="float"):
    """Yield (addr, value, kind) for matches near target value."""
    for base, buf in mem_ranges:
        mv = memoryview(buf)
        if kind == "float":
            step, read = 4, f32
        elif kind == "double":
            step, read = 8, f64
        else:
            continue
        for off in range(0, len(buf) - step + 1, step):
            try:
                val = read(mv[off:off+step])
                if val == val and within(val, want_val, tol):
                    yield base + off, float(val), kind
            except Exception:
                pass

def gather_mem_ranges(md: MinidumpFile):
    """
    Return list[(base, bytes)] of mapped regions.
    Supports: memory_info_list, memory64_list, memory_list.
    """
    out = []

    # 1) Preferred: memory_info_list (gives VA + size and file reader can map it)
    meminfo_list = getattr(getattr(md, "memory_info_list", None), "memory_info", None)
    if meminfo_list:
        reader = md.get_reader()
        for info in meminfo_list:
            base = getattr(info, "BaseAddress", None)
            size = int(getattr(info, "RegionSize", 0) or 0)
            if base is None or size <= 0:
                continue
            try:
                data = reader.read(base, size)
                out.append((base, data))
            except Exception:
                continue
        if out:
            return out

    # 2) Common with ProcDump: memory64_list (data is contiguous in file at BaseRva)
    mem64 = getattr(md, "memory64_list", None)
    if mem64:
        # Different libs expose names slightly differently; normalize with getattr
        base_rva = int(getattr(mem64, "BaseRva", getattr(mem64, "base_rva", 0)) or 0)
        # list element name can be "memories", "ranges", or "memory_ranges"
        ranges = getattr(mem64, "memories", None) or getattr(mem64, "ranges", None) or getattr(mem64, "memory_ranges", None) or []
        if base_rva and ranges:
            r = md.get_reader()
            cursor = base_rva
            for d in ranges:
                start = int(getattr(d, "StartOfMemoryRange", getattr(d, "start_of_memory_range", 0)) or 0)
                size  = int(getattr(d, "DataSize", getattr(d, "data_size", 0)) or 0)
                if size <= 0:
                    continue
                try:
                    data = r.read_at_rva(cursor, size)
                    out.append((start, data))
                    cursor += size
                except Exception:
                    # If one fails, continue — many segments still usable
                    continue
            if out:
                return out

    # 3) Fallback: memory_list (older style dumps)
    memlist = getattr(md, "memory_list", None)
    if memlist:
        memories = getattr(memlist, "memories", []) or []
        for d in memories:
            base = getattr(d, "start_of_memory_range", None)
            if base is None:
                continue
            try:
                data = d.read(md.file_handle)
                out.append((base, data))
            except Exception:
                continue

    return out

def list_modules(md: MinidumpFile):
    """Return [(name, base, size)] and tolerate field name changes."""
    mods = []
    modules = getattr(getattr(md, "modules", None), "modules", None)
    if not modules:
        return mods
    entries = list(modules)
    entries.sort(key=lambda m: getattr(m, "baseaddress", 0))
    for i, m in enumerate(entries):
        base = getattr(m, "baseaddress", 0)
        name = getattr(m, "name", "(unknown)")
        size = getattr(m, "sizeofimage", None)
        if size is None:
            size = getattr(m, "size_of_image", None)
        if size is None:
            # rough estimate to next module; if last, 16MB fallback
            next_base = getattr(entries[i+1], "baseaddress", 0) if i+1 < len(entries) else 0
            size = max(0, next_base - base) if next_base else 0x1000000
        mods.append((name, base, int(size)))
    return mods

def find_module(mods, name):
    key = name.lower()
    for nm, base, size in mods:
        low = nm.lower()
        if low.endswith(key) or low == key or key in low:
            return nm, base, size
    return None

def build_pointer_candidates(mem_ranges, target_addr, depth=4, max_offset=0x4000, module_base=None, module_end=None):
    """Conservative reverse pointer search to produce chains toward a module base."""
    index = defaultdict(list)
    for base, buf in mem_ranges:
        mv = memoryview(buf)
        for off in range(0, len(buf) - 8 + 1, 8):
            try:
                val = u64(mv[off:off+8])
                index[val].append(base + off)
            except Exception:
                pass

    chains = []

    def backtrack(current_addr, chain):
        if len(chain) >= depth:
            return
        for off in range(0, max_offset + 1, 4):
            want = current_addr - off
            locs = index.get(want)
            if not locs:
                continue
            for ptr_loc in locs:
                if module_base is not None and (module_base <= want < module_end):
                    chains.append([(ptr_loc, off)] + chain)
                    continue
                backtrack(ptr_loc, [(ptr_loc, off)] + chain)

    backtrack(target_addr, [])
    uniq, seen = [], set()
    for ch in chains:
        t = tuple(ch)
        if t in seen: continue
        seen.add(t); uniq.append(ch)
    return uniq

def pretty_chain(chain, module_name, module_base):
    if not chain: return ""
    first_ptr, first_off = chain[0]
    head = f"{module_name}+0x{first_ptr - module_base:X} -> +0x{first_off:X}"
    rest = " -> ".join(f"+0x{off:X}" for (_loc, off) in chain[1:])
    return head if not rest else f"{head} -> {rest}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, help='Path to wow_full.dmp (quote if path has spaces)')
    ap.add_argument("--x", type=float, required=True, help="Known X at dump time")
    ap.add_argument("--y", type=float, required=True, help="Known Y at dump time")
    ap.add_argument("--heading", type=float, help="Known heading at dump time (deg or rad)")
    ap.add_argument("--deg", action="store_true", help="Heading is in degrees (default)")
    ap.add_argument("--rad", dest="deg", action="store_false", help="Heading is in radians")
    ap.add_argument("--tol", type=float, default=0.5, help="Tolerance for coords")
    ap.add_argument("--htol", type=float, default=2.0, help="Tolerance for heading")
    ap.add_argument("--module", default="Wow.exe", help="Anchor module name (e.g., WowClassic.exe)")
    ap.add_argument("--depth", type=int, default=4, help="Max pointer depth")
    ap.add_argument("--maxoff", type=lambda s: int(s,0), default="0x4000", help="Max field offset per hop")
    args = ap.parse_args()

    print(f"[+] Loading dump: {args.dump}")
    md = MinidumpFile.parse(args.dump)

    mods = list_modules(md)
    print("[+] Modules:")
    for nm, base, size in mods:
        print(f"    {nm:60s}  base=0x{base:016X}  size=0x{size:X}")

    anchor = find_module(mods, args.module)
    if not anchor:
        print(f"[!] Anchor module '{args.module}' not found among above modules."); sys.exit(2)
    mod_name, mod_base, mod_size = anchor
    print(f"[+] Using anchor: {mod_name} base=0x{mod_base:016X} size=0x{mod_size:X}")

    mem_ranges = gather_mem_ranges(md)
    print(f"[+] Scanning {len(mem_ranges)} ranges… (this can take a few minutes on big dumps)")

    # X / Y candidates (float + double)
    x_hits = list(scan_for_values(mem_ranges, args.x, args.tol, "float")) + \
             list(scan_for_values(mem_ranges, args.x, args.tol, "double"))
    y_hits = list(scan_for_values(mem_ranges, args.y, args.tol, "float")) + \
             list(scan_for_values(mem_ranges, args.y, args.tol, "double"))
    print(f"[+] X candidates: {len(x_hits)}")
    print(f"[+] Y candidates: {len(y_hits)}")

    # Optional heading
    h_hits = []
    if args.heading is not None:
        h_hits = list(scan_for_values(mem_ranges, args.heading, args.htol, "float")) + \
                 list(scan_for_values(mem_ranges, args.heading, args.htol, "double"))
        print(f"[+] Heading candidates: {len(h_hits)}")

    def show(label, hits, n=10):
        print(f"\n--- {label} (top {min(n,len(hits))}) ---")
        for addr, val, kind in hits[:n]:
            print(f"0x{addr:016X}  {val:.6f}  ({kind})")

    show("X", x_hits)
    show("Y", y_hits)
    if h_hits: show("Heading", h_hits)

    def chains_for(label, hits):
        if not hits:
            print(f"[!] No {label} hits to backtrace."); return
        addr = hits[0][0]
        print(f"\n[+] Backtracing {label} @ 0x{addr:016X}")
        chains = build_pointer_candidates(
            mem_ranges, addr, depth=args.depth, max_offset=args.maxoff,
            module_base=mod_base, module_end=mod_base+mod_size
        )
        if not chains:
            print(f"[!] No chains found for {label}. Try increasing --depth or --maxoff."); return
        scored = []
        for ch in chains:
            first_ptr, _ = ch[0]
            in_mod = (mod_base <= first_ptr < mod_base + mod_size)
            score = (0 if in_mod else 1, len(ch))  # prefer in-mod + shorter
            scored.append((score, ch))
        scored.sort(key=lambda t: t[0])
        for i, (_, ch) in enumerate(scored[:10], 1):
            print(f"  [{i}] {pretty_chain(ch, mod_name, mod_base)}")

    chains_for("X", x_hits)
    chains_for("Y", y_hits)
    if h_hits: chains_for("Heading", h_hits)

if __name__ == "__main__":
    main()
