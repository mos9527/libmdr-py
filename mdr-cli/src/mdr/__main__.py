#!/usr/bin/env python3
"""
usage:
    mdr [option=value ...] <context> [show]
    mdr [option=value ...] <context> [set] key=value [key=value ...]
    mdr [option=value ...] <context> <action>
    mdr <context> help

examples:
    mdr anc set mode=amb level=15 voice=on
    mdr anc mode=nc
    mdr device=XM6 eq preset=bright clearbass=3
    mdr playback volume+=2
    mdr playback toggle
    mdr json=on battery

fuzzy matching is also supported, with prefix matching unique ones, the above is equivalent to:
    mdr a set m=amb l=15 v=on
    mdr a m=nc
    mdr d=XM6 e p=b c=3
    mdr pl v+=2
    mdr pl t
    mdr j=on b

use the verb 'help' to show all options for a context:
    mdr playback help
    ...
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Iterator, Literal, get_args, get_origin, get_type_hints

from libmdr import Headphones, MDRError
from libmdr import constants as C
from libmdr import result as R
from libmdr_bt import create_connection

CURRENT, DESIRED = C.PROPERTY_CURRENT, C.PROPERTY_DESIRED
DISCOVERY = C.HEADPHONES_INIT_DISCOVERY
RO = "read-only"
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
KV_RE = re.compile(r"^(\w+)([+-]?=)(.*)$")


class UsageError(Exception):
    pass


class Unsupported(Exception):
    pass


def resolve(word: str, choices: list[str], what: str, see: str = "") -> str:
    """Match ``word`` exactly or by unique prefix; otherwise suggest close matches."""
    w = word.lower()
    if w in choices:
        return w
    hits = [c for c in choices if c.startswith(w)]
    if len(hits) == 1:
        return hits[0]
    if hits:
        message = f"ambiguous {what} {word!r}, could be: {', '.join(hits)}"
    else:
        message = f"unknown {what} {word!r}"
        close = difflib.get_close_matches(w, choices, n=3, cutoff=0.6)
        if close:
            message += f"\n\ndid you mean {' or '.join(map(repr, close))}?"
    if see:
        message += f"\nsee '{see}'"
    raise UsageError(message)


# --------------------------------------------------------------------------- #
# Models. Field names are the keys accepted on the command line; Annotated
# notes show up in `mdr <context> help`.
# --------------------------------------------------------------------------- #


@dataclass
class Options:
    device: Annotated[str, "MAC address or part of the name; default $MDR_DEVICE"] = ""
    ble: Annotated[bool, "connect over BLE (Windows)"] = False
    protocol: Literal["auto", "v1", "v2"] = "auto"
    timeout: Annotated[float, "seconds per step"] = 10.0
    json: Annotated[bool, "JSON output"] = False
    verbose: Annotated[bool, "connection and init timings on stderr"] = False


@dataclass
class Info:
    model: str
    series: str
    firmware: str
    protocol: str
    features: list[str]


@dataclass
class Battery:
    main: int | None = None
    left: int | None = None
    right: int | None = None
    case: int | None = None
    charging: list[str] = field(default_factory=list)


@dataclass
class NoiseControl:
    mode: Literal["off", "nc", "amb"]
    level: Annotated[int, "ambient level 0..20"]
    voice: Annotated[bool, "focus on voice"]
    adaptive: Annotated[bool, "adaptive ambient sound"]


@dataclass
class SpeakToChat:
    state: bool


@dataclass
class Equalizer:
    preset: Annotated[str, "name from 'presets'"]
    bands: Annotated[list[int], "5 bands: -10..10, 10 bands: -6..6"]
    clearbass: Annotated[int, "-10..10"]
    dsee: bool
    presets: Annotated[list[str], RO] = field(default_factory=list)


@dataclass
class Playback:
    volume: Annotated[int, "0..30"]
    status: Annotated[str, RO] = ""
    title: Annotated[str, RO] = ""
    artist: Annotated[str, RO] = ""
    album: Annotated[str, RO] = ""


@dataclass
class Power:
    autooff: Annotated[int, "minutes, 0 = never"]


# --------------------------------------------------------------------------- #
# key=value <-> dataclass
# --------------------------------------------------------------------------- #


def unwrap(tp: Any) -> tuple[Any, list[str]]:
    if get_origin(tp) is Annotated:
        base, *notes = get_args(tp)
        return base, list(notes)
    return tp, []


def parse_value(tp: Any, text: str, key: str) -> Any:
    tp, _ = unwrap(tp)
    if get_origin(tp) is Literal:
        return resolve(text, list(get_args(tp)), f"{key} value")
    if get_origin(tp) is list:
        (item,) = get_args(tp)
        return [parse_value(item, t.strip(), key) for t in text.split(",") if t.strip()]
    if tp is bool:
        if text.lower() in ("on", "yes", "true", "1"):
            return True
        if text.lower() in ("off", "no", "false", "0"):
            return False
        raise UsageError(f"{key} must be on or off")
    try:
        return tp(text)
    except ValueError:
        raise UsageError(f"{key} expects {tp.__name__}, got {text!r}") from None


def apply(obj: Any, pairs: list[str]) -> Any:
    """Return a copy of ``obj`` with ``key=value`` pairs applied."""
    hints = get_type_hints(type(obj), include_extras=True)
    writable = [k for k, tp in hints.items() if RO not in unwrap(tp)[1]]
    changes: dict[str, Any] = {}
    for pair in pairs:
        m = KV_RE.match(pair)
        if not m:
            raise UsageError(f"expected key=value, got {pair!r}")
        key, op, text = m.group(1).lower(), m.group(2), m.group(3)
        if key in hints and key not in writable:
            raise UsageError(f"key {key!r} is read-only")
        key = resolve(key, writable, "key")
        base, _ = unwrap(hints[key])
        value = parse_value(base, text, key)
        if op != "=":
            if base not in (int, float):
                raise UsageError(f"{key}{op} only works on numbers")
            current = changes.get(key, getattr(obj, key))
            value = current + value if op == "+=" else current - value
        changes[key] = value
    return dataclasses.replace(obj, **changes)


def describe(tp: Any) -> tuple[str, str]:
    tp, notes = unwrap(tp)
    if get_origin(tp) is Literal:
        kind = "|".join(get_args(tp))
    elif tp is bool:
        kind = "on|off"
    elif get_origin(tp) is list:
        kind = f"{describe(get_args(tp)[0])[0]},..."
    else:
        kind = tp.__name__
    return kind, ", ".join(n for n in notes if n != RO)


def print_keys(model: type, writable_only: bool = True) -> None:
    hints = get_type_hints(model, include_extras=True)
    for f in dataclasses.fields(model):
        if writable_only and RO in unwrap(hints[f.name])[1]:
            continue
        kind, note = describe(hints[f.name])
        print(f"    {f.name + '=' + kind:<28} {note}".rstrip())


def fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ",".join(map(str, value)) if all(isinstance(v, int) for v in value) else ", ".join(value)
    return str(value)


def as_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in dataclasses.asdict(obj).items() if v is not None and v != ""}


def emit(obj: Any, opts: Options) -> None:
    data = as_dict(obj)
    if opts.json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        for key, value in data.items():
            print(f"{key}: {fmt(value)}")


# --------------------------------------------------------------------------- #
# Device access
# --------------------------------------------------------------------------- #


def flag(enabled: bool) -> int:
    return C.TRUE if enabled else C.FALSE


def require(hp: Headphones, *features: int) -> None:
    for f in features:
        if not hp.feature_available(f):
            raise Unsupported(f"device does not support {C.FEATURE_NAMES.get(f, f)}")


def log(opts: Options, message: str) -> None:
    if opts.verbose:
        print(message, file=sys.stderr)


def find_device(pc, query: str) -> str:
    if MAC_RE.match(query):
        return query.replace("-", ":").upper()
    devices = pc.devices()
    q = query.lower()
    matches = [d for d in devices if d.name.lower() == q] or [d for d in devices if q in d.name.lower()]
    if len(matches) == 1:
        return matches[0].address
    if not matches:
        raise UsageError(f"no paired device matches {query!r}" if query else "no paired devices")
    listing = "\n".join(f"  {d.address}  {d.name}" for d in matches)
    raise UsageError(f"several devices match, pass device=...\n{listing}")


def open_link(pc, address: str, opts: Options) -> int:
    v2, v1 = (R.SERVICE_UUID_V2, C.PROTOCOL_V2), (R.SERVICE_UUID_V1, C.PROTOCOL_V1)
    services = [(R.SERVICE_UUID_BLE, C.PROTOCOL_V2)] if opts.ble else {
        "auto": [v2, v1], "v2": [v2], "v1": [v1]
    }[opts.protocol]
    errors = []
    for uuid, protocol in services:
        try:
            pc.connect(address, uuid)
            deadline = time.monotonic() + opts.timeout
            while (code := pc.poll(100)) != R.OK:
                if code not in (R.INPROGRESS, R.ERROR_TIMEOUT):
                    raise MDRError(code, pc.last_error() or None)
                if time.monotonic() > deadline:
                    raise MDRError(R.ERROR_TIMEOUT)
                if code == R.INPROGRESS:
                    time.sleep(0.01)
            return protocol
        except MDRError as e:
            errors.append(f"{C.PROTOCOL_NAMES[protocol]}: {e}")
            pc.disconnect()
    raise MDRError(R.ERROR_NO_CONNECTION, f"cannot connect to {address} ({'; '.join(errors)})")


def wait(hp: Headphones, target: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while (event := hp.poll()) != target:
        if event == C.EVENT_ALERT:
            print(f"device asks: {hp.get_text(C.TEXT_LAST_ALERT)}", file=sys.stderr)
        if time.monotonic() > deadline:
            raise MDRError(R.ERROR_TIMEOUT, f"timed out waiting for {C.EVENT_NAMES[target]}")
        if event == C.EVENT_NONE:
            time.sleep(0.005)


def commit(hp: Headphones, timeout: float) -> None:
    if hp.is_dirty():
        hp.request_commit()
        wait(hp, C.EVENT_APPLY_COMPLETE, timeout)


@contextmanager
def connect(opts: Options, init: int) -> Iterator[tuple[Headphones, int]]:
    """Connect, run the requested init and yield ``(headphones, protocol)``."""
    with create_connection(ble=opts.ble) as pc:
        t0 = time.monotonic()
        address = find_device(pc, opts.device)
        protocol = open_link(pc, address, opts)
        log(opts, f"connected to {address} ({C.PROTOCOL_NAMES[protocol]}) in {time.monotonic() - t0:.2f}s")
        try:
            with Headphones(pc.connection, protocol_version=protocol) as hp:
                t0 = time.monotonic()
                hp.request_init(init)
                wait(hp, C.EVENT_INITIALIZE_COMPLETE, opts.timeout)
                log(opts, f"init 0x{init:05x} in {time.monotonic() - t0:.2f}s")
                yield hp, protocol
        finally:
            pc.disconnect()


# --------------------------------------------------------------------------- #
# Contexts: read(hp, protocol, view) -> model, write(hp, protocol, old, new)
# --------------------------------------------------------------------------- #


def read_info(hp: Headphones, proto: int, view: int) -> Info:
    return Info(
        model=hp.get_text(C.TEXT_MODEL_NAME),
        series=hp.get_text(C.TEXT_MODEL_SERIES),
        firmware=hp.get_text(C.TEXT_FIRMWARE_VERSION),
        protocol=C.PROTOCOL_NAMES[proto],
        features=[
            C.FEATURE_NAMES.get(f, str(f))
            for f in range(1, C.FEATURE_MAX_VALUE + 1)
            if hp.feature_available(f)
        ],
    )


def read_battery(hp: Headphones, proto: int, view: int) -> Battery:
    out = Battery()
    for b in hp.get_batteries():
        part = C.BATTERY_PART_NAMES.get(b.part)
        if b.present and part:
            setattr(out, part, int(b.level_percent))
            if b.charging == C.CHARGING_YES:
                out.charging.append(part)
    return out


def read_anc(hp: Headphones, proto: int, view: int) -> NoiseControl:
    nc = hp.get_noise_control(view)
    level = int(nc.ambient_level)
    if nc.mode == C.NOISE_MODE_OFF:
        mode = "off"
    elif proto == C.PROTOCOL_V1:
        mode = "nc" if level == C.NOISE_AMBIENT_LEVEL_V1_NOISE_CANCELLING else "amb"
    else:
        mode = "nc" if nc.mode == C.NOISE_MODE_CANCELLING else "amb"
    return NoiseControl(mode, min(level, 20), bool(nc.focus_on_voice), bool(nc.adaptive_ambient))


def write_anc(hp: Headphones, proto: int, old: NoiseControl, new: NoiseControl) -> None:
    if new.mode == "nc":
        require(hp, C.FEATURE_NOISE_CANCELLING)
    if new.mode == "amb":
        require(hp, C.FEATURE_AMBIENT_SOUND)
    if new.adaptive != old.adaptive:
        require(hp, C.FEATURE_ADAPTIVE_AMBIENT_SOUND)
    v1 = proto == C.PROTOCOL_V1
    nc = hp.get_noise_control(DESIRED)
    if new.mode == "off":
        nc.mode = C.NOISE_MODE_OFF
    elif v1:
        nc.mode = C.NOISE_MODE_V1_ON
    else:
        nc.mode = C.NOISE_MODE_CANCELLING if new.mode == "nc" else C.NOISE_MODE_AMBIENT
    nc.ambient_level = C.NOISE_AMBIENT_LEVEL_V1_NOISE_CANCELLING if v1 and new.mode == "nc" else new.level
    nc.focus_on_voice = flag(new.voice)
    nc.adaptive_ambient = flag(new.adaptive)
    nc.changing_asm_level = C.FALSE
    hp.set_noise_control(nc)


def read_stc(hp: Headphones, proto: int, view: int) -> SpeakToChat:
    return SpeakToChat(bool(hp.get_speak_to_chat(view).enabled))


def write_stc(hp: Headphones, proto: int, old: SpeakToChat, new: SpeakToChat) -> None:
    value = hp.get_speak_to_chat(DESIRED)
    value.enabled = flag(new.state)
    hp.set_speak_to_chat(value)


def eq_presets(hp: Headphones) -> dict[int, str]:
    ids = hp.get_equalizer_presets()
    if not ids:
        return {k: v for k, v in C.EQUALIZER_PRESET_NAMES.items() if k != C.EQ_UNKNOWN}
    return {
        pid: hp.equalizer_preset_name(i) or C.EQUALIZER_PRESET_NAMES.get(pid, str(pid))
        for i, pid in enumerate(ids)
    }


def read_eq(hp: Headphones, proto: int, view: int) -> Equalizer:
    eq = hp.get_equalizer(view)
    names = eq_presets(hp)
    preset = int(eq.preset)
    return Equalizer(
        preset=names.get(preset) or C.EQUALIZER_PRESET_NAMES.get(preset, str(preset)),
        bands=hp.get_equalizer_bands(view),
        clearbass=int(eq.clear_bass),
        dsee=bool(eq.dsee_enabled),
        presets=list(names.values()),
    )


def write_eq(hp: Headphones, proto: int, old: Equalizer, new: Equalizer) -> None:
    if new.preset != old.preset:
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())

        ids = [pid for pid, name in eq_presets(hp).items() if norm(name) == norm(new.preset)]
        if not ids:
            raise UsageError(f"unknown preset {new.preset!r}, see 'mdr eq'")
        hp.set_equalizer_preset(ids[0])
    if new.bands != old.bands:
        hp.set_equalizer_bands(new.bands)
    if new.clearbass != old.clearbass:
        hp.set_equalizer_clear_bass(new.clearbass)
    if new.dsee != old.dsee:
        require(hp, C.FEATURE_DSEE)
        hp.set_dsee(new.dsee)


def read_playback(hp: Headphones, proto: int, view: int) -> Playback:
    pb = hp.get_playback(view)
    return Playback(
        volume=int(pb.volume),
        status=C.PLAYBACK_STATUS_NAMES.get(pb.status, "Unknown").lower(),
        title=hp.get_text(C.TEXT_TRACK_TITLE),
        artist=hp.get_text(C.TEXT_TRACK_ARTIST),
        album=hp.get_text(C.TEXT_TRACK_ALBUM),
    )


def write_playback(hp: Headphones, proto: int, old: Playback, new: Playback) -> None:
    if new.volume != old.volume:
        require(hp, C.FEATURE_PLAYBACK_VOLUME)
        hp.set_volume(new.volume)


def playback_action(name: str) -> Callable[[Headphones, Callable[[], None]], None]:
    def run(hp: Headphones, done: Callable[[], None]) -> None:
        require(hp, C.FEATURE_PLAYBACK_CONTROL)
        if name == "toggle":
            hp.toggle_playback()
        else:
            hp.playback_command(getattr(C, f"PLAYBACK_{name.upper()}"))
        done()

    return run


def read_power(hp: Headphones, proto: int, view: int) -> Power:
    return Power(int(hp.get_power(view).auto_power_off_minutes))


def write_power(hp: Headphones, proto: int, old: Power, new: Power) -> None:
    require(hp, C.FEATURE_AUTO_POWER_OFF)
    power = hp.get_power(DESIRED)
    power.auto_power_off_minutes = new.autooff
    hp.set_power(power)


def power_off(hp: Headphones, done: Callable[[], None]) -> None:
    require(hp, C.FEATURE_SHUTDOWN)
    hp.shutdown()
    try:
        done()
    except MDRError:
        pass  # The link usually drops before the ACK arrives.


@dataclass
class Context:
    help: str
    model: type
    init: int
    read: Callable[[Headphones, int, int], Any]
    write: Callable[[Headphones, int, Any, Any], None] | None = None
    actions: dict[str, Callable[[Headphones, Callable[[], None]], None]] = field(default_factory=dict)
    feature: int | None = None


CONTEXTS: dict[str, Context] = {
    "info": Context("model, firmware and supported features", Info, DISCOVERY, read_info),
    "battery": Context("battery levels", Battery, DISCOVERY | C.HEADPHONES_INIT_BATTERY, read_battery),
    "anc": Context("noise cancelling / ambient sound", NoiseControl,
                   DISCOVERY | C.HEADPHONES_INIT_NOISE_CONTROL, read_anc, write_anc),
    "stc": Context("speak-to-chat", SpeakToChat, DISCOVERY | C.HEADPHONES_INIT_SPEAK_TO_CHAT,
                   read_stc, write_stc, feature=C.FEATURE_SPEAK_TO_CHAT),
    "eq": Context("equalizer and DSEE", Equalizer,
                  DISCOVERY | C.HEADPHONES_INIT_EQUALIZER | C.HEADPHONES_INIT_DSEE,
                  read_eq, write_eq, feature=C.FEATURE_EQUALIZER),
    "playback": Context("volume and media keys", Playback, DISCOVERY | C.HEADPHONES_INIT_PLAYBACK,
                        read_playback, write_playback,
                        actions={a: playback_action(a) for a in ("play", "pause", "toggle", "next", "prev")}),
    "power": Context("auto power off and shutdown", Power, DISCOVERY | C.HEADPHONES_INIT_POWER,
                     read_power, write_power, actions={"off": power_off}),
}

WATCH_EVENTS = {
    C.EVENT_BATTERY_CHANGED: "battery",
    C.EVENT_NOISE_CONTROL_CHANGED: "anc",
    C.EVENT_SPEAK_TO_CHAT_CHANGED: "stc",
    C.EVENT_EQUALIZER_CHANGED: "eq",
    C.EVENT_PLAYBACK_CHANGED: "playback",
    C.EVENT_POWER_CHANGED: "power",
}


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_devices(opts: Options) -> None:
    with create_connection(ble=opts.ble) as pc:
        devices = pc.devices()
    if opts.json:
        print(json.dumps([dataclasses.asdict(d) for d in devices], ensure_ascii=False))
    for d in [] if opts.json else devices:
        print(f"{d.address}  {d.name}")


def cmd_watch(opts: Options) -> None:
    with connect(opts, C.HEADPHONES_INIT_DEFAULT) as (hp, proto):
        print("watching, Ctrl+C to stop", file=sys.stderr)
        need_sync = C.HEADPHONES_SYNC_NONE
        while True:
            if need_sync and hp.is_ready():
                hp.request_sync(need_sync)
                need_sync = C.HEADPHONES_SYNC_NONE
            event = hp.poll()
            if event == C.EVENT_NONE:
                time.sleep(0.01)
                continue
            if event == C.EVENT_NEED_SYNC:
                need_sync |= hp.get_sync()
            name = WATCH_EVENTS.get(event)
            data = as_dict(CONTEXTS[name].read(hp, proto, CURRENT)) if name else {}
            data.pop("presets", None)
            stamp, label = time.strftime("%H:%M:%S"), name or C.EVENT_NAMES.get(event, str(event))
            if opts.json:
                print(json.dumps({"time": stamp, "event": label, **data}, ensure_ascii=False), flush=True)
            else:
                pairs = " ".join(f"{k}={fmt(v)}" for k, v in data.items())
                print(f"{stamp} {label} {pairs}".rstrip(), flush=True)


def cmd_context(name: str, ctx: Context, verb: str, pairs: list[str], opts: Options) -> None:
    if verb == "set" and not pairs:
        raise UsageError("set needs key=value")
    if verb != "set" and pairs:
        raise UsageError(f"'{name} {verb}' takes no key=value")

    with connect(opts, ctx.init) as (hp, proto):
        if ctx.feature:
            require(hp, ctx.feature)
        if verb == "show":
            emit(ctx.read(hp, proto, CURRENT), opts)
        elif verb == "set":
            old = ctx.read(hp, proto, DESIRED)
            ctx.write(hp, proto, old, apply(old, pairs))
            commit(hp, opts.timeout)
            emit(ctx.read(hp, proto, DESIRED), opts)
        else:
            ctx.actions[verb](hp, lambda: commit(hp, opts.timeout))


def print_usage() -> None:
    print(__doc__.strip())
    print("\ncontexts:")
    print(f"    {'devices':<10} paired Bluetooth devices")
    for name, ctx in CONTEXTS.items():
        print(f"    {name:<10} {ctx.help}")
    print(f"    {'watch':<10} stay connected and print device events")
    print("\noptions:")
    print_keys(Options)


def context_verbs(ctx: Context) -> list[str]:
    return ["show"] + (["set"] if ctx.write else []) + list(ctx.actions)


def print_context_help(name: str, ctx: Context) -> None:
    print(f"mdr {name} - {ctx.help}\n\nverbs: {' | '.join(context_verbs(ctx))}")
    if ctx.write:
        print("\nkeys:")
        print_keys(ctx.model)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        split = next((i for i, a in enumerate(args) if "=" not in a), len(args))
        opts = apply(Options(device=os.environ.get("MDR_DEVICE", "")), args[:split])
        rest = args[split:]
        if not rest or rest[0].lower() in ("help", "-h", "--help", "/?"):
            print_usage()
            return 0 if rest else 2

        name = resolve(rest.pop(0), ["devices", *CONTEXTS, "watch", "help"], "context", "mdr help")
        if name == "help":
            print_usage()
        elif name == "devices":
            cmd_devices(opts)
        elif name == "watch":
            cmd_watch(opts)
        else:
            ctx = CONTEXTS[name]
            if rest and "=" not in rest[0]:
                word = rest.pop(0)
                if ctx.write is None and word.lower() == "set":
                    raise UsageError(f"'{name}' is read-only")
                verb = resolve(word, [*context_verbs(ctx), "help"], "verb", f"mdr {name} help")
            else:
                verb = "set" if rest else "show"
            if verb == "set" and ctx.write is None:
                raise UsageError(f"'{name}' is read-only")
            if verb == "help":
                print_context_help(name, ctx)
            else:
                cmd_context(name, ctx, verb, rest, opts)
        return 0
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Unsupported as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except MDRError as e:
        print(f"error: {e}", file=sys.stderr)
        return {R.ERROR_INVALID_ARGUMENT: 2, R.ERROR_NOT_SUPPORTED: 3}.get(e.code, 1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
