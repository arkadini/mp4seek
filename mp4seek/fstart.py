from iso import move_header_and_write

if __name__ == '__main__':
    import sys
    move_header_and_write(file(sys.argv[1]), file(sys.argv[2], 'w'))
