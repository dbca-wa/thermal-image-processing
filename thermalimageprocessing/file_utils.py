import os
import shutil


def copy_tree_files_only(src, dst):
    """
    Recursively copy a directory tree from src to dst, copying only file data.

    Unlike shutil.copytree, this does NOT call shutil.copystat on directories,
    which prevents [Errno 1] Operation not permitted errors on restricted storage
    mounts (e.g., Azure Container rclone mounts) that do not support setting
    directory timestamps or permissions.
    """
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            copy_tree_files_only(s, d)
        else:
            shutil.copyfile(s, d)
