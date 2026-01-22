from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import os
import CoolProp.CoolProp as CP

API_KEY = os.getenv("API_KEY", "").strip()

app = FastAPI(title="CoolProp API", version="1.0")

class StateRequest(BaseModel):
    fluid: str
    inputs: Dict[str, float]
    outputs: List[str]

@app.get("/")
def root():
    return {"service": "CoolProp API", "ok": True, "endpoints": ["/health", "/fluids", "/state"]}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/fluids")
def fluids():
    s = CP.get_global_param_string("fluids_list")
    fluids_list = sorted({f.strip() for f in s.split(",") if f.strip()})
    return {"ok": True, "fluids": fluids_list}

@app.post("/state")
def state(req: StateRequest, authorization: Optional[str] = Header(default=None)):
    # Si hay API_KEY configurada, exigir auth
    if API_KEY:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization.split(" ", 1)[1].strip()
        if token != API_KEY:
            raise HTTPException(status_code=403, detail="Invalid token")

    if len(req.inputs) != 2:
        raise HTTPException(status_code=400, detail="inputs must contain exactly 2 properties (e.g. P and T)")

    (k1, v1), (k2, v2) = list(req.inputs.items())

    try:
        values: Dict[str, Any] = {}
        for out in req.outputs:
            values[out] = CP.PropsSI(out, k1, v1, k2, v2, req.fluid)

        if "Q" in values and isinstance(values["Q"], (int, float)) and values["Q"] < 0:
            values["Q"] = None

        return {"ok": True, "fluid": req.fluid, "inputs": {k1: v1, k2: v2},
                "units": {"T": "K", "P": "Pa", "H": "J/kg", "S": "J/kg/K", "D": "kg/m3"},
                "values": values}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
