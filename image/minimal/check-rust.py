"""Reject incompatible vendored Rust dependencies before the full cross-build."""
from pathlib import Path
import sys
import tomllib


def check(vendor, compiler="1.82.0"):
    supported = tuple(int(n) for n in compiler.split(".")[:2])
    manifests = sorted(Path(vendor).glob("*/Cargo.toml"))
    if not manifests:
        raise SystemExit("Rust vendor directory is empty.")
    errors = []
    for manifest in manifests:
        package = tomllib.loads(manifest.read_text())["package"]
        edition = str(package.get("edition", "2015"))
        minimum = package.get("rust-version", "1.0")
        required = tuple(int(n) for n in minimum.split(".")[:2])
        if required > supported or (edition == "2024" and supported < (1, 85)):
            errors.append(f"{package['name']} {package['version']}: "
                          f"edition={edition}, rust-version={minimum}")
    if errors:
        raise SystemExit(f"Dependencies incompatible with Rust {compiler}:\n" + "\n".join(errors))
    print(f"All {len(manifests)} vendored Rust manifests support Rust {compiler}.")


if __name__ == "__main__":
    check(sys.argv[1])
