-- Synthetic test-only schema and records. Never copy these rows into production data.
PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    path TEXT NOT NULL
);
CREATE TABLE components (
    component_id TEXT PRIMARY KEY,
    manufacturer_normalized TEXT,
    family TEXT,
    part_number TEXT,
    component_type TEXT,
    record_status TEXT,
    source_file_ref TEXT,
    source_locator TEXT
);
CREATE TABLE component_attributes (
    attribute_id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL,
    parameter_key TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    numeric_value REAL,
    unit TEXT,
    min_value REAL,
    max_value REAL,
    record_status TEXT,
    source_file_ref TEXT,
    source_locator TEXT
);

INSERT INTO sources (source_id, path) VALUES
    ('SRC-001', 'test-catalog.pdf'),
    ('SRC-002', 'verified-catalog.pdf');

INSERT INTO components VALUES
    ('C-001', 'TestCo', 'Test', 'TEST-001', 'Circuit Breaker/Contactor', 'extracted', 'test-catalog.pdf', 'page:1'),
    ('C-002', 'TestCo', 'Test', 'TEST-002', 'Motor Protection', 'verified', 'verified-catalog.pdf', 'page:2'),
    ('C-003', 'TestCo', 'Test', 'TEST-003', 'Circuit Breaker', 'needs_review', 'test-catalog.pdf', 'page:3'),
    ('C-004', 'TestCo', 'Test', 'TEST-004', 'Circuit Breaker', 'raw', 'test-catalog.pdf', 'page:4'),
    ('C-005', 'TestCo', 'Test', 'TEST-005', 'Circuit Breaker', 'deprecated', 'test-catalog.pdf', 'page:5'),
    ('C-006', 'TestCo', 'Test', 'TEST-006', 'Contactor', 'extracted', 'test-catalog.pdf', 'page:6'),
    ('C-007', 'TestCo', 'Test', 'TEST-007', 'Circuit Breaker', 'extracted', 'test-catalog.pdf', 'page:7'),
    ('C-008', 'TestCo', 'Test', 'TEST-008', 'Motor Protection', 'extracted', 'test-catalog.pdf', 'page:8'),
    ('C-009', 'TestCo', 'Test', 'TEST-009', 'Motor Protection', 'extracted', 'test-catalog.pdf', 'page:9'),
    ('C-010', 'TestCo', 'Test', 'TEST-010', 'Motor Protection', 'extracted', 'test-catalog.pdf', 'page:10');

INSERT INTO component_attributes VALUES
    ('A-001', 'C-001', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'extracted', 'test-catalog.pdf', 'page:1|row:1'),
    ('A-002', 'C-001', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'extracted', 'test-catalog.pdf', 'page:1|row:2'),
    ('A-003', 'C-002', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'verified', 'verified-catalog.pdf', 'page:2|row:1'),
    ('A-004', 'C-002', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'verified', 'verified-catalog.pdf', 'page:2|row:2'),
    ('A-005', 'C-003', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'needs_review', 'test-catalog.pdf', 'page:3|row:1'),
    ('A-006', 'C-003', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'needs_review', 'test-catalog.pdf', 'page:3|row:2'),
    ('A-007', 'C-004', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'raw', 'test-catalog.pdf', 'page:4|row:1'),
    ('A-008', 'C-004', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'raw', 'test-catalog.pdf', 'page:4|row:2'),
    ('A-009', 'C-005', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'deprecated', 'test-catalog.pdf', 'page:5|row:1'),
    ('A-010', 'C-005', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'deprecated', 'test-catalog.pdf', 'page:5|row:2'),
    ('A-011', 'C-006', 'rated_current', '11-16 A', NULL, NULL, 'A', 11, 16, 'extracted', 'test-catalog.pdf', 'page:6|row:1'),
    ('A-012', 'C-006', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'extracted', 'test-catalog.pdf', 'page:6|row:2'),
    ('A-013', 'C-007', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'extracted', 'test-catalog.pdf', 'page:7|row:1'),
    ('A-014', 'C-007', 'rated_voltage', '230 V', NULL, 230, 'V', 230, 230, 'extracted', 'test-catalog.pdf', 'page:7|row:2'),
    ('A-015', 'C-008', 'rated_current', '7-10 kA', NULL, NULL, 'kA', 7, 10, 'extracted', 'test-catalog.pdf', 'page:8|row:1'),
    ('A-016', 'C-008', 'rated_voltage', '690 V', NULL, 690, 'V', 690, 690, 'extracted', 'test-catalog.pdf', 'page:8|row:2'),
    ('A-017', 'C-009', 'rated_current', '7-10 A', NULL, NULL, 'A', 7, 10, 'extracted', 'test-catalog.pdf', 'page:9|row:1'),
    ('A-018', 'C-009', 'rated_voltage', '6 kV', NULL, 6, 'kV', 6, 6, 'extracted', 'test-catalog.pdf', 'page:9|row:2'),
    ('A-019', 'C-010', 'rated_current', NULL, NULL, NULL, 'A', NULL, NULL, 'extracted', NULL, NULL),
    ('A-020', 'C-010', 'rated_voltage', NULL, NULL, NULL, 'V', NULL, NULL, 'extracted', NULL, NULL);
