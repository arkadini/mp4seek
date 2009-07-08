import struct

class Atom(object):
    def __init__(self, size, type, offset, fobj, real_size=None):
        self.size = size
        self.type = type
        self.offset = offset
        self.f = fobj
        self.real_size = real_size
        if self.real_size is None:
            self.real_size = size

        self._hsize = None

    def head_size(self):
        if self._hsize is None:
            head_size = 8
            if self.real_size == 1:
                head_size += 8
            self._hsize = head_size
        return self._hsize

    def read_data(self):
        data_left = self.seek_to_data()
        return self.f.read(data_left)

    def read_bytes(self, bytes):
        return read_bytes(self.f, bytes)

    def skip(self, bytes):
        self.f.seek(bytes, 1)

    def seek_to_data(self):
        head_size = self.head_size()
        self.f.seek(self.offset + head_size)
        return self.size - head_size

    def seek_to_end(self):
        self.f.seek(self.offset + self.size)

    def itype(self):
        return struct.unpack('>L', self.type)[0]

    def __repr__(self):
        return ('%s(%d, %r, %d, real_size=%d)' %
                (self.__class__.__name__, self.size, self.type, self.offset,
                 self.real_size))


class ContainerAtom(Atom):
    def __init__(self, size, type, offset, fobj, real_size=None):
        Atom.__init__(self, size, type, offset, fobj, real_size)
        self._children = None
        self._children_dict = None

    def read_children(self):
        head_size = 8
        if self.real_size == 1:
            head_size += 8
        self.f.seek(self.offset + head_size)
        return read_atoms(self.f, self.size - head_size)

    def get_children(self):
        if self._children is None:
            self._children = list(self.read_children())
        return self._children

    def get_children_dict(self):
        if self._children_dict is None:
            self._children_dict = atoms_dict(self.read_children())
        return self._children_dict

    @classmethod
    def from_atom(cls, a):
        return cls(a.size, a.type, a.offset, a.f, real_size=a.real_size)


class FullAtom(Atom):
    def __init__(self, size, type, offset, v, flags, fobj, real_size=None):
        Atom.__init__(self, size, type, offset, fobj, real_size=real_size)
        self.v = v
        self.flags = flags

    @classmethod
    def from_atom(cls, a, v, flags):
        return cls(a.size, a.type, a.offset, v, flags, a.f,
                   real_size=a.real_size)

    @classmethod
    def read_from_atom(cls, a):
        a.seek_to_data()        # verify size?
        extra = read_ulong(a.f)
        v, flags = extra >> 24, extra & 0xffffff
        return cls(a.size, a.type, a.offset, v, flags, a.f,
                   real_size=a.real_size)

    def __repr__(self):
        return ('%s(%d, %r, %d, %d, 0x%x, real_size=%d)' %
                (self.__class__.__name__, self.size, self.type, self.offset,
                 self.v, self.flags, self.real_size))


def read_bytes(fobj, bytes):
    data = fobj.read(bytes)
    if len(data) != bytes:
        raise RuntimeError('Not enough data: requested %d, read %d' %
                           (bytes, len(data)))
    return data

def read_ulong(fobj):
    return struct.unpack('>L', read_bytes(fobj, 4))[0]

def read_ulonglong(fobj):
    return struct.unpack('>Q', read_bytes(fobj, 8))[0]

def read_fcc(fobj):
    "Returns a big-endian encoded FCC string."
    return read_bytes(fobj, 4)

def read_atom(fobj):
    pos = fobj.tell()
    size = real_size = read_ulong(fobj)
    type = read_fcc(fobj)

    if size == 1:
        size = read_ulonglong(fobj)
    elif size == 0:
        fobj.seek(0, 2)
        size = fobj.tell() - pos
        fobj.seek(pos + 8)

    return Atom(size, type, pos, fobj, real_size=real_size)

def full(a):
    return FullAtom.read_from_atom(a)

def read_full_atom(fobj):
    return full(read_atom(fobj))

def container(a):
    return ContainerAtom.from_atom(a)

def read_container_atom(fobj):
    return container(read_atom(fobj))

def read_atoms(fobj, limit=None):
    lpos = fobj.tell()
    fobj.seek(0, 2)
    end = fobj.tell()
    fobj.seek(lpos)

    if limit is not None:
        end = min(lpos + limit, end)

    size = 0

    while 1:
        if lpos + size < end:
            lpos += size
            fobj.seek(lpos)
            a = read_atom(fobj)
            yield a
            size = a.size
            lpos = a.offset
        else:
            break

def atoms_dict(atoms):
    d = {}
    for a in atoms:
        d.setdefault(a.type, []).append(a)
    return d
