import os
import sys
from natsort import natsorted

"""
Usage Guide for generate_structure.py

How to Use:
-----------
- From your project root directory, run:
    python tools/generate_structure.py .
- The `.` means "current directory", so the script will print the structure of your main project folder only.

- To print the structure of another directory, pass its path instead:
    python tools/generate_structure.py /full/path/to/your/folder

How It Works:
-------------
- The script takes a single argument (the folder to print the structure for).
- `.` means "current directory" (where you are right now).
- `..` means "parent directory" (one folder up).
- You can also use any valid relative or absolute path.
- This makes it flexible—no need to move the script or change its location!

Examples:
---------
# Print your main project tree
python tools/generate_structure.py .

# Print everything in parent folder (not recommended—prints all projects!)
python tools/generate_structure.py ..

# Print a specific directory
python tools/generate_structure.py /Users/you/projects/Echo_Protocol

"""

def generate_project_structure(root_dir, exclude_dirs=None):
    """
    Generate a formatted string representing the directory structure of a project in a natural folder-first order.

    Args:
        root_dir (str): The root directory of the project.
        exclude_dirs (list): List of directory names to exclude from the output.

    Returns:
        str: A string representing the formatted directory structure.
    """
    if exclude_dirs is None:
        exclude_dirs = ["venv", "__pycache__", ".git", "2m", "5m", "15m", "timeline"]

    def walk_dir(directory, prefix=""):
        structure = ""
        entries = os.listdir(directory)  # Get all entries
        # Separate folders and files
        folders = [e for e in entries if os.path.isdir(os.path.join(directory, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(directory, e))]

        # Sort folders and files separately
        sorted_folders = natsorted(folders)
        sorted_files = natsorted(files)

        # Combine folders and files
        sorted_entries = sorted_folders + sorted_files

        for idx, entry in enumerate(sorted_entries):
            entry_path = os.path.join(directory, entry)
            is_last = idx == len(sorted_entries) - 1
            connector = "└── " if is_last else "├── "

            if os.path.isdir(entry_path):
                # Include excluded directories without showing their contents
                if entry in exclude_dirs:
                    structure += f"{prefix}{connector}{entry}/\n"
                    continue
                structure += f"{prefix}{connector}{entry}/\n"
                structure += walk_dir(entry_path, prefix + ("    " if is_last else "│   "))
            else:
                structure += f"{prefix}{connector}{entry}\n"
        return structure

    return f"{os.path.basename(root_dir)}/\n" + walk_dir(root_dir)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        project_root = os.path.abspath(sys.argv[1])
    else:
        project_root = os.path.abspath(os.path.dirname(__file__))

    # Generate the structure and print it
    project_structure = generate_project_structure(project_root)
    print(project_structure)
