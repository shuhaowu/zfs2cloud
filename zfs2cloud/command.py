from contextlib import contextmanager
from datetime import datetime
import json
import logging
import os
import subprocess

from .config import Config


class Command(object):
  @classmethod
  def standalone_main(cls, args):
    config = Config(args.config, args._commands)
    cls(config, args).run()

  @classmethod
  def add_arguments(cls, parser):
    pass

  def __init__(self, config, args):
    self.logger = logging.getLogger(self.__class__.__name__)
    self.config = config
    self.args = args

  def run(self):
    raise NotImplementedError(self.__class__.__name__)

  def _discover_snapshots(self):
    snapshots = []
    data = self._execute("zfs list -H -t snapshot -o name,creation -S creation -d1 {}".format(self.config.main["zfs_fs"]), capture=True, log=False).stdout.strip()
    if len(data) == 0:  # No snapshots
      return []

    data = data.split("\n")

    for line in data:
      line = line.split("\t")
      if len(line) != 2:
        raise RuntimeError("zfs command should have returned two columns?")

      name = line[0]
      creation = line[1]

      creation = datetime.strptime(creation, "%a %b %d %H:%M %Y")
      snapshots.append((name, creation))

    return snapshots

  def _get_last_full_backup_from_cache_file(self):
    if os.path.exists(self.config.last_full_cache_file):
      with open(self.config.last_full_cache_file) as f:
        data = json.load(f)

      data[1] = datetime.strptime(data[1], "%Y-%m-%d %H:%M:%S")
      return tuple(data)
    else:
      return (None, None)

  def _intermediate_folder_file_name(self, snapshot_name, full):
    folder_name = snapshot_name.split("@")[1]
    if full:
      folder_name += "-full"

    return folder_name, snapshot_name.replace("/", "-") + ".zfs.gpg."

  def _execute(self, cmd, env=None, capture=False, raises=True, encoding="utf-8", log=True, dry_run=False):
    if log:
      self.logger.info("+ {}".format(cmd))

    if not dry_run:
      stdout = subprocess.PIPE if capture else None
      status = subprocess.run(cmd, stdout=stdout, check=raises, shell=True, env=env)

      if capture:
        status.stdout = status.stdout.decode(encoding)

      return status

  @contextmanager
  def chdir(self, path):
    old_cwd = os.getcwd()
    try:
      os.chdir(path)
      yield
    finally:
      os.chdir(old_cwd)


class ShowConfig(Command):
  """Shows the config as seen by zfs-backup."""
  def run(self):
    self.config.show(self.logger)

    snapshots = self._discover_snapshots()
    self.logger.info("")
    self.logger.info("Snapshots")
    self.logger.info("=========")

    for name, creation in snapshots:
      self.logger.info("{}: {}".format(name, creation))

    last_full_backup = self._get_last_full_backup_from_cache_file()
    self.logger.info("Last full backup: {} at {}".format(*last_full_backup))


class Lock(Command):
  """Attempt to create a lock file and thus disallow other calls to perform."""

  def run(self):
    self.logger.debug("creating lock file")

    if not self.args.dry_run:
      try:
        open(self.config.lock_path, "x")
      except FileExistsError:
        raise RuntimeError("lockfile already exists!")
      else:
        self.logger.debug("lock acquired")


class Unlock(Command):
  """Remove the lock file and thus allow other calls to perform."""

  def run(self):
    self.logger.debug("deleting lock file")

    if not self.args.dry_run:
      try:
        os.remove(self.config.lock_path)
      except FileNotFoundError:
        pass
      self.logger.debug("lock file removed")
