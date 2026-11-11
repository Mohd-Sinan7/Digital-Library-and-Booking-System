"""Tests for DLBS-15: Presentation slides deck validation."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"
SLIDES_MD = DOCS_DIR / "presentation_slides.md"
SLIDES_HTML = DOCS_DIR / "presentation_slides.html"


def test_slides_files_exist():
    """Verify both markdown and interactive HTML presentation slide files exist."""
    assert SLIDES_MD.exists(), "presentation_slides.md must exist in docs/"
    assert SLIDES_HTML.exists(), "presentation_slides.html must exist in docs/"


def test_slides_markdown_content():
    """Verify presentation_slides.md contains all required sections and topics."""
    content = SLIDES_MD.read_text(encoding="utf-8")

    # Team members coverage
    assert "Mohammed Sinan M T" in content
    assert "M Rishyendra" in content
    assert "Nagalapuram Sai Mukesh Reddy" in content
    assert "Marreddy Rushieswar Reddy" in content

    # All module sections present
    assert "Module 1: Recommendation Engine" in content or "Module 1" in content
    assert "Module 2: Book Catalog" in content or "Module 2" in content
    assert "Module 3: Users & Reading Tracking" in content or "Module 3" in content
    assert "Module 4: Booking & Borrowing" in content or "Module 4" in content

    # Key topics specified in Member 1 document
    assert "Problem Statement & Motivation" in content
    assert "Requirements Baseline" in content
    assert "System Architecture" in content
    assert "Recommendation Engine Evaluation" in content or "Evaluation" in content
    assert "CI/CD Pipeline" in content
    assert "Agile Project Management" in content or "Jira Burndown" in content
    assert "Quality Assurance" in content or "Testing Strategy" in content
    assert "Live Demonstration Script" in content or "Demonstration" in content
    assert "Lessons Learned" in content

    # Speaker notes present
    assert "Speaker Notes" in content


def test_slides_html_structure():
    """Verify presentation_slides.html contains interactive structure and scripts."""
    content = SLIDES_HTML.read_text(encoding="utf-8")

    assert "<!DOCTYPE html>" in content
    assert "id=\"deck-container\"" in content
    assert "slide active" in content

    # Ensure all 14 slides are present
    for i in range(1, 15):
        assert f"id=\"slide-{i}\"" in content, f"slide-{i} missing in HTML presentation"

    # Ensure interactive navigation script exists
    assert "nextSlide()" in content
    assert "prevSlide()" in content
    assert "toggleNotes()" in content
    assert "toggleFullScreen()" in content
