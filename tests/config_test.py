from contextlib import contextmanager
import os
import tempfile
import textwrap
import shutil

import unittest

from zfs2cloud.config import Config


class ConfigTest(unittest.TestCase):
  def setUp(self):
    self.config_dir = tempfile.mkdtemp()
    with open(os.path.join(self.config_dir, "rclone.conf"), "w"):
      pass

  def teardown(self):
    shutil.rmtree(self.config_dir)

  @contextmanager
  def config(self, data):
    data = textwrap.dedent(data)
    path = os.path.join(self.config_dir, "config.ini")
    with open(path, "w") as f:
      f.write(data)

    yield Config(path)

    os.remove(path)

  def test_backup_sequences_script_paths(self):
    data = """\
    [main]
    encryption_passphrase = 123456
    zfs_fs                = data/test
    intermediate_basedir  = /data/tmp
    remote                = b2:bucket/whatever
    rclone_conf           = ./rclone.conf

    [backup_sequences]
    step01 = ./script
    """

    script_path = os.path.join(self.config_dir, "script")

    with open(script_path, "w"):
      pass

    with self.config(data) as c:
      self.assertEqual(c.backup_sequences, [script_path])
