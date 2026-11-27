"""Restricted operator review and portable feedback backup/restore (local files only)."""

import argparse
import sys

from hi_scenario.feedback import backup, feedback_directory, records, restore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["review", "export", "restore"])
    args = parser.parse_args()
    try:
        directory = feedback_directory()
        if args.action == "review":
            for record in records(directory):
                # JSON escaping keeps user-controlled terminal control characters inert.
                print(record.model_dump_json(ensure_ascii=True))
        elif args.action == "export":
            print(backup(directory).model_dump_json(ensure_ascii=True))
        else:
            count = restore(directory, sys.stdin.read())
            print(f"Verified {count} restored feedback records.", file=sys.stderr)
    except (OSError, ValueError):
        # Never print submitted content, filenames, or exception contexts to logs.
        print("Feedback operation failed. Check private storage, backup integrity, and destination state.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
