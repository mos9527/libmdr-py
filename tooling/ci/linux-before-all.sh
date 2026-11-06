#!/bin/sh
# cibuildwheel `before-all` for the manylinux build containers.
#   $1 = "bt": also install the libmdr-bt build dependencies (D-Bus, BlueZ).
set -eux

if command -v dnf >/dev/null 2>&1; then
    # manylinux_2_28 (AlmaLinux 8, x86_64/aarch64): gcc-toolset-14 is the default.
    # bluez-libs-devel lives in PowerTools (named CRB on EL9).
    if [ "${1:-}" = bt ]; then
        dnf install -y --enablerepo=powertools dbus-devel bluez-libs-devel ||
            dnf install -y --enablerepo=crb dbus-devel bluez-libs-devel
    fi
else
    # manylinux_2_35 (Ubuntu 22.04, armv7l): defaults to GCC 11. Use GCC 12, which
    # matches the image's system libstdc++ and thus the manylinux_2_35 policy.
    apt-get update
    apt-get install -y --no-install-recommends g++-12
    update-alternatives --install /usr/bin/cc cc /usr/bin/gcc-12 100
    update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++-12 100
    if [ "${1:-}" = bt ]; then
        apt-get install -y --no-install-recommends libdbus-1-dev libbluetooth-dev
    fi
fi
