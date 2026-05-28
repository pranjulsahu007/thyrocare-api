import math
import re
from typing import Any

import fitz

NEUTRAL_VALUES = {
    "albumin": 4.3,
    "creatinine": 0.9,
    "glucose": 90,
    "crp": 1.0,
    "lymphocyte": 30,
    "mcv": 90,
    "rdw": 13.5,
    "alp": 70,
    "wbc": 6.5,
}

BLOOD_AGE_MODEL = [
    {"id": "age", "required_unit": "years", "coefficient": -0.025669127, "feature_mean": 56.0487752},
    {"id": "S-albumin", "required_unit": "g/L", "coefficient": -0.011331946, "feature_mean": 45.1238763},
    {"id": "S-ALP", "required_unit": "IU/L", "coefficient": 0.00164946, "feature_mean": 82.6847975},
    {"id": "S-urea", "required_unit": "mmol/L", "coefficient": -0.029554872, "feature_mean": 5.3547152},
    {"id": "S-cholesterol", "required_unit": "mmol/L", "coefficient": -0.0805656, "feature_mean": 5.6177437},
    {"id": "S-creatinine", "required_unit": "µmol/L", "coefficient": -0.01095746, "feature_mean": 71.565605},
    {"id": "S-cystatin-C", "required_unit": "mg/L", "coefficient": 1.859556436, "feature_mean": 0.900946},
    {"id": "B-HbA1c", "required_unit": "mmol/mol", "coefficient": 0.018116675, "feature_mean": 35.4785711},
    {"id": "S-hsCRP", "required_unit": "mg/L", "coefficient": 0.079109916, "feature_mean": 0.3003624, "transform": "log"},
    {"id": "S-GGT", "required_unit": "IU/L", "coefficient": 0.265550311, "feature_mean": 3.3795613, "transform": "log"},
    {"id": "RBC", "required_unit": "x10^12/L", "coefficient": -0.204442153, "feature_mean": 4.4994648},
    {"id": "MCV", "required_unit": "fL", "coefficient": 0.017165356, "feature_mean": 91.9251099},
    {"id": "RDW", "required_unit": "%", "coefficient": 0.202009895, "feature_mean": 13.4342296},
    {"id": "MONOabs", "required_unit": "x10^9/L", "coefficient": 0.36937314, "feature_mean": 0.4746987},
    {"id": "NEUabs", "required_unit": "x10^9/L", "coefficient": 0.06679092, "feature_mean": 4.1849454},
    {"id": "LYM", "required_unit": "%", "coefficient": -0.0108158, "feature_mean": 28.5817604},
    {"id": "S-ALT", "required_unit": "IU/L", "coefficient": -0.312442261, "feature_mean": 3.077868, "transform": "log"},
    {"id": "S-SHBG", "required_unit": "nmol/L", "coefficient": 0.292323186, "feature_mean": 3.8202787, "transform": "log"},
    {"id": "S-25-OH-D", "required_unit": "nmol/L", "coefficient": -0.265467867, "feature_mean": 3.6052878, "transform": "log"},
    {"id": "S-glucose", "required_unit": "mmol/L", "coefficient": 0.032171478, "feature_mean": 4.9563054},
    {"id": "MCH", "required_unit": "pg", "coefficient": 0.02746487, "feature_mean": 31.8396206},
    {"id": "S-ApoA1", "required_unit": "g/L", "coefficient": -0.185139395, "feature_mean": 1.5238771},
    {"id": "S-insulin", "required_unit": "µIU/mL", "coefficient": 0.29, "feature_mean": 2.39, "transform": "log"},
]


def normalize_glucose(value, source):
    if source == "abg":
        return value * 0.85
    return value


def compute_phenoage(d):
    crp_val = max(d["crp"], 0.01)

    xb = (
        -19.907
        - 0.0336 * d["albumin"]
        + 0.0095 * d["creatinine"]
        + 0.0095 * d["glucose"]
        + 0.0954 * math.log(crp_val)
        - 0.012 * d["lymphocyte"]
        + 0.0268 * d["mcv"]
        + 0.3306 * d["rdw"]
        + 0.00188 * d["alp"]
        + 0.0554 * d["wbc"]
        + 0.0804 * d["age"]
    )

    gamma = 0.0076927
    exp_xb = math.exp(xb)
    term = (math.exp(120 * gamma) - 1) / gamma
    mortality = 1 - math.exp(-exp_xb * term)
    mortality = max(min(mortality, 0.999999), 1e-10)
    return 141.50225 + math.log(-0.00553 * math.log(1 - mortality)) / 0.090165


def ocr_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    lines = []

    for page in doc:
        words = page.get_text("words")
        words.sort(key=lambda w: (round(w[1] / 5), w[0]))

        current_line = []
        last_y = None
        for word in words:
            y = round(word[1] / 5)
            if last_y is None or abs(y - last_y) <= 1:
                current_line.append(word[4])
                last_y = y
            else:
                lines.append(" ".join(current_line))
                current_line = [word[4]]
                last_y = y

        if current_line:
            lines.append(" ".join(current_line))

    return "\n".join(lines).lower()


def extract_value_multi(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def convert_hba1c_percent_to_mmol_per_mol(value):
    return (value - 2.15) * 10.929


def normalize_count_to_x10_9_per_l(value, unit_hint):
    if value is None:
        return None

    normalized_unit = (unit_hint or "").lower().replace(" ", "")
    accepted_units = {
        "x10³/µl",
        "x10^3/µl",
        "x10³/ul",
        "x10^3/ul",
        "x10^9/l",
    }

    if normalized_unit in accepted_units:
        return value
    return value


def extract_number_with_unit(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = to_float(match.group(1))
            if value is None:
                continue
            unit = match.group(2).strip() if match.lastindex and match.lastindex > 1 else None
            return value, unit
    return None, None


def safe_log(value):
    if value is None or value <= 0 or math.isnan(value):
        return None
    return math.log(value)


def round_or_none(value, digits=4):
    if value is None:
        return None
    return round(value, digits)


def get_range_color(age_acceleration):
    if age_acceleration < -6:
        return "green"
    if age_acceleration < 3:
        return "yellow"
    return "red"


def get_blood_age_status(missing_count):
    if missing_count >= 8:
        return "low_confidence"
    if missing_count >= 3:
        return "medium_confidence"
    return "high_confidence"


def extract_blood_age_inputs(text):
    data = {}
    data["age"] = extract_value_multi([r"(\d+)\s*y/?[mf]", r"age[^0-9]*([\d\.]+)"], text)

    albumin_g_dl = extract_value_multi(
        [
            r"albumin\s*-\s*serum[^0-9]*([\d\.]+)\s*g(?:m)?/dl",
            r"albumin[^0-9]*([\d\.]+)\s*g(?:m)?/dl",
        ],
        text,
    )
    data["S-albumin"] = albumin_g_dl * 10 if albumin_g_dl is not None else None

    data["S-ALP"] = extract_value_multi(
        [r"alkaline phosphatase[^0-9]*([\d\.]+)\s*u/l", r"\balp[^0-9]*([\d\.]+)\s*u/l"],
        text,
    )

    urea_mg_dl = extract_value_multi(
        [r"urea\s*\(calculated\)[^0-9]*([\d\.]+)\s*mg/dl", r"\burea\b[^0-9]*([\d\.]+)\s*mg/dl"],
        text,
    )
    data["S-urea"] = urea_mg_dl * 0.1665 if urea_mg_dl is not None else None

    cholesterol_mg_dl = extract_value_multi(
        [r"total cholesterol[^0-9]*([\d\.]+)\s*mg/dl", r"cholesterol[^0-9]*([\d\.]+)\s*mg/dl"],
        text,
    )
    data["S-cholesterol"] = cholesterol_mg_dl * 0.02586 if cholesterol_mg_dl is not None else None

    creatinine_mg_dl = extract_value_multi(
        [r"creatinine\s*-\s*serum[^0-9]*([\d\.]+)\s*mg/dl", r"creatinine[^0-9]*([\d\.]+)\s*mg/dl"],
        text,
    )
    data["S-creatinine"] = creatinine_mg_dl * 88.4 if creatinine_mg_dl is not None else None

    data["S-cystatin-C"] = extract_value_multi([r"cystatin\s*-?\s*c[^0-9]*([\d\.]+)\s*mg/l"], text)

    hba1c_percent = extract_value_multi([r"hba1c[^0-9]*([\d\.]+)\s*%"], text)
    data["B-HbA1c"] = convert_hba1c_percent_to_mmol_per_mol(hba1c_percent) if hba1c_percent is not None else None

    data["S-hsCRP"] = extract_value_multi(
        [
            r"hs[-\s]?crp[^0-9]*([\d\.]+)\s*mg/l",
            r"c-reactive protein[^0-9]*([\d\.]+)\s*mg/l",
            r"\bcrp\b[^0-9]*([\d\.]+)\s*mg/l",
        ],
        text,
    )

    data["S-GGT"] = extract_value_multi(
        [r"gamma glutamyl transferase\s*\(ggt\)[^0-9]*([\d\.]+)\s*u/l", r"\bggt\b[^0-9]*([\d\.]+)\s*u/l"],
        text,
    )

    rbc_value, rbc_unit = extract_number_with_unit(
        [r"total rbc[^0-9]*([\d\.]+)\s*(x\s*10\^6\s*/\s*[µu]l)", r"\brbc\b[^0-9]*([\d\.]+)\s*(x\s*10\^6\s*/\s*[µu]l)"],
        text,
    )
    data["RBC"] = rbc_value if rbc_value is not None and rbc_unit else None

    data["MCV"] = extract_value_multi(
        [r"mean corpuscular volume\s*\(mcv\)[^0-9]*([\d\.]+)\s*fl", r"\bmcv\b[^0-9]*([\d\.]+)\s*fl"],
        text,
    )

    data["RDW"] = extract_value_multi(
        [
            r"red cell distribution width\s*\(rdw\s*-\s*cv\)[^0-9]*([\d\.]+)\s*%",
            r"rdw[-\s]*cv[^0-9]*([\d\.]+)\s*%",
            r"\brdw\b[^0-9]*([\d\.]+)\s*%",
        ],
        text,
    )

    mono_abs_value, mono_abs_unit = extract_number_with_unit(
        [r"monocytes\s*-\s*absolute count[^0-9]*([\d\.]+)\s*(x\s*10[³\^]3\s*/\s*[µu]l)"],
        text,
    )
    data["MONOabs"] = normalize_count_to_x10_9_per_l(mono_abs_value, mono_abs_unit)

    neu_abs_value, neu_abs_unit = extract_number_with_unit(
        [r"neutrophils\s*-\s*absolute count[^0-9]*([\d\.]+)\s*(x\s*10[³\^]3\s*/\s*[µu]l)"],
        text,
    )
    data["NEUabs"] = normalize_count_to_x10_9_per_l(neu_abs_value, neu_abs_unit)

    data["LYM"] = extract_value_multi(
        [r"lymphocytes percentage[^0-9]*([\d\.]+)\s*%", r"lymphocyte[^0-9]*([\d\.]+)\s*%"],
        text,
    )

    data["S-ALT"] = extract_value_multi(
        [
            r"alanine transaminase\s*\(sgpt\)[^0-9]*([\d\.]+)\s*u/l",
            r"\bsgpt\b[^0-9]*([\d\.]+)\s*u/l",
            r"\balt\b[^0-9]*([\d\.]+)\s*u/l",
        ],
        text,
    )

    data["S-SHBG"] = extract_value_multi([r"\bshbg\b[^0-9]*([\d\.]+)\s*nmol/l"], text)

    vitamin_d_ng_ml = extract_value_multi(
        [r"25-oh vitamin d\s*\(total\)[^0-9]*([\d\.]+)\s*ng/ml", r"vitamin d[^0-9]*([\d\.]+)\s*ng/ml"],
        text,
    )
    data["S-25-OH-D"] = vitamin_d_ng_ml * 2.496 if vitamin_d_ng_ml is not None else None

    glucose_mg_dl = extract_value_multi(
        [r"average blood glucose\s*\(abg\)[^0-9]*([\d\.]+)\s*mg/dl", r"glucose[^0-9]*([\d\.]+)\s*mg/dl"],
        text,
    )
    data["S-glucose"] = glucose_mg_dl * 0.0555 if glucose_mg_dl is not None else None

    data["MCH"] = extract_value_multi(
        [r"mean corpuscular hemoglobin\s*\(mch\)[^0-9]*([\d\.]+)", r"\bmch\b[^0-9]*([\d\.]+)"],
        text,
    )

    data["S-ApoA1"] = extract_value_multi(
        [r"apo[a ]?1[^0-9]*([\d\.]+)\s*g/l", r"apolipoprotein a1[^0-9]*([\d\.]+)\s*g/l"],
        text,
    )

    data["S-insulin"] = extract_value_multi([r"\binsulin\b[^0-9]*([\d\.]+)\s*[µu]iu/ml"], text)

    missing = [key for key, value in data.items() if value is None and key != "age"]
    return {
        "biomarkers": data,
        "missing_biomarkers": missing,
        "available_biomarkers": [key for key, value in data.items() if value is not None],
        "available_count": len([key for key, value in data.items() if value is not None and key != "age"]),
    }


def calculate_blood_age(age: float, biomarkers: dict[str, Any], include_insulin: bool = True):
    scores = []
    warnings = []
    missing_biomarkers = []
    total_score_sum = 0.0

    biomarker_values = dict(biomarkers)
    biomarker_values["age"] = age

    for config in BLOOD_AGE_MODEL:
        biomarker_id = config["id"]
        if biomarker_id == "S-insulin" and not include_insulin:
            continue

        raw_value = biomarker_values.get(biomarker_id)
        used_neutral = False
        coefficient = config["coefficient"]
        feature_mean = config["feature_mean"]
        transform = config.get("transform")

        if raw_value is None:
            used_neutral = True
            missing_biomarkers.append(biomarker_id)
            transformed_value = feature_mean
            centered_value = 0.0
            score = 0.0
            warnings.append(f"{biomarker_id} missing, using neutral mean.")
        else:
            raw_value = to_float(raw_value)
            transformed_value = raw_value

            if raw_value is None or math.isnan(raw_value):
                used_neutral = True
                missing_biomarkers.append(biomarker_id)
                transformed_value = feature_mean
                centered_value = 0.0
                score = 0.0
                warnings.append(f"{biomarker_id} invalid, using neutral mean.")
            elif transform == "log":
                transformed_value = safe_log(raw_value)
                if transformed_value is None:
                    used_neutral = True
                    missing_biomarkers.append(biomarker_id)
                    transformed_value = feature_mean
                    centered_value = 0.0
                    score = 0.0
                    warnings.append(f"{biomarker_id} must be > 0 for log transform, using neutral mean.")
                else:
                    centered_value = transformed_value - feature_mean
                    score = centered_value * coefficient
            else:
                centered_value = transformed_value - feature_mean
                score = centered_value * coefficient

        total_score_sum += score
        scores.append(
            {
                "id": biomarker_id,
                "raw_value": round_or_none(raw_value),
                "transformed_value": round_or_none(transformed_value),
                "centered_value": round_or_none(centered_value),
                "coefficient": coefficient,
                "score": round_or_none(score),
                "required_unit": config["required_unit"],
                "used_neutral": used_neutral,
            }
        )

    total_score = 10 * total_score_sum
    bio_age = age + total_score
    age_acceleration = bio_age - age
    age_acceleration_percent = (age_acceleration / age * 100) if age > 0 else 0.0

    if not include_insulin:
        warnings.append("S-insulin excluded from scoring by request.")

    status = get_blood_age_status(len(missing_biomarkers))
    if missing_biomarkers:
        message = f"Blood age computed with {len(missing_biomarkers)} neutral biomarkers."
    else:
        message = "Blood age computed successfully."

    return {
        "bio_age": round(bio_age, 1),
        "age_acceleration": round(age_acceleration, 1),
        "age_acceleration_percent": round(age_acceleration_percent, 1),
        "range_color": get_range_color(age_acceleration),
        "scores": scores,
        "missing_biomarkers": missing_biomarkers,
        "missing_count": len(missing_biomarkers),
        "warnings": warnings,
        "status": status,
        "message": message,
        "biomarker_count_used": len(scores) - len(missing_biomarkers),
        "neutral_biomarker_count": len(missing_biomarkers),
    }


def extract_phenoage_inputs(text):
    data = {}
    data["albumin"] = extract_value_multi([r"albumin[^0-9]*([\d\.]+)\s*g.*dl"], text)
    data["creatinine"] = extract_value_multi([r"creatinine[^0-9]*([\d\.]+)\s*m.*dl"], text)

    glucose_abg = extract_value_multi([r"average blood glucose \(abg\)[^0-9]*([\d\.]+)"], text)
    if glucose_abg is not None:
        data["glucose"] = normalize_glucose(glucose_abg, "abg")
    else:
        data["glucose"] = extract_value_multi([r"glucose[^0-9]*([\d\.]+)\s*m.*dl"], text)

    data["crp"] = extract_value_multi([r"(?:hs[- ]?crp|crp)[^0-9]*([\d\.]+)\s*m.*l", r"c-reactive[^0-9]*([\d\.]+)\s*m.*l"], text)
    data["lymphocyte"] = extract_value_multi([r"lymphocyte[^0-9]*([\d\.]+)\s*%"], text)
    data["mcv"] = extract_value_multi([r"mcv\)?.*?([\d\.]+)\s*f.*l", r"mcv[^0-9]*([\d\.]+)\s*f?l"], text)
    data["rdw"] = extract_value_multi([r"rdw\s*-\s*cv[^0-9]*([\d\.]+)", r"rdw[- ]?cv.*?([\d\.]+)", r"rdw[^0-9]*([\d\.]+)\s*%"], text)
    data["alp"] = extract_value_multi([r"alkaline phosphatase[^0-9]*([\d\.]+)", r"\balp[^0-9]*([\d\.]+)"], text)
    data["wbc"] = extract_value_multi([r"total leucocyte count[^0-9]*([\d\.]+)", r"wbc[^0-9]*([\d\.]+)", r"leucocytes[^0-9]*([\d\.]+)\s*thou"], text)
    data["age"] = extract_value_multi([r"(\d+)\s*y/?[mf]", r"age[^0-9]*([\d\.]+)"], text)

    if data["wbc"] and data["wbc"] > 50:
        data["wbc"] = data["wbc"] / 1000

    missing = [key for key, value in data.items() if value is None and key != "age"]
    calc_data = data.copy()
    for key in missing:
        calc_data[key] = NEUTRAL_VALUES.get(key, 0)

    if calc_data.get("age") is None:
        calc_data["age"] = 30
        if "age" not in missing:
            missing.append("age")

    pheno_age = None
    status = "high_confidence"
    message = "PhenoAge computed successfully"

    if len(missing) > 3:
        status = "low_confidence"
        message = f"Too many biomarkers missing ({len(missing)}: {', '.join(missing)}). Results may be inaccurate."
    elif missing:
        status = "medium_confidence"
        message = f"Some biomarkers missing ({len(missing)}: {', '.join(missing)}), using neutral values."

    try:
        pheno_age = compute_phenoage(calc_data)
    except Exception as exc:
        message = f"Error computing PhenoAge: {str(exc)}"
        status = "error"

    return {
        "biomarkers": data,
        "calculation_data": calc_data,
        "pheno_age": pheno_age,
        "status": status,
        "message": message,
        "missing_count": len(missing),
        "missing_biomarkers": missing,
    }
