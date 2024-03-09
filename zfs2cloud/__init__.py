import argparse
import logging
import os
import sys

from .command import ShowConfig, Lock, Unlock
from .snapshot import Snapshot, PruneSnapshots
from .intermediate import ExportIntermediate, PruneIntermediate, UploadIntermediateToRemote
from .perform import Perform
from .restore import Restore
from .file_mode import MountSnapshot, UploadSnapshotFilesToRemote, UmountSnapshot

commands = {
  "show-config": ShowConfig,
  "lock": Lock,
  "unlock": Unlock,
  "snapshot": Snapshot,
  "prune-snapshots": PruneSnapshots,
  "export-intermediate": ExportIntermediate,
  "prune-intermediates": PruneIntermediate,
  "prune-snapshots": PruneSnapshots,
  "upload-intermediate-to-remote": UploadIntermediateToRemote,
  "mount-snapshot": MountSnapshot,
  "upload-snapshot-files-to-remote": UploadSnapshotFilesToRemote,
  "umount-snapshot": UmountSnapshot,
  "perform": Perform,
  "restore": Restore,
}


def main():
  global_parser = argparse.ArgumentParser(description="ZFS backup with snapshot management")
  global_parser.add_argument(
    "-c", "--config", default=os.environ.get("ZFS_BACKUP_CONFIG", None),
    help="the config ini file path (could also be specified by ZFS_BACKUP_CONFIG env var)"
  )

  global_parser.add_argument(
    "--dry-run", action="store_true", default=False,
    help="only print out what needs to be done instead of actually doing things"
  )

  global_parser.add_argument(
    "-v", "--verbose", action="store_true", default=False,
    help="print verbosely"
  )

  subparsers = global_parser.add_subparsers()
  for name, command in commands.items():
    parser = subparsers.add_parser(name, help=command.__doc__)
    command.add_arguments(parser)
    parser.set_defaults(f=command.standalone_main)

  global_parser.set_defaults(f=Perform.standalone_main)
  global_parser.set_defaults(_commands=commands)  # A hack to allow backup-sequences to be validated, and used in Perform

  args = global_parser.parse_args()
  if args.f != Restore.standalone_main:
    if args.config is None:
      print("error: must specify --config or ZFS_BACKUP_CONFIG", file=sys.stderr)
      sys.exit(1)

    if not os.path.isfile(args.config):
      print("error: {} is not a valid file".format(args.config), file=sys.stderr)
      sys.exit(1)

  level = logging.DEBUG if args.verbose else logging.INFO
  logging.basicConfig(format="{asctime} | {name: >12.12} | {levelname:.1} | {message}", datefmt="%Y-%m-%d %H:%M:%S", level=level, style="{")

  args.f(args)
