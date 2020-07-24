from argparse import Namespace
from contextlib import contextmanager
from datetime import datetime
import os
import shutil
import json
import tempfile
import textwrap
import unittest

from zfs2cloud.config import Config


class Zfs2CloudTestCase(unittest.TestCase):
  def setUp(self):
    self.config_dir = tempfile.mkdtemp()
    self.rclone_path = os.path.join(self.config_dir, "rclone.conf")
    with open(self.rclone_path, "w"):
      pass

    self.intermediate_basedir = tempfile.mkdtemp()

  def teardown(self):
    shutil.rmtree(self.config_dir)
    shutil.rmtree(self.intermediate_basedir)

  @contextmanager
  def config(self, data):
    data = textwrap.dedent(data)
    path = os.path.join(self.config_dir, "config.ini")
    with open(path, "w") as f:
      f.write(data)

    yield Config(path)

    os.remove(path)

  def default_args(self, **kwargs):
    default_options = {
      "dry_run": False,
    }

    default_options.update(kwargs)

    return Namespace(**default_options)

  def datetime_mock_now(self, datetime_mock, now):
    datetime_mock.now.return_value = now
    datetime_mock.side_effect = lambda *args, **kw: datetime(*args, **kw)

  def set_last_full_backup(self, snapshot_name, creation_date):
    creation_date = creation_date.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(self.intermediate_basedir, "_last_full_backup"), "w") as f:
      json.dump([snapshot_name, creation_date], f)
