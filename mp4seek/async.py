from cStringIO import StringIO
import struct

import iso

class Splitter(object):
    """Helper class for async/data-driven splitting."""

    MIN_HEAD_CHUNK = 16

    def __init__(self, t):
        """
        @param t: split point, in seconds - nearest sync point will be used
        @type  t: float
        """
        self.t = t
        self.data_cb = None
        self._offset = 0

        self._inc_offset = 0
        self._moov_found = False

        self._all_found = False

        self._out_f = None
        self._out_offset = None

    def start(self, data_cb):
        """Prepare L{Splitter} object.

        @param data_cb: callback function that will be called with
                        requests for data
        @type  data_cb: (size, offset) -> None
        """
        self.data_cb = data_cb
        self.data_cb(*self.next_chunk())

    def stop(self):
        """Clean-up method."""
        self.data_cb = None

    def feed(self, data):
        """Feed L{Splitter} with data.

        @param data: buffer of data, as requested in call to data_cb
        @type  data: str
        """
        # not checking if the data size is what we actually requested... FIXME?
        size, offset = self._handle_feed(data)
        self.data_cb(size, offset)

    def result(self):
        """Returns results of splitting.

        @returns: rewritten file header and the offset at which
        copying data for the original file should start
        @rtype:   StringIO, int
        """
        if self._out_f is None:
            self._build_result()
        return self._out_f, self._out_offset

    def _handle_feed(self, data):
        if self._all_found:
            self.in_f = StringIO(data)
            return 0, 0

        a, next = get_stub(self._offset, data)
        if a.type == 'mdat':
            if not self._moov_found:
                raise iso.FormatError('No "moov" before "mdat" found - cannot'
                                      ' seek')
            self._all_found = True
        elif a.type == 'moov':
            self._moov_found = True

        self._inc_offset = a.offset
        self._offset = next
        if next is None and not self._all_found:
            raise iso.FormatError('Not all needed atoms found - cannot seek')

        return self.next_chunk()

    def _build_result(self):
        self._out_f, self._out_offset = iso.split(self.in_f, self.t, out_f=StringIO())

    def next_chunk(self):
        if self._all_found:
            return self._inc_offset + self.MIN_HEAD_CHUNK, 0
        return self.MIN_HEAD_CHUNK, self._offset


class AtomStub(object):
    def __init__(self, size, type, offset, real_size=None):
        self.size = size
        self.type = type
        self.offset = offset
        self.real_size = real_size
        if self.real_size is None:
            self.real_size = size

    def next(self):
        if not self.size:
            return None
        return self.offset + self.size

def read_atom_stub(offset, data):
    # same logic as in atoms
    # data should be big enough to be able to read:
    #   * size (4 bytes)
    #   * type (4 bytes)
    #   * extended size (8 bytes)
    size, type = struct.unpack('>L4s', data[0:8])
    real_size = size
    if size == 1:
        size = struct.unpack('>Q', data[8:16])
    return AtomStub(size, type, offset, real_size)

def get_stub(offset, data):
    a = read_atom_stub(offset, data)
    return a, a.next()


def test(f, t):
    out_f = file('/tmp/at.mp4', 'w')

    # dummy data callback, with storage to not recurse on stack
    req = [None, None]
    def data_cb(size, offset):
        req[0] = size
        req[1] = offset

    s = Splitter(t)
    s.start(data_cb)

    # simulate async data feeding
    while req[0] != 0:
        f.seek(req[1])
        s.feed(f.read(req[0]))

    # get the results
    header_f, new_offset = s.result()

    # we have all we need to write the new file
    header_f.seek(0)
    out_f.write(header_f.read())
    f.seek(new_offset)
    out_f.write(f.read())


if __name__ == '__main__':
    import sys
    f = file(sys.argv[1])
    t = float(sys.argv[2])
    test(f, t)
