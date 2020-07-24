import os
import textwrap

from .test_case import Zfs2CloudTestCase
from zfs2cloud.command import Lock, Unlock
from zfs2cloud.config import Config


class CommandTest(Zfs2CloudTestCase):
  def setUp(self):
    super().setUp()

    config_data = """\
    [main]
    encryption_passphrase = 123456
    zfs_fs                = data/test
    intermediate_basedir  = {}
    remote                = b2:bucket/whatever
    rclone_conf           = ./rclone.conf

    [backup_sequences]
    step01 = snapshot
    """.format(self.intermediate_basedir)

    config_data = textwrap.dedent(config_data)
    path = os.path.join(self.config_dir, "config.ini")
    with open(path, "w") as f:
      f.write(config_data)

    self.config = Config(path)

  def test_lock_unlock(self):
    cmd = Lock(self.config, self.default_args())
    cmd.run()

    lock_path = os.path.join(self.intermediate_basedir, "_lock")

    self.assertTrue(os.path.exists(lock_path))

    cmd = Lock(self.config, self.default_args())
    with self.assertRaises(RuntimeError) as r:
      cmd.run()

    self.assertEqual(str(r.exception), "lockfile already exists!")
    self.assertTrue(os.path.exists(lock_path))

    cmd = Unlock(self.config, self.default_args())
    cmd.run()

    self.assertFalse(os.path.exists(lock_path))

    cmd = Unlock(self.config, self.default_args())
    cmd.run()

    self.assertFalse(os.path.exists(lock_path))
