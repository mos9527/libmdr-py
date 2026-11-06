# libmdr-cli

`mdr`, a command line tool for Sony headphones, built on [`libmdr`](https://pypi.org/project/libmdr/).

## Installation

```
pip install libmdr-cli    # or: pip install libmdr[cli]
```

See [`libmdr-bt`](https://pypi.org/project/libmdr-bt/) for the supported platforms
and the system libraries needed on Linux.

## Usage

```
mdr [option=value ...] <context> [show]
mdr [option=value ...] <context> [set] key=value [key=value ...]
mdr [option=value ...] <context> <action>
mdr <context> help
```

For example:

```
mdr anc set mode=amb level=15 voice=on
mdr device=XM6 eq preset=bright clearbass=3
mdr playback volume+=2
mdr json=on battery
```

Run `mdr help` for everything else, including fuzzy matching of names.

## Links

- [Source and documentation](https://github.com/mos9527/libmdr-py)
