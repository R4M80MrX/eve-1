#Embedded file name: c:\depot\games\branches\release\EVE-TRANQUILITY\carbon\common\stdlib\json\tool.py
import sys
import json

def main():
    if len(sys.argv) == 1:
        infile = sys.stdin
        outfile = sys.stdout
    elif len(sys.argv) == 2:
        infile = open(sys.argv[1], 'rb')
        outfile = sys.stdout
    elif len(sys.argv) == 3:
        infile = open(sys.argv[1], 'rb')
        outfile = open(sys.argv[2], 'wb')
    else:
        raise SystemExit(sys.argv[0] + ' [infile [outfile]]')
    try:
        obj = json.load(infile)
    except ValueError as e:
        raise SystemExit(e)

    json.dump(obj, outfile, sort_keys=True, indent=4)
    outfile.write('\n')


if __name__ == '__main__':
    main()