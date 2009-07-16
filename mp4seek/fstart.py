import os
import sys
import shutil
import tempfile

from mp4seek.iso import move_header_and_write


def fstart_file(inpath, outpath=None):
    fi = open(inpath, 'rb')
    if outpath:
        fo = open(outpath, 'wb')
    else:
        fd, temppath = tempfile.mkstemp()
        shutil.copymode(inpath, temppath)
        fo = os.fdopen(fd, 'wb')
    move_header_and_write(fi, fo)
    fi.close()
    fo.close()
    if not outpath:
        shutil.move(temppath, inpath)

def main():
    if not 2 <= len(sys.argv) <= 3:
        print >>sys.stderr, "Usage: %s infile [outfile]" % sys.argv[0]
        sys.exit(2)
    try:
        fstart_file(sys.argv[1], (len(sys.argv) > 2 and sys.argv[2]) or None)
    except Exception, e:
        try:
            print >>sys.stderr, e
        except StandardError:
            pass
        sys.exit(1)

    sys.exit(0)
