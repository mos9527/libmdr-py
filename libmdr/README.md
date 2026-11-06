# libmdr

Python (ctypes) bindings for libmdr, the protocol library behind
[SonyHeadphonesClient](https://github.com/mos9527/SonyHeadphonesClient).

## Installation

```
pip install libmdr        # core bindings
pip install libmdr[bt]    # + libmdr-bt, the platform Bluetooth backend
pip install libmdr[cli]   # + libmdr-cli, the `mdr` command line tool
```

The extras are shorthands for the standalone
[`libmdr-bt`](https://pypi.org/project/libmdr-bt/) and
[`libmdr-cli`](https://pypi.org/project/libmdr-cli/) packages.

## Platforms

Prebuilt wheels are not tied to a Python version, and install on any Python >= 3.10 on:

| OS                | Architectures        |
|-------------------|----------------------|
| Windows           | x86-64, arm64        |
| macOS 12+         | x86-64, arm64        |
| Linux (glibc 2.17+) | x86-64, arm64, armv7 |

Elsewhere (e.g. musl) pip builds from the sdist, which needs CMake >= 3.31, git and a C++20 compiler.

## Links

- [Source and documentation](https://github.com/mos9527/libmdr-py)
