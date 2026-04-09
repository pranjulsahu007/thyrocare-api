import re
import fitz

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

    return data
