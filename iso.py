import struct

import atoms
from atoms import read_fcc, read_ulong, read_ulonglong


class UnsuportedVersion(Exception):
    pass

class FormatError(Exception):
    pass


def ellipsisize(l, num=4):
    if len(l) <= num:
        return l
    # ... for displaying, "ellipsisize!" :P
    return l[0:min(num, len(l) - 1)] + ['...'] + l[-1:]

def container_children(a):
    a = atoms.container(a)
    cd = atoms.atoms_dict(a.read_children())
    return a, cd

def read_mvhd(a):
    a = atoms.full(a)
    if a.v == 0:
        a.skip(8)
        ts = read_ulong(a.f)
        duration = read_ulong(a.f)
    elif a.v == 1:
        a.skip(16)
        ts = read_ulong(a.f)
        duration = read_ulonglong(a.f)
    else:
        raise UnsuportedVersion()
    # we don't care about the rest of fields, for the moment
    return a.type, ts, duration

def read_tkhd(a):
    a = atoms.full(a)
    if a.v == 0:
        a.skip(16)
        duration = read_ulong(a.f)
    elif a.v == 1:
        a.skip(24)
        duration = read_ulonglong(a.f)
    else:
        raise UnsuportedVersion()
    return a.type, duration

def read_mdhd(a):
    a = atoms.full(a)
    if a.v == 0:
        a.skip(8)
        ts = read_ulong(a.f)
        duration = read_ulong(a.f)
    elif a.v == 1:
        a.skip(16)
        ts = read_ulong(a.f)
        duration = read_ulonglong(a.f)
    else:
        raise UnsuportedVersion()
    return a.type, ts, duration

def read_stts(a):
    a = atoms.full(a)
    entries = read_ulong(a.f)
    table = [(read_ulong(a.f), read_ulong(a.f)) for _ in xrange(entries)]
    return a.type, entries, ellipsisize(table)

def read_ctts(a):
    a = atoms.full(a)
    entries = read_ulong(a.f)
    table = [(read_ulong(a.f), read_ulong(a.f)) for _ in xrange(entries)]
    return a.type, entries, table

def read_stss(a):
    a = atoms.full(a)
    entries = read_ulong(a.f)
    table = [read_ulong(a.f) for _ in xrange(entries)]
    return a.type, entries, ellipsisize(table)

def read_stsz(a):
    a = atoms.full(a)
    sample_size = read_ulong(a.f)
    entries = read_ulong(a.f)
    if sample_size == 0:
        sizes = [read_ulong(a.f) for _ in xrange(entries)]
    else:
        sizes = []
    return a.type, sample_size, entries, ellipsisize(sizes)

def read_stsc(a):
    a = atoms.full(a)
    entries = read_ulong(a.f)
    chunks = [(read_ulong(a.f), read_ulong(a.f), read_ulong(a.f))
              for _ in xrange(entries)]
    return a.type, entries, ellipsisize(chunks)

def read_stco(a):
    a = atoms.full(a)
    entries = read_ulong(a.f)
    table = [read_ulong(a.f) for _ in xrange(entries)]
    return a.type, entries, ellipsisize(table)

def read_co64(a):
    a = atoms.full(a)
    entries = read_ulong(a.f)
    table = [read_ulonglong(a.f) for _ in xrange(entries)]
    return a.type, entries, ellipsisize(table)

def read_stz2(a):
    a = atoms.full(a)
    field_size = read_ulong(a.f) & 0xff
    entries = read_ulong(a.f)

    def read_u16(f):
        return struct.unpack('>H', read_bytes(f, 2))[0]
    def read_u8(f):
        return read_bytes(f, 1)
    def read_2u4(f):
        b = read_bytes(f, 1)
        return (b >> 4) & 0x0f, b & 0x0f
    def flatten(l):
        ret = []
        for elt in l:
            ret.extend(elt)
        return ret
    if field_size == 16:
        sizes = [read_u16(a.f) for _ in xrange(entries)]
    elif field_size == 8:
        sizes = [read_u8(a.f) for _ in xrange(entries)]
    elif field_size == 4:
        sizes = flatten([read_2u4(a.f) for _ in xrange((entries + 1) / 2)])
    else:
        raise FormatError()

    return a.type, sample_size, entries, ellipsisize(sizes)

def read_stbl(a):
    a, cd = container_children(a)
    stss = cd.get('stss')
    stsz = cd.get('stsz')
    stz2 = cd.get('stz2')
    stco = cd.get('stco')
    co64 = cd.get('co64')
    return (a.type, cd, read_stts(cd.get('stts')[0]),
            read_stsc(cd.get('stsc')[0]),
            stss and read_stss(stss[0]) or '/no stss/',
            stsz and read_stsz(stsz[0]) or read_stz2(stz2[0]),
            stco and read_stco(stco[0]) or read_co64(co64[0]))

def read_minf(a):
    a, cd = container_children(a)
    return a.type, cd, read_stbl(cd.get('stbl')[0])

def read_mdia(a):
    a, cd = container_children(a)
    return (a.type, cd, read_mdhd(cd.get('mdhd')[0]),
            read_minf(cd.get('minf')[0]))

def read_trak(a):
    a, cd = container_children(a)
    return (a.type, cd, read_tkhd(cd.get('tkhd')[0]),
            read_mdia(cd.get('mdia')[0]))

def read_moov(a):
    a, cd = container_children(a)
    return (a.type, cd, read_mvhd(cd.get('mvhd')[0]),
            map(read_trak, cd.get('trak')))

def read_iso_file(fobj):
    fobj.seek(0)                # ??

    brand = 'mp41'
    version = 0

    a = atoms.read_atom(fobj)

    if a.type == 'ftyp':
        a.seek_to_data()
        brand = read_fcc(a.f)
        version = read_ulong(a.f)
        a.seek_to_end()

    d = atoms.atoms_dict(atoms.read_atoms(fobj))
    moov = d.get('moov')[0]
    return brand, hex(version), d, read_moov(moov)


if __name__ == '__main__':
    import sys
    f = file(sys.argv[1])
    import pprint
    pprint.pprint(read_iso_file(f))
