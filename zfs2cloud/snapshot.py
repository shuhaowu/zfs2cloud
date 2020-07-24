from datetime import datetime

from .command import Command


class Snapshot(Command):
  """Invokes zfs snapshot."""

  def run(self):
    snapshot_id = datetime.now().strftime("%Y%m%d%H%M%S")
    zfs_name = "{}@{}".format(self.config.main["zfs_fs"], snapshot_id)

    self._execute("{} snapshot {}".format(self.config.zfs_path, zfs_name), dry_run=self.args.dry_run)


class PruneSnapshots(Command):
  """Prunes zfs snapshots locally according to oldest_snapshot_days. Defaults to dry run mode."""

  @classmethod
  def add_arguments(cls, parser):
    parser.add_argument("-y", "--yes", action="store_true", default=False, help="actually delete the snapshot instead of just dry run")

  def run(self):
    dry_run = not self.args.yes or self.args.dry_run
    if dry_run:
      self.logger.info("in dry run mode")

    now = datetime.now()
    snapshots = self._discover_snapshots()

    if len(snapshots) == 0:
      self.logger.info("no snapshots to prune")
      return

    for snapshot, creation_time in snapshots:
      delta = (now - creation_time).total_seconds() / 86400
      if delta > self.config.main.getint("oldest_snapshot_days"):
        self.logger.info("expiring {} as it is {:.2f} days old (threshold = {})".format(snapshot, delta, self.config.main.getint("oldest_snapshot_days")))
        command = "zfs destroy {}".format(snapshot).strip()

        # Extra caution...
        if command == "zfs destroy {}".format(self.config.main["zfs_fs"]):
          raise RuntimeError("Whoa what")

        self._execute(command, dry_run=dry_run)
      else:
        self.logger.debug("ignoring {} as it is only {:.2f} days old".format(snapshot, delta))
