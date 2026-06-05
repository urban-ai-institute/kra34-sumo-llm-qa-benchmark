#!/usr/bin/env python3
"""Extract <tlLogic> and TLS-controlled <connection> elements from .net.xml
files and write them to separate {network}_tls.add.xml files."""

import xml.etree.ElementTree as ET
from pathlib import Path

NETWORK_DIR = Path(__file__).parent / "data" / "network"
NETWORKS = ["grid_8x8", "random", "random_large", "times_square"]


def extract_tls(net_file: Path, out_file: Path):
    tree = ET.parse(str(net_file))
    root = tree.getroot()

    add_root = ET.Element("additional")

    for tl in root.findall("tlLogic"):
        add_root.append(tl)

    for conn in root.findall("connection"):
        if conn.get("tl"):
            add_root.append(conn)

    ET.ElementTree(add_root).write(str(out_file), encoding="utf-8", xml_declaration=True)
    tl_count = len(add_root.findall("tlLogic"))
    conn_count = len(add_root.findall("connection"))
    print(f"  {out_file.name}: {tl_count} tlLogic, {conn_count} connections")


def main():
    for net in NETWORKS:
        net_file = NETWORK_DIR / f"{net}.net.xml"
        out_file = NETWORK_DIR / f"{net}_tls.add.xml"
        print(f"{net}:")
        extract_tls(net_file, out_file)


if __name__ == "__main__":
    main()
