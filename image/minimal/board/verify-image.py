"""Validate the real MBR and filesystems, not just the image filename."""
from pathlib import Path
import struct
import sys


def verify(path):
    path = Path(path)
    with path.open("rb") as stream:
        mbr = stream.read(512)
        if mbr[510:512] != b"\x55\xaa":
            raise SystemExit("Missing MBR signature; refusing unbootable artifact.")
        end = 0
        for index, kind in enumerate((0x0C, 0x83, 0x83)):
            entry = mbr[446 + 16 * index:462 + 16 * index]
            start, length = struct.unpack_from("<II", entry, 8)
            if entry[4] != kind or not length or start * 512 < end:
                raise SystemExit("Invalid or overlapping boot/root/data partitions.")
            end = (start + length) * 512
            if end > path.stat().st_size:
                raise SystemExit("Partition extends beyond the image.")
            if index:
                stream.seek(start * 512 + 1024 + 56)
                if stream.read(2) != b"\x53\xef":
                    raise SystemExit("Root/data partition is not an ext filesystem.")
    print("MBR and separate boot/root/data filesystem layout verified.")


if __name__ == "__main__":
    verify(sys.argv[1])
