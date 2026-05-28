import os
import shutil
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
print("Starting API...")
try:
    from soem import calculate_blood_age, extract_blood_age_inputs, extract_phenoage_inputs, ocr_pdf
    print("Successfully imported soem modules.")
except Exception as e:
    print(f"Error importing soem: {e}")

app = FastAPI(title="Thyrocare Parser API")

# Allow React Native / any frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "API running"}

@app.head("/")
async def root_head():
    return None

class ParseReportUrlRequest(BaseModel):
    blood_test_report_url: str = Field(..., alias="bloodTestReportUrl")
    user_id: str | None = Field(default=None, alias="userId")
    assessment_id: str | None = Field(default=None, alias="assessmentId")

    class Config:
        allow_population_by_field_name = True


class BloodAgeRequest(BaseModel):
    age: float = Field(..., example=41)
    gender: str | None = Field(default=None, example="male")
    include_insulin: bool = Field(default=True, alias="includeInsulin", example=True)
    biomarkers: dict[str, float | None] = Field(
        ...,
        example={
            "S-albumin": 42.3,
            "S-ALP": 96.3,
            "S-urea": 5.52,
            "S-cholesterol": 6.41,
            "S-creatinine": 85.75,
            "B-HbA1c": 31.14,
            "S-GGT": 25.1,
            "RBC": 5.24,
            "MCV": 91.8,
            "RDW": 14.8,
            "MONOabs": 0.46,
            "NEUabs": 4.89,
            "LYM": 34.7,
            "S-ALT": 28.1,
            "S-25-OH-D": 64.65,
            "S-glucose": 5.38,
            "MCH": 28.2,
        },
    )

    class Config:
        allow_population_by_field_name = True


def build_report_response(filename, source_type, source_file_url, parsed_data, raw_text, user_id=None, assessment_id=None):
    return {
        "success": True,
        "filename": filename,
        "source_type": source_type,
        "source_file_url": source_file_url,
        "user_id": user_id,
        "assessment_id": assessment_id,
        "derived_ages": {
            "biological_age": parsed_data["pheno_age"],
            "blood_age": parsed_data.get("blood_age", {}).get("bio_age"),
            "chronological_age": parsed_data["biomarkers"].get("age"),
        },
        "data": parsed_data,
        "raw_text": raw_text,
    }


def build_blood_age_report_response(
    filename,
    source_type,
    source_file_url,
    blood_age_data,
    extracted_inputs,
    raw_text,
    user_id=None,
    assessment_id=None,
):
    return {
        "success": True,
        "filename": filename,
        "source_type": source_type,
        "source_file_url": source_file_url,
        "user_id": user_id,
        "assessment_id": assessment_id,
        "data": blood_age_data,
        "extracted_inputs": extracted_inputs,
        "raw_text": raw_text,
    }


def process_pdf_path(tmp_path, filename, source_type, source_file_url=None, user_id=None, assessment_id=None):
    try:
        text = ocr_pdf(tmp_path)
        data = extract_phenoage_inputs(text)
        data["blood_age_inputs"] = extract_blood_age_inputs(text)
        extracted_blood_biomarkers = data["blood_age_inputs"]["biomarkers"]
        extracted_age = extracted_blood_biomarkers.get("age")
        if extracted_age is not None:
            data["blood_age"] = calculate_blood_age(
                age=extracted_age,
                biomarkers=extracted_blood_biomarkers,
            )
        return build_report_response(
            filename=filename,
            source_type=source_type,
            source_file_url=source_file_url,
            parsed_data=data,
            raw_text=text,
            user_id=user_id,
            assessment_id=assessment_id,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def process_blood_age_pdf_path(
    tmp_path,
    filename,
    source_type,
    source_file_url=None,
    user_id=None,
    assessment_id=None,
):
    try:
        text = ocr_pdf(tmp_path)
        extracted_inputs = extract_blood_age_inputs(text)
        extracted_biomarkers = extracted_inputs["biomarkers"]
        extracted_age = extracted_biomarkers.get("age")

        if extracted_age is None:
            raise HTTPException(status_code=400, detail="Unable to extract age from report for blood age calculation")

        blood_age_data = calculate_blood_age(
            age=extracted_age,
            biomarkers=extracted_biomarkers,
        )

        return build_blood_age_report_response(
            filename=filename,
            source_type=source_type,
            source_file_url=source_file_url,
            blood_age_data=blood_age_data,
            extracted_inputs=extracted_inputs,
            raw_text=text,
            user_id=user_id,
            assessment_id=assessment_id,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def save_upload_to_temp(upload_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        shutil.copyfileobj(upload_file.file, tmp_file)
        return tmp_file.name


def download_pdf_to_temp(url):
    request = Request(
        url,
        headers={
            "User-Agent": "thyrocare-api/1.0",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        if content_type and "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
            raise HTTPException(status_code=400, detail="Remote file must be a PDF")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            shutil.copyfileobj(response, tmp_file)
            return tmp_file.name


@app.post("/parse-report")
async def parse_report(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        tmp_path = save_upload_to_temp(file)
        return process_pdf_path(
            tmp_path=tmp_path,
            filename=file.filename,
            source_type="file_upload",
        )
    except Exception as e:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/blood-age-from-report")
async def blood_age_from_report(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        tmp_path = save_upload_to_temp(file)
        return process_blood_age_pdf_path(
            tmp_path=tmp_path,
            filename=file.filename,
            source_type="file_upload",
        )
    except HTTPException:
        raise
    except Exception as e:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/blood-age")
async def blood_age(payload: BloodAgeRequest):
    try:
        return calculate_blood_age(
            age=payload.age,
            biomarkers=payload.biomarkers,
            include_insulin=payload.include_insulin,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/blood-age-from-report-url")
async def blood_age_from_report_url(payload: ParseReportUrlRequest):
    try:
        tmp_path = download_pdf_to_temp(payload.blood_test_report_url)
        filename = os.path.basename(payload.blood_test_report_url.split("?")[0]) or "report.pdf"
        return process_blood_age_pdf_path(
            tmp_path=tmp_path,
            filename=filename,
            source_type="remote_url",
            source_file_url=payload.blood_test_report_url,
            user_id=payload.user_id,
            assessment_id=payload.assessment_id,
        )
    except HTTPException:
        raise
    except HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Unable to download report: HTTP {e.code}")
    except URLError as e:
        raise HTTPException(status_code=400, detail=f"Unable to download report: {e.reason}")
    except Exception as e:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/parse-report-url")
async def parse_report_url(payload: ParseReportUrlRequest):
    try:
        tmp_path = download_pdf_to_temp(payload.blood_test_report_url)
        filename = os.path.basename(payload.blood_test_report_url.split("?")[0]) or "report.pdf"
        return process_pdf_path(
            tmp_path=tmp_path,
            filename=filename,
            source_type="remote_url",
            source_file_url=payload.blood_test_report_url,
            user_id=payload.user_id,
            assessment_id=payload.assessment_id,
        )
    except HTTPException:
        raise
    except HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Unable to download report: HTTP {e.code}")
    except URLError as e:
        raise HTTPException(status_code=400, detail=f"Unable to download report: {e.reason}")
    except Exception as e:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
