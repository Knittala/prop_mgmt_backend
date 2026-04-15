from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
import uuid
import os
import json
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ID = os.getenv("PROJECT_ID", "nittala-purdue-devops")
DATASET = "property_mgmt"

# ---------------------------------------------------------------------------
# Dependency: BigQuery client
# ---------------------------------------------------------------------------

def get_bq_client():
    client = bigquery.Client()
    try:
        yield client
    finally:
        client.close()

# ---------------------------------------------------------------------------
# Helper: load job insert (avoids streaming buffer)
# ---------------------------------------------------------------------------

def load_rows(bq, table_id, rows):
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=False,
    )
    data = "\n".join(json.dumps(row, default=str) for row in rows)
    job = bq.load_table_from_file(
        io.StringIO(data),
        table_id,
        job_config=job_config,
    )
    job.result()
    if job.errors:
        raise Exception(f"Load job failed: {job.errors}")

# ---------------------------------------------------------------------------
# Models (Pydantic)
# ---------------------------------------------------------------------------

class IncomeCreate(BaseModel):
    amount: float
    source: str
    payment_date: date

class ExpenseCreate(BaseModel):
    amount: float
    category: str
    description: str
    expense_date: date

class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    tenant_name: Optional[str] = None
    monthly_rent: Optional[float] = None

class PropertyCreate(BaseModel):
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    property_type: Optional[str] = None
    tenant_name: Optional[str] = None
    monthly_rent: Optional[float] = None

# ---------------------------------------------------------------------------
# Properties Endpoints
# ---------------------------------------------------------------------------

@app.get("/properties")
def get_properties(bq: bigquery.Client = Depends(get_bq_client)):
    query = f"""
        SELECT property_id, name, address, city, state, postal_code,
               property_type, tenant_name, monthly_rent
        FROM `{PROJECT_ID}.{DATASET}.properties`
        ORDER BY property_id
    """
    try:
        results = bq.query(query).result()
        return [dict(row) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# FIX: POST /properties must be registered BEFORE /properties/{property_id}
# so FastAPI does not try to match the literal path "/properties" as a property_id param.
@app.post("/properties", status_code=status.HTTP_201_CREATED)
def create_property(prop: PropertyCreate, bq: bigquery.Client = Depends(get_bq_client)):
    table_id = f"{PROJECT_ID}.{DATASET}.properties"

    # FIX: property_id is INT64 in BigQuery (consistent with every other endpoint
    # that declares property_id: int). Generate a large random int instead of a string.
    new_id = uuid.uuid4().int >> 96  # produces a positive 32-bit-range integer

    new_row = [{
        "property_id": new_id,
        "name": prop.name,
        "address": prop.address,
        "city": prop.city,
        "state": prop.state,
        "postal_code": prop.postal_code,
        "property_type": prop.property_type,
        "tenant_name": prop.tenant_name,
        "monthly_rent": prop.monthly_rent,
    }]
    try:
        load_rows(bq, table_id, new_row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")
    return {"status": "success", "property_id": new_id, "data": new_row[0]}

@app.get("/properties/{property_id}")
def get_property(property_id: int, bq: bigquery.Client = Depends(get_bq_client)):
    query = f"SELECT * FROM `{PROJECT_ID}.{DATASET}.properties` WHERE property_id = @prop_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prop_id", "INT64", property_id)]
    )
    try:
        results = bq.query(query, job_config=job_config).result()
        properties = [dict(row) for row in results]
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        return properties[0]
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/properties/{property_id}")
def update_property(property_id: int, updates: PropertyUpdate, bq: bigquery.Client = Depends(get_bq_client)):
    update_data = updates.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    set_clause = ", ".join([f"{key} = @{key}" for key in update_data.keys()])
    query = f"UPDATE `{PROJECT_ID}.{DATASET}.properties` SET {set_clause} WHERE property_id = @prop_id"

    query_params = [bigquery.ScalarQueryParameter("prop_id", "INT64", property_id)]
    for key, value in update_data.items():
        p_type = "FLOAT64" if isinstance(value, float) else "STRING"
        query_params.append(bigquery.ScalarQueryParameter(key, p_type, value))

    try:
        bq.query(query, job_config=bigquery.QueryJobConfig(query_parameters=query_params)).result()
        return {"message": f"Property {property_id} updated", "fields": list(update_data.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/properties/{property_id}", status_code=status.HTTP_200_OK)
def delete_property(property_id: int, bq: bigquery.Client = Depends(get_bq_client)):
    query = f"DELETE FROM `{PROJECT_ID}.{DATASET}.properties` WHERE property_id = @prop_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prop_id", "INT64", property_id)]
    )
    try:
        bq.query(query, job_config=job_config).result()
        return {"message": f"Property {property_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Income Endpoints
# FIX: /income/status/arrears must be registered BEFORE /income/{property_id}
# otherwise FastAPI matches "status" as the property_id param and throws a 422.
# ---------------------------------------------------------------------------

@app.get("/income/status/arrears")
def get_arrears_report(bq: bigquery.Client = Depends(get_bq_client)):
    now = datetime.now()
    query = f"""
        SELECT
            p.property_id, p.name, p.tenant_name, p.monthly_rent,
            IFNULL(SUM(i.amount), 0) as paid,
            (p.monthly_rent - IFNULL(SUM(i.amount), 0)) as debt
        FROM `{PROJECT_ID}.{DATASET}.properties` p
        LEFT JOIN `{PROJECT_ID}.{DATASET}.income` i ON p.property_id = i.property_id
             AND EXTRACT(MONTH FROM i.payment_date) = @m
             AND EXTRACT(YEAR FROM i.payment_date) = @y
        WHERE p.tenant_name IS NOT NULL
        GROUP BY 1, 2, 3, 4
        HAVING debt > 0
    """
    params = [
        bigquery.ScalarQueryParameter("m", "INT64", now.month),
        bigquery.ScalarQueryParameter("y", "INT64", now.year)
    ]
    try:
        results = bq.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return [dict(row) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/income/{property_id}")
def get_income_records(property_id: int, bq: bigquery.Client = Depends(get_bq_client)):
    query = f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET}.income`
        WHERE property_id = @prop_id
        ORDER BY payment_date DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prop_id", "INT64", property_id)]
    )
    try:
        results = bq.query(query, job_config=job_config).result()
        return [dict(row) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch income records")

@app.post("/income/{property_id}")
def create_income(property_id: int, income: IncomeCreate, bq: bigquery.Client = Depends(get_bq_client)):
    try:
        data = income.dict()
        row_to_insert = {
            "income_id": str(uuid.uuid4()),
            "property_id": property_id,
            "amount": data["amount"],
            "payment_date": str(data["payment_date"]),
            "source": data["source"]
        }
        table_id = f"{PROJECT_ID}.{DATASET}.income"
        load_rows(bq, table_id, [row_to_insert])
        return {"status": "success", "data_logged": row_to_insert}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Python Crash: {str(e)}")

# ---------------------------------------------------------------------------
# Expenses Endpoints
# ---------------------------------------------------------------------------

@app.get("/expenses/{property_id}")
def get_expenses(property_id: int, bq: bigquery.Client = Depends(get_bq_client)):
    query = f"SELECT * FROM `{PROJECT_ID}.{DATASET}.expenses` WHERE property_id = @prop_id ORDER BY expense_date DESC"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prop_id", "INT64", property_id)]
    )
    try:
        results = bq.query(query, job_config=job_config).result()
        return [dict(row) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/expenses/{property_id}", status_code=status.HTTP_201_CREATED)
def create_expense(property_id: int, expense: ExpenseCreate, bq: bigquery.Client = Depends(get_bq_client)):
    table_id = f"{PROJECT_ID}.{DATASET}.expenses"
    generated_id = str(uuid.uuid4())[:8]
    new_row = [{
        "expense_id": generated_id,
        "property_id": property_id,
        "amount": expense.amount,
        "category": expense.category,
        "description": expense.description,
        "expense_date": str(expense.expense_date),
        "status": "Pending"
    }]
    try:
        load_rows(bq, table_id, new_row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")
    return {"status": "success", "expense_id": generated_id, "data": new_row[0]}

@app.patch("/expenses/{expense_id}/pay")
def mark_expense_paid(expense_id: str, bq: bigquery.Client = Depends(get_bq_client)):
    query = f"UPDATE `{PROJECT_ID}.{DATASET}.expenses` SET status = 'Paid' WHERE expense_id = @exp_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("exp_id", "STRING", expense_id)]
    )
    try:
        bq.query(query, job_config=job_config).result()
        return {"message": f"Expense {expense_id} marked as paid"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Analytics Endpoints
# ---------------------------------------------------------------------------

@app.get("/occupancy/vacant")
def get_vacant_properties(bq: bigquery.Client = Depends(get_bq_client)):
    query = f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET}.properties`
        WHERE tenant_name IS NULL OR tenant_name = ''
    """
    try:
        results = bq.query(query).result()
        return [dict(row) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
