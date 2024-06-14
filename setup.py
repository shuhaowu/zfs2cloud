from setuptools import setup, find_packages

setup(
  name="zfs2cloud",
  version="1.2.0",
  description="Backup ZFS to the cloud",
  packages=find_packages(),
  test_suite="tests",
  entry_points={
    "console_scripts": [
      "zfs2cloud=zfs2cloud:main"
    ],
  }
)
