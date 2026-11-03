"""Scenario-specific preliminary checks, separate from general AC panel sizing."""
import math
from dataclasses import dataclass

from lv_assist.i18n import i18n
from lv_assist.models import SpecialScenario, ValidationResult, ValidationStatus


def localized(texts):
    return texts[{'fa': 0, 'en': 1, 'de': 2}[i18n.get_language()]]


FIELD_LABELS = {
    'review_reference': ('مرجع بازبینی مهندسی', 'Engineering review reference', 'Referenz der Fachprüfung'),
    'load_kw': ('توان بار سناریو (kW)', 'Scenario load power (kW)', 'Szenario-Lastleistung (kW)'),
    'load_pf': ('ضریب توان بار', 'Load power factor', 'Lastleistungsfaktor'),
    'equipment_rating_a': ('جریان نامی تجهیز (A)', 'Equipment rated current (A)', 'Gerätebemessungsstrom (A)'),
    'ac_phases': ('تعداد فاز ورودی AC (1 یا 3)', 'AC input phases (1 or 3)', 'AC-Eingangsphasen (1 oder 3)'),
    'ac_voltage_v': ('ولتاژ ورودی شارژر؛ تک‌فاز L-N، سه‌فاز L-L (V)', 'Charger input voltage: 1-phase L-N / 3-phase L-L (V)', 'Lade-Eingangsspannung: 1-phasig L-N / 3-phasig L-L (V)'),
    'equipment_fault_ka': ('تحمل اتصال کوتاه مجموعه (kA)', 'Assembly short-circuit rating (kA)', 'Kurzschlussfestigkeit (kA)'),
    'interlock_proven': ('آزمون اینترلاک انجام شده', 'Interlock test documented', 'Verriegelungsprüfung dokumentiert'),
    'synchronism_proven': ('آزمون سنکرون‌سازی انجام شده', 'Synchronism test documented', 'Synchronprüfung dokumentiert'),
    'utility_parallel_approved': ('موازی‌سازی با شبکه مجاز است', 'Utility paralleling approved', 'Netzparallelbetrieb genehmigt'),
    'ups_kva': ('ظرفیت UPS (kVA)', 'UPS capacity (kVA)', 'USV-Scheinleistung (kVA)'),
    'ups_kw': ('توان خروجی UPS (kW)', 'UPS output rating (kW)', 'USV-Wirkleistung (kW)'),
    'dc_voltage_v': ('ولتاژ DC (V)', 'DC voltage (V)', 'DC-Spannung (V)'),
    'autonomy_min': ('زمان پشتیبانی موردنیاز (min)', 'Required autonomy (min)', 'Geforderte Überbrückungszeit (min)'),
    'efficiency': ('بازده تبدیل (0–1)', 'Conversion efficiency (0–1)', 'Umwandlungswirkungsgrad (0–1)'),
    'usable_fraction': ('سهم قابل استفاده ظرفیت باتری (0–1)', 'Usable battery fraction (0–1)', 'Nutzbarer Batterieanteil (0–1)'),
    'battery_ah': ('ظرفیت نامی باتری (Ah)', 'Nominal battery capacity (Ah)', 'Batterie-Nennkapazität (Ah)'),
    'transformer_kva': ('ظرفیت ترانس ایزوله (kVA)', 'Isolation transformer rating (kVA)', 'Trenntransformator (kVA)'),
    'isolated_secondary_it': ('ثانویه ایزوله IT تأیید شده', 'Isolated IT secondary confirmed', 'Isolierte IT-Sekundärseite bestätigt'),
    'imd_alarm_kohm': ('آستانه پاسخ هشدار IMD (kΩ)', 'IMD alarm response threshold (kΩ)', 'IMD-Ansprechwert (kΩ)'),
    'insulation_kohm': ('مقاومت عایقی اندازه‌گیری‌شده (kΩ)', 'Measured insulation resistance (kΩ)', 'Gemessener Isolationswiderstand (kΩ)'),
    'remote_alarm_proven': ('آزمون هشدار صوتی و بصری از راه دور', 'Remote audible/visual alarm tested', 'Fernalarm akustisch/optisch geprüft'),
    'area_classification': ('زون و گروه گاز/گردوغبار', 'Zone and gas/dust group', 'Zone und Gas-/Staubgruppe'),
    'equipment_marking': ('مارکینگ Ex و EPL/Category', 'Ex marking and EPL/category', 'Ex-Kennzeichnung und EPL/Kategorie'),
    'certificate_reference': ('مرجع گواهی و شرایط استفاده', 'Certificate and conditions reference', 'Zertifikat und Einsatzbedingungen'),
    'redundancy_reference': ('طرح افزونگی و مسیرهای مستقل', 'Redundancy and independent-path design', 'Redundanz und unabhängige Pfade'),
    'fire_strategy_reference': ('طرح حفاظت حرارتی و حریق', 'Thermal/fire protection strategy', 'Wärme-/Brandschutzkonzept'),
    'marine_class_reference': ('مرجع مؤسسه رده‌بندی دریایی', 'Marine classification reference', 'Schiffsklassen-Referenz'),
    'safety_functions_reference': ('طرح توقف اضطراری، ترمز و حدود حرکت', 'Emergency stop, braking and travel limits', 'Not-Halt, Bremsen und Endschalter'),
    'pv_voc_module_v': ('Voc ماژول در STC (V)', 'Module Voc at STC (V)', 'Modul-Voc bei STC (V)'),
    'pv_voc_temp_pct_c': ('ضریب دمایی Voc (%/°C، منفی)', 'Voc temperature coefficient (%/°C, negative)', 'Voc-Temperaturkoeffizient (%/°C, negativ)'),
    'pv_min_temp_c': ('کمینه دمای طراحی ماژول (°C)', 'Minimum module design temperature (°C)', 'Minimale Modul-Auslegungstemperatur (°C)'),
    'pv_series_modules': ('تعداد ماژول سری', 'Series modules', 'Module in Reihe'),
    'pv_parallel_strings': ('تعداد رشته موازی', 'Parallel strings', 'Parallele Stränge'),
    'pv_isc_module_a': ('Isc ماژول (A)', 'Module Isc (A)', 'Modul-Isc (A)'),
    'pv_current_factor': ('ضریب طراحی جریان با مرجع سازنده', 'Current design factor with manufacturer basis', 'Strom-Auslegungsfaktor mit Herstellerbeleg'),
    'dc_equipment_voltage_v': ('حد ولتاژ DC تجهیزات (V)', 'Equipment DC voltage limit (V)', 'DC-Spannungsgrenze der Geräte (V)'),
    'ev_supply_type': ('نوع شارژ: AC / DC / DC_LOW_VOLTAGE', 'Charging: AC / DC / DC_LOW_VOLTAGE', 'Ladung: AC / DC / DC_LOW_VOLTAGE'),
}


@dataclass(frozen=True)
class ScenarioProfile:
    standards: str
    fields: tuple
    notes: tuple


BATTERY_FIELDS = ('load_kw', 'load_pf', 'dc_voltage_v', 'autonomy_min', 'efficiency', 'usable_fraction', 'battery_ah')
ATS_FIELDS = ('equipment_rating_a', 'equipment_fault_ka', 'interlock_proven')
EX_FIELDS = ('area_classification', 'equipment_marking', 'certificate_reference')
PROFILES = {
    'FIRE_PUMP': ScenarioProfile('IEC 62091; NFPA 20; UL 62091; FM 1321/1323', (), (
        'کنترلر اختصاصی پمپ آتش لازم است؛ UL 218 با UL 62091 جایگزین شده است. جریان قفل‌روتور واقعی هر فیدر و آزمون افت ولتاژ/حفاظت لازم است. ضریب ثابت 6 برابر، تأیید NFPA نیست.',
        'A dedicated fire-pump controller is required. UL 62091 replaced UL 218. Use actual feeder locked-rotor data and verify starting voltage drop/protection; a fixed 6× factor is not NFPA approval.',
        'Ein spezieller Feuerlöschpumpen-Controller ist erforderlich. UL 62091 ersetzt UL 218. Reale Anlaufdaten sowie Spannungsfall und Schutz prüfen; Faktor 6 ist kein NFPA-Nachweis.')),
    'ATS_MAINS_GEN': ScenarioProfile('IEC 60947-6-1:2026', ATS_FIELDS, (
        'مجموعه TSE کامل و آزموده‌شده، اینترلاک، نول و تنظیم حفاظت هر دو منبع بررسی شوند. کنترلر به‌تنهایی مجموعه ATS تأییدشده نیست.',
        'Verify a complete tested TSE assembly, interlocking, neutral arrangement and protection for both sources. A controller alone is not an approved ATS assembly.',
        'Vollständig geprüftes TSE, Verriegelung, Neutralleiter und Schutz beider Quellen prüfen. Ein Controller allein ist keine geprüfte ATS-Anlage.')),
    'ATS_CLOSED_TRANSITION': ScenarioProfile('IEC 60947-6-1:2026 Annex D', ATS_FIELDS + ('synchronism_proven', 'utility_parallel_approved'), (
        'انتقال بسته به سنکرون‌سازی، محدودیت زمان موازی و مجوز بهره‌بردار شبکه نیاز دارد؛ هم‌زمانی اتصال دو منبع بدون این موارد مجاز فرض نمی‌شود.',
        'Closed transition requires synchronism, controlled parallel duration and utility approval; source paralleling is never assumed permissible.',
        'Geschlossener Übergang erfordert Synchronisierung, begrenzte Paralleldauer und Netzbetreiberfreigabe; Parallelbetrieb wird nicht vorausgesetzt.')),
    'ATS_CONTROLLER': ScenarioProfile('IEC 60947-6-1:2026 Annex E', (), (
        'این سناریو کنترلر مستقل ATS است؛ تحمل جریان و اتصال کوتاه باید برای TSE کامل جداگانه تأیید شود.',
        'This covers a stand-alone ATS controller; verify current and fault duty separately for the complete TSE.',
        'Eigenständiger ATS-Controller; Strom- und Kurzschlussfestigkeit des vollständigen TSE separat nachweisen.')),
    'FIRE_PUMP_TRANSFER': ScenarioProfile('IEC 60947-6-1:2026 Annex F; IEC 62091; NFPA 20', ATS_FIELDS, (
        'TSE پمپ آتش علاوه بر الزامات انتقال منبع، به کنترلر و آزمون‌های اختصاصی پمپ آتش نیاز دارد.',
        'Fire-pump TSE needs both transfer-switch verification and dedicated fire-pump controller/testing requirements.',
        'Feuerlöschpumpen-TSE benötigt Umschaltprüfung sowie spezifische Pumpensteuerung und Prüfungen.')),
    'UPS_CRITICAL': ScenarioProfile('IEC 62040-1; IEC 62040-2; IEC 62040-3', ('ups_kva', 'ups_kw') + BATTERY_FIELDS, (
        'بخش 1 ایمنی، بخش 2 EMC و بخش 3 عملکرد است. برآورد انرژی خطی باتری جایگزین منحنی تخلیه، پیرشدگی، دما و آزمون زمان پشتیبانی نیست.',
        'Part 1 covers safety, part 2 EMC and part 3 performance. Linear battery energy is only an estimate; verify discharge curves, ageing, temperature and autonomy tests.',
        'Teil 1 Sicherheit, Teil 2 EMV, Teil 3 Leistung. Lineare Batterieenergie ist nur eine Schätzung; Entladekurven, Alterung, Temperatur und Überbrückung prüfen.')),
    'MEDICAL_IT': ScenarioProfile('IEC 60364-7-710; IEC 61557-8; IEC 61558-2-15', (
        'load_kw', 'load_pf', 'transformer_kva', 'isolated_secondary_it', 'imd_alarm_kohm', 'insulation_kohm', 'remote_alarm_proven'), (
        'کاربری محل پزشکی و ثانویه IT باید مشخص باشد. 50 kΩ مرجع پاسخ هشدار IMD است، نه حد قبولی عمومی آزمون عایقی. هشدار صوتی/بصری و پایش بار و دمای ترانس جداگانه آزموده شوند.',
        'Establish the medical-location classification and IT secondary. 50 kΩ concerns IMD alarm response, not a universal insulation acceptance test. Verify remote alarms and transformer load/temperature monitoring.',
        'Medizinische Raumklassifikation und IT-Sekundärseite festlegen. 50 kΩ betrifft die IMD-Meldung, nicht einen allgemeinen Isolations-Prüfgrenzwert. Fernalarm sowie Last-/Temperaturüberwachung prüfen.')),
    'EXPLOSIVE_GAS_D': ScenarioProfile('IEC 60079-0; IEC 60079-1; IEC 60079-14; ATEX 2014/34/EU', EX_FIELDS, (
        'Ex d برای گاز است. زون، گروه، کلاس دما، EPL و گواهی مجموعه و گلندها باید تطبیق داده شوند؛ IP به‌تنهایی اثبات ضدانفجار بودن نیست.',
        'Ex d is for gas. Match zone, group, temperature class, EPL and assembly/gland certificates; IP alone does not establish explosion protection.',
        'Ex d gilt für Gas. Zone, Gruppe, Temperaturklasse, EPL und Zertifikate für Anlage/Verschraubungen abgleichen; IP allein genügt nicht.')),
    'EXPLOSIVE_GAS_E': ScenarioProfile('IEC 60079-0; IEC 60079-7; IEC 60079-14; ATEX 2014/34/EU', EX_FIELDS, (
        'Ex e ایمنی افزوده است؛ نصب تجهیزات جرقه‌زن در محفظه عمومی Ex e بدون ارزیابی مجاز فرض نمی‌شود.',
        'Ex e is increased safety; arcing equipment inside a generic Ex e enclosure is not automatically acceptable.',
        'Ex e ist erhöhte Sicherheit; funkenbildende Geräte in einem allgemeinen Ex-e-Gehäuse sind nicht automatisch zulässig.')),
    'EXPLOSIVE_DUST': ScenarioProfile('IEC 60079-0; IEC 60079-31; IEC 60079-14; ATEX 2014/34/EU', EX_FIELDS, (
        'حفاظت گردوغبار با محفظه t به زون، گروه گردوغبار، دمای سطح و لایه گردوغبار وابسته است؛ معادل Ex d گازی نیست.',
        'Dust protection by enclosure t depends on zone, dust group, surface temperature and dust layers; gas Ex d is not equivalent.',
        'Staubschutz durch Gehäuse t hängt von Zone, Staubgruppe, Oberflächentemperatur und Staubschichten ab; Gas-Ex-d ist nicht gleichwertig.')),
    'EMERGENCY_LIGHTING': ScenarioProfile('IEC 60364-5-56; EN 50171; IEC 60598-2-22', BATTERY_FIELDS + ('fire_strategy_reference',), (
        'IEC 60598-2-22 استاندارد چراغ اضطراری است؛ تابلو و منبع مرکزی به الزامات خدمات ایمنی، باتری، جداسازی مدار و زمان پشتیبانی پروژه نیز نیاز دارند.',
        'IEC 60598-2-22 covers emergency luminaires. The board/central supply also needs safety-service, battery, circuit-separation and project-autonomy verification.',
        'IEC 60598-2-22 gilt für Notleuchten. Verteilung/Zentralversorgung erfordern zusätzlich Sicherheitsversorgung, Batterie, Stromkreistrennung und geforderte Überbrückung.')),
    'DATA_CENTER': ScenarioProfile('IEC 60364-4-42; EN 50600-2-2; ISO/IEC 22237-3', ('redundancy_reference', 'fire_strategy_reference'), (
        'IEC 60364-4-42 حفاظت عمومی حرارتی است. مسیرهای A/B، افزونگی، سلکتیویته و معماری توزیع مطابق نیاز دسترس‌پذیری پروژه جداگانه بررسی شوند.',
        'IEC 60364-4-42 is general thermal protection. Review A/B paths, redundancy, selectivity and distribution architecture against the project availability requirement.',
        'IEC 60364-4-42 behandelt allgemeinen Wärmeschutz. A/B-Pfade, Redundanz, Selektivität und Verteilungsarchitektur nach Projekt-Verfügbarkeitsziel prüfen.')),
    'MARINE': ScenarioProfile('IEC 60092-302-2; IEC 60092-201; IEC 60092-202', ('marine_class_reference',), (
        'الزامات دریایی و مؤسسه رده‌بندی شامل شرایط محیط، لرزش، خوردگی و تداوم سرویس است؛ محاسبه تابلو زمینی به‌تنهایی کافی نیست.',
        'Marine/class requirements include environment, vibration, corrosion and service continuity; land-based board sizing alone is insufficient.',
        'Schiffs-/Klassenanforderungen umfassen Umwelt, Vibration, Korrosion und Betriebsverfügbarkeit; reine Landanlagen-Dimensionierung reicht nicht.')),
    'MINING': ScenarioProfile('IEC 60079; EN 50303 (Group I Category M1 where applicable)', EX_FIELDS, (
        'EN 50303 مخصوص گروه I رده M1 در معرض گریز و گرد زغال است، نه همه معادن. رده M1/M2 و نیاز ادامه کار باید توسط طرح خطر مشخص شود.',
        'EN 50303 is specific to Group I category M1 exposed to firedamp/coal dust, not all mines. Establish M1/M2 and continued-operation requirements from the hazard assessment.',
        'EN 50303 betrifft Gruppe I Kategorie M1 bei Schlagwetter/Kohlenstaub, nicht alle Bergwerke. M1/M2 und Weiterbetriebsanforderungen aus der Gefährdungsbeurteilung bestimmen.')),
    'PV_DC': ScenarioProfile('IEC 62548-1; IEC 60364-7-712; IEC 60947-3', (
        'pv_voc_module_v', 'pv_voc_temp_pct_c', 'pv_min_temp_c', 'pv_series_modules', 'pv_parallel_strings',
        'pv_isc_module_a', 'pv_current_factor', 'dc_equipment_voltage_v', 'equipment_rating_a'), (
        'محاسبه Voc سرد و جریان آرایه DC مستقل است. ضرایب دمایی، جریان دوطرفه/بایفیشیال، رده قطع DC، فیوز رشته و SPD باید با دیتاشیت کنترل شوند. نتایج عمومی شینه و فیدر برنامه مربوط به AC هستند.',
        'Cold Voc and DC array current are separate calculations. Verify temperature/bifacial factors, DC breaking duty, string fuses and SPD from datasheets. General busbar/feeder results in this app are AC-side only.',
        'Kalt-Voc und DC-Arraystrom separat berechnen. Temperatur-/Bifazialfaktoren, DC-Schaltvermögen, Strangsicherungen und SPD anhand Datenblättern prüfen. Allgemeine Schienen-/Abgangswerte gelten nur AC-seitig.')),
    'EV_CHARGING': ScenarioProfile('IEC 61851-1; IEC 61851-23 (DC); IEC 60364-7-722', (
        'ev_supply_type', 'ac_phases', 'ac_voltage_v', 'load_kw', 'load_pf', 'efficiency', 'dc_voltage_v', 'equipment_rating_a'), (
        'IEC TS 61851-3-1 مخصوص سامانه DC کم‌ولتاژ است، نه مرجع عمومی شارژ DC. برای شارژ DC بخش 23 و برای تأسیسات بخش 7-722 بررسی شود. حفاظت جریان باقیمانده و مدیریت بار به مشخصات EVSE وابسته‌اند.',
        'IEC TS 61851-3-1 is for low-voltage DC systems, not general DC charging. Use part 23 for DC equipment and 7-722 for installation; residual-current protection and load management depend on the EVSE.',
        'IEC TS 61851-3-1 gilt für DC-Kleinspannung, nicht allgemein für DC-Ladung. Teil 23 für DC-Geräte und 7-722 für die Installation beachten; Fehlerstromschutz und Lastmanagement hängen vom EVSE ab.')),
    'HOISTING': ScenarioProfile('IEC 60204-32; IEC 60204-1', ('safety_functions_reference',), (
        'توقف اضطراری، ترمز نگهدارنده، کلیدهای حدی، چرخه کاری، استارت‌های متوالی و بار ترمزی باید بررسی شوند؛ جریان نامی به‌تنهایی مبنای انتخاب کامل نیست.',
        'Review emergency stop, holding brakes, travel limits, duty cycle, repeated starts and braking load; rated current alone cannot establish the complete design.',
        'Not-Halt, Haltebremsen, Endschalter, Lastspiel, wiederholte Starts und Bremslast prüfen; Nennstrom allein reicht für die Auslegung nicht.')),
}
PROFILES['ATS_MAINS_MAINS'] = PROFILES['ATS_MAINS_GEN']
PROFILES['FIRE_PUMP_BYPASS'] = PROFILES['FIRE_PUMP']


def evaluate_scenario(project, feeders, summary_current_a, ik_ka):
    profile = PROFILES.get(project.special_scenario.value)
    if profile is None:
        return []
    data = project.scenario_inputs
    results = []

    def result(code, label, fields, predicate=None, evidence='', unavailable=False, pass_status=ValidationStatus.COMPLETED):
        missing = [field for field in fields if getattr(data, field) in (None, '')]
        status = (ValidationStatus.INSUFFICIENT_DATA if missing or unavailable else
                  ValidationStatus.WARNING if predicate is None else
                  pass_status if predicate() else ValidationStatus.ERROR)
        details = ', '.join(localized(FIELD_LABELS[field]) for field in missing)
        results.append(ValidationResult(rule_id=f'SCEN-{code}', feeder_id='PANEL', standard_ref=profile.standards,
            status=status, description=localized(label), supporting_evidence=details or evidence,
            consequence=localized(('این کنترل جایگزین تأیید مجموعه نیست.', 'This check is not assembly certification.', 'Diese Prüfung ersetzt keine Bauartbestätigung.')),
            recommended_action=localized(profile.notes)))

    scenario = project.special_scenario.value
    result('REVIEW', ('بازبینی تخصصی سناریو', 'Specialist scenario review', 'Szenario-Fachprüfung'),
           ('review_reference',), evidence=data.review_reference or '')
    if scenario.startswith('ATS_') and scenario != 'ATS_CONTROLLER' or scenario == 'FIRE_PUMP_TRANSFER':
        result('ATS-CURRENT', ('ظرفیت جریان TSE', 'TSE current rating', 'TSE-Strombemessung'),
               ('equipment_rating_a',), lambda: data.equipment_rating_a >= summary_current_a,
               f'In={data.equipment_rating_a} A; AC design={summary_current_a:.3f} A')
        result('ATS-FAULT', ('کنترل اولیه دامنه جریان خطا', 'Preliminary fault-current magnitude screen', 'Vorläufiger Kurzschlussstromvergleich'),
               ('equipment_fault_ka',), None if ik_ka is None else lambda: data.equipment_fault_ka >= ik_ka,
               f'Assembly={data.equipment_fault_ka} kA; prospective={ik_ka} kA; coordination/time basis requires review',
               unavailable=ik_ka is None, pass_status=ValidationStatus.WARNING)
        result('ATS-INTERLOCK', ('آزمون اینترلاک', 'Interlock test', 'Verriegelungsprüfung'),
               ('interlock_proven',), lambda: data.interlock_proven is True)
        if scenario == 'ATS_CLOSED_TRANSITION':
            for field in ('synchronism_proven', 'utility_parallel_approved'):
                result(field.upper(), FIELD_LABELS[field], (field,), lambda field=field: getattr(data, field) is True)
    if scenario in ('UPS_CRITICAL', 'MEDICAL_IT'):
        fields = ('load_kw', 'load_pf', 'transformer_kva' if scenario == 'MEDICAL_IT' else 'ups_kva')
        rating = fields[-1]
        result('APPARENT-POWER', ('ظرفیت توان ظاهری', 'Apparent-power capacity', 'Scheinleistungskapazität'), fields,
               lambda: getattr(data, rating) >= data.load_kw / data.load_pf,
               f'S=P/PF; P={data.load_kw} kW; PF={data.load_pf}; rating={getattr(data, rating)} kVA')
        if scenario == 'UPS_CRITICAL':
            result('UPS-KW', FIELD_LABELS['ups_kw'], ('load_kw', 'ups_kw'),
                   lambda: data.ups_kw >= data.load_kw, f'UPS={data.ups_kw} kW; load={data.load_kw} kW')
    if scenario in ('UPS_CRITICAL', 'EMERGENCY_LIGHTING'):
        fields = ('load_kw', 'dc_voltage_v', 'autonomy_min', 'efficiency', 'usable_fraction', 'battery_ah')
        ready = all(getattr(data, field) is not None for field in fields)
        required = (data.load_kw * 1000 * data.autonomy_min / 60 /
                    (data.dc_voltage_v * data.efficiency * data.usable_fraction)) if ready else None
        result('BATTERY-ENERGY', ('برآورد اولیه انرژی باتری', 'Preliminary battery energy', 'Vorläufige Batterieenergie'), fields,
               None if not ready else lambda: data.battery_ah >= required,
               f'Ah_req=P(W)×t(h)/(Vdc×η×usable); Ah_req={required}; installed={data.battery_ah} Ah; linear estimate only')
    if scenario == 'MEDICAL_IT':
        for field in ('isolated_secondary_it', 'remote_alarm_proven'):
            result(field.upper(), FIELD_LABELS[field], (field,), lambda field=field: getattr(data, field) is True)
        result('IMD-SETTING', FIELD_LABELS['imd_alarm_kohm'], ('imd_alarm_kohm',),
               lambda: data.imd_alarm_kohm >= 50, f'IMD={data.imd_alarm_kohm} kΩ; response must occur by 50 kΩ; verify device and adopted edition')
        result('IMD-MEASURED', FIELD_LABELS['insulation_kohm'], ('insulation_kohm', 'imd_alarm_kohm'),
               lambda: data.insulation_kohm > data.imd_alarm_kohm,
               f'Rins={data.insulation_kohm} kΩ; IMD response={data.imd_alarm_kohm} kΩ; this is an alarm-state comparison')
    if scenario in ('EXPLOSIVE_GAS_D', 'EXPLOSIVE_GAS_E', 'EXPLOSIVE_DUST', 'MINING'):
        for field in EX_FIELDS:
            result(field.upper(), FIELD_LABELS[field], (field,), evidence=getattr(data, field) or '')
    for field in ('redundancy_reference', 'fire_strategy_reference', 'marine_class_reference', 'safety_functions_reference'):
        if field in profile.fields:
            result(field.upper(), FIELD_LABELS[field], (field,), evidence=getattr(data, field) or '')
    if scenario == 'PV_DC':
        voltage_fields = ('pv_voc_module_v', 'pv_voc_temp_pct_c', 'pv_min_temp_c', 'pv_series_modules', 'dc_equipment_voltage_v')
        ready = all(getattr(data, field) is not None for field in voltage_fields)
        voc = data.pv_series_modules * data.pv_voc_module_v * (1 + data.pv_voc_temp_pct_c / 100 * (data.pv_min_temp_c - 25)) if ready else None
        result('PV-VOC', ('ولتاژ مدار باز در سرما', 'Cold open-circuit voltage', 'Kalt-Leerlaufspannung'), voltage_fields,
               None if not ready else lambda: data.dc_equipment_voltage_v >= voc,
               f'Voc_cold=Ns×Voc_STC×[1+β/100×(Tmin−25)]={voc} V; DC limit={data.dc_equipment_voltage_v} V')
        current_fields = ('pv_isc_module_a', 'pv_parallel_strings', 'pv_current_factor', 'equipment_rating_a')
        ready = all(getattr(data, field) is not None for field in current_fields)
        current = data.pv_isc_module_a * data.pv_parallel_strings * data.pv_current_factor if ready else None
        result('PV-CURRENT', ('جریان طراحی آرایه DC', 'DC array design current', 'DC-Array-Auslegungsstrom'), current_fields,
               None if not ready else lambda: data.equipment_rating_a >= current,
               f'Ireq=Isc×Np×K={current} A; In={data.equipment_rating_a} A; verify coefficient and DC utilisation category')
    if scenario == 'EV_CHARGING':
        fields = ('ev_supply_type', 'ac_phases', 'ac_voltage_v', 'load_kw', 'load_pf', 'efficiency', 'equipment_rating_a')
        ready = all(getattr(data, field) is not None for field in fields)
        phase_factor = math.sqrt(3) if data.ac_phases == 3 else 1
        current = data.load_kw * 1000 / (phase_factor * data.ac_voltage_v * data.load_pf * data.efficiency) if ready else None
        result('EV-AC-INPUT', ('جریان ورودی AC شارژر', 'AC charger input current', 'AC-Lade-Eingangsstrom'), fields,
               None if not ready else lambda: data.equipment_rating_a >= current,
               f'Iac=Pout/(Kphase×Vac×PF×η)={current} A; phases={data.ac_phases}; Vac must be L-N for 1-phase or L-L for 3-phase')
        if data.ev_supply_type in ('DC', 'DC_LOW_VOLTAGE'):
            ready = data.load_kw is not None and data.dc_voltage_v is not None
            current = data.load_kw * 1000 / data.dc_voltage_v if ready else None
            result('EV-DC-OUTPUT', ('جریان خروجی DC شارژر', 'DC charger output current', 'DC-Lade-Ausgangsstrom'),
                   ('load_kw', 'dc_voltage_v'), evidence=f'Idc=Pout/Vdc={current} A; DC output equipment not selected by the AC engine')
            if data.ev_supply_type == 'DC_LOW_VOLTAGE':
                result('EV-LOW-VOLTAGE', ('دامنه ولتاژ بخش 3-1', 'Part 3-1 voltage scope', 'Spannungsbereich Teil 3-1'),
                       ('dc_voltage_v',), lambda: data.dc_voltage_v <= 120,
                       f'IEC TS 61851-3-1: output={data.dc_voltage_v} V DC; scope ≤120 V DC; other scope conditions require review')
    if scenario in ('FIRE_PUMP', 'FIRE_PUMP_BYPASS', 'FIRE_PUMP_TRANSFER'):
        pumps = [feeder for feeder in feeders if feeder.fire_pump_service]
        known = bool(pumps) and all(feeder.locked_rotor_current_a is not None for feeder in pumps)
        results.append(ValidationResult(rule_id='SCEN-FIRE-START', feeder_id='PANEL', standard_ref=profile.standards,
            status=ValidationStatus.WARNING if known else ValidationStatus.INSUFFICIENT_DATA,
            description=localized(('کنترل راه‌اندازی پمپ آتش', 'Fire-pump starting review', 'Feuerlöschpumpen-Anlaufprüfung')),
            supporting_evidence='; '.join(f'{feeder.feeder_id}: LRC={feeder.locked_rotor_current_a} A' for feeder in pumps) or 'No designated fire-pump feeder',
            consequence=localized(profile.notes), recommended_action=localized(profile.notes)))
    return results
