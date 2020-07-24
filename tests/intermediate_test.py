from unittest.mock import patch, call
import datetime
import os
import textwrap

from .test_case import Zfs2CloudTestCase

from zfs2cloud.intermediate import ExportIntermediate, PruneIntermediate, UploadIntermediateToRemote
from zfs2cloud.config import Config


class IntermediateTest(Zfs2CloudTestCase):
  def setUp(self):
    super().setUp()

    config_data = """\
    [main]
    encryption_passphrase = 123456
    zfs_fs                = data/test
    intermediate_basedir  = {}
    remote                = b2:bucket/whatever
    rclone_conf           = ./rclone.conf
    oldest_snapshot_days  = 45
    full_every_x_days     = 30

    [backup_sequences]
    step01 = snapshot
    """.format(self.intermediate_basedir)

    config_data = textwrap.dedent(config_data)
    path = os.path.join(self.config_dir, "config.ini")
    with open(path, "w") as f:
      f.write(config_data)

    self.config = Config(path)

  # Note: this kind of mocking is not great to do.. as it makes the code
  # super inflexible. That said, it _does_ allow me to test the logic of
  # the code with a bit more confidence without resorting to full
  # integration testing, which is hard to setup (requires root).
  def incremental_subprocess_calls(self, snapshot_name, base_snapshot_name):
    basedir = os.path.join(self.intermediate_basedir, snapshot_name.split("@")[1])
    fileprefix = os.path.join(basedir, "{}.zfs.gpg.".format(snapshot_name.replace("/", "-")))
    return [
      call("mkdir -p {}".format(basedir), stdout=None, check=True, shell=True, env=None),
      call(
        "zfs send -i {} {} | gpg1 -c --cipher-algo AES256 --batch --passphrase 123456 | split - --bytes 1G --suffix-length=4 --numeric-suffixes {}".format(base_snapshot_name, snapshot_name, fileprefix),
        stdout=None, check=True, shell=True, env=None
      )
    ]

  def full_subprocess_calls(self, snapshot_name):
    basedir = os.path.join(self.intermediate_basedir, snapshot_name.split("@")[1] + "-full")
    fileprefix = os.path.join(basedir, "{}.zfs.gpg.".format(snapshot_name.replace("/", "-")))
    return [
      call("mkdir -p {}".format(basedir), stdout=None, check=True, shell=True, env=None),
      call(
        "zfs send  {} | gpg1 -c --cipher-algo AES256 --batch --passphrase 123456 | split - --bytes 1G --suffix-length=4 --numeric-suffixes {}".format(snapshot_name, fileprefix),
        stdout=None, check=True, shell=True, env=None
      ),
    ]

  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_does_nothing_in_dryrun(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    cmd = ExportIntermediate(self.config, self.default_args(full=False, incremental=False, dry_run=True))
    cmd.run()

    subprocess_run.assert_not_called()

  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_exports_full_on_initial_snapshot(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    cmd = ExportIntermediate(self.config, self.default_args(full=False, incremental=False))
    cmd.run()

    self.assertEqual(subprocess_run.mock_calls, self.full_subprocess_calls("data/test@20200515121005"))

  @patch("zfs2cloud.intermediate.datetime")
  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_exports_increment_normally_and_full_if_forced_full(self, subprocess_run, discover_snapshots, datetime_mock):
    mocked_now = datetime.datetime(2020, 5, 20, 12, 10, 5)
    self.datetime_mock_now(datetime_mock, mocked_now)

    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    self.set_last_full_backup(*discover_snapshots.return_value[-1])

    cmd = ExportIntermediate(self.config, self.default_args(full=True, incremental=False))
    cmd.run()

    self.assertEqual(subprocess_run.mock_calls, self.full_subprocess_calls("data/test@20200520120805"))

  @patch("zfs2cloud.intermediate.datetime")
  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_exports_full_if_no_last_full_backup(self, subprocess_run, discover_snapshots, datetime_mock):
    mocked_now = datetime.datetime(2020, 5, 20, 12, 10, 5)
    self.datetime_mock_now(datetime_mock, mocked_now)

    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    cmd = ExportIntermediate(self.config, self.default_args(full=True, incremental=False))
    cmd.run()

    self.assertEqual(subprocess_run.mock_calls, self.full_subprocess_calls("data/test@20200520120805"))

  @patch("zfs2cloud.intermediate.datetime")
  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_exports_full_if_full_every_x_days_passed(self, subprocess_run, discover_snapshots, datetime_mock):
    mocked_now = datetime.datetime(2020, 5, 20, 12, 10, 5)
    self.datetime_mock_now(datetime_mock, mocked_now)

    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
    ]

    old_creation_date = mocked_now - datetime.timedelta(days=30, seconds=2)
    self.set_last_full_backup("data/test@{}".format(old_creation_date.strftime("%Y%m%d%H%M%S")), old_creation_date)

    cmd = ExportIntermediate(self.config, self.default_args(full=True, incremental=False))
    cmd.run()

    self.assertEqual(subprocess_run.mock_calls, self.full_subprocess_calls("data/test@20200520120805"))

  @patch("zfs2cloud.intermediate.datetime")
  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_exports_incremental(self, subprocess_run, discover_snapshots, datetime_mock):
    mocked_now = datetime.datetime(2020, 5, 20, 12, 10, 5)
    self.datetime_mock_now(datetime_mock, mocked_now)

    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    self.set_last_full_backup(*discover_snapshots.return_value[-1])

    cmd = ExportIntermediate(self.config, self.default_args(full=False, incremental=False))
    cmd.run()

    self.assertEqual(subprocess_run.mock_calls, self.incremental_subprocess_calls("data/test@20200520120805", "data/test@20200515121005"))

  @patch("zfs2cloud.intermediate.datetime")
  @patch.object(ExportIntermediate, "_discover_snapshots")
  @patch("subprocess.run")
  def test_export_intermediate_errors_if_last_full_not_found(self, subprocess_run, discover_snapshots, datetime_mock):
    mocked_now = datetime.datetime(2020, 5, 20, 12, 10, 5)
    self.datetime_mock_now(datetime_mock, mocked_now)

    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
    ]

    self.set_last_full_backup("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),

    cmd = ExportIntermediate(self.config, self.default_args(full=False, incremental=False))
    with self.assertRaises(RuntimeError) as r:
      cmd.run()

    self.assertEqual(str(r.exception), "last full snapshot deleted? looked for data/test@20200515121005 but couldn't find it.")
    subprocess_run.assert_not_called()

  @patch.object(PruneIntermediate, "_discover_snapshots")
  def test_prune_intermediate(self, discover_snapshots):
    unrelated_path = os.path.join(self.intermediate_basedir, "unrelated")
    os.mkdir(unrelated_path)

    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    snapshot_paths = [
      os.path.join(self.intermediate_basedir, "20200515121005"),
      os.path.join(self.intermediate_basedir, "20200517121005"),
      os.path.join(self.intermediate_basedir, "20200520120805"),
    ]

    all_paths = snapshot_paths[:]
    all_paths.append(unrelated_path)

    for path in snapshot_paths:
      os.mkdir(path)

    cmd = PruneIntermediate(self.config, self.default_args(dry_run=False, yes=False))
    cmd.run()

    for path in all_paths:
      self.assertTrue(os.path.isdir(path), "{} doesn't exist but should.".format(path))

    cmd = PruneIntermediate(self.config, self.default_args(dry_run=True, yes=True))
    cmd.run()

    for path in all_paths:
      self.assertTrue(os.path.isdir(path), "{} doesn't exist but should.".format(path))

    cmd = PruneIntermediate(self.config, self.default_args(dry_run=False, yes=True))
    cmd.run()

    for path in snapshot_paths[:-1]:
      self.assertFalse(os.path.isdir(path), "{} exist but shouldn't.".format(path))

    self.assertTrue(unrelated_path)

  @patch.object(UploadIntermediateToRemote, "_discover_snapshots")
  @patch("subprocess.run")
  def test_upload_intermediate_uploads_last_full_backup(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    snapshot_paths = [
      os.path.join(self.intermediate_basedir, "20200520120805-full"),
    ]

    for path in snapshot_paths:
      os.mkdir(path)

    self.set_last_full_backup(*discover_snapshots.return_value[0])

    cmd = UploadIntermediateToRemote(self.config, self.default_args(snapshot=None))
    cmd.run()

    subprocess_run.assert_called_once_with(
      "rclone sync -v --stats=60s {0}/{1} b2:bucket/whatever/{1}".format(self.intermediate_basedir, "20200520120805-full"),
      check=True,
      env={"RCLONE_CONFIG": os.path.join(self.config_dir, "rclone.conf")},
      shell=True,
      stdout=None,
    )

  @patch.object(UploadIntermediateToRemote, "_discover_snapshots")
  @patch("subprocess.run")
  def test_upload_intermediate_uploads_last_incremental_backup(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    snapshot_paths = [
      os.path.join(self.intermediate_basedir, "20200520120805"),
    ]

    for path in snapshot_paths:
      os.mkdir(path)

    cmd = UploadIntermediateToRemote(self.config, self.default_args(snapshot=None))
    cmd.run()

    subprocess_run.assert_called_once_with(
      "rclone sync -v --stats=60s {0}/{1} b2:bucket/whatever/{1}".format(self.intermediate_basedir, "20200520120805"),
      check=True,
      env={"RCLONE_CONFIG": os.path.join(self.config_dir, "rclone.conf")},
      shell=True,
      stdout=None,
    )

  @patch.object(UploadIntermediateToRemote, "_discover_snapshots")
  @patch("subprocess.run")
  def test_upload_intermediate_fails_if_backup_not_found_in_path(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    cmd = UploadIntermediateToRemote(self.config, self.default_args(snapshot=None))

    with self.assertRaises(RuntimeError) as r:
      cmd.run()

    subprocess_run.assert_not_called()
    self.assertTrue("cannot find the snapshot intermediate or have too many candidates:" in str(r.exception))

  @patch.object(UploadIntermediateToRemote, "_discover_snapshots")
  @patch("subprocess.run")
  def test_upload_intermediate_uploads_specified_full_backup(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    snapshot_paths = [
      os.path.join(self.intermediate_basedir, "20200515121005-full"),
    ]

    for path in snapshot_paths:
      os.mkdir(path)

    cmd = UploadIntermediateToRemote(self.config, self.default_args(snapshot="data/test@20200515121005"))
    cmd.run()

    subprocess_run.assert_called_once_with(
      "rclone sync -v --stats=60s {0}/{1} b2:bucket/whatever/{1}".format(self.intermediate_basedir, "20200515121005-full"),
      check=True,
      env={"RCLONE_CONFIG": os.path.join(self.config_dir, "rclone.conf")},
      shell=True,
      stdout=None,
    )

  @patch.object(UploadIntermediateToRemote, "_discover_snapshots")
  @patch("subprocess.run")
  def test_upload_intermediate_uploads_specified_incremental_backup(self, subprocess_run, discover_snapshots):
    discover_snapshots.return_value = [
      ("data/test@20200520120805", datetime.datetime(2020, 5, 20, 12, 8, 5)),
      ("data/test@20200517121005", datetime.datetime(2020, 5, 17, 12, 10, 5)),
      ("data/test@20200515121005", datetime.datetime(2020, 5, 15, 12, 10, 5)),
    ]

    snapshot_paths = [
      os.path.join(self.intermediate_basedir, "20200515121005"),
    ]

    for path in snapshot_paths:
      os.mkdir(path)

    cmd = UploadIntermediateToRemote(self.config, self.default_args(snapshot="data/test@20200515121005"))
    cmd.run()

    subprocess_run.assert_called_once_with(
      "rclone sync -v --stats=60s {0}/{1} b2:bucket/whatever/{1}".format(self.intermediate_basedir, "20200515121005"),
      check=True,
      env={"RCLONE_CONFIG": os.path.join(self.config_dir, "rclone.conf")},
      shell=True,
      stdout=None,
    )
