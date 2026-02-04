from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import os
import CoolProp.CoolProp as CP

# Si defines API_KEY en Render, se exigirá Authorization: Bearer <API_KEY>
API_KEY = os.getenv("API_KEY", "").strip()

app = FastAPI(title="CoolProp API", version="1.2")

# CORS: para que Base44 (frontend) pueda llamar a la API directamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # luego puedes restringirlo a tu dominio Base44
    allow_credentials=False,  # no usamos cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

class StateRequest(BaseModel):
    fluid: str
    inputs: Dict[str, float]                 # EXACTAMENTE 2 propiedades (ej. {"P":300000,"T":278.15})
    outputs: Optional[List[str]] = None      # si es None -> usamos DEFAULT_OUTPUTS

# Set “grande y útil” (lo máximo razonable sin volverlo inmanejable)
DEFAULT_OUTPUTS: List[str] = [
    # Básicas termo
    "T", "P", "H", "S", "D", "Q",

    # Energéticas / caloríficas
    "CPMASS", "CVMASS", "UMASS",

    # Transporte (según backend/fluido algunas pueden fallar)
    "V",               # viscosidad dinámica [Pa*s]
    "L",               # conductividad térmica [W/m/K] (en CoolProp suele ser L)
    "CONDUCTIVITY",    # alias en algunas builds/backends
    "PRANDTL",         # a veces disponible
    "SURFACE_TENSION", # a veces disponible

    # Compresibilidad / velocidad del sonido
    "Z", "A",

    # Exponente isentrópico (puede variar)
    "ISENTROPIC_EXPONENT",

    # Derivadas comunes (si están disponibles)
    "DPDT", "DVDT", "DPDRHO", "DHDP", "DHDT", "DSDT", "DSDP",
]

# Unidades aproximadas por clave (no todas son universales, pero sirve para UI)
UNITS_MAP = {
    "T": "K",
    "P": "Pa",
    "H": "J/kg",
    "S": "J/kg/K",
    "D": "kg/m3",
    "Q": "-",
    "CPMASS": "J/kg/K",
    "CVMASS": "J/kg/K",
    "UMASS": "J/kg",
    "V": "Pa*s",
    "L": "W/m/K",
    "CONDUCTIVITY": "W/m/K",
    "PRANDTL": "-",
    "SURFACE_TENSION": "N/m",
    "Z": "-",
    "A": "m/s",
    "ISENTROPIC_EXPONENT": "-",
    "DPDT": "Pa/K",
    "DVDT": "m3/kg/K",
    "DPDRHO": "Pa/(kg/m3)",
    "DHDP": "(J/kg)/Pa",
    "DHDT": "J/kg/K",
    "DSDT": "J/kg/K^2",
    "DSDP": "(J/kg/K)/Pa",
}

@app.get("/")
def root():
    return {
        "service": "CoolProp API",
        "ok": True,
        "endpoints": ["/health", "/fluids", "/outputs", "/state"]
    }

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/fluids")
def fluids():
    """
    Devuelve la lista de fluidos del backend por defecto (normalmente HEOS).
    """
    s = CP.get_global_param_string("fluids_list")
    fluids_list = sorted({f.strip() for f in s.split(",") if f.strip()})
    return {"ok": True, "fluids": fluids_list}

@app.get("/outputs")
def outputs():
    """
    Lista de propiedades (outputs) sugeridas para consultar.
    """
    # Puedes devolver varios perfiles si quieres. Aquí devolvemos el "default grande".
    return {"ok": True, "outputs": DEFAULT_OUTPUTS, "units_hint": UNITS_MAP}

@app.post("/state")
def state(req: StateRequest, authorization: Optional[str] = Header(default=None)):
    # Auth opcional (solo si existe API_KEY en entorno)
    if API_KEY:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization.split(" ", 1)[1].strip()
        if token != API_KEY:
            raise HTTPException(status_code=403, detail="Invalid token")

    # Validación: exactamente 2 inputs
    if not req.inputs or len(req.inputs) != 2:
        raise HTTPException(
            status_code=400,
            detail="inputs must contain exactly 2 properties (e.g. {'P':300000,'T':278.15})"
        )

    # Tomar inputs de forma estable
    keys = list(req.inputs.keys())
    k1, k2 = keys[0], keys[1]
    v1, v2 = float(req.inputs[k1]), float(req.inputs[k2])

    outs = req.outputs if req.outputs and len(req.outputs) > 0 else DEFAULT_OUTPUTS

    values: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    try:
        for out in outs:
            out_key = out.strip()
            if not out_key:
                continue

            try:
                val = CP.PropsSI(out_key, k1, v1, k2, v2, req.fluid)

                # NaN / inf -> null
                if isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf")):
                    values[out_key] = None
                else:
                    values[out_key] = val

            except Exception as e:
                values[out_key] = None
                errors[out_key] = str(e)

        # Calidad Q: si existe y fuera de [0,1], lo marcamos N/A
        if "Q" in values and isinstance(values["Q"], (int, float)):
            if values["Q"] < 0 or values["Q"] > 1:
                values["Q"] = None

        return {
            "ok": True,
            "fluid": req.fluid,
            "inputs": {k1: v1, k2: v2},
            "units_hint": UNITS_MAP,
            "values": values,
            "errors": errors
        }

    except Exception as e:
        # Error general inesperado
        raise HTTPException(status_code=400, detail=str(e))
