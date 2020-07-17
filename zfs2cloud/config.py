from configparser import ConfigParser
import os
import shlex


class Config(object):
  SINCE_LAST_FULL = "since_last_full"
  SINCE_LAST_INCREMENTAL = "since_last_incremental"
  NEVER_INCREMENTAL = "never_incremental"

  def __init__(self, config_path, commands=None):
    self._commands = commands

    self.c = ConfigParser(allow_no_value=True)
    self.c["main"] = {
      "incremental_strategy": self.SINCE_LAST_FULL,
      "split_size": "1G",
      "rclone_conf": os.environ.get("RCLONE_CONFIG", os.path.join(os.path.expanduser("~"), ".rclone.conf")),
      "rclone_bwlimit": "-v --stats=60s",
      "rclone_global_flags": "",
      "rclone_args": "",
      "oldest_snapshot_days": 120,
      "full_every_x_days": 30,
      "on_failure": "",
    }

    self.config_path = config_path
    # Read the config file
    self.c.read(config_path)

    # Generate the proper backup sequences
    self.backup_sequences = []
    for k in sorted(list(self.c["backup_sequences"].keys())):
      v = self.c["backup_sequences"][k]
      if v.startswith("./"):
        # If the step starts with !./, assume the script is relative to the config file.
        v = self.get_abspath_from_config_file_folder(v[2:])

      self.backup_sequences.append(v)

    if self.main["on_failure"] and self.main["on_failure"].startswith("./"):
      self.main["on_failure"] = self.get_abspath_from_config_file_folder(self.main["on_failure"][2:])

    if self.main["rclone_conf"] and self.main["rclone_conf"].startswith("./"):
      self.main["rclone_conf"] = self.get_abspath_from_config_file_folder(self.main["rclone_conf"][2:])

    # Generate internal variables
    self.autofill_variables()

    # Validate
    self.validate()

  def __getattr__(self, key):
    return self.c[key]

  def get_abspath_from_config_file_folder(self, filename):
    return os.path.join(os.path.dirname(os.path.abspath(self.config_path)), filename)

  def autofill_variables(self):
    self.zfs_path = os.environ.get("ZFS_PATH", "zfs")
    self.rclone_path = os.environ.get("RCLONE_PATH", "rclone")

    self.lock_path = os.path.join(self.main["intermediate_basedir"], "_lock")
    self.last_full_cache_file = os.path.join(self.main["intermediate_basedir"], "_last_full_backup")

  def validate(self):
    for k in ["encryption_passphrase", "zfs_fs", "intermediate_basedir", "remote"]:
      if k not in self.main:
        raise KeyError("{} must be specified in [main]".format(k))

    if not os.path.isdir(self.main["intermediate_basedir"]):
      raise ValueError("intermediate_basedir: {} is not a valid directory".format(self.main["intermediate_basedir"]))

    if self.main["on_failure"] and not os.path.isfile(self.main["on_failure"]):
      raise ValueError("on_failure: {} is not a valid file".format(self.main["on_failure"]))

    if not os.path.isfile(self.main["rclone_conf"]):
      raise ValueError("rclone_conf: {} is not a valid file".format(self.main["rclone_conf"]))

    for step in self.backup_sequences:
      if step.startswith("/"):
        if not os.path.isfile(step):
          raise ValueError("backup_sequences: {} is not a valid file".format(step))
      else:
        if self._commands is not None:
          commands = set(self._commands.keys())
          command = shlex.split(step)[0]
          if command not in commands:
            raise ValueError("{} is not a valid step ({})".format(step, commands))

    for k in ["full_every_x_days", "oldest_snapshot_days"]:
      try:
        self.main.getint(k)
      except ValueError as e:
        raise ValueError("{} must be an integer ({})".format(k, str(e)))

    if self.main["incremental_strategy"] != self.SINCE_LAST_FULL:
      raise NotImplementedError("incremental_strategy = {} not implemented".format(self.main["incremental_strategy"]))

  def show(self, logger):
    other_info = {
      "zfs_path": self.zfs_path,
      "rclone_path": self.rclone_path,
      "lock_path": self.lock_path,
      "last_full_cache_file": self.last_full_cache_file,
      "locked": os.path.exists(self.lock_path),
    }

    logger.info("Configuration")
    logger.info("=============")

    maxl = len(max(
      list(self.main.keys()) + list(other_info.keys()),
      key=lambda v: len(v)
    ))

    self._log_section(logger, "main", self.main, maxl)
    logger.info("")
    self._log_section(logger, "backup_sequences", {"step_" + str(i + 1): s for i, s in enumerate(self.backup_sequences)}, maxl)
    logger.info("")
    self._log_section(logger, "autofilled", other_info, maxl)

  def _log_section(self, logger, section_name, section, maxl):
    logger.info("[{}]".format(section_name))
    for k, v in section.items():
      if k == "encryption_passphrase":
        v = "*" * len(v)

      logger.info("{: <{width}} = {}".format(k, v, width=maxl))
