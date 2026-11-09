"""Prevent optional distro modules from becoming built-ins in this appliance."""
from pathlib import Path
import re
import sys


def prepare(path):
    path = Path(path)
    original = path.read_text()
    updated, count = re.subn(
        r"^(CONFIG_[A-Z0-9_]+)=m$", r"# \1 is not set", original, flags=re.MULTILINE
    )
    # Explicit appliance requirements are merged afterwards by Buildroot.
    # Do not disable modules only after olddefconfig: Kconfig promotes m to y.
    path.write_text(updated)
    print(f"Disabled {count} optional distro modules before appliance configuration.")
    return count


if __name__ == "__main__":
    prepare(sys.argv[1])
