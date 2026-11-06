# libmdr-bt

Platform Bluetooth backend for [`libmdr`](https://pypi.org/project/libmdr/), as Python (ctypes) bindings.

## Installation

```
pip install libmdr-bt     # or: pip install libmdr[bt]
```

## Platforms

Prebuilt wheels are not tied to a Python version, and install on any Python >= 3.10 on:

| OS                | Architectures        | Backend         |
|-------------------|----------------------|-----------------|
| Windows           | x86-64, arm64        | Classic and BLE |
| macOS 12+         | x86-64, arm64        | IOBluetooth     |
| Linux (glibc 2.17+) | x86-64, arm64, armv7 | BlueZ, via D-Bus |

On Linux, the system must provide `libdbus-1.so.3` and `libbluetooth.so.3`. These are not bundled,
and on Debian and Ubuntu are in the `libdbus-1-3` and `libbluetooth3` packages.

Elsewhere pip builds from the sdist, which needs CMake >= 3.31, git and a C++20 compiler,
plus the libdbus-1 and libbluetooth headers on Linux.

## Links

- [Source and documentation](https://github.com/mos9527/libmdr-py)
