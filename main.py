from fastapi import FastAPI, Depends, HTTPException, status
from google.cloud import bigquery
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
import uuid
import os

app = FastAPI()

# Setting Project ID and Dataset information
# Cloud Run will automatically provide the PROJECT_ID if you set it in your deploy command
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

# ---------------------------------------------------------------------------
# Income Endpoints
# ---------------------------------------------------------------------------

@app.get("/income/{property_id}")
def get_income_records(property_id: int, bq: bigquery.Client = Depends(get_bq_client)):
    # Using backticks around `date` because it is a reserved SQL keyword
    query = f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET}.income`
        WHERE property_id = @prop_id
        ORDER BY `date` DESC
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
        
        # Build row to match BigQuery schema exactly. 
        # Using "date" as the key to match your BigQuery column name.
        row_to_insert = {
            "income_id": str(uuid.uuid4()), 
            "property_id": property_id,
            "amount": data["amount"],
            "date": str(data["payment_date"]), 
            "source": data["source"]
        }

        table_id = f"{PROJECT_ID}.{DATASET}.income"
        errors = bq.insert_rows_json(table_id, [row_to_insert])
        
        if errors:
            raise HTTPException(status_code=400, detail=f"BigQuery Insert Error: {errors}")
            
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
    errors = bq.insert_rows_json(table_id, new_row)
    if errors:
        raise HTTPException(status_code=500, detail=f"Insert failed: {errors}")
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

@app.get("/income/status/arrears")
def get_arrears_report(bq: bigquery.Client = Depends(get_bq_client)):
    now = datetime.now()
    # Note: using i.`date` to match your BigQuery column name
    query = f"""
        SELECT 
            p.property_id, p.name, p.tenant_name, p.monthly_rent,
            IFNULL(SUM(i.amount), 0) as paid, 
            (p.monthly_rent - IFNULL(SUM(i.amount), 0)) as debt
        FROM `{PROJECT_ID}.{DATASET}.properties` p
        LEFT JOIN `{PROJECT_ID}.{DATASET}.income` i ON p.property_id = i.property_id 
             AND EXTRACT(MONTH FROM i.`date`) = @m 
             AND EXTRACT(YEAR FROM i.`date`) = @y
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

# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    # This port logic is mandatory for Cloud Run
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)