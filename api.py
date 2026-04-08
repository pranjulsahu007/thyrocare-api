import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
print("Starting API...")
try:
    from soem import ocr_pdf, extract_phenoage_inputs
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
def root():
    return {"status": "API running"}

@app.post("/parse-report")
async def parse_report(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name

        text = ocr_pdf(tmp_path)
        data = extract_phenoage_inputs(text)
        os.remove(tmp_path)

        return {
            "success": True,
            "filename": file.filename,
            "data": data
        }
    except Exception as e:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
