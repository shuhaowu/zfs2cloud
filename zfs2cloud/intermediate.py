from datetime import datetime
import json
import os
import shutil
import shlex

from .command import Command


class ExportIntermediate(Command):
  """Exports the ZFS snapshot into encrypted and splitted files."""

  @classmethod
  def add_arguments(cls, parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-f", "--full", action="store_true", default=False, help="forces a full backup")
    group.add_argument("-i", "--incremental", action="store_true", default=False, help="forces an incremental backup")

  def run(self):
    snapshots = self._discover_snapshots()
    if len(snapshots) == 0:
      raise RuntimeError("cannot export-intermediate when there are no existing snapshots")

    last_full_backup = self._get_last_full_backup_from_cache_file()
    full, reason = self._should_be_full_export(snapshots, last_full_backup)

    self.logger.info("performing {}".format(reason))

    snapshot_to_export = snapshots[0][0]
    snapshot_intermediate_folder_name, snapshot_intermediate_file_prefix = self._intermediate_folder_file_name(snapshot_to_export, full)

    os.umask(0o77)
    if not full:
      if self.config.main["incremental_strategy"] != self.config.SINCE_LAST_FULL:
        raise NotImplementedError

      base_zfs_name = last_full_backup[0]
      opts = "-i {}".format(base_zfs_name)
    else:
      opts = ""

    snapshot_intermediate_folder_name = os.path.join(self.config.main["intermediate_basedir"], snapshot_intermediate_folder_name)
    snapshot_intermediate_file_prefix = os.path.join(snapshot_intermediate_folder_name, snapshot_intermediate_file_prefix)

    self._execute("{} -p {}".format("mkdir", snapshot_intermediate_folder_name), dry_run=self.args.dry_run)

    command = "{zfs} send {opts} {current_zfs_name} | gpg1 -c --cipher-algo AES256 --batch --passphrase {key} | split - --bytes {split_size} --suffix-length=4 --numeric-suffixes {fileprefix}".format(
      zfs=self.config.zfs_path,
      opts=opts,
      current_zfs_name=snapshot_to_export,
      key=self.config.main["encryption_passphrase"],
      split_size=self.config.main["split_size"],
      fileprefix=snapshot_intermediate_file_prefix
    )

    self.logger.info("+ {}".format(command.replace(self.config.main["encryption_passphrase"], "*****")))
    self._execute(command, log=False, dry_run=self.args.dry_run)

    if full:
      data = json.dumps([snapshot_to_export, snapshots[0][1].strftime("%Y-%m-%d %H:%M:%S")])
      self.logger.info("updating {} to {}".format(self.config.last_full_cache_file, data))
      if not self.args.dry_run:
        with open(self.config.last_full_cache_file, "w") as f:
          f.write(data)

    return full

  def _should_be_full_export(self, snapshots, last_full_backup):
    last_full_backup_name, last_full_backup_creation_time = last_full_backup
    full = False
    reason = "incremental export by default"

    if self.args.full:
      full = True
      reason = "full export due to override via --full"

    if self.args.incremental:
      full = False
      reason = "incremental export due to override via --incremental"

    if len(snapshots) == 1:
      full = True
      reason = "full export since there's only a single snapshot"
    elif last_full_backup_name is None:
      full = True
      reason = "full export due to no known full export"
    elif not self.args.incremental and (datetime.now() - last_full_backup_creation_time).total_seconds() > self.config.main.getint("full_every_x_days") * 86400:
      delta = (datetime.now() - last_full_backup_creation_time).total_seconds() / 86400
      full = True
      reason = "full export since last full backup is {:.1f} days old and larger than threshold days of {}".format(delta, self.config.main.getint("full_every_x_days"))

    return full, reason


class PruneIntermediate(Command):
  """
  Prune the intermediate folder until there's only the most recent backup left.
  Defaults to dry run mode.
  """

  @classmethod
  def add_arguments(cls, parser):
    parser.add_argument("-y", "--yes", action="store_true", default=False, help="actually delete the intermediates instead of just dry run")

  def run(self):
    if not self.args.yes:
      self.logger.info("in dry-run mode")

    snapshots = self._discover_snapshots()

    if len(snapshots) == 0:
      raise RuntimeError("cannot prune-intermediate when there are no existing snapshots")
    elif len(snapshots) == 1:
      self.logger.info("nothing pruned as there's only a single snapshot")
      return

    possible_folder_names = set()
    for snapshot_name, _ in snapshots[1:]:
      folder_name, _ = self._intermediate_folder_file_name(snapshot_name, False)
      possible_folder_names.add(folder_name)

      folder_name, _ = self._intermediate_folder_file_name(snapshot_name, True)
      possible_folder_names.add(folder_name)

    for fn in os.listdir(self.config.main["intermediate_basedir"]):
      path = os.path.join(self.config.main["intermediate_basedir"], fn)
      if not os.path.isdir(path):
        self.logger.debug("ignoring {}".format(path))
        continue

      if fn in possible_folder_names:
        self.logger.info("pruning {}".format(path))
        if self.args.yes:
          shutil.rmtree(path)
      else:
        self.logger.debug("ignoring {}".format(path))


class UploadIntermediateToRemote(Command):
  """Uploads intermediate files to the cloud via rclone."""

  @classmethod
  def add_arguments(cls, parser):
    parser.add_argument("-s", "--snapshot", default=None, help="the snapshot to upload (specifically the value of this option should be the zfs name). Default: the latest snapshot")

  def run(self):
    snapshots = self._discover_snapshots()
    if len(snapshots) == 0:
      raise RuntimeError("cannot upload-intermediate-to-remote when there are no existing snapshots")

    snapshot_to_upload = self.args.snapshot

    if snapshot_to_upload is None:
      snapshot_to_upload = snapshots[0][0]

    if not snapshot_to_upload.startswith(self.config.main["zfs_fs"]):
      raise ValueError("{} should start with {} but doesn't".format(snapshot_to_upload, self.config.main["zfs_fs"]))

    possible_folder_names = set()

    folder_name, _ = self._intermediate_folder_file_name(snapshot_to_upload, False)
    possible_folder_names.add(folder_name)
    folder_name, _ = self._intermediate_folder_file_name(snapshot_to_upload, True)
    possible_folder_names.add(folder_name)

    self.logger.debug("looking for either {} in the intermediate basedir".format(possible_folder_names))

    actual_folders = []

    for fn in os.listdir(self.config.main["intermediate_basedir"]):
      path = os.path.join(self.config.main["intermediate_basedir"], fn)
      if not os.path.isdir(path):
        continue

      if fn in possible_folder_names:
        actual_folders.append(fn)

    if len(actual_folders) != 1:
      raise RuntimeError("cannot find the snapshot intermediate or have too many candidates: {}".format(actual_folders))

    path_to_upload = os.path.join(self.config.main["intermediate_basedir"], actual_folders[0])
    self.logger.info("uploading {} to {}".format(path_to_upload, self.config.main["remote"]))

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

    command.append(path_to_upload)
    command.append("{upload_to}/{backup_folder_name}".format(upload_to=self.config.main["remote"], backup_folder_name=actual_folders[0]))
    command = " ".join(command)

    env = {}
    env["RCLONE_CONFIG"] = self.config.main["rclone_conf"]
    self._execute(command, env=env, dry_run=self.args.dry_run)
