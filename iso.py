import struct

import atoms
from atoms import read_fcc, read_ulong, read_ulonglong


def write_ulong(fobj, n):
    fobj.write(struct.pack('>L', n))

def write_ulonglong(fobj, n):
    fobj.write(struct.pack('>Q', n))

def write_fcc(fobj, fcc_str):
    # print '[wfcc]: @%d %r' % (fobj.tell(), fcc_str)
    fobj.write('%-4.4s' % fcc_str)


class UnsuportedVersion(Exception):
    pass

class FormatError(Exception):
    pass

class CannotSelect(Exception):
    pass


class AttribInitializer(type):
    def __new__(meta, classname, bases, classdict):
        if '_fields' in classdict:
            fields = classdict['_fields']
            orig_init = classdict.pop('__init__', None)
            def __init__(self, *a, **kw):
                f_dict = {}
                for f in fields:
                    f_dict[f] = kw.pop(f, None)
                if orig_init:
                    self.__dict__.update(f_dict)
                    orig_init(self, *a, **kw)
                elif bases and bases[0] != object:
                    super(self.__class__, self).__init__(*a, **kw)
                    self.__dict__.update(f_dict)
            classdict['__init__'] = __init__
            if '__repr__' not in classdict:
                def __repr__(self):
                    r = '%s(%s)' % (self.__class__.__name__,
                                    ', '.join(['%s=%r' % (n, getattr(self, n))
                                               for n in fields]))
                    return r
                classdict['__repr__'] = __repr__
        return type.__new__(meta, classname, bases, classdict)

class Box(object):
    __metaclass__ = AttribInitializer
    def __init__(self, atom):
        self._atom = atom

    def get_size(self):
        # should be overriden in the boxes we want to be able to modify
        return self._atom.get_size()

    def get_offset(self):
        return self._atom.get_offset()

    def copy(self, *a, **kw):
        cls = self.__class__
        if getattr(self, '_fields', None):
            attribs = dict([(k, getattr(self, k)) for k in self._fields])
            attribs.update(dict([(k, kw[k]) for k in self._fields if k in kw]))
        else:
            attribs = {}
        return cls(self._atom, **attribs)

    def write(self, fobj):
        # print '[ b] writing:', self
        self._atom.write(fobj)

    def write_head(self, fobj):
        # assuming 'short' sizes for now - FIXME!
        # print '[ b] writing head:', self._atom
        a = self._atom
        write_ulong(fobj, self.get_size())
        write_fcc(fobj, a.type)

class FullBox(Box):
    def tabled_size(self, body_size, loop_size):
        # TODO: move to a separate TableFullBox subclass?
        return (self._atom.head_size_ext() + body_size +
                len(self.table) * loop_size)

    def write_head(self, fobj):
        Box.write_head(self, fobj)
        a = self._atom
        write_ulong(fobj, (a.v & 0xff) << 24 | (a.flags & 0xffffff))

class ContainerBox(Box):
    def get_size(self):
        # print '[>] getting size: %r' % self._atom
        fields = getattr(self, '_fields', [])
        cd = self._atom.get_children_dict()
        size = self._atom.head_size_ext()
        for k, v in cd.items():
            if k in fields:
                v = getattr(self, k)
                if not isinstance(v, (tuple, list)):
                    if v is None:
                        v = []
                    else:
                        v = [v]
            # print 'size for %r = %r' % (sum([a.get_size() for a in v]), v)
            size += sum([a.get_size() for a in v])
        # print '[<] getting size: %r = %r' % (self._atom, size)
        return size

    def write(self, fobj):
        self.write_head(fobj)

        fields = getattr(self, '_fields', [])
        cd = self._atom.get_children_dict()
        to_write = []
        for k, v in cd.items():
            if k in fields:
                v = getattr(self, k)
                if not isinstance(v, (tuple, list)):
                    if v is None:
                        v = []
                    else:
                        v = [v]
            to_write.extend(v)

        def _get_offset(a):
            return a.get_offset()

        to_write.sort(key=_get_offset)

        # print '[  ] going to write:', \
        #     ([(isinstance(a, Box) and a._atom.type or a.type)
        #       for a in to_write])
        for ca in to_write:
            # print '[cb] writing:', ca
            ca.write(fobj)

def fullboxread(f):
    def _with_full_atom_read_wrapper(cls, a):
        return f(cls, atoms.full(a))
    return _with_full_atom_read_wrapper

def containerboxread(f):
    def _with_container_atom_read_wrapper(cls, a):
        return f(cls, atoms.container(a))
    return _with_container_atom_read_wrapper

def ver_skip(atom, sizes):
    if atom.v > len(sizes) or atom.v < 0:
        raise UnsuportedVersion('version requested: %d' % atom.v)
    atom.skip(sizes[atom.v])

def ver_read(atom, readers):
    if atom.v > len(readers) or atom.v < 0:
        raise UnsuportedVersion('version requested: %d' % atom.v)
    return readers[atom.v](atom.f)

def maybe_build_atoms(atype, alist):
    cls = globals().get(atype)
    if cls and issubclass(cls, Box):
        return map(cls.read, alist)
    return alist

def select_children_atoms(a, *selection):
    return select_atoms(a.get_children_dict(), *selection)

def select_atoms(ad, *selection):
    """ad: atom dict
    selection: [(type, min_required, max_required), ...]"""
    selected = []
    for atype, req_min, req_max in selection:
        alist = ad.get(atype, [])
        found = len(alist)
        if ((req_min is not None and found < req_min) or
            (req_max is not None and found > req_max)):
            raise CannotSelect('requested number of atoms %r: in [%s; %s],'
                               ' found: %d (all children: %r)' %
                               (atype, req_min, req_max, found, ad))
        alist = maybe_build_atoms(atype, alist)
        if req_max == 1:
            if found == 0:
                selected.append(None)
            else:
                selected.append(alist[0])
        else:
            selected.append(alist)
    return selected

def ellipsisize(l, num=4):
    if len(l) <= num:
        return l
    # ... for displaying, "ellipsisize!" :P
    return l[0:min(num, len(l) - 1)] + ['...'] + l[-1:]

def container_children(a):
    a = atoms.container(a)
    cd = atoms.atoms_dict(a.read_children())
    return a, cd

def find_cut_stts(stts, mt):
    "stts - table of the 'stts' atom; mt - media time"
    current = 0
    trimmed = None
    i, n = 0, len(stts)
    while i < n:
        count, delta = stts[i]
        cdelta = count * delta
        if mt == current:
            trimmed = stts[i + 1:]
            break
        elif mt < current + cdelta:
            new_count = count - (mt - current) / delta
            trimmed = [(new_count, delta)] + stts[i + 1:]
            break
        current += cdelta
        i += 1
    return trimmed or stts

def find_samplenum_stts(stts, mt):
    "stts - table of the 'stts' atom; mt - media time"
    ctime = 0
    samples = 1
    i, n = 0, len(stts)
    while i < n:
        if mt == ctime:
            break
        count, delta = stts[i]
        cdelta = count * delta
        if mt < ctime + cdelta:
            samples += (mt - ctime) // delta
            break
        ctime += cdelta
        samples += count
        i += 1

    return samples

def find_mediatime_stts(stts, sample):
    ctime = 0
    samples = 1
    i, n = 0, len(stts)
    while i < n:
        count, delta = stts[i]
        if samples + count >= sample:
            return ctime + (sample - samples) * delta
        ctime += count * delta
        samples += count
    return ctime

def find_chunknum_stsc(stsc, sample_num):
    current = 1                 # 1-based indices!
    per_chunk = 0
    samples = 1
    i, n = 0, len(stsc)
    while i < n:
        next, next_per_chunk, _sdidx = stsc[i]
        samples_here = (next - current) * per_chunk
        if samples + samples_here > sample_num:
            break
        samples += samples_here
        current, per_chunk = next, next_per_chunk
        i += 1
    return int((sample_num - samples) // per_chunk + current)

def get_chunk_offset(stco64, chunk_num):
    # 1-based indices!
    return stco64[chunk_num - 1]

class mvhd(FullBox):
    _fields = (
        # 'creation_time', 'modification_time',
        'timescale', 'duration',
        # 'rate', 'volume', 'matrix', 'next_track_ID'
        )

    @classmethod
    @fullboxread
    def read(cls, a):
        ver_skip(a, (8, 16))
        ts = read_ulong(a.f)
        d = ver_read(a, (read_ulong, read_ulonglong))
        return cls(a, timescale=ts, duration=d)

    def write(self, fobj):
        self.write_head(fobj)
        a = self._atom
        a.seek_to_start()
        a.skip(a.head_size_ext())

        if a.v == 0:
            fobj.write(a.read_bytes(8))
            write_ulong(fobj, self.timescale)
            write_ulong(fobj, self.duration)
            a.skip(8)
        elif a.v == 1:
            fobj.write(a.read_bytes(16))
            write_ulong(fobj, self.timescale)
            write_ulonglong(fobj, self.duration)
            a.skip(12)
        else:
            raise RuntimeError()

        fobj.write(a.read_bytes(80))

class tkhd(FullBox):
    _fields = ('duration',)

    @classmethod
    @fullboxread
    def read(cls, a):
        ver_skip(a, (16, 24))
        d = ver_read(a, (read_ulong, read_ulonglong))
        return cls(a, duration=d)

    def write(self, fobj):
        self.write_head(fobj)
        a = self._atom
        a.seek_to_start()
        a.skip(a.head_size_ext())

        if a.v == 0:
            fobj.write(a.read_bytes(16))
            write_ulong(fobj, self.duration)
            a.skip(4)
        elif a.v == 1:
            fobj.write(a.read_bytes(24))
            write_ulonglong(fobj, self.duration)
            a.skip(8)
        else:
            raise RuntimeError()

        fobj.write(a.read_bytes(60))

class mdhd(FullBox):
    _fields = ('timescale', 'duration')

    @classmethod
    @fullboxread
    def read(cls, a):
        ver_skip(a, (8, 16))
        ts = read_ulong(a.f)
        d = ver_read(a, (read_ulong, read_ulonglong))
        return cls(a, timescale=ts, duration=d)

    def write(self, fobj):
        self.write_head(fobj)
        a = self._atom
        a.seek_to_start()
        a.skip(a.head_size_ext())

        if a.v == 0:
            fobj.write(a.read_bytes(8))
            write_ulong(fobj, self.timescale)
            write_ulong(fobj, self.duration)
            a.skip(8)
        elif a.v == 1:
            fobj.write(a.read_bytes(16))
            write_ulong(fobj, self.timescale)
            write_ulonglong(fobj, self.duration)
            a.skip(12)
        else:
            raise RuntimeError()

        fobj.write(a.read_bytes(4))

class stts(FullBox):
    _fields = ('table',)

    @classmethod
    @fullboxread
    def read(cls, a):
        entries = read_ulong(a.f)
        t = [(read_ulong(a.f), read_ulong(a.f)) for _ in xrange(entries)]
        return cls(a, table=t)

    def get_size(self):
        return self.tabled_size(4, 8)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, len(self.table))
        for elt in self.table:
            write_ulong(fobj, elt[0])
            write_ulong(fobj, elt[1])

class ctts(FullBox):
    _fields = ('table',)

    @classmethod
    @fullboxread
    def read(cls, a):
        entries = read_ulong(a.f)
        t = [(read_ulong(a.f), read_ulong(a.f)) for _ in xrange(entries)]
        return cls(a, table=t)

    def get_size(self):
        return self.tabled_size(4, 8)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, len(self.table))
        for elt in self.table:
            write_ulong(fobj, elt[0])
            write_ulong(fobj, elt[1])

class stss(FullBox):
    _fields = ('table',)

    @classmethod
    @fullboxread
    def read(cls, a):
        entries = read_ulong(a.f)
        t = [read_ulong(a.f) for _ in xrange(entries)]
        return cls(a, table=t)

    def get_size(self):
        return self.tabled_size(4, 4)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, len(self.table))
        for elt in self.table:
            write_ulong(fobj, elt)

class stsz(FullBox):
    _fields = ('sample_size', 'table')

    @classmethod
    @fullboxread
    def read(cls, a):
        ss = read_ulong(a.f)
        entries = read_ulong(a.f)
        if ss == 0:
            t = [read_ulong(a.f) for _ in xrange(entries)]
        else:
            t = []
        return cls(a, sample_size=ss, table=t)

    def get_size(self):
        if self.sample_size != 0:
            return self._atom.head_size_ext() + 8
        return self.tabled_size(8, 4)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, self.sample_size)
        write_ulong(fobj, len(self.table))
        if self.sample_size == 0:
            for elt in self.table:
                write_ulong(fobj, elt)

class stsc(FullBox):
    _fields = ('table',)

    @classmethod
    @fullboxread
    def read(cls, a):
        entries = read_ulong(a.f)
        t = [(read_ulong(a.f), read_ulong(a.f), read_ulong(a.f))
             for _ in xrange(entries)]
        return cls(a, table=t)

    def get_size(self):
        return self.tabled_size(4, 12)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, len(self.table))
        for elt in self.table:
            write_ulong(fobj, elt[0])
            write_ulong(fobj, elt[1])
            write_ulong(fobj, elt[2])

class stco(FullBox):
    _fields = ('table',)

    @classmethod
    @fullboxread
    def read(cls, a):
        entries = read_ulong(a.f)
        t = [read_ulong(a.f) for _ in xrange(entries)]
        return cls(a, table=t)

    def get_size(self):
        return self.tabled_size(4, 4)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, len(self.table))
        for elt in self.table:
            write_ulong(fobj, elt)

class co64(FullBox):
    _fields = ('table',)

    @classmethod
    @fullboxread
    def read(cls, a):
        entries = read_ulong(a.f)
        t = [read_ulonglong(a.f) for _ in xrange(entries)]
        return cls(a, table=t)

    def get_size(self):
        return self.tabled_size(4, 8)

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, len(self.table))
        for elt in self.table:
            write_ulonglong(fobj, elt)

class stz2(FullBox):
    _fields = ('field_size', 'table')

    @classmethod
    @fullboxread
    def read(cls, a):
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
            t = [read_u16(a.f) for _ in xrange(entries)]
        elif field_size == 8:
            t = [read_u8(a.f) for _ in xrange(entries)]
        elif field_size == 4:
            t = flatten([read_2u4(a.f) for _ in xrange((entries + 1) / 2)])
        else:
            raise FormatError()
        return cls(a, field_size=field_size, table=t)

    def get_size(self):
        fs = self.field_size / 8.0
        return int(self.tabled_size(8, fs))

    def write(self, fobj):
        self.write_head(fobj)
        write_ulong(fobj, self.field_size & 0xff)
        write_ulong(fobj, len(self.table))

        def write_u16(f, n):
            fobj.write(struct.pack('>H', n))
        def write_u8(f, n):
            fobj.write(struct.pack('B', n))
        def write_2u4(f, n, m):
            fobj.write(struct.pack('B', ((n & 0x0f) << 4) | (m & 0x0f)))
        def takeby(seq, n):
            return [seq[i:i + n] for i in xrange(0, len(seq), n)]
        if field_size == 16:
            for elt in self.table:
                write_u16(fobj, elt)
        elif field_size == 8:
            for elt in self.table:
                write_u8(fobj, elt)
        elif field_size == 4:
            for elt in takeby(self.table, 2):
                write_2u4(fobj, *elt)
        else:
            raise FormatError()

class stbl(ContainerBox):
    _fields = ('stss', 'stsz', 'stz2', 'stco', 'co64', 'stts', 'ctts', 'stsc')

    @classmethod
    @containerboxread
    def read(cls, a):
        (astss, astsz, astz2, astco, aco64, astts, actts, astsc) = \
            select_children_atoms(a, ('stss', 0, 1), ('stsz', 0, 1),
                                  ('stz2', 0, 1), ('stco', 0, 1),
                                  ('co64', 0, 1), ('stts', 1, 1),
                                  ('ctts', 0, 1), ('stsc', 1, 1))
        return cls(a, stss=astss, stsz=astsz, stz2=astz2, stco=astco,
                   co64=aco64, stts=astts, ctts=actts, stsc=astsc)

class minf(ContainerBox):
    _fields = ('stbl',)

    @classmethod
    @containerboxread
    def read(cls, a):
        (astbl,) = select_children_atoms(a, ('stbl', 1, 1))
        return cls(a, stbl=astbl)

class mdia(ContainerBox):
    _fields = ('mdhd', 'minf')

    @classmethod
    @containerboxread
    def read(cls, a):
        (amdhd, aminf) = select_children_atoms(a, ('mdhd', 1, 1),
                                               ('minf', 1, 1))
        return cls(a, mdhd=amdhd, minf=aminf)

class trak(ContainerBox):
    _fields = ('tkhd', 'mdia')

    @classmethod
    @containerboxread
    def read(cls, a):
        (atkhd, amdia) = select_children_atoms(a, ('tkhd', 1, 1),
                                               ('mdia', 1, 1))
        return cls(a, tkhd=atkhd, mdia=amdia)

class moov(ContainerBox):
    _fields = ('mvhd', 'trak')

    @classmethod
    @containerboxread
    def read(cls, a):
        (amvhd, traks) = select_children_atoms(a, ('mvhd', 1, 1),
                                               ('trak', 1, None))
        return cls(a, mvhd=amvhd, trak=traks)

class ftyp(Box):
    _fields = ('brand', 'version')

    @classmethod
    def read(cls, a):
        a.seek_to_data()
        brand = read_fcc(a.f)
        v = read_ulong(a.f)
        return cls(a, brand=brand, version=v)

def read_iso_file(fobj):
    fobj.seek(0)

    al = list(atoms.read_atoms(fobj))
    ad = atoms.atoms_dict(al)
    aftyp, amoov, mdat = select_atoms(ad, ('ftyp', 1, 1), ('moov', 1, 1),
                                      ('mdat', 1, None))
    print '(first mdat offset: %d)' % mdat[0].offset

    return aftyp, amoov, al

def find_cut_trak_info(atrak, t):
    ts = atrak.mdia.mdhd.timescale
    stbl = atrak.mdia.minf.stbl
    mt = int(t * ts)
    print 'finding cut for trak %r @ time %r (%r/%r)' % (atrak._atom, t, mt, ts)
    sample = find_samplenum_stts(stbl.stts.table, mt)
    chunk = find_chunknum_stsc(stbl.stsc.table, sample)
    print 'found sample: %d and chunk: %d/%r' % (sample, chunk, stbl.stsc.table[-1])
    stco64 = stbl.stco or stbl.co64
    chunk_offset = get_chunk_offset(stco64.table, chunk)
    zero_offset = get_chunk_offset(stco64.table, 1)
    return sample, chunk, zero_offset, chunk_offset

def cut_stco64(stco64, chunk_num, offset_change):
    new_table = [offset - offset_change for offset in stco64[chunk_num - 1:]]
    return new_table

def cut_stsc(stsc, chunk_num):
    i, n = 0, len(stsc)
    current, per_chunk, sdidx = None, None, None
    while i < n:
        next, next_per_chunk, next_sdidx = stsc[i]
        if next > chunk_num:
            offset = chunk_num - 1
            return ([(1, per_chunk, sdidx)]
                    + [(c - offset, p_c, i) for (c, p_c, i) in stsc[i:]])
        current, per_chunk, sdidx = next, next_per_chunk, next_sdidx
        i += 1
    return [(1, per_chunk, sdidx)]

def cut_sctts(sctts, sample):
    samples = 1
    i, n = 0, len(sctts)
    while i < n:
        count, delta = sctts[i]
        if samples + count > sample:
            return [(samples + count - sample, delta)] + sctts[i+1:]
        samples += count
        i += 1
    return []                   # ? :/

def cut_stss(stss, sample):
    i, n = 0, len(stss)
    while i < n:
        snum = stss[i]
        if snum >= sample:
            return [s - sample + 1 for s in stss[i:]]
        i += 1
    return []

def cut_stsz2(stsz2, sample):
    if not stsz2:
        return []
    return stsz2[sample - 1:]

def cut_trak(atrak, sample, data_offset_change):
    stbl = atrak.mdia.minf.stbl
    chunk = find_chunknum_stsc(stbl.stsc.table, sample)
    print 'cutting trak: %r @ sample %d [chnk %d]' % (atrak._atom, sample, chunk)
    media_time_diff = find_mediatime_stts(stbl.stts.table, sample) # - 0
    new_media_duration = atrak.mdia.mdhd.duration - media_time_diff

    
    """
    cut_stco64()
    cut_stsc()
    cut_stsz2()
    cut_sctts(stts)
    cut_sctts(ctts)
    cut_stss()
    """
    
    stco64 = stbl.stco or stbl.co64
    new_stco64 = stco64.copy(table=cut_stco64(stco64.table, chunk,
                                              data_offset_change))
    print 'stco:'
    print '\t', len(stco64.table)
    print '\t', len(new_stco64.table)


    new_stsc = stbl.stsc.copy(table=cut_stsc(stbl.stsc.table, chunk))
    print 'stsc:'
    print '\t', stbl.stsc.table
    print '\t', new_stsc.table

    stsz2 = stbl.stsz or stbl.stz2
    new_stsz2 = stsz2.copy(table=cut_stsz2(stsz2.table, sample))

    new_stts = stbl.stts.copy(table=cut_sctts(stbl.stts.table, sample))

    new_ctts = None
    if stbl.ctts:
        new_ctts = stbl.ctts.copy(table=cut_sctts(stbl.ctts.table, sample))

    new_stss = None
    if stbl.stss:
        new_stss = stbl.stss.copy(table=cut_stss(stbl.stss.table, sample))

    """
    new_mdhd = atrak.mdia.mdhd.copy()
    new_minf = atrak.mdia.minf.copy()
    new_mdia = atrak.mdia.copy()
    new_trak = atrak.copy()
    """

    stbl_attribs = dict(stts=new_stts, stsc=new_stsc)
    stbl_attribs[stbl.stco and 'stco' or 'co64'] = new_stco64
    stbl_attribs[stbl.stsz and 'stsz' or 'stz2'] = new_stsz2
    if new_ctts:
        stbl_attribs['ctts'] = new_ctts
    if new_stss:
        stbl_attribs['stss'] = new_stss

    new_stbl = stbl.copy(**stbl_attribs)
    new_minf = atrak.mdia.minf.copy(stbl=new_stbl)
    new_mdhd = atrak.mdia.mdhd.copy(duration=new_media_duration)
    new_mdia = atrak.mdia.copy(mdhd=new_mdhd, minf=new_minf)
    new_tkhd = atrak.tkhd.copy()
    new_trak = atrak.copy(tkhd=new_tkhd, mdia=new_mdia)

    # print 'old trak:'
    # print atrak

    return new_trak

def update_offsets(atrak, data_offset_change):
    """
    cut_stco64(stco64, 1, ...)  # again, after calculating new size of moov
    atrak.mdia.mdhd.duration = new_duration
    """

    # print 'offset updates:'
    # print atrak

    stbl = atrak.mdia.minf.stbl
    stco64 = stbl.stco or stbl.co64
    stco64.table = cut_stco64(stco64.table, 1, data_offset_change)

    # print atrak
    # print

def cut_moov(amoov, t):
    ts = amoov.mvhd.timescale
    duration = amoov.mvhd.duration
    if t * ts >= duration:
        raise RuntimeError('Exceeded file duration: %r' %
                           (duration / float(ts)))
    traks = amoov.trak
    print 'movie timescale: %d, num tracks: %d' % (ts, len(traks))
    print
    cut_info = map(lambda a: find_cut_trak_info(a, t), traks)
    print 'cut_info:', cut_info
    new_data_offset = min([ci[3] for ci in cut_info])
    zero_offset = min([ci[2] for ci in cut_info])
    print 'new offset: %d, delta: %d' % (new_data_offset,
                                         new_data_offset - zero_offset)

    new_traks = map(lambda a, ci: cut_trak(a, ci[0],
                                           new_data_offset - zero_offset),
                    traks, cut_info)

    new_moov = amoov.copy(mvhd=amoov.mvhd.copy(), trak=new_traks)

    moov_size_diff = amoov.get_size() - new_moov.get_size()
    print ('moov_size_diff', moov_size_diff, amoov.get_size(),
           new_moov.get_size())
    print 'real moov sizes', amoov._atom.size, new_moov._atom.size
    print 'new mdat start', zero_offset - moov_size_diff - 8

    def update_trak_duration(atrak):
        amdhd = atrak.mdia.mdhd
        new_duration = amdhd.duration * ts // amdhd.timescale # ... different
                                                                # rounding? :/
        atrak.tkhd.duration = new_duration

    # print

    map(update_trak_duration, new_traks)
    map(lambda a: update_offsets(a, moov_size_diff), new_traks)

    return new_moov, new_data_offset - zero_offset, new_data_offset


def _split_headers(f, out_f, t):
    aftype, amoov, alist = read_iso_file(f)
    nmoov, delta, new_offset = cut_moov(amoov, t)

    i, n = 0, len(alist)
    while i < n:
        a = alist[i]
        i += 1
        if a.type == 'moov':
            break
        a.write(out_f)

    nmoov.write(out_f)

    while i < n:
        a = alist[i]
        i += 1
        if a.type == 'mdat':
            break
        a.write(out_f)

    mdat_size = a.size - delta
    write_ulong(out_f, mdat_size)
    write_fcc(out_f, 'mdat')

    return new_offset

def split(f, t, out_f=None):
    wf = out_f
    if wf is None:
        from cStringIO import StringIO
        wf = StringIO()

    new_offset = _split_headers(f, wf, t)
    return wf, new_offset

def split_and_write(in_f, out_f, t):
    header_f, new_offset = split(in_f, t)
    header_f.seek(0)
    out_f.write(header_f.read())
    in_f.seek(new_offset)
    out_f.write(in_f.read())

def main2(f, t):
    split_and_write(f, file('/tmp/t.mp4', 'w'), t)

def main1(f, t):
    from pprint import pprint
    aftyp, amoov, alist = read_iso_file(f)
    print aftyp
    nmoov, delta, _ = cut_moov(amoov, t)

    wf = file('/tmp/t.mp4', 'w')
    i, n = 0, len(alist)
    while i < n:
        a = alist[i]
        i += 1
        if a.type == 'moov':
            break
        a.write(wf)

    nmoov.write(wf)

    while i < n:
        a = alist[i]
        i += 1
        if a.type == 'mdat':
            break
        a.write(wf)

    print 'starting writing mdat: @%r' % wf.tell()
    mdat_size = a.size - delta
    write_ulong(wf, mdat_size)
    write_fcc(wf, 'mdat')

    a.seek_to_data()
    a.skip(delta)

    wf.write(a.f.read(mdat_size))

    while i < n:
        a = alist[i]
        i += 1
        a.write(wf)

    wf.close()

def get_sync_points(f):
    aftyp, amoov, alist = read_iso_file(f)
    ts = amoov.mvhd.timescale
    print aftyp
    traks = amoov.trak
    def find_sync_samples(a):
        stbl = a.mdia.minf.stbl
        if not stbl.stss:
            return []
        stss = stbl.stss
        stts = stbl.stts.table
        ts = float(a.mdia.mdhd.timescale)
        def sample_time(s):
            return find_mediatime_stts(stts, s) / ts
        return map(sample_time, stss.table)
    return [t for t in map(find_sync_samples, traks) if t][0]

def get_debugging(f):
    aftyp, amoov, alist = read_iso_file(f)
    ts = amoov.mvhd.timescale
    print aftyp
    traks = amoov.trak

    from pprint import pprint
    pprint(map(lambda a: a.mdia.minf.stbl.stco, traks))

if __name__ == '__main__':
    import sys
    f = file(sys.argv[1])
    if len(sys.argv) > 2:
        main2(f, float(sys.argv[2]))
    else:
        print get_sync_points(f)
        # get_debugging(f)
