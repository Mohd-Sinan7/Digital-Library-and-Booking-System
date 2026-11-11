"""Tests verifying Lab 3 architecture deliverables and integrity (DLBS-6)."""

import xml.etree.ElementTree as ET
from pathlib import Path


def test_lab3_directory_and_files_exist():
    base = Path("Lab3")
    assert base.is_dir(), "Lab3 directory must exist"

    drawio_file = base / "component_diagram.drawio"
    svg_file = base / "component_diagram.svg"
    justification_file = base / "architecture_justification.md"

    assert drawio_file.exists(), "component_diagram.drawio must exist"
    assert svg_file.exists(), "component_diagram.svg must exist"
    assert justification_file.exists(), "architecture_justification.md must exist"


def test_drawio_diagram_valid_xml_and_components():
    drawio_file = Path("Lab3/component_diagram.drawio")
    tree = ET.parse(drawio_file)
    root = tree.getroot()
    assert root.tag == "mxfile", "Root tag of draw.io must be mxfile"

    content = drawio_file.read_text(encoding="utf-8")
    expected_substrings = [
        "Web UI",
        "FastAPI",
        "Catalog",
        "Reading",
        "Booking",
        "Recommendation Engine",
        "Database",
        "CI/CD Pipeline",
    ]
    for comp in expected_substrings:
        assert comp in content, f"Component {comp} must be present in drawio file"


def test_svg_diagram_renders_valid_svg():
    svg_file = Path("Lab3/component_diagram.svg")
    content = svg_file.read_text(encoding="utf-8")
    assert "<svg" in content and "</svg>" in content, "Must be valid SVG structure"
    assert "Book Catalog" in content
    assert "Recommendation Engine" in content
    assert "Booking" in content
    assert "Database" in content


def test_architecture_justification_structure():
    doc = Path("Lab3/architecture_justification.md").read_text(encoding="utf-8")
    required_sections = [
        "Modular Monolith",
        "Single Responsibility Principle",
        "Loose Coupling",
        "Quality Attributes",
        "Performance",
        "Concurrency",
        "Security",
    ]
    for sec in required_sections:
        assert sec in doc, f"Section '{sec}' must be covered in architecture justification"
