from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import CoolProp.CoolProp as CP

API_KEY = "CHANGE_ME"  # luego lo pondremos como variable de entorno en Render

app = FastAPI(title="CoolProp API", version="1.0")

class StateRequest(BaseModel):
    fluid: str
    inputs: Dict[str, float]   # ejemplo: {"P": 300000, "T": 278.15}
    outputs: List[str]         # ejemplo: ["H","S","D","Q","CPMASS"]

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/state")
def state(req: StateRequest, authorization: Optional[str] = Header(default=None)):
    # Auth simple tipo Bearer
    if API_KEY != "CHANGE_ME":
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization.split(" ", 1)[1].strip()
        if token != API_KEY:
            raise HTTPException(status_code=403, detail="Invalid token")

    # Validación mínima
    if len(req.inputs) != 2:
        raise HTTPException(status_code=400, detail="inputs must contain exactly 2 properties (e.g. P and T)")

    (k1, v1), (k2, v2) = list(req.inputs.items())

    try:
        values: Dict[str, Any] = {}
        for out in req.outputs:
            values[out] = CP.PropsSI(out, k1, v1, k2, v2, req.fluid)

        return {
            "ok": True,
            "fluid": req.fluid,
            "inputs": {k1: v1, k2: v2},
            "units": {"T": "K", "P": "Pa", "H": "J/kg", "S": "J/kg/K", "D": "kg/m3"},
            "values": values
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
