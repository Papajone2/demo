"""Boot the built kernel/rootfs and exercise the real offline launcher in QEMU.

Only a disposable copy is modified. This checks Linux namespaces/privilege
dropping, which qemu-user ABI/import checks cannot exercise. It does not emulate
the bonnet or establish physical USB/signing readiness.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import time


INIT = """#!/bin/sh
set -eu
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
mount -t tmpfs tmpfs /data
mkdir -p /data/satooshi
chown 1000:1000 /data/satooshi
chmod 700 /data/satooshi
# Device stand-ins are exclusively in this disposable emulation rootfs.
for node in ttyGS0 i2c-1; do
  test -c "/dev/$node" || mknod "/dev/$node" c 1 3
done
test -c /dev/gpiomem || mknod /dev/gpiomem c 1 3
touch /run/storage-ready
status=0
/sandbox-launcher || status=$?
# This run contains no wallet runtime, keys, screens or transaction payloads.
cat /run/wallet.log
if test "$status" -eq 0 &&
   grep -q '^SATOOSHI_SANDBOX_PROBE_OK$' /run/wallet.log; then
  echo SATOOSHI_SANDBOX_BOOT_OK
else
  echo SATOOSHI_SANDBOX_BOOT_FAILED
fi
while true; do sleep 30; done
"""

PROBE = """import errno
import os
import socket
from pathlib import Path
assert os.getuid() == 1000 and os.geteuid() == 1000
assert os.getgroups() == []
status = Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\\t1' in status
assert 'CapEff:\\t0000000000000000' in status
try:
    Path('/sandbox-root-write').write_text('must fail')
except OSError as error:
    assert error.errno in (errno.EROFS, errno.EACCES)
else:
    raise AssertionError('root filesystem is writable')
path = Path('/var/lib/satooshi/probe')
path.write_text('public sandbox check')
path.unlink()
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as local:
    local.bind(('127.0.0.1', 0))
    local.listen(1)
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as outbound:
    outbound.settimeout(1)
    try:
        outbound.connect(('1.1.1.1', 443))
    except OSError as error:
        assert error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)
    else:
        raise AssertionError('sandbox has external networking')
print('SATOOSHI_SANDBOX_PROBE_OK', flush=True)
"""


def launcher_for_probe(source):
    command = "/usr/bin/python3 -m satooshi.main"
    if source.count(command) != 1:
        raise SystemExit("Wallet launcher changed: update its full-system preflight.")
    return source.replace(command, "/usr/bin/python3 /sandbox-probe.py")


def check(images, target):
    images, target = Path(images).resolve(), Path(target).resolve()
    for command in ("qemu-system-arm", "fdtput", "debugfs"):
        if not shutil.which(command):
            raise SystemExit(f"Required full-system startup checker missing: {command}")
    work = images.parent / "sandbox-boot-preflight"
    work.mkdir(exist_ok=True)
    rootfs, dtb = work / "root.ext4", work / "zero.dtb"
    shutil.copyfile(images / "rootfs.ext2", rootfs)
    shutil.copyfile(images / "bcm2708-rpi-zero-w.dtb", dtb)
    # Real firmware supplies RAM sizing, overlays and aliases. QEMU bypasses it.
    edits = [
        ("x", "/memory@0", "reg", "0", "20000000"),
        ("s", "/soc/power", "status", "disabled"),
        ("s", "/soc/watchdog@7e100000", "status", "disabled"),
        ("s", "/soc/mmc@7e202000", "status", "disabled"),
        ("s", "/soc/mmcnr@7e300000", "status", "disabled"),
        ("s", "/soc/mmc@7e300000", "status", "okay"),
        ("s", "/aliases", "serial0", "/soc/serial@7e201000"),
    ]
    for kind, node, key, *values in edits:
        subprocess.run(["fdtput", "-t", kind, str(dtb), node, key, *values], check=True)
    subprocess.run(["fdtput", "-d", str(dtb), "/aliases", "serial1"], check=True)
    launcher = launcher_for_probe((target / "usr/sbin/satooshi-run").read_text())
    for name, content, executable in (
        ("sandbox-init", INIT, True),
        ("sandbox-launcher", launcher, True),
        ("sandbox-probe.py", PROBE, False),
    ):
        path = work / name
        path.write_text(content)
        subprocess.run(["debugfs", "-w", "-R", f"write {path} /{name}", str(rootfs)],
                       check=True, capture_output=True)
        mode = "0100755" if executable else "0100644"
        subprocess.run(["debugfs", "-w", "-R",
                        f"set_inode_field /{name} mode {mode}", str(rootfs)],
                       check=True, capture_output=True)
    log = work / "boot.log"
    command = [
        "qemu-system-arm", "-M", "raspi0", "-kernel", str(images / "zImage"),
        "-dtb", str(dtb), "-drive", f"file={rootfs},format=raw,if=sd",
        "-append", "root=/dev/mmcblk2 rootfstype=ext4 rootwait ro "
        "console=ttyAMA0 init=/sandbox-init",
        "-display", "none", "-serial", "stdio", "-monitor", "none",
    ]
    success = False
    with log.open("w") as output:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                text = log.read_text(errors="replace")
                if "SATOOSHI_SANDBOX_BOOT_OK" in text:
                    success = True
                    break
                if ("SATOOSHI_SANDBOX_BOOT_FAILED" in text or
                        "Kernel panic" in text or process.poll() is not None):
                    break
                time.sleep(0.25)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if not success:
        print(log.read_text(errors="replace"))
        raise SystemExit("Full-system wallet sandbox startup failed; refusing image release.")
    print("ARMv6 full-system wallet launcher, offline loopback and isolation checks passed.")


if __name__ == "__main__":
    check(sys.argv[1], sys.argv[2])
