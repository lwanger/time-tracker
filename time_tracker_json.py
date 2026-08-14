"""Reading and writing the JSON data files - clients.json and invoices.json.

Both are small hand-editable dicts, which is why they are written indented rather
than compactly.

Leonard Wanger, 2026
"""

import json
import os
from typing import Any


def read_json_args(args_file: str) -> dict[str, Any]:
    # read arguments from a JSON file
    stored_args = {}

    if os.path.isfile(args_file):
        with open(args_file) as data_file:
            stored_args = json.load(data_file)

    return stored_args


def write_json_args(args_file: str, args: dict[str, Any]) -> None:
    """Write arguments to a JSON file, indented.

    ``clients.json`` is hand-edited and diff-reviewed, and ``add-client``/``edit-client``
    rewrite the whole file - so it is written the way a person would write it rather
    than as one long line.

    Args:
        args_file: Path to the JSON file to write.
        args: The mapping to store.

    Raises:
        OSError: If the file cannot be written.
    """
    with open(args_file, "w", encoding="utf-8") as data_file:
        data_file.write(json.dumps(args, indent=2))
        data_file.write("\n")
