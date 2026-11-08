from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent / "docs" / "qa"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def test_qa_files_exist_and_non_empty():
    """Verify all four mandatory QA documents exist in docs/qa/ and are non-empty."""
    expected_files = [
        "test-plan.md",
        "test-cases.md",
        "rtm.md",
        "test-summary.md",
    ]
    for filename in expected_files:
        path = QA_DIR / filename
        assert path.exists(), f"Missing QA deliverable: {filename}"
        assert path.stat().st_size > 1000, f"QA deliverable {filename} is too small / incomplete"


def test_rtm_contains_all_booking_requirements():
    """DLBS-56: Verify RTM contains all functional and non-functional requirements for Booking."""
    rtm_path = QA_DIR / "rtm.md"
    content = rtm_path.read_text(encoding="utf-8")

    # FR-B1 to FR-B10
    for i in range(1, 11):
        req_id = f"FR-B{i}"
        assert req_id in content, f"Requirement {req_id} missing from RTM"

    # NFR-B1 to NFR-B3
    for i in range(1, 4):
        nfr_id = f"NFR-B{i}"
        assert nfr_id in content, f"Requirement {nfr_id} missing from RTM"


def test_rtm_contains_all_modules_and_passed_status():
    """DLBS-56: Verify RTM covers all four system modules and all rows show Passed."""
    rtm_path = QA_DIR / "rtm.md"
    content = rtm_path.read_text(encoding="utf-8")

    # Verify Catalog requirements
    for i in range(1, 9):
        assert f"FR-C{i}" in content

    # Verify Users requirements
    for i in range(1, 8):
        assert f"FR-U{i}" in content

    # Verify Recommender requirements
    for i in range(1, 7):
        assert f"FR-R{i}" in content

    # Verify that there are no unverified or failed requirements
    assert "Pending" not in content
    assert "Failed" not in content
    assert "**Passed**" in content


def test_test_summary_report_has_required_sections():
    """DLBS-56: Verify test-summary.md contains all sections mandated by QA Lead duties."""
    summary_path = QA_DIR / "test-summary.md"
    content = summary_path.read_text(encoding="utf-8")

    required_sections = [
        "Executive Summary",
        "Test Execution Statistics",
        "Statement Code Coverage Breakdown",
        "Defect Tracking and Resolution",
        "Non-Functional Requirements Verification",
        "Open Risks and Mitigation",
        "Retrospective and Lessons Learned",
        "Formal Quality Assurance Sign-off",
    ]

    for section in required_sections:
        assert section in content, f"Mandatory section '{section}' missing from test-summary.md"


def test_test_summary_report_sign_off_and_author():
    """DLBS-56: Verify report is dated, signed by QA Lead Marreddy Rushieswar Reddy."""
    summary_path = QA_DIR / "test-summary.md"
    content = summary_path.read_text(encoding="utf-8")

    assert "Marreddy Rushieswar Reddy" in content
    assert "Member 4" in content
    assert "QA Lead" in content
    assert "7 November 2026" in content or "7 Nov 2026" in content
    assert "PES1UG24AM158" in content
    assert "APPROVED FOR RELEASE" in content or "GO FOR PRESENTATION" in content


def test_test_cases_template_and_module_coverage():
    """DLBS-56: Verify test-cases.md follows the standardized template for all modules."""
    tc_path = QA_DIR / "test-cases.md"
    content = tc_path.read_text(encoding="utf-8")

    assert "Standard Template" in content
    assert "TC-B01" in content
    assert "TC-C01" in content
    assert "TC-U01" in content
    assert "TC-R01" in content
    assert "Execution Summary" in content
