# -*- coding: utf-8 -*-
from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

class EarthingSystem(str, Enum):
    TN_S = "TN-S"
    TN_C_S = "TN-C-S"
    TT = "TT"
    IT = "IT"

class LoadType(str, Enum):
    MOTOR_DOL = "MOTOR_DOL"
    MOTOR_STAR_DELTA = "MOTOR_STAR_DELTA"
    MOTOR_SOFT_STARTER = "MOTOR_SOFT_STARTER"
    MOTOR_VFD = "MOTOR_VFD"
    SUB_FEEDER = "SUB_FEEDER"
    LIGHTING_SOCKET = "LIGHTING_SOCKET"
    HEATER_RESISTIVE = "HEATER_RESISTIVE"

class PanelType(str, Enum):
    MCC = "MCC"
    DISTRIBUTION = "DISTRIBUTION"
    CONTROL = "CONTROL"
    PUMP_STATION = "PUMP_STATION"

class EnclosureMounting(str, Enum):
    UNSPECIFIED = "UNSPECIFIED"
    FLOOR_STANDING = "FLOOR_STANDING"
    WALL_MOUNTED = "WALL_MOUNTED"
    CONSOLE = "CONSOLE"
    RACK = "RACK"

class SpecialScenario(str, Enum):
    NONE = "NONE"
    FIRE_PUMP = "FIRE_PUMP"
    ATS_MAINS_GEN = "ATS_MAINS_GEN"
    FIRE_PUMP_BYPASS = "FIRE_PUMP_BYPASS"
    ATS_MAINS_MAINS = "ATS_MAINS_MAINS"
    UPS_CRITICAL = "UPS_CRITICAL"
    EMERGENCY_LIGHTING = "EMERGENCY_LIGHTING"
    ATS_CLOSED_TRANSITION = "ATS_CLOSED_TRANSITION"
    ATS_CONTROLLER = "ATS_CONTROLLER"
    FIRE_PUMP_TRANSFER = "FIRE_PUMP_TRANSFER"
    MEDICAL_IT = "MEDICAL_IT"
    EXPLOSIVE_GAS_D = "EXPLOSIVE_GAS_D"
    EXPLOSIVE_GAS_E = "EXPLOSIVE_GAS_E"
    EXPLOSIVE_DUST = "EXPLOSIVE_DUST"
    DATA_CENTER = "DATA_CENTER"
    MARINE = "MARINE"
    MINING = "MINING"
    PV_DC = "PV_DC"
    EV_CHARGING = "EV_CHARGING"
    HOISTING = "HOISTING"

class ConductorMaterial(str, Enum):
    CU = "CU"
    AL = "AL"

class InsulationType(str, Enum):
    PVC = "PVC"
    XLPE = "XLPE"

class InstallationMethod(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C = "C"
    E = "E"
    F = "F"
    D = "D"

class ValidationStatus(str, Enum):
    COMPLETED = "COMPLETED"
    WARNING = "WARNING"
    ERROR = "ERROR"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

class SelectivityEvalState(str, Enum):
    VERIFIED_TOTAL = "VERIFIED_TOTAL"
    VERIFIED_PARTIAL = "VERIFIED_PARTIAL"
    PRELIMINARY = "PRELIMINARY"
    PRELIMINARY_RATIO_ONLY = "PRELIMINARY_RATIO"
    VIOLATION = "VIOLATION"

class DataQuality(str, Enum):
    REAL_VERIFIED = "REAL_VERIFIED"
    ESTIMATED = "ESTIMATED"

class SpdClass(str, Enum):
    NONE = "NONE"
    T1 = "T1"
    T2 = "T2"
    T1_T2 = "T1_T2"

class ScenarioInputs(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    review_reference: Optional[str] = None
    load_kw: Optional[float] = Field(default=None, gt=0)
    load_pf: Optional[float] = Field(default=None, gt=0, le=1)
    equipment_rating_a: Optional[float] = Field(default=None, gt=0)
    ac_phases: Optional[Literal[1, 3]] = None
    ac_voltage_v: Optional[float] = Field(default=None, gt=0)
    equipment_fault_ka: Optional[float] = Field(default=None, gt=0)
    interlock_proven: Optional[bool] = None
    synchronism_proven: Optional[bool] = None
    utility_parallel_approved: Optional[bool] = None
    ups_kva: Optional[float] = Field(default=None, gt=0)
    ups_kw: Optional[float] = Field(default=None, gt=0)
    dc_voltage_v: Optional[float] = Field(default=None, gt=0)
    autonomy_min: Optional[float] = Field(default=None, gt=0)
    efficiency: Optional[float] = Field(default=None, gt=0, le=1)
    usable_fraction: Optional[float] = Field(default=None, gt=0, le=1)
    battery_ah: Optional[float] = Field(default=None, gt=0)
    transformer_kva: Optional[float] = Field(default=None, gt=0)
    isolated_secondary_it: Optional[bool] = None
    imd_alarm_kohm: Optional[float] = Field(default=None, gt=0)
    insulation_kohm: Optional[float] = Field(default=None, gt=0)
    remote_alarm_proven: Optional[bool] = None
    area_classification: Optional[str] = None
    equipment_marking: Optional[str] = None
    certificate_reference: Optional[str] = None
    redundancy_reference: Optional[str] = None
    fire_strategy_reference: Optional[str] = None
    marine_class_reference: Optional[str] = None
    safety_functions_reference: Optional[str] = None
    pv_voc_module_v: Optional[float] = Field(default=None, gt=0)
    pv_voc_temp_pct_c: Optional[float] = Field(default=None, lt=0)
    pv_min_temp_c: Optional[float] = Field(default=None, ge=-100, le=25)
    pv_series_modules: Optional[int] = Field(default=None, ge=1)
    pv_parallel_strings: Optional[int] = Field(default=None, ge=1)
    pv_isc_module_a: Optional[float] = Field(default=None, gt=0)
    pv_current_factor: Optional[float] = Field(default=None, ge=1)
    dc_equipment_voltage_v: Optional[float] = Field(default=None, gt=0)
    ev_supply_type: Optional[Literal['AC', 'DC', 'DC_LOW_VOLTAGE']] = None

class EngineeringInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, validate_assignment=True)

    @property
    def assumed_fields(self) -> dict:
        return {name: getattr(self, name) for name in type(self).model_fields
                if name not in self.model_fields_set and getattr(self, name) is not None}


class ProjectSpec(EngineeringInput):

    project_name: str = Field(..., min_length=2)
    panel_tag: str = Field(default="+MCC1")
    standard_ref: str = Field(default="IEC 61439-2 / IEC 60204-1")
    nominal_voltage_v: float = Field(default=400.0, gt=0)
    frequency_hz: float = Field(default=50.0, gt=0)
    earthing_system: EarthingSystem = Field(default=EarthingSystem.TN_S)
    panel_type: PanelType = Field(default=PanelType.MCC)
    special_scenario: SpecialScenario = Field(default=SpecialScenario.NONE)
    enclosure_mounting: EnclosureMounting = EnclosureMounting.UNSPECIFIED
    enclosure_width_mm: Optional[float] = Field(default=None, gt=0)
    enclosure_height_mm: Optional[float] = Field(default=None, gt=0)
    enclosure_depth_mm: Optional[float] = Field(default=None, gt=0)
    scenario_inputs: ScenarioInputs = Field(default_factory=ScenarioInputs)
    prospective_ik_ka: Optional[float] = Field(default=None, gt=0)
    transformer_kva: Optional[float] = Field(default=None, gt=0)
    transformer_uk_pct: float = Field(default=6.0, gt=0.0, le=20.0)
    ambient_temp_c: float = Field(default=40.0, ge=-20.0, le=60.0)
    max_internal_temp_c: float = Field(default=50.0, ge=35.0, le=70.0)
    altitude_m: float = Field(default=1000.0, ge=0.0, le=4000.0)
    target_ip: str = Field(default="IP54")
    internal_separation_form: str = Field(default="Form 2b")
    simultaneity_factor_ks: float = Field(default=0.85, gt=0.1, le=1.0)
    spare_factor: float = Field(default=0.20, ge=0.0, le=1.0)
    cable_grouping_factor_k2: float = Field(default=0.80, gt=0.3, le=1.0)
    plc_hmi_24vdc_power_w: float = Field(default=55.0, ge=0.0)
    simultaneous_motor_starts: int = Field(default=2, ge=1, le=10)
    preferred_manufacturer: str = Field(default="ANY", min_length=1)
    designer_name: Optional[str] = Field(default=None, min_length=1)
    spd_class: SpdClass = Field(default=SpdClass.T2)
    spd_connection_length_m: float = Field(default=0.5, ge=0.0, le=10.0)

class FeederInput(EngineeringInput):

    feeder_id: str = Field(..., min_length=1)
    func_tag: str = Field(default="=PWR")
    loc_tag: str = Field(default="+MCC1")
    description: str
    load_type: LoadType
    power_kw: float = Field(..., gt=0)
    phases: Literal[1, 3] = 3
    cos_phi: Optional[float] = Field(default=None, ge=0.1, le=1.0)
    efficiency: Optional[float] = Field(default=None, gt=0.1, le=1.0)
    demand_factor_kd: float = Field(default=1.0, gt=0.0, le=1.0)
    cable_length_m: Optional[float] = Field(default=None, gt=0)
    cable_section_mm2: Optional[float] = Field(default=None, gt=0)
    has_socket_outlets: bool = Field(default=False)
    fire_pump_service: bool = Field(default=False)
    locked_rotor_current_a: Optional[float] = Field(default=None, gt=0)
    conductor_material: ConductorMaterial = ConductorMaterial.CU
    insulation: InsulationType = InsulationType.PVC
    installation_method: InstallationMethod = InstallationMethod.C
    fire_resistant: bool = Field(default=False)
    thdi_pct: Optional[float] = Field(default=None, ge=0.0, le=200.0)

class CatalogDevice(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    part_number: str
    manufacturer: str
    series: str
    device_type: str
    rated_current_in_a: float = 0.0
    boost_current_peak_a: float = 0.0
    setting_min_a: float = 0.0
    setting_max_a: float = 0.0
    motor_kw_400v: float = 0.0
    icu_ka_400v: float = 0.0
    power_loss_w: float = 0.0
    coil_holding_24v_w: float = 0.0
    coil_pull_in_24v_w: float = 0.0
    derating_40c: float = 1.0
    derating_50c: float = 1.0
    cap_kvar_400v: float = 0.0
    detuned_pct: float = 0.0
    tuned_hz: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    depth_mm: float = 0.0
    airflow_m3h: float = 0.0
    ip_rating: str = "IP20"
    enclosure_mounting: EnclosureMounting = EnclosureMounting.UNSPECIFIED
    data_quality: DataQuality = DataQuality.REAL_VERIFIED
    spd_class: Optional[str] = None
    spd_uc_v: float = 0.0
    spd_up_kv: float = 0.0
    spd_in_ka: float = 0.0
    spd_imax_ka: float = 0.0
    spd_iimp_ka: float = 0.0
    spd_poles: str = "4P"
    spd_backup_fuse_a: float = 0.0

class SelectivityRuleRecord(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    upstream_series: str
    upstream_min_in_a: float
    downstream_series: str
    downstream_max_in_a: float
    selectivity_limit_is_ka: float
    is_total_up_to_icu: bool = False
    catalog_reference: str

class ValidationResult(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    rule_id: str
    feeder_id: str
    standard_ref: str
    status: ValidationStatus
    description: str
    supporting_evidence: str
    consequence: str
    recommended_action: str

class ControlWire(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    wire_no: str
    from_dev: str
    from_term: str
    to_dev: str
    to_term: str
    color: str = "BU"
    cross_section_mm2: float = 1.5
    remark: str = ""

class LayoutDevice(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    tag: str
    part_number: str
    zone: str
    width_mm: float
    height_mm: float
    depth_mm: float = 0.0
    loss_w: float = 0.0
    clearance_mm: float = 0.0

class LayoutRow(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    row_no: int
    zone: str
    y_mm: float
    used_width_mm: float
    devices: List[LayoutDevice]

class PanelLayoutResult(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    panel_width_mm: float
    panel_height_mm: float
    panel_depth_mm: float
    usable_width_mm: float
    rows: List[LayoutRow]
    fill_factor_pct: float
    total_loss_w: float
    natural_dissipation_w: float
    spare_space_pct: float = 20.0
    form_partition_factor: float = 1.0
    validations: List[ValidationResult]

class BusbarResult(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    spec: str
    rating_a: float
    cross_section_mm2: float
    icw_1s_ka: float
    ipk_ka: float
    required_ipk_ka: Optional[float] = None
    max_support_spacing_mm: Optional[float] = None
    required_supports: int = 2
    r_mohm_m: float = 0.0
    x_mohm_m: float = 0.0
    length_m: float = 0.0
    voltage_drop_v: float = 0.0
    voltage_drop_pct: float = 0.0
    validations: List[ValidationResult] = []

class FeederCalcOutput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    feeder_id: str
    func_tag: str
    loc_tag: str
    description: str
    load_type: LoadType
    power_kw: float
    active_power_demand_kw: float
    reactive_power_demand_kvar: float
    design_current_ib_a: float
    delta_loop_current_a: Optional[float] = None
    star_current_a: Optional[float] = None
    required_in_after_derating_a: float
    cable_length_m: float = 20.0
    selected_phase_mm2: float = 2.5
    selected_pe_mm2: Optional[float] = 2.5
    cable_derated_iz_a: Optional[float] = 0.0
    cable_Auto_sized: bool = True
    cable_designation_str: str = ""
    cable_temp_factor_k1: float = 1.0
    cable_grouping_factor_k2: float = 1.0
    cable_total_derating_k: float = 1.0
    cable_method_ref_str: str = ""
    pe_basis_str: str = ""
    protection_icu_ka: Optional[float] = None
    voltage_drop_percent: float = 0.0
    assumptions_used: List[str] = []
    selected_protection: Optional[CatalogDevice] = None
    selected_contactor_main: Optional[CatalogDevice] = None
    selected_contactor_delta: Optional[CatalogDevice] = None
    selected_contactor_star: Optional[CatalogDevice] = None
    selected_bimetal: Optional[CatalogDevice] = None
    selected_timer_yd: Optional[CatalogDevice] = None
    selected_vfd: Optional[CatalogDevice] = None
    selected_soft_starter: Optional[CatalogDevice] = None
    selected_rcd: Optional[CatalogDevice] = None
    ctrl_24v_holding_w: float = 0.0
    ctrl_24v_pull_in_surge_w: float = 0.0
    selectivity_state: SelectivityEvalState = SelectivityEvalState.PRELIMINARY_RATIO_ONLY
    selectivity_limit_is_ka: Optional[float] = None
    selectivity_ref_doc: str = "-"
    total_feeder_loss_w: float = 0.0
    selection_reason: str = ""
    suggested_spec_str: str = ""
    starting_kva: float = 0.0
    starting_dip_pct: Optional[float] = None
    fire_pump_service: bool = False
    locked_rotor_current_a: Optional[float] = Field(default=None, gt=0)
    thdi_pct: Optional[float] = None
    fire_resistant: bool = False

class PanelSummaryOutput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    total_active_kw: float
    total_reactive_kvar: float
    total_apparent_kva: float
    overall_cos_phi: float
    sum_feeder_currents_a: float
    design_main_current_a: float
    main_breaker: Optional[CatalogDevice] = None
    recommended_busbar_spec: str
    recommended_pe_busbar_spec: str
    busbar_rating_a: float = 0.0
    busbar_icw_1s_ka: float = 0.0
    busbar_ipk_ka: float = 0.0
    busbar_required_ipk_ka: Optional[float] = None
    busbar_max_support_spacing_mm: Optional[float] = None
    busbar_required_supports: int = 2
    recommended_incoming_cable_str: str
    ctrl_24v_plc_hmi_w: float = 0.0
    ctrl_24v_coils_holding_w: float = 0.0
    ctrl_24v_total_continuous_w: float = 0.0
    ctrl_24v_continuous_current_a: float = 0.0
    ctrl_24v_design_current_with_spare_a: float = 0.0
    ctrl_24v_peak_inrush_current_a: float = 0.0
    selected_psu_24v: Optional[CatalogDevice] = None
    selected_dc_selectivity_mod: Optional[CatalogDevice] = None
    selected_psu_primary_mcb: Optional[CatalogDevice] = None
    total_power_loss_w: float
    enclosure_natural_dissipation_w: float
    required_airflow_m3h: float
    selected_fan: Optional[CatalogDevice] = None
    selected_enclosure: Optional[CatalogDevice] = None
    estimated_panel_width_mm: float
    estimated_panel_height_mm: float
    estimated_panel_depth_mm: float
    ik_used_ka: Optional[float] = None
    motor_contribution_ka: Optional[float] = None
    ik_bus_total_ka: Optional[float] = None
    ip_bus_total_ka: Optional[float] = None
    busbar_du_v: float = 0.0
    busbar_du_pct: float = 0.0
    max_total_du_pct: float = 0.0
    ik_source_str: str = ""
    effective_ip_str: str = ""
    suggested_main_breaker_str: str = ""
    suggested_psu_str: str = ""
    suggested_fan_str: str = ""
    max_motor_starting_dip_pct: Optional[float] = None
    max_starting_dip_motor: str = ""
    panel_thdi_pct: Optional[float] = None
    cap_bank_required_kvar: float = 0.0
    cap_bank_installed_kvar: float = 0.0
    cap_bank_steps: List[float] = []
    cap_bank_detuned_pct: float = 0.0
    cap_bank_reactor_tuned_hz: float = 0.0
    cap_bank_contactor: Optional[CatalogDevice] = None
    cap_bank_protection: Optional[CatalogDevice] = None
    cap_bank_reactor_dev: Optional[CatalogDevice] = None
    cap_bank_module_dev: Optional[CatalogDevice] = None
    cap_bank_resonance_order: Optional[float] = None
    cap_bank_suggested_str: str = ""
    selected_spd: Optional[CatalogDevice] = None
    spd_suggested_str: str = ""
    estimated_internal_temp_c: Optional[float] = None
    altitude_derating_factor: float = 1.0

class VerificationMethod(str, Enum):
    CALCULATION = "CALCULATION"
    DESIGN_RULE = "DESIGN_RULE"
    MANUFACTURER_DATA = "MANUFACTURER_DATA"
    TYPE_TEST = "TYPE_TEST"

class VerificationStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_VERIFIED = "NOT_VERIFIED"

class DesignVerificationItem(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    clause_ref: str
    title: str
    requirement: str
    method: VerificationMethod
    status: VerificationStatus
    computed_value: str
    evidence: str
    rule_ids: List[str] = []

class DesignVerificationReport(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    standard_ref: str = "IEC 61439-1"
    clause_ref: str = "Clause 10"
    items: List[DesignVerificationItem]
    conclusion_status: VerificationStatus
    conclusion_text: str
    generated_by: str = "LV-PanelAssist"



# ============================================================
# Priority 1 additions — Audit fixes
# ------------------------------------------------------------
# NOTE: The original audit guide proposed an enum named
# "VerificationStatus" for catalog provenance. But that name is
# already in use in this file for IEC 61439 design verification
# (PASS/WARNING/FAIL/NOT_VERIFIED). To avoid breaking existing
# code, the new enum is named CatalogProvenance.
# ============================================================

class CatalogProvenance(str, Enum):
    """Trust level of catalog data (distinct from design VerificationStatus)."""
    VERIFIED_CATALOG = "verified_catalog"
    UNVERIFIED_WEB = "unverified_web"
    USER_ESTIMATED = "user_estimated"


class StepExecState(str, Enum):
    """Execution state of a workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    CALCULATED = "calculated"
    FAILED = "failed"
    STALE = "stale"


class StepEngStatus(str, Enum):
    """Engineering review status of a workflow step."""
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    INSUFFICIENT_DATA = "insufficient_data"


class MainBreakerSpec(BaseModel):
    """Real selected main breaker spec (distinct from panel design current)."""
    model_config = ConfigDict(allow_inf_nan=False)

    device_type: Optional[str] = None
    model_name: Optional[str] = None
    part_number: Optional[str] = None
    in_a: Optional[float] = None
    poles: Optional[int] = None
    rated_voltage_v: Optional[float] = None
    icu_ka: Optional[float] = None
    ics_ka: Optional[float] = None
    icn_ka: Optional[float] = None
    icw_ka_1s: Optional[float] = None
    ir_setting_a: Optional[float] = None
    isd_setting_a: Optional[float] = None
    im_setting_a: Optional[float] = None
    ig_setting_a: Optional[float] = None
    verification_status: CatalogProvenance = CatalogProvenance.VERIFIED_CATALOG


class EnclosureSpec(BaseModel):
    """Explicit enclosure dimensions for summary card."""
    model_config = ConfigDict(allow_inf_nan=False)

    width_mm: Optional[int] = None
    height_mm: Optional[int] = None
    depth_mm: Optional[int] = None
    mounting_type: Optional[str] = None
    ip_rating: Optional[str] = None


class SPDType(str, Enum):
    """IEC 61643-11 SPD type (distinct from existing SpdClass)."""
    TYPE_1 = "Type 1"
    TYPE_2 = "Type 2"
    TYPE_3 = "Type 3"
    TYPE_1_2 = "Type 1+2"
    TYPE_2_3 = "Type 2+3"


class SPDSelectionResult(BaseModel):
    """SPD pre-selection result with explicit engineering status."""
    model_config = ConfigDict(allow_inf_nan=False)

    spd_type: Optional[SPDType] = None
    model_name: Optional[str] = None
    uc_v: Optional[float] = None
    up_kv: Optional[float] = None
    iimp_ka: Optional[float] = None
    in_ka: Optional[float] = None
    imax_ka: Optional[float] = None
    backup_fuse_a: Optional[float] = None
    engineering_status: StepEngStatus = StepEngStatus.INSUFFICIENT_DATA
    missing_parameters: List[str] = Field(default_factory=list)
    review_notes: List[str] = Field(default_factory=list)
