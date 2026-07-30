#!/usr/bin/env python3
"""Prints the --help text for a run_*.sh bot launcher.

The settings a bot accepts are documented in its own Bot.elm header and
implemented in its own parseBotSettings, so they are read from there rather
than restated here -- a copy in the launcher script would drift the first time
a bot gained a setting. The host's flags come from botlab_host.py's own
argparse for the same reason.
"""

import argparse
import os
import re
import signal
import subprocess
import sys

# So that `run_saxrat.sh --help | head` (or quitting out of a pager) ends
# quietly, the way any other command-line tool does, instead of reporting a
# broken pipe.
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.path.join(HERE, "botlab_host", "botlab_host.py")


def find_bot_elm(bot_source):
    direct = os.path.join(bot_source, "Bot.elm")
    if os.path.isfile(direct):
        return direct
    for root, _dirs, files in os.walk(bot_source):
        if "Bot.elm" in files:
            return os.path.join(root, "Bot.elm")
    return None


def settings_section(bot_elm_text):
    """The '## Configuration Settings' part of Bot.elm's header comment.

    Ends at the next '##' heading or at the header's own example settings
    string, whichever comes first -- the example is already shown separately as
    this script's own defaults.
    """
    lines = bot_elm_text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("## Configuration Settings"):
            start = index + 1
            break
    if start is None:
        return []

    collected = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("##"):
            break
        if stripped.startswith("When using more than one setting"):
            break
        collected.append(line)

    # The header sits inside `{- ... -}` and is indented as a block; strip that
    # common indentation so the output does not look nested under nothing.
    indents = [len(l) - len(l.lstrip()) for l in collected if l.strip()]
    dedent = min(indents) if indents else 0
    return [l[dedent:] if len(l) >= dedent else l for l in collected]


def setting_keys(bot_elm_text):
    """Every key the bot's parseBotSettings actually accepts."""
    match = re.search(
        r"^parseBotSettings :.*?(?=\n\n\n|\Z)", bot_elm_text, re.DOTALL | re.MULTILINE
    )
    body = match.group(0) if match else bot_elm_text
    return re.findall(r'"([a-z][a-z0-9-]*)"\s*\n?\s*,\s*AppSettings\.valueType', body)


def trim_blank_edges(lines):
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("bot_source")
    ap.add_argument("--script", default="the launcher",
                    help="name of the launcher script, for the usage lines")
    ap.add_argument("--summary", default="",
                    help="one-line description of what this bot does")
    ap.add_argument("--note", default="",
                    help="warning or caveat to show directly under the summary")
    ap.add_argument("--usage", default="",
                    help="usage lines, already formatted")
    ap.add_argument("--defaults", default="",
                    help="the settings string the launcher passes by default")
    args = ap.parse_args()

    out = []
    if args.summary:
        out += [f"{args.script} -- {args.summary}", ""]

    if args.note:
        out += [args.note.strip(), ""]

    if args.usage:
        out += ["Usage:", *[f"  {line}" for line in args.usage.strip().split("\n")], ""]

    bot_elm = find_bot_elm(args.bot_source)
    if bot_elm is None:
        out += [f"Could not find Bot.elm under {args.bot_source}, so I cannot list this "
                "bot's settings.", ""]
    else:
        text = open(bot_elm, encoding="utf-8", errors="replace").read()

        out += ['Bot settings -- pass with --settings "...", one key=value per line:', ""]
        documented = settings_section(text)
        if documented:
            out += trim_blank_edges(documented) + [""]
        else:
            out += ["  (this bot's Bot.elm header documents none)", ""]

        documented_text = "\n".join(documented)
        undocumented = [k for k in setting_keys(text) if k not in documented_text]
        if undocumented:
            out += ["Also accepted, but not described in the bot's own header:",
                    "  " + ", ".join(sorted(set(undocumented))), ""]

    if args.defaults:
        out += [f"Settings {args.script} passes unless you override --settings:", ""]
        out += [f"  {line}" for line in args.defaults.strip().split("\n")]
        out += [""]

    out += [f"Host flags -- any of these can be appended to {args.script} and are passed",
            "straight through:", ""]

    host_help = subprocess.run(
        [sys.executable, HOST, "--help"], capture_output=True, text=True
    ).stdout
    # Only the options list: the host's own usage line and positional argument
    # name botlab_host.py and the bot source, neither of which is something a
    # launcher user passes.
    out += host_help.split("options:", 1)[-1].split("\n")[1:]

    print("\n".join(out).rstrip())


if __name__ == "__main__":
    main()
