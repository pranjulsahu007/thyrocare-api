import re
import fitz
import math

NEUTRAL_VALUES = {
    "albumin": 4.3,        # g/dL
    "creatinine": 0.9,     # mg/dL
    "glucose": 90,         # mg/dL
    "crp": 1.0,            # mg/L
    "lymphocyte": 30,      # %
    "mcv": 90,             # fL
    "rdw": 13.5,           # %
    "alp": 70,             # IU/L
    "wbc": 6.5             # x10^3/µL
}

def compute_phenoage(d):
    # Ensure crp is at least 0.01 to avoid log errors
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

    mortality = 1 - math.exp(
        (-math.exp(xb) * (math.exp(120 * gamma) - 1)) / gamma
    )

    mortality = max(min(mortality, 0.999999), 1e-6)

    pheno_age = (
        141.50225 +
        math.log(-0.00553 * math.log(1 - mortality)) / 0.090165
    )

    return pheno_age

# ---------- PDF Text Extraction ----------
def ocr_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    lines = []
    
    for page in doc:
        words = page.get_text("words")
        # Sort words by vertical coordinate (y-axis) then horizontal (x-axis)
        words.sort(key=lambda w: (round(w[1] / 5), w[0]))
        
        current_line = []
        last_y = None
        
        for w in words:
            y = round(w[1] / 5)
            if last_y is None or abs(y - last_y) <= 1:
                current_line.append(w[4])
                last_y = y
            else:
                lines.append(" ".join(current_line))
                current_line = [w[4]]
                last_y = y
        if current_line:
            lines.append(" ".join(current_line))

    return "\n".join(lines).lower()


# ---------- Extraction Helpers ----------
def extract_value_multi(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except:
                continue
    return None


# ---------- Main Extraction ----------
def extract_phenoage_inputs(text):
    data = {}

    data["albumin"] = extract_value_multi([r'albumin[^0-9]*([\d\.]+)\s*g.*dl'], text)
    data["creatinine"] = extract_value_multi([r'creatinine[^0-9]*([\d\.]+)\s*m.*dl'], text)
    data["glucose"] = extract_value_multi([r'average blood glucose \(abg\)[^0-9]*([\d\.]+)', r'glucose[^0-9]*([\d\.]+)\s*m.*dl'], text)
    data["crp"] = extract_value_multi([r'(?:hs[- ]?crp|crp)[^0-9]*([\d\.]+)\s*m.*l', r'c-reactive[^0-9]*([\d\.]+)\s*m.*l'], text)
    data["lymphocyte"] = extract_value_multi([r'lymphocyte[^0-9]*([\d\.]+)\s*%'], text)
    data["mcv"] = extract_value_multi([r'mcv\)?.*?([\d\.]+)\s*f.*l', r'mcv[^0-9]*([\d\.]+)\s*f?l'], text)
    data["rdw"] = extract_value_multi([r'rdw\s*-\s*cv[^0-9]*([\d\.]+)', r'rdw[- ]?cv.*?([\d\.]+)', r'rdw[^0-9]*([\d\.]+)\s*%'], text)
    data["alp"] = extract_value_multi([r'alkaline phosphatase[^0-9]*([\d\.]+)', r'\balp[^0-9]*([\d\.]+)'], text)
    data["wbc"] = extract_value_multi([r'total leucocyte count[^0-9]*([\d\.]+)', r'wbc[^0-9]*([\d\.]+)', r'leucocytes[^0-9]*([\d\.]+)\s*thou'], text)
    data["age"] = extract_value_multi([r'(\d+)\s*y/?[mf]', r'age[^0-9]*([\d\.]+)'], text)

    # ---------- Normalization ----------
    if data["wbc"] and data["wbc"] > 50:
        data["wbc"] = data["wbc"] / 1000

    # ---------- Handle Missing Values & Compute PhenoAge ----------
    missing = [k for k, v in data.items() if v is None and k != "age"]
    
    # Fill missing values with neutrals for the calculation
    calc_data = data.copy()
    for k in missing:
        calc_data[k] = NEUTRAL_VALUES.get(k, 0)
    
    # Default age if not found (though age is usually present)
    if calc_data.get("age") is None:
        calc_data["age"] = 30 # fallback
        if "age" not in missing: missing.append("age")

    pheno_age = None
    status = "high_confidence"
    message = "PhenoAge computed successfully"

    if len(missing) > 3:
        status = "low_confidence"
        message = f"Too many biomarkers missing ({len(missing)}: {', '.join(missing)}). Results may be inaccurate."
    elif len(missing) > 0:
        status = "medium_confidence"
        message = f"Some biomarkers missing ({len(missing)}: {', '.join(missing)}), using neutral values."

    try:
        pheno_age = compute_phenoage(calc_data)
    except Exception as e:
        message = f"Error computing PhenoAge: {str(e)}"
        status = "error"

    return {
        "biomarkers": data,
        "calculation_data": calc_data,
        "pheno_age": pheno_age,
        "status": status,
        "message": message,
        "missing_count": len(missing),
        "missing_biomarkers": missing
    }
