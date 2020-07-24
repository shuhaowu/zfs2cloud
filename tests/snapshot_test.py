import datetime
from unittest.mock import patch, call


from .test_case import Zfs2CloudTestCase
from zfs2cloud.snapshot import Snapshot, PruneSnapshots


class SnapshotTest(Zfs2CloudTestCase):
  def setUp(self):
    super().setUp()

    self.maxDiff = None

    self.oldest_snapshot_days = 20

    self.config_data = """\
    [main]
    encryption_passphrase = 123456
    zfs_fs                = data/test
    intermediate_basedir  = {}
    remote                = b2:bucket/whatever
    rclone_conf           = ./rclone.conf
    oldest_snapshot_days  = {}
    full_every_x_days     = {}

    [backup_sequences]
    step01 = snapshot
    """.format(self.intermediate_basedir, self.oldest_snapshot_days, self.oldest_snapshot_days - 2)

  @patch("zfs2cloud.snapshot.datetime")
  @patch("subprocess.run")
  def test_snapshot(self, subprocess_run, datetime_mock):
    self.datetime_mock_now(datetime_mock, datetime.datetime(2020, 5, 15, 12, 10, 20))

    with self.config(self.config_data) as c:
      s = Snapshot(c, self.default_args(dry_run=False))
      s.run()

    subprocess_run.assert_called_once_with(
      "zfs snapshot data/test@20200515121020",
      stdout=None,
      check=True,
      shell=True,
      env=None
    )

  @patch("subprocess.run")
  def test_snapshot_dryrun(self, subprocess_run):
    with self.config(self.config_data) as c:
      s = Snapshot(c, self.default_args(dry_run=True))
      s.run()

    subprocess_run.assert_not_called()

  @patch("zfs2cloud.snapshot.datetime")
  @patch.object(PruneSnapshots, "_discover_snapshots")
  @patch("subprocess.run")
  def test_prune_snapshots(self, subprocess_run, discover_snapshots, datetime_mock):
    mocked_now = datetime.datetime(2020, 5, 15, 12, 10, 20)
    self.datetime_mock_now(datetime_mock, mocked_now)
    mocked_snapshots = []
    expected_subprocess_calls = []

    for i in range(self.oldest_snapshot_days + 30):
      creation_time = mocked_now - datetime.timedelta(days=i, minutes=2)
      name = "data/test@{}".format(creation_time.strftime("%Y%m%d%H%M%S"))
      mocked_snapshots.append((name, creation_time))

      if i >= self.oldest_snapshot_days:  # We need >= because the creation time is n days + 2 seconds ago.
        expected_subprocess_calls.append(call(
          "zfs destroy {}".format(name), stdout=None, check=True, shell=True, env=None
        ))

    discover_snapshots.return_value = mocked_snapshots

    with self.config(self.config_data) as c:
      s = PruneSnapshots(c, self.default_args(dry_run=True, yes=False))
      s.run()

      subprocess_run.assert_not_called()

      s = PruneSnapshots(c, self.default_args(dry_run=False, yes=False))
      s.run()

      subprocess_run.assert_not_called()

      s = PruneSnapshots(c, self.default_args(dry_run=True, yes=True))
      s.run()

      subprocess_run.assert_not_called()

      s = PruneSnapshots(c, self.default_args(dry_run=False, yes=True))
      s.run()

      self.assertEqual(subprocess_run.mock_calls, expected_subprocess_calls)
