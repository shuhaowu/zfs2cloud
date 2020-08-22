import os
import getpass

from .command import Command


class Restore(Command):
  """Unsupport command to restore ZFS snapshots."""
  @classmethod
  def standalone_main(cls, args):
    # Don't need config
    cls(None, args).run()

  @classmethod
  def add_arguments(cls, parser):
    parser.add_argument("--zfs-fs", required=True, help="the name of the zfs filesystem to restore to")
    parser.add_argument("backup_folders", nargs="+", help="The path to the backup folder. This should be to the folder containing the .zfs file, not its parent folder.")

  def run(self):
    for folder in self.args.backup_folders:
      if not os.path.isdir(folder):
        raise ValueError("{} is not a valid directory".format(folder))

    passphrase = getpass.getpass(prompt="Encryption passphrase: ")

    for folder in self.args.backup_folders:
      self.logger.info("+ cd {}".format(folder))
      with self.chdir(folder):
        command = "bash -c \"set -o pipefail; cat * | pv | gpg --decrypt --batch --passphrase '{}' | zfs recv {}\"".format(passphrase, self.args.zfs_fs)
        self.logger.info("+ {}".format(command.replace(passphrase, "*****")))
        self._execute(command, log=False, dry_run=self.args.dry_run)
