import configparser
import pathlib
from typing import Final

from strands import tool

INVENTORY_PATH: Final[pathlib.Path] = pathlib.Path("ansible/inventory.ini")


@tool
def get_ansible_inventory_groups() -> list[str]:
    """Return the supported top-level inventory groups from ansible/inventory.ini."""
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(INVENTORY_PATH, encoding="utf-8")
    return sorted(section for section in parser.sections() if ":" not in section)
