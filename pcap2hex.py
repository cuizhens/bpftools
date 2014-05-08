#!/usr/bin/env python

import getopt
import os
import sys
import string
import struct
import pcappy


def usage():
    print """
pcap2hex.py [ OPTIONS ] [ file... ]

Read pcap from stdin or given pcap files and print hex-encoded
packets. Additionally pcap2hex can normalize DLT_LINUX_SLL l2 header
(used by "tcpdump -i any") to something that looks more like
DLT_EN10MB (by "tcpdump -i eth0"). Pcap2hex can also scrub (anonymize)
packets by overwriting l2 MAC addresses and l3 IPv4 and IPv6 addresses
with zeros.

Options are:
  -h, --help         print this message
  -s, --scrub        scrub/anonymize MAC and IP addresses
  -n, --no-normalize don't normalize L2 headers from 16 to
                     14 bytes (from DLT_LINUX_SLL to DLT_EN10MB)
  -a, --ascii        print printable asci characters
""".lstrip()
    sys.exit(2)

def main():
    scrub = ascii = False
    normalize = True

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hsnaA",
                                   ["help", "scrub", "no-normalize", "ascii"])
    except getopt.GetoptError as err:
        print str(err)
        usage()

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
        elif o in ("-s", "--scrub"):
            scrub = True
        elif o in ("-n", "--no-normalize"):
            normalize = False
        elif o in ("-a", "-A", "--ascii"):
            ascii = True
        else:
            assert False, "unhandled option"

    if not args:
        readfds = [sys.stdin]
    else:
        readfds = [open(fname, 'rb') for fname in args]

    off = None

    for fd in readfds:
        p = pcappy.open_offline(fd)

        while True:
            try:
                r = p.next_ex()
            except pcappy.PcapPyException:
                break
            if r is None:
                break
            hdr, data = r

            if off is None:
                off = find_ip_offset(data)

            if scrub:
                data = do_scrub(data, off)

            if normalize and off in (16,):
                data = data[2:]

            h = data.encode('hex')
            if not ascii:
                print h
            else:
                s = ''.join([c if (c in string.printable and
                                   c not in string.whitespace) else '.'
                             for c in data])

                print "%s\t%s" % (h, s)


def _looks_like_ip(l2, off):
    ipver, _, total_length = struct.unpack_from('!BBH', l2, off)
    if (ipver & 0xF0 == 0x40 and (ipver & 0x0f) >= 5
        and total_length + off == len(l2)):
        return 4

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

    raise Exception("can't find an IP header")


def do_scrub(l2, off):
    data = list(l2)
    if off not in (14, 16):
        raise Exception("off=%i Not ethernet, not sure how to scrub MACS" % off)
    for i in xrange(12):
        data[i] = '\x00'
    ipver, = struct.unpack_from('!B', l2, off)
    if ipver & 0xF0 == 0x40:
        for i in xrange(off+12, off+12+4+4):
            data[i] = '\x00'
    elif ipver & 0xF0 == 0x60:
        for i in xrange(off+8, off+8+16+16):
            data[i] = '\x00'
    else:
        assert False, "neither ipv4 or 6"
    return ''.join(data)


if __name__ == "__main__":
    try:
        main()
    except IOError, e:
        if e.errno == 32:
            os._exit(-1)
        else:
            raise e
    except KeyboardInterrupt:
        os._exit(-1)

    # normal exit crashes due to a double free error in pcappy
    os._exit(0)
