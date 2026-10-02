"""Create/restore encrypted local backups. Keys are read only from the environment."""
import argparse
import json
import os
from pathlib import Path
from core.recovery import backup, restore
from market.persistence import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('source')
    parser.add_argument('destination', help='New path; existing files are never overwritten')
    args = parser.parse_args()
    key = os.getenv('JARVIS_BACKUP_KEY')
    if not key:
        parser.error('Set JARVIS_BACKUP_KEY to a Fernet key held outside the repository')
    if not Path(args.source).is_file():
        parser.error('Source file does not exist')
    if args.operation == 'backup':
        store = SQLiteStore(args.source)
        try:
            result = backup(store, args.destination, key)
        finally:
            store.close()
    else:
        result = restore(args.source, args.destination, key)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
