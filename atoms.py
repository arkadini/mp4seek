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

    def read_data(self):
        head_size = 8
        if self.real_size == 1:
            head_size += 8
        self.f.seek(self.offset + head_size)
        return self.f.read(self.size - head_size)

    def __repr__(self):
        return ('%s(%d, %r, %d, real_size=%d)' %
                (self.__class__.__name__, self.size, self.type, self.offset,
                 self.real_size))


class ContainerAtom(Atom):
    def __init__(self, size, type, offset, fobj, real_size=None):
        Atom.__init__(self, size, type, offset, fobj, real_size)
        self.child_offsets = []

    def read_children(self):
        head_size = 8
        if self.real_size == 1:
            head_size += 8
        self.f.seek(self.offset + head_size)
        return read_atoms(self.f, self.size - head_size)

    @classmethod
    def from_atom(cls, a):
        return cls(a.size, a.type, a.offset, a.f, real_size=a.real_size)


def read_bytes(fobj, bytes):
    data = fobj.read(bytes)
    if len(data) != bytes:
        raise RuntimeError('Not enough data: requested %d, read %d' %
                           (bytes, len(data)))
    return data

def _read_size(fobj):
    return struct.unpack('>L', read_bytes(fobj, 4))[0]

def _read_ext_size(fobj):
    return struct.unpack('>Q', read_bytes(fobj, 8))[0]

def _read_type(fobj):
    "Returns atom type as a big-endian encoded FCC string."
    return read_bytes(fobj, 4)

def read_atom(fobj):
    pos = fobj.tell()
    size = real_size = _read_size(fobj)
    type = _read_type(fobj)

    if size == 1:
        size = _read_ext_size(fobj)
    elif size == 0:
        fobj.seek(0, 2)
        size = fobj.tell() - pos
        fobj.seek(pos + 8)

    return Atom(size, type, pos, fobj, real_size=real_size)

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
