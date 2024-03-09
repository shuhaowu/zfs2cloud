from argparse import ArgumentParser, Namespace
import os

from .command import Command

class MountSnapshot(Command):
  @classmethod
  def add_arguments(cls, parser: ArgumentParser):
    pass

  def run(self):
    snapshots = self._discover_snapshots()
    if len(snapshots) == 0:
      raise RuntimeError("cannot mount-snapshot when there are no existing snapshots")

    snapshot_to_mount = snapshots[0][0]
    snapshot_mount_path, _ = self._intermediate_folder_file_name(snapshot_to_mount, True)
    snapshot_mount_path = os.path.join(self.config.main["intermediate_basedir"], snapshot_mount_path)

    os.umask(0o77)
    cmd = "mkdir -p {}".format(snapshot_mount_path)
    self._execute(cmd)

    cmd = "mount -t zfs {} {}".format(snapshot_to_mount, snapshot_mount_path)
    self._execute(cmd)


class UmountSnapshot(Command):
  @classmethod
  def add_arguments(cls, parser: ArgumentParser):
    pass

  def run(self):
    snapshots = self._discover_snapshots()
    if len(snapshots) == 0:
      raise RuntimeError("cannot umount-snapshot when there are no existing snapshots")

    snapshot_to_mount = snapshots[0][0]
    snapshot_mount_path, _ = self._intermediate_folder_file_name(snapshot_to_mount, True)
    snapshot_mount_path = os.path.join(self.config.main["intermediate_basedir"], snapshot_mount_path)

    cmd = "umount {}".format(snapshot_mount_path)
    self._execute(cmd)

    cmd = "rmdir {}".format(snapshot_mount_path)
    self._execute(cmd)


class UploadSnapshotFilesToRemote(Command):
  @classmethod
  def add_arguments(cls, parser: ArgumentParser):
    pass

  def run(self):
    # TODO: refactor this with UploadIntermediateToRemote. They are almost
    # identical except the intermediate uploads the intermediate files into
    # subdirectories, where as this doesn't.
    snapshots = self._discover_snapshots()
    if len(snapshots) == 0:
      raise RuntimeError("cannot umount-snapshot when there are no existing snapshots")

    snapshot = snapshots[0][0]
    snapshot_mount_path, _ = self._intermediate_folder_file_name(snapshot, True)
    snapshot_mount_path = os.path.join(self.config.main["intermediate_basedir"], snapshot_mount_path)

    command = [
      self.config.rclone_path,
    ]

    rclone_global_flags = self.config.main.get("rclone_global_flags")
    if rclone_global_flags:
      command.append(rclone_global_flags)

    command.append("sync")

    rclone_args = self.config.main.get("rclone_args")
    if rclone_args:
      command.append(rclone_args)

    command.append("{}/".format(snapshot_mount_path)) # So the content is copied
    command.append(self.config.main["remote"])
    command = " ".join(command)

    env = {}
    env["RCLONE_CONFIG"] = self.config.main["rclone_conf"]
    self._execute(command, env=env, dry_run=self.args.dry_run)
