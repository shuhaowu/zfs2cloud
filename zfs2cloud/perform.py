import argparse
import copy
import os
import subprocess
import traceback
import shlex

from .command import Command


class Perform(Command):
  """Performs all steps outlined in backup_sequences"""

  def run(self):
    try:
      self.actual_run()
    except Exception:
      if self.config.main["on_failure"] and os.path.exists(self.config.main["on_failure"]):
        subprocess.run(self.config.main["on_failure"], input=traceback.format_exc(), text=True, shell=True)

      raise

  def actual_run(self):
    if self.args.dry_run:
      self.logger.info("in dry run mode")

    for step in self.config.backup_sequences:
      if step.startswith("/"):
        self._execute(step, dry_run=self.args.dry_run)
        continue

      step = shlex.split(step)
      self.logger.info("executing {}".format(step))

      command_cls = self.args._commands[step[0]]
      parser = argparse.ArgumentParser()
      command_cls.add_arguments(parser)
      parent_args = copy.deepcopy(self.args)
      args = parser.parse_args(step[1:], namespace=parent_args)

      command = command_cls(self.config, args)
      command.run()
