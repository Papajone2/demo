"""Public, fixed-stage timing only. Never pass wallet data to this module."""
import time

STAGES = ("logo", "runtime_started", "imports_ready", "serial_ready", "wallet_ready")


def mark(stage):
    if stage not in STAGES:
        raise ValueError("Unknown boot stage")
    seconds = time.clock_gettime(time.CLOCK_BOOTTIME)
    print(f"SATOOSHI_BOOT stage={stage} kernel_seconds={seconds:.3f}", flush=True)
