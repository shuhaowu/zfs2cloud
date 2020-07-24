import os

from .test_case import Zfs2CloudTestCase


class ConfigTest(Zfs2CloudTestCase):
  def test_transforms_variables(self):
    data = """\
    [main]
    encryption_passphrase = 123456
    zfs_fs                = data/test
    intermediate_basedir  = {}
    remote                = b2:bucket/whatever
    rclone_conf           = ./rclone.conf

    [backup_sequences]
    step01 = ./script
    """.format(self.intermediate_basedir)

    script_path = os.path.join(self.config_dir, "script")
    with open(script_path, "w"):
      pass

    with self.config(data) as c:
      self.assertEqual(c.backup_sequences, [script_path])
      self.assertEqual(c.main["rclone_conf"], self.rclone_path)

      self.assertEqual(c.lock_path, os.path.join(self.intermediate_basedir, "_lock"))
      self.assertEqual(c.last_full_cache_file, os.path.join(self.intermediate_basedir, "_last_full_backup"))

  def test_validate_full_every_and_oldest_snapshot(self):
    data = """\
    [main]
    encryption_passphrase = 123456
    zfs_fs                = data/test
    intermediate_basedir  = {}
    remote                = b2:bucket/whatever
    rclone_conf           = ./rclone.conf
    oldest_snapshot_days  = 7
    full_every_x_days     = 14

    [backup_sequences]
    step01 = snapshot
    """.format(self.intermediate_basedir)

    with self.assertRaises(ValueError) as r:
      with self.config(data):
        pass

    self.assertEqual(str(r.exception), "oldest_snapshot_days must be greater than full_every_x_days so that incremental backups based on the last full backup can take place")
