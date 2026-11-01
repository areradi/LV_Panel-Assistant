from enum import Enum
from dataclasses import dataclass
from typing import Optional
from lv_assist.core_verification import CheckResult, ValidationStatus


class DataConfidenceLevel(str, Enum):
    REAL_VERIFIED = "REAL_VERIFIED"
    CURVE_EXTRACTED = "CURVE_EXTRACTED"
    ESTIMATED = "ESTIMATED"


@dataclass
class CatalogDataProvenance:
    manufacturer: str
    part_number: str
    datasheet_title_or_id: str
    datasheet_edition_date: str
    valid_voltage_v: int = 400
    valid_ambient_temp_c: int = 40
    valid_frequency_hz: int = 50
    confidence: DataConfidenceLevel = DataConfidenceLevel.ESTIMATED
    last_audited_by: Optional[str] = None
    last_audited_date: Optional[str] = None

    def is_production_verified(self) -> bool:
        return (
            self.confidence == DataConfidenceLevel.REAL_VERIFIED
            and bool(self.datasheet_title_or_id.strip())
            and bool(self.datasheet_edition_date.strip())
        )


def evaluate_selectivity_status(
    upstream_in_a: Optional[float],
    downstream_in_a: Optional[float],
    has_manufacturer_coordination_table: bool = False,
    manufacturer_table_limit_ka: Optional[float] = None,
    prospective_ik_ka: Optional[float] = None,
) -> CheckResult:
    if not upstream_in_a or not downstream_in_a or upstream_in_a <= 0 or downstream_in_a <= 0:
        return CheckResult(
            check_id="SELECTIVITY_CHECK",
            title="هماهنگی حفاظتی و سلکتیویتی (Selectivity)",
            status=ValidationStatus.INSUFFICIENT_DATA,
            cause="جریان نامی کلید بالادست یا پایین‌دست نامشخص است.",
            effect="امکان بررسی سلکتیویتی وجود ندارد.",
            recommended_action="کلیدهای بالادست و پایین‌دست را مشخص کنید."
        )

    ratio = upstream_in_a / downstream_in_a
    if ratio < 1.6:
        return CheckResult(
            check_id="SELECTIVITY_CHECK",
            title="هماهنگی حفاظتی و سلکتیویتی (Selectivity)",
            status=ValidationStatus.ERROR,
            measured_or_calc_value=f"In_up / In_down = {ratio:.2f}",
            limit_or_reference="حداقل نسبت پیشنهادی اولیه >= 1.6",
            cause="نسبت جریان نامی کلید بالادست به پایین‌دست کمتر از 1.6 است.",
            effect="احتمال بالای قطع هم‌زمان هر دو کلید.",
            recommended_action="فاصله رنج جریانی کلیدها را افزایش دهید."
        )

    if has_manufacturer_coordination_table and manufacturer_table_limit_ka and prospective_ik_ka:
        if prospective_ik_ka <= manufacturer_table_limit_ka:
            return CheckResult(
                check_id="SELECTIVITY_CHECK",
                title="هماهنگی حفاظتی و سلکتیویتی (Selectivity)",
                status=ValidationStatus.COMPLETED,
                measured_or_calc_value=f"Is = {manufacturer_table_limit_ka:.1f} kA >= Ik = {prospective_ik_ka:.2f} kA",
                limit_or_reference="جدول هماهنگی تست‌شده سازنده (IEC 60947-2 Annex A)",
                effect="سلکتیویتی کامل (Total Selectivity) تأیید شد."
            )
        return CheckResult(
            check_id="SELECTIVITY_CHECK",
            title="هماهنگی حفاظتی و سلکتیویتی (Selectivity)",
            status=ValidationStatus.WARNING,
            measured_or_calc_value=f"Is = {manufacturer_table_limit_ka:.1f} kA < Ik = {prospective_ik_ka:.2f} kA",
            limit_or_reference="سلکتیویتی جزئی (Partial Selectivity)",
            cause="جریان اتصال کوتاه محل نصب از مرز سلکتیویتی جدول سازنده بیشتر است.",
            effect="سلکتیویتی فقط تا جریان Is برقرار است.",
            recommended_action="فریم سایز کلید بالادست را ارتقا دهید."
        )

    return CheckResult(
        check_id="SELECTIVITY_CHECK",
        title="هماهنگی حفاظتی و سلکتیویتی (برآورد مقدماتی)",
        status=ValidationStatus.WARNING,
        measured_or_calc_value=f"Ratio = {ratio:.2f} (بدون جدول تست سازنده)",
        limit_or_reference="PRELIMINARY — نیازمند جدول هماهنگی سازنده",
        cause="صرفاً بر اساس نسبت جریان نامی برآورد شده است.",
        effect="سلکتیویتی در ناحیه اتصال کوتاه دینامیکی اثبات‌شده نیست.",
        recommended_action="مرز سلکتیویتی (Is) را در جداول هماهنگی سازنده کنترل کنید."
    )
