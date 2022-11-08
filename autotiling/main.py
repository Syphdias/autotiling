#!/usr/bin/env python3

"""
This script uses the i3ipc python module to switch the layout splith / splitv
for the currently focused window, depending on its dimensions.
It works on both sway and i3 window managers.

Inspired by https://github.com/olemartinorg/i3-alternating-layout

Copyright: 2019-2021 Piotr Miller & Contributors
e-mail: nwg.piotr@gmail.com
Project: https://github.com/nwg-piotr/autotiling
License: GPL3

Dependencies: python-i3ipc>=2.0.1 (i3ipc-python)
"""
import argparse
import os
import sys
from functools import partial

from i3ipc import Connection, Event

try:
    from .__about__ import __version__
except ImportError:
    __version__ = "unknown"


def temp_dir():
    if os.getenv("TMPDIR"):
        return os.getenv("TMPDIR")
    elif os.getenv("TEMP"):
        return os.getenv("TEMP")
    elif os.getenv("TMP"):
        return os.getenv("TMP")

    return "/tmp"


def save_string(string, file):
    try:
        file = open(file, "wt")
        file.write(string)
        file.close()
    except Exception as e:
        print(e)


def output_name(con):
    if con.type == "root":
        return None

    if p := con.parent:
        if p.type == "output":
            return p.name
        else:
            return output_name(p)


def switch_splitting(
    i3, e, debug, outputs, workspaces, depth_limit, splitwidth, splitheight, splitratio
):
    try:
        con = i3.get_tree().find_focused()
        if not con:
            if debug:
                print(
                    "Debug: No focused container",
                    file=sys.stderr,
                )
            return

        output = output_name(con)
        # Stop, if outputs is set and current output is not in the selection
        if outputs and output not in outputs:
            if debug:
                print(
                    "Debug: Autotiling turned off on output {}".format(output),
                    file=sys.stderr,
                )
            return

        # Stop here, if workspaces is set and current workspace is not in the selection
        if workspaces and str(con.workspace().num) not in workspaces:
            if debug:
                print(
                    "Debug: No focused container found or autotiling on the workspace turned off",
                    file=sys.stderr,
                )
            return

        if con.floating:
            # We're on i3: on sway it would be None
            # May be 'auto_on' or 'user_on'
            is_floating = "_on" in con.floating
        else:
            # We are on sway
            is_floating = con.type == "floating_con"

        # Exclude floating containers, stacked layouts, tabbed layouts and full screen mode
        if (
            is_floating
            or con.parent.layout == "stacked"
            or con.parent.layout == "tabbed"
            or con.fullscreen_mode == 1
        ):
            if debug:
                print(
                    "Debug: Ignore container because it floats, is fullscreened or "
                    "part of stacked/tabbed layout",
                    file=sys.stderr,
                )
            return

        # Limit how far/deep autotiling will split
        if depth_limit:
            # Assume we reached the depth limit, unless we can find a workspace
            depth_limit_reached = True
            current_con = con
            current_depth = 0
            while current_depth < depth_limit:
                # Check if we found the workspace of the current container
                if current_con.type == "workspace":
                    # Found the workspace within the depth limitation
                    depth_limit_reached = False
                    break

                # Look at the parent for next iteration
                current_con = current_con.parent

                # Only count up the depth, if the container has more than
                # one container as child
                if len(current_con.nodes) > 1:
                    current_depth += 1

            if depth_limit_reached:
                if debug:
                    print("Debug: Depth limit reached")
                return

        new_layout = (
            "splitv" if con.rect.height > con.rect.width / splitratio else "splith"
        )

        if new_layout != con.parent.layout:
            result = i3.command(new_layout)
            if result[0].success and debug:
                print("Debug: Switched to {}".format(new_layout), file=sys.stderr)
            elif debug:
                print(
                    "Error: Switch failed with err {}".format(result[0].error),
                    file=sys.stderr,
                )

        if e.change == "new" and con.percent:
            if con.parent.layout == "splitv":  # top / bottom
                # print(f"split top fac {splitheight*100}")
                i3.command(f"resize set height {int(con.percent*splitheight*100)} ppt")
            else:  # left / right
                # print(f"split right fac {splitwidth*100} ")
                i3.command(f"resize set width {int(con.percent*splitwidth*100)} ppt")

    except Exception as e:
        print("Error: {}".format(e), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--debug", action="store_true", help="print debug messages to stderr"
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s {}, Python {}".format(__version__, sys.version),
        help="display version information",
    )
    parser.add_argument(
        "-o",
        "--outputs",
        help="restricts autotiling to certain output; "
        "example: autotiling --output  DP-1 HDMI-0",
        nargs="*",
        type=str,
        default=[],
    )
    parser.add_argument(
        "-w",
        "--workspaces",
        help="restricts autotiling to certain workspaces; example: autotiling --workspaces 8 9",
        nargs="*",
        type=str,
        default=[],
    )
    parser.add_argument(
        "-l",
        "--limit",
        help="limit how often autotiling will split a container; "
        'try "2", if you like master-stack layouts; default: 0 (no limit)',
        type=int,
        default=0,
    )
    parser.add_argument(
        "-sw",
        "--splitwidth",
        help="set the width of the vertical split (as factor); default: 1.0;",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "-sh",
        "--splitheight",
        help="set the height of the horizontal split (as factor); default: 1.0;",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "-sr",
        "--splitratio",
        help="Split direction ratio - based on window height/width; default: 1;"
        'try "1.61", for golden ratio - window has to be 61%% wider for left/right split; default: 1.0;',
        type=float,
        default=1.0,
    )
    """
    Changing event subscription has already been the objective of several pull request. To avoid doing this again
    and again, let's allow to specify them in the `--events` argument.
    """
    parser.add_argument(
        "-e",
        "--events",
        help="list of events to trigger switching split orientation; default: WINDOW MODE",
        nargs="*",
        type=str,
        default=["WINDOW", "MODE"],
    )

    args = parser.parse_args()

    if args.debug and args.outputs:
        print("autotiling is only active on outputs:", ",".join(args.outputs))

    if args.debug and args.workspaces:
        print("autotiling is only active on workspaces:", ",".join(args.workspaces))

    # For use w/ nwg-panel
    ws_file = os.path.join(temp_dir(), "autotiling")
    if args.workspaces:
        save_string(",".join(args.workspaces), ws_file)
    else:
        if os.path.isfile(ws_file):
            os.remove(ws_file)

    if not args.events:
        print("No events specified", file=sys.stderr)
        sys.exit(1)

    handler = partial(
        switch_splitting,
        debug=args.debug,
        outputs=args.outputs,
        workspaces=args.workspaces,
        depth_limit=args.limit,
        splitwidth=args.splitwidth,
        splitheight=args.splitheight,
        splitratio=args.splitratio,
    )
    i3 = Connection()
    for e in args.events:
        try:
            i3.on(Event[e], handler)
            print("{} subscribed".format(Event[e]))
        except KeyError:
            print("'{}' is not a valid event".format(e), file=sys.stderr)

    i3.main()


if __name__ == "__main__":
    # execute only if run as a script
    main()
