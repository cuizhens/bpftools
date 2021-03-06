import os
import struct
import subprocess
import sys

from pkg_resources import resource_filename


def find_binary(prefixes, name, args):
    for prefix in prefixes:
        try:
            subprocess.call([os.path.join(prefix, name)] + args)
        except OSError, e:
            continue
        return prefix
    print >> sys.stderr, prefix, "%r not found in your PATH nor LINUX_TOOLS_PATH" % (name,)
    os._exit(-2)


def bpf_compile(assembly):
    prefixes = ["",
                resource_filename(__name__, "."),
                resource_filename(__name__, os.path.join("..","linux_tools")),
                resource_filename(__name__, "linux_tools"),
                ".",
                "linux_tools",
                os.path.dirname(sys.argv[0]),
                os.path.realpath(os.path.dirname(sys.argv[0])),
                os.getenv("LINUX_TOOLS_PATH", "."),
                ]
    prefix = find_binary(prefixes, "bpf_asm", ['/dev/null'])

    out, err = subprocess.Popen([os.path.join(prefix, "bpf_asm")],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE).communicate(assembly)

    if set(out) - set(" ,0123456789\n") or not out:
        print >> sys.stderr, "Compiling failed with:\n%s\n" % (out.strip() + err.strip())
        os._exit(-3)
    return out.strip()


def _looks_like_ip(l2, off):
    if len(l2) - off >= 20:
        ipver, _, total_length = struct.unpack_from('!BBH', l2, off)
        if (ipver & 0xF0 == 0x40 and (ipver & 0x0f) >= 5):
            return 4

    if len(l2) - off >= 40:
        vertos, _, _,  pay_len, proto, ttl = struct.unpack_from('!BBHHBB', l2, off)
        if (vertos & 0xF0 == 0x60 and pay_len + off + 40 == len(l2)
            and ttl > 0):
            return 6
    return None


def find_ip_offset(l2, max_off=40):
    # first look for both ethernet and ip header
    for off in xrange(2, max_off+2, 2):
        if l2[off-2:off] == '\x08\x00' and _looks_like_ip(l2, off) == 4:
            return off
        if l2[off-2:off] == '\x86\xdd' and _looks_like_ip(l2, off) == 6:
            return off

    # okay, just look for ip header
    for off in xrange(0, max_off, 2):
        if _looks_like_ip(l2, off):
            return off

    return None


def do_scrub(l2, off):
    data = list(l2)
    if off not in (14, 16):
        raise Exception("off=%i Not ethernet, not sure how to scrub MACS" % off)
    for i in xrange(off-2):
        data[i] = '\x00'

    ipver = ord(data[off])
    if ipver & 0xF0 == 0x40:
        for i in xrange(off+12, off+12+4+4):
            data[i] = '\x00'
    elif ipver & 0xF0 == 0x60:
        for i in xrange(off+8, off+8+16+16):
            data[i] = '\x00'
    return ''.join(data)
