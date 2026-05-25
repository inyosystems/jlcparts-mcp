def pytest_addoption(parser):
    parser.addoption(
        "--attribute-section",
        action="append",
        default=[],
        help=(
            "Generated attribute section to scan. May be passed multiple times; "
            "the JLC_ATTRIBUTE_SECTION environment variable is still supported."
        ),
    )
    parser.addoption(
        "--attribute-value-re",
        default=None,
        help=(
            "Optional regular expression limiting generated values scanned by "
            "test_attribute_section_scan.py."
        ),
    )
    parser.addoption(
        "--attribute-section-limit",
        type=int,
        default=None,
        help=(
            "Optional maximum number of generated values scanned per attribute "
            "section by test_attribute_section_scan.py."
        ),
    )
