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
        "--attribute-value",
        action="append",
        default=[],
        help=(
            "Raw attribute value to test directly with --attribute-section. "
            "May be passed multiple times; avoids reading generated datatables."
        ),
    )
    parser.addoption(
        "--attribute-value-file",
        default=None,
        help=(
            "Optional newline-delimited file with raw attribute values to test "
            "directly with --attribute-section. This avoids rebuilding "
            "generated datatables and avoids scanning the SQLite cache during "
            "pytest."
        ),
    )
    parser.addoption(
        "--attribute-sqlite",
        default=None,
        help=(
            "Optional legacy cache.sqlite3 path. This avoids a full generated "
            "datatable rebuild, but can be slow because attributes are stored "
            "inside JSON blobs."
        ),
    )
    parser.addoption(
        "--attribute-source-db",
        default=None,
        help=(
            "Optional compact source-db-v2 SQLite path. The focused attribute "
            "section scan reads only the selected raw attribute values from "
            "SQLite, avoiding a full generated datatable rebuild."
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
    parser.addoption(
        "--attribute-all-strings",
        action="store_true",
        default=False,
        help=(
            "Scan all generated string values for the selected attribute section, "
            "not only numeric-looking strings."
        ),
    )
