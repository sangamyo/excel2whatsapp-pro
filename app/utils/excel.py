import pandas as pd
from fastapi import UploadFile, HTTPException
import io
import re

PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")

async def parse_excel_upload(file: UploadFile):
    contents = await file.read()
    try:
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents), dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(io.BytesIO(contents), dtype=str)
        df = df.fillna("")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid spreadsheet file: {e}")

    required = {"Name", "Phone", "CustomField"}
    if not required.issubset(set(df.columns)):
        raise HTTPException(status_code=400, detail=f"Missing required columns: {required - set(df.columns)}")

    rows = []
    for _, row in df.iterrows():
        name = str(row.get('Name')) if not pd.isna(row.get('Name')) else ''
        phone = str(row.get('Phone')) if not pd.isna(row.get('Phone')) else ''
        custom = str(row.get('CustomField')) if not pd.isna(row.get('CustomField')) else ''

        phone = phone.strip()
        if not PHONE_RE.match(phone):
            raise HTTPException(status_code=400, detail=f"Invalid phone number format: {phone}")

        rows.append({"Name": name, "Phone": phone, "CustomField": custom})

    return rows
