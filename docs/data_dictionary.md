# 📚 فرهنگ داده (Data Dictionary) - LV Panel Database

## جدول: `sources`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| source_id | TEXT | بله | - | - |
| path | TEXT | خیر | - | - |
| availability | TEXT | بله | - | - |
| source_type | TEXT | بله | - | - |
| publisher_or_manufacturer | TEXT | بله | - | - |
| version_or_date | TEXT | بله | - | - |
| specific_locator | TEXT | بله | - | - |
| access_limitations | TEXT | بله | - | - |

## جدول: `components`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| component_id | TEXT | بله | - | - |
| manufacturer_original | TEXT | بله | - | - |
| manufacturer_normalized | TEXT | بله | - | - |
| family | TEXT | بله | - | - |
| part_number | TEXT | بله | - | - |
| component_type | TEXT | بله | - | - |
| product_version | TEXT | بله | - | - |
| record_status | TEXT | بله | - | - |
| source_file_ref | TEXT | بله | - | - |
| source_locator | TEXT | بله | - | - |
| notes | TEXT | بله | - | - |

## جدول: `component_attributes`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| attribute_id | TEXT | بله | - | - |
| component_id | TEXT | خیر | - | - |
| parameter_key | TEXT | خیر | - | - |
| source_parameter_name | TEXT | بله | - | - |
| raw_value | TEXT | بله | - | - |
| normalized_value | TEXT | بله | - | - |
| numeric_value | REAL | بله | - | - |
| unit | TEXT | بله | - | - |
| min_value | REAL | بله | - | - |
| max_value | REAL | بله | - | - |
| data_type | TEXT | بله | - | - |
| application_conditions | TEXT | بله | - | - |
| test_conditions | TEXT | بله | - | - |
| installation_conditions | TEXT | بله | - | - |
| record_status | TEXT | بله | - | - |
| source_file_ref | TEXT | بله | - | - |
| source_locator | TEXT | بله | - | - |
| validation_notes | TEXT | بله | - | - |

## جدول: `engineering_rules`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| rule_id | TEXT | بله | - | - |
| rule_type | TEXT | بله | - | - |
| domain | TEXT | بله | - | - |
| title | TEXT | بله | - | - |
| statement | TEXT | بله | - | - |
| value | TEXT | بله | - | - |
| unit | TEXT | بله | - | - |
| applicability | TEXT | بله | - | - |
| conditions | TEXT | بله | - | - |
| ref_source_id | TEXT | بله | - | - |
| ref_location | TEXT | بله | - | - |
| review_status | TEXT | بله | - | - |
| limitations | TEXT | بله | - | - |

## جدول: `compatibility_relations`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| relation_id | TEXT | بله | - | - |
| component_a_id | TEXT | بله | - | - |
| component_b_id | TEXT | بله | - | - |
| relation_type | TEXT | بله | - | - |
| constraint_text | TEXT | بله | - | - |
| conditions | TEXT | بله | - | - |
| source_id | TEXT | بله | - | - |
| source_location | TEXT | بله | - | - |
| review_status | TEXT | بله | - | - |
| notes | TEXT | بله | - | - |

## جدول: `review_queue`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| review_id | TEXT | بله | - | - |
| severity | TEXT | بله | - | - |
| subject_type | TEXT | بله | - | - |
| subject_id | TEXT | بله | - | - |
| issue_type | TEXT | بله | - | - |
| description | TEXT | بله | - | - |
| evidence | TEXT | بله | - | - |
| required_action | TEXT | بله | - | - |
| status | TEXT | بله | - | - |

## جدول: `change_history`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| change_id | INTEGER | بله | - | - |
| entity_type | TEXT | بله | - | - |
| entity_id | TEXT | بله | - | - |
| changed_at | TEXT | بله | - | - |
| old_status | TEXT | بله | - | - |
| new_status | TEXT | بله | - | - |
| change_note | TEXT | بله | - | - |
| actor | TEXT | بله | - | - |

## جدول: `staging_pdf_tables`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| id | INTEGER | بله | - | - |
| source_file | TEXT | بله | - | - |
| page_number | INTEGER | بله | - | - |
| table_index | INTEGER | بله | - | - |
| raw_table_json | TEXT | بله | - | - |
| headers | TEXT | بله | - | - |
| status | TEXT | بله | 'extracted' | - |

## جدول: `normalized_attributes_pilot`
| نام ستون | نوع داده | اجازه NULL | مقدار پیش‌فرض | توضیحات |
|---|---|---|---|---|
| id | INTEGER | بله | - | - |
| component_part_number | TEXT | بله | - | - |
| parameter_key | TEXT | بله | - | - |
| source_parameter_name | TEXT | بله | - | - |
| raw_value | TEXT | بله | - | - |
| numeric_value | REAL | بله | - | - |
| unit | TEXT | بله | - | - |
| source_file | TEXT | بله | - | - |
| page_number | INTEGER | بله | - | - |
| status | TEXT | بله | 'extracted' | - |
| min_value | REAL | بله | - | - |
| max_value | REAL | بله | - | - |

