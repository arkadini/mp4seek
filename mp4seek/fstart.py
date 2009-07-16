from mp4seek.iso import move_header_and_write

if __name__ == '__main__':
    import sys
    moved = move_header_and_write(file(sys.argv[1]), sys.argv[2])
    if not moved:
        # FIXME: handle it better?
        sys.exit(1)
