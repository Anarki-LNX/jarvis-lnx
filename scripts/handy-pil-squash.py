#!/usr/bin/env python3
"""Fuegt Qualcomm-Split-Firmware (name.mdt + name.bNN) zu einem .mbn zusammen (wie pil-squasher)."""
import struct, sys, os
out, mdt = sys.argv[1], sys.argv[2]
base = mdt[:-4]
hdr = open(mdt, 'rb').read()
assert hdr[:4] == b'\x7fELF'
is64 = hdr[4] == 2
if is64:
    phoff, = struct.unpack_from('<Q', hdr, 0x20); phentsize, phnum = struct.unpack_from('<HH', hdr, 0x36)
else:
    phoff, = struct.unpack_from('<I', hdr, 0x1c); phentsize, phnum = struct.unpack_from('<HH', hdr, 0x2a)
buf = bytearray()
def put(off, data):
    global buf
    if len(buf) < off + len(data): buf.extend(b'\0' * (off + len(data) - len(buf)))
    buf[off:off+len(data)] = data
put(0, hdr[:phoff + phentsize * phnum])
for i in range(phnum):
    p = phoff + i * phentsize
    if is64:
        _, _, off, _, _, filesz = struct.unpack_from('<IIQQQQ', hdr, p)
    else:
        _, off, _, _, filesz = struct.unpack_from('<IIIII', hdr, p)
    if filesz == 0: continue
    seg = f'{base}.b{i:02d}'
    if os.path.exists(seg):
        put(off, open(seg, 'rb').read()[:filesz])
    elif off + filesz <= len(hdr):
        put(off, hdr[off:off+filesz])
open(out, 'wb').write(buf)
print(out, len(buf))
