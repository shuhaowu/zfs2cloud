ZFS2Cloud
=========

General backup work flow
------------------------

1. In a cronjob, zfs2cloud runs every day.
2. When it starts, zfs2cloud looks at the config.ini file and executes the list
   of steps as specified in `backup-sequences`. A typical one is as follows:
   1. Create a lock file to prevent another backup for the same thing from
      taking place.
   2. Perform some pre-snapshot operations, such as shutting down the
      application temporarily.
   3. Perform the `zfs snapshot` operation. This should take no more than a few
      seconds.
   4. Perform some post-snapshot operations, such as restart the application.
   5. Exports the snapshot to files (called intermediates), via `gpg` and
      `split`. This is exported to a local path (or maybe something on NFS).
      These files are by default generated **incremental from the last full
      snapshot** (`zfs send -i`), but every X many days (according to the
      `full_every_x_days` config), a full backup is exported.
   6. The intermediate directory can be pruned. This will remove all but the
      most recent intermediate files.
   7. The actual ZFS snapshots can be pruned. This will `zfs destroy` and
      snapshots older than `oldest_snapshot_days`.
   8. The intermediate files is uploaded to the cloud via `rclone`.
   9. Finally, remove the lock file.

The cloud storage can be configured so that files over N days is automatically
deleted. This will automatically prune the data from the cloud and remove the
need to manage the remote snapshots manually. This does mean that some orphaned
incremental snapshots are present on the cloud host and these files cannot be
restored from as the full snapshots are already deleted. One could also create
some custom code to trim those snapshots.

These steps are configurable via `backup-sequences`, which is documented more
below. One can be creative and use some sort of network file system and only
export the intermediate without uploading via rclone, and prune using external
scripts.

System Requirements
-------------------

- Python 3
- ZFS, and `zfs` command available (so root, or somehow got the permission)
- `rclone` (optional)

Descriptions
------------

### Global Flags ###

### Commands ###

Config File
-----------

### Main Configuration ###

### Backup Sequences ###
