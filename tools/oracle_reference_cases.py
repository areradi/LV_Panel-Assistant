"""Fixed reference vectors for the standalone cable-selection oracle."""

REFERENCE_CASES = (
    {
        "name": "iec_table_copper_pvc_method_c_4mm2",
        # IEC 60364-5-52 Table B.52.4, 4 mm2 Cu/PVC, 3 loaded conductors,
        # reference method C: 32 A. The nominal current is set to this limit.
        "inputs": {
            "ib_a": 30.0, "voltage_v": 400.0, "phases": 3,
            "length_m": 10.0, "cos_phi": 0.9, "ambient_temp_c": 30.0,
            "grouping_k2": 1.0, "insulation": "PVC", "material": "CU",
            "installation_method": "C", "max_vdrop_pct": 5.0,
            "protection_in_a": 32.0, "is_adjustable_prot": True,
            "thdi_pct": None, "load_type": "MOTOR_DOL",
            "user_specified_mm2": None, "ik_ka": None, "fault_time_s": None,
            "overload_i2_factor": 1.45,
        },
        "expected": {"phase_mm2": 4.0, "iz0_a": 32.0},
    },
    {
        "name": "xlpe_copper_method_e_corrected_ampacity",
        # 16 mm2 reference ampacity is 76 A in the copied table; copied
        # correction factors yield k_total=0.954 at 40 C and k2=0.8.
        "inputs": {
            "ib_a": 70.0, "voltage_v": 400.0, "phases": 3,
            "length_m": 25.0, "cos_phi": 0.9, "ambient_temp_c": 40.0,
            "grouping_k2": 0.8, "insulation": "XLPE", "material": "CU",
            "installation_method": "E", "max_vdrop_pct": 5.0,
            "protection_in_a": 70.0, "is_adjustable_prot": True,
            "thdi_pct": None, "load_type": "MOTOR_DOL",
            "user_specified_mm2": None, "ik_ka": None, "fault_time_s": None,
            "overload_i2_factor": 1.45,
        },
        "expected": {"phase_mm2": 16.0, "iz0_a": 76.0, "k_total": 0.954},
    },
    {
        "name": "three_phase_voltage_drop_hand_calculation",
        # Hand calculation from the stated R20, temperature factor and X values.
        "inputs": {
            "ib_a": 40.0, "voltage_v": 400.0, "phases": 3,
            "length_m": 100.0, "cos_phi": 0.9, "ambient_temp_c": 30.0,
            "grouping_k2": 1.0, "insulation": "PVC", "material": "CU",
            "installation_method": "C", "max_vdrop_pct": 10.0,
            "protection_in_a": 40.0, "is_adjustable_prot": True,
            "thdi_pct": None, "load_type": "MOTOR_DOL",
            "user_specified_mm2": 10.0, "ik_ka": None, "fault_time_s": None,
            "overload_i2_factor": 1.45,
        },
        "expected": {"phase_mm2": 10.0, "delta_u_pct": 4.27},
    },
    {
        "name": "pe_section_with_table_and_adiabatic_minimum",
        # IEC 60364-5-54 Table 54.2: Cu/PVC in-cable k=115.
        "inputs": {
            "ib_a": 20.0, "voltage_v": 400.0, "phases": 3,
            "length_m": 10.0, "cos_phi": 0.9, "ambient_temp_c": 30.0,
            "grouping_k2": 1.0, "insulation": "PVC", "material": "CU",
            "installation_method": "C", "max_vdrop_pct": 5.0,
            "protection_in_a": 20.0, "is_adjustable_prot": True,
            "thdi_pct": None, "load_type": "MOTOR_DOL",
            "user_specified_mm2": 4.0, "ik_ka": 1.0, "fault_time_s": 0.1,
            "overload_i2_factor": 1.45,
        },
        "expected": {"phase_mm2": 4.0, "pe_mm2": 4.0},
    },
)
