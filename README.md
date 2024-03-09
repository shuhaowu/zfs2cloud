ZFS2Cloud
=========

ZFS2Cloud backs up ZFS file systems via snapshots. It's designed for homelab
use cases where you want to take backups and upload them to offsite locations
(via rclone) with minimal downtime. The general workflow is as follows:

1. **(Downtime starts)** The application server is gracefully shutdown to
   maintain data consistency.
2. A ZFS snapshot is taken. This should be instantaneous.
3. **(Downtime ends)** The application server is restarted.
4. The snapshot is processed in either intermediate mode or file mode.
5. The intermediate files or the raw files from the snapshot are uploaded to
   the cloud.
6. Local pruning of old intermediate data and/or ZFS snapshots occurs.

There are two different snapshot processing modes:

- [**Intermediate mode**](#intermediate-mode): The ZFS FS snapshot is exported
  via `zfs send` (either full or incrementally) into files. To ensure the exported
  file is not one giant file which is not as parallelizable for cloud data
  providers, the file is splitted. All files are also encrypted via a symmetric
  passphrase with gpg.
- [**File mode**](#file-mode): The ZFS FS snapshot is read-only mounted to a
  path. The files within the mounted path are then uploaded via rclone. No
  encryption is applied in this mode. You can use rclone's [`crypt`
  backend](https://rclone.org/crypt/) to establish client-side encryption.

System requirements
-------------------

- Python 3
- ZFS with the `zfs` command available
   - Root permissions or permissions to invoke the `zfs` command
- Optionally: `rclone`

How it works
------------

### Intermediate mode

The intermediate mode intends to upload the incremental ZFS filesystem snapshots
as encrypted files to the cloud (via `rclone`). This makes the restore very
simple, as all you need to do is to get the encrypted files, decrypt it, and use
`zfs recv` to restore the filesystem. This is best suited for data for
production services that have arbitrary on-disk formats.

As an example, the ZFS filesystem `fs` has no initial snapshot. Upon running
`zfs2cloud` on 2024-01-01 00:00:00, an initial snapshot is generated and named
`fs@20240101000000`. Since there are no previous backup, the full snapshot is
exported via `zfs send`. The resulting data stream is encrypted via `gpg` and
splitted into multiple files, `fs@20240101000000.zfs.gpg.0000`,
`fs@20240101000000.zfs.gpg.0001`, and so on:

```mermaid
flowchart LR

A[fs@20240101000000] --> B[fs@20240101000000.zfs.gpg.0000]
A --> C[fs@20240101000000.zfs.gpg.0001]
A --> D[fs@20240101000000.zfs.gpg.0002]
A --> E[...]
```

The splitted files are stored in "intermediate" directory. Once the entire
snapshot has been encrypted and exported, the resulting data can be uploaded to
the clone via the `upload-intermediate-to-remote` step (via `rclone`).
`zfs2cloud` will also remember 2024-01-01 00:00:00 is the last known full
backup.

The next day, `zfs2cloud` runs again. A second snapshot, `fs@20240102000000`
is created. Instead of exporting the entire snapshot again, it detects that a
previous full backup was made and only export an incremental snapshot via `zfs
send -i`:

```mermaid
flowchart LR

A[fs@20240101000000 -> fs@20240102000000] --> B[fs@20240102000000.zfs.gpg.0000]
```

The splitted files are once again stored in an intermediate directory and the
results are uploaded to the cloud.

On the third day, `zfs2cloud` runs for the third time. A third snapshot,
`fs@20240103000000` is created. A full backup was made two days ago, and
`zfs2cloud` export an incremental snapshot **not against the previous day's
snapshot, but against the last known full backup**:

```mermaid
flowchart LR

A[fs@20240101000000 -> fs@20240103000000] --> B[fs@20240103000000.zfs.gpg.0000]
```

The reason we do not export an incremental snapshot against the previous
incremental snapshot is for redundancy reasons. In homelab environments, it is
frequently infeasible or very costly to validate backups. It is also feasible
for `zfs2cloud` or `rclone` to run into some sort of unhandled error. If
`zfs2cloud` always exported incremental snapshots from the previous incremental
snapshot, if any of the middle snapshot is corrupted, it will cause all
snapshots after it to be lost. Trading off backup size with reliability is a
intentional decision made in the design of this software.

After a certain amount of days (configurable via `full_every_x_days`), a new
full backup is created and uploaded. Subsequent incremental backups will thus
use this new full backup as a base.

Cloud storage can be configured so that files over N days are automatically
deleted. This will automatically prune the data on the cloud and removes the
need to manually manage and prune the updated data. While this could result in
some orphaned incremental snapshots being left behind on the cloud storage when
the full backup is deleted, it is a safer method than using custom code to prune
the older backups.

### File mode

File mode is designed to upload the actual files to the cloud, as opposed to
incremental snapshots. This makes the backup more reliable and more resilient to
corruption, as it skips the complexity of ZFS. This is best suited for regular
files (so not a custom storage file format that many applications require) that
are highly critical where complexity arising from ZFS could be detrimental for
reliability over decades. It could also be good for situations where incremental
snapshots takes up too much storage. An example of this situation would be for
large photo/video collections.

The way this mode works is as follows:

1. Initially, the ZFS filesystem `fs` has no snapshots. A snapshot is taken and
   named `fs@20240101000000`.
2. The snapshot `fs@20240101000000` is mounted to a configurable path.
3. Using rclone, the files within the mounted path can be uploaded to the cloud.
4. The snapshot is unmounted from the disk.
5. Snapshot pruning can occur at this point.


Note: this mode does not provide the following features out of the box:

- Client-side encryption
   - Can be achieved with rclone's [crypt backend](https://rclone.org/crypt/)
- Incremental backup
   - Can be achieved with another backup tool that runs after the snapshot is
     mounted.
