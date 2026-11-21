-- طرح پایگاه داده LV Panel (استخراج شده خودکار)
-- موتور پایگاه داده: SQLite

CREATE TABLE sources(source_id TEXT PRIMARY KEY,path TEXT NOT NULL,availability TEXT,source_type TEXT,publisher_or_manufacturer TEXT,version_or_date TEXT,specific_locator TEXT,access_limitations TEXT);

CREATE TABLE components(component_id TEXT PRIMARY KEY,manufacturer_original TEXT,manufacturer_normalized TEXT,family TEXT,part_number TEXT,component_type TEXT,product_version TEXT,record_status TEXT CHECK(record_status IN ('raw','extracted','needs_review','verified','deprecated')),source_file_ref TEXT,source_locator TEXT,notes TEXT);

CREATE TABLE component_attributes(attribute_id TEXT PRIMARY KEY,component_id TEXT NOT NULL REFERENCES components(component_id),parameter_key TEXT NOT NULL,source_parameter_name TEXT,raw_value TEXT,normalized_value TEXT,numeric_value REAL,unit TEXT,min_value REAL,max_value REAL,data_type TEXT,application_conditions TEXT,test_conditions TEXT,installation_conditions TEXT,record_status TEXT CHECK(record_status IN ('raw','extracted','needs_review','verified','deprecated')),source_file_ref TEXT,source_locator TEXT,validation_notes TEXT);

CREATE TABLE engineering_rules(rule_id TEXT PRIMARY KEY,rule_type TEXT,domain TEXT,title TEXT,statement TEXT,value TEXT,unit TEXT,applicability TEXT,conditions TEXT,ref_source_id TEXT REFERENCES sources(source_id),ref_location TEXT,review_status TEXT,limitations TEXT);

CREATE TABLE compatibility_relations(relation_id TEXT PRIMARY KEY,component_a_id TEXT REFERENCES components(component_id),component_b_id TEXT REFERENCES components(component_id),relation_type TEXT,constraint_text TEXT,conditions TEXT,source_id TEXT REFERENCES sources(source_id),source_location TEXT,review_status TEXT,notes TEXT);

CREATE TABLE review_queue(review_id TEXT PRIMARY KEY,severity TEXT,subject_type TEXT,subject_id TEXT,issue_type TEXT,description TEXT,evidence TEXT,required_action TEXT,status TEXT);

CREATE TABLE change_history(change_id INTEGER PRIMARY KEY AUTOINCREMENT,entity_type TEXT,entity_id TEXT,changed_at TEXT,old_status TEXT,new_status TEXT,change_note TEXT,actor TEXT);

CREATE TABLE staging_pdf_tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT,
        page_number INTEGER,
        table_index INTEGER,
        raw_table_json TEXT,
        headers TEXT,
        status TEXT DEFAULT 'extracted'
    );

CREATE TABLE normalized_attributes_pilot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        component_part_number TEXT,
        parameter_key TEXT,
        source_parameter_name TEXT,
        raw_value TEXT,
        numeric_value REAL,
        unit TEXT,
        source_file TEXT,
        page_number INTEGER,
        status TEXT DEFAULT 'extracted'
    , min_value REAL, max_value REAL);

