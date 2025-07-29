from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, root_validator
from typing import Literal
import os
import httpx

# Application metadata for Swagger/OpenAPI docs
app = FastAPI(
    title="Universal Unit Converter API",
    description="REST API for unit and currency conversions across multiple categories. Supports length, weight, temperature, speed, and currency conversion (using a third-party API).",
    version="1.0.0",
    openapi_tags=[
        {"name": "unit-conversion", "description": "Endpoints for converting between different units."},
        {"name": "currency-conversion", "description": "Endpoint for converting between currencies."},
        {"name": "health", "description": "Health and root endpoint."},
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------- Constants and Supported Categories ---------------
UNIT_CATEGORIES = {
    "length": {
        "units": {
            "meters": 1.0,
            "kilometers": 1000.0,
            "centimeters": 0.01,
            "millimeters": 0.001,
            "miles": 1609.344,
            "yards": 0.9144,
            "feet": 0.3048,
            "inches": 0.0254,
        },
        "display": "Length"
    },
    "weight": {
        "units": {
            "kilograms": 1.0,
            "grams": 0.001,
            "milligrams": 0.000001,
            "pounds": 0.45359237,
            "ounces": 0.0283495231,
            "stones": 6.35029318,
            "tons": 1000.0,
        },
        "display": "Weight"
    },
    "temperature": {
        "units": {
            "celsius": None,
            "fahrenheit": None,
            "kelvin": None
        },
        "display": "Temperature"
    },
    "speed": {
        "units": {
            "m/s": 1.0,
            "km/h": 0.277778,
            "mph": 0.44704,
            "ft/s": 0.3048,
            "knots": 0.514444,
        },
        "display": "Speed"
    }
}
SUPPORTED_UNIT_CATEGORIES = list(UNIT_CATEGORIES.keys())

# ----------- pydantic Models for Validation & Documentation ----------

class UnitConversionRequest(BaseModel):
    """Request for unit conversion."""
    category: Literal["length", "weight", "temperature", "speed"] = Field(..., description="Category of unit conversion.")
    from_unit: str = Field(..., description="Source unit identifier.")
    to_unit: str = Field(..., description="Target unit identifier.")
    value: float = Field(..., description="Numeric value to convert.")

    # PUBLIC_INTERFACE
    @root_validator
    def validate_units(cls, values):
        category = values.get("category")
        from_unit = values.get("from_unit")
        to_unit = values.get("to_unit")

        if category not in UNIT_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'. Supported: {list(UNIT_CATEGORIES.keys())}")
        units = UNIT_CATEGORIES[category]["units"]
        if from_unit not in units:
            raise ValueError(f"from_unit '{from_unit}' not valid for category '{category}'. Supported: {list(units.keys())}")
        if to_unit not in units:
            raise ValueError(f"to_unit '{to_unit}' not valid for category '{category}'. Supported: {list(units.keys())}")
        return values

class UnitConversionResponse(BaseModel):
    """Response containing conversion result."""
    category: str = Field(..., description="Unit category.")
    from_unit: str = Field(..., description="Source unit.")
    to_unit: str = Field(..., description="Target unit.")
    input_value: float = Field(..., description="Input value.")
    converted_value: float = Field(..., description="Result after conversion.")

class CurrencyConversionRequest(BaseModel):
    """Request for currency conversion."""
    from_currency: str = Field(..., description="Source currency ISO code (e.g., USD).")
    to_currency: str = Field(..., description="Target currency ISO code (e.g., EUR).")
    amount: float = Field(..., gt=0, description="Amount to convert (must be positive).")

class CurrencyConversionResponse(BaseModel):
    """Response with currency conversion result."""
    from_currency: str = Field(..., description="Source currency.")
    to_currency: str = Field(..., description="Target currency.")
    input_amount: float = Field(..., description="Requested amount.")
    converted_amount: float = Field(..., description="Converted result.")
    rate: float = Field(..., description="Exchange rate used.")

# ----------- Business Logic ----------

# PUBLIC_INTERFACE
def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    """Convert length units."""
    units = UNIT_CATEGORIES["length"]["units"]
    value_meters = value * units[from_unit]
    return value_meters / units[to_unit]

# PUBLIC_INTERFACE
def convert_weight(value: float, from_unit: str, to_unit: str) -> float:
    """Convert weight units."""
    units = UNIT_CATEGORIES["weight"]["units"]
    value_kg = value * units[from_unit]
    return value_kg / units[to_unit]

# PUBLIC_INTERFACE
def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert temperature between Celsius, Fahrenheit, Kelvin."""
    # Convert to Celsius first
    if from_unit == to_unit:
        return value
    if from_unit == "celsius":
        c = value
    elif from_unit == "fahrenheit":
        c = (value - 32) * 5 / 9
    elif from_unit == "kelvin":
        c = value - 273.15
    else:
        raise ValueError(f"Unsupported temperature unit: {from_unit}")

    # Convert from Celsius to target
    if to_unit == "celsius":
        return c
    elif to_unit == "fahrenheit":
        return c * 9 / 5 + 32
    elif to_unit == "kelvin":
        return c + 273.15
    else:
        raise ValueError(f"Unsupported temperature unit: {to_unit}")

# PUBLIC_INTERFACE
def convert_speed(value: float, from_unit: str, to_unit: str) -> float:
    """Convert speed units."""
    units = UNIT_CATEGORIES["speed"]["units"]
    value_mps = value * units[from_unit]
    return value_mps / units[to_unit]

def round_result(value: float) -> float:
    """Smart rounding for display."""
    if abs(value) < 1e-6:
        return 0
    elif abs(value) < 1:
        return round(value, 6)
    elif abs(value) < 100:
        return round(value, 4)
    elif abs(value) < 10000:
        return round(value, 2)
    else:
        return round(value, 1)

# Mapping from category to conversion function
CONVERSION_FUNC = {
    "length": convert_length,
    "weight": convert_weight,
    "temperature": convert_temperature,
    "speed": convert_speed,
}

# ----------- REST API Endpoints -----------

@app.get("/", response_model=dict, tags=["health"])
def health_check():
    """Health check route for backend."""
    return {"message": "Healthy"}

# PUBLIC_INTERFACE
@app.get("/categories", tags=["unit-conversion"], summary="Get supported categories", response_model=list)
def get_categories():
    """
    List all supported unit conversion categories.
    """
    return [
        {"key": key, "display": UNIT_CATEGORIES[key]["display"]}
        for key in SUPPORTED_UNIT_CATEGORIES
    ]

# PUBLIC_INTERFACE
@app.get("/units", tags=["unit-conversion"], summary="Get units for a category")
def get_units(category: str = Query(..., description="Category (length, weight, temperature, speed)")):
    """
    Get available units for a given category.
    """
    if category not in UNIT_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    return list(UNIT_CATEGORIES[category]["units"].keys())

# PUBLIC_INTERFACE
@app.post("/convert", tags=["unit-conversion"], response_model=UnitConversionResponse,
          summary="Convert between units",
          description="Convert a value from one unit to another within supported categories (length, weight, temperature, speed).")
async def convert_units(request: UnitConversionRequest):
    """
    Unit conversion API. Accepts category, from_unit, to_unit, and value.
    Returns converted result.
    """
    conversion_func = CONVERSION_FUNC[request.category]
    try:
        result = conversion_func(request.value, request.from_unit, request.to_unit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return UnitConversionResponse(
        category=request.category,
        from_unit=request.from_unit,
        to_unit=request.to_unit,
        input_value=request.value,
        converted_value=round_result(result)
    )

# ----------- Currency Conversion Integration -----------

CURRENCY_API_KEY = os.getenv("CURRENCY_API_KEY")

# Choose a public currency API (exchangerate-api, exchangerate-host, etc.)
CURRENCY_API_URL = "https://api.exchangerate.host/convert"

# PUBLIC_INTERFACE
@app.post("/currency/convert", tags=["currency-conversion"], response_model=CurrencyConversionResponse,
          summary="Currency conversion", description="Convert an amount between currencies using a third-party API.")
async def convert_currency(req: CurrencyConversionRequest):
    """
    Convert an amount from one currency to another using latest market rates.
    """
    from_curr = req.from_currency.upper()
    to_curr = req.to_currency.upper()
    amount = req.amount

    try:
        async with httpx.AsyncClient() as client:
            # exchangerate.host does not require an API key
            params = {
                "from": from_curr,
                "to": to_curr,
                "amount": amount,
            }
            response = await client.get(CURRENCY_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Currency API error: {str(e)}")

    if not data.get("success", True):
        raise HTTPException(status_code=400, detail=f"Currency conversion failed: {data.get('error', 'Unknown error')}")

    rate = data["info"]["rate"] if "info" in data and "rate" in data["info"] else None
    converted = data.get("result")
    if converted is None or rate is None:
        raise HTTPException(status_code=502, detail="Currency API returned incomplete data")

    return CurrencyConversionResponse(
        from_currency=from_curr,
        to_currency=to_curr,
        input_amount=amount,
        converted_amount=round_result(converted),
        rate=round_result(rate)
    )

@app.get("/currency/symbols", tags=["currency-conversion"], summary="Get list of currency symbols")
async def get_currency_symbols():
    """
    List all supported currency symbols/codes via public API.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.exchangerate.host/symbols")
        response.raise_for_status()
        data = response.json()
        return sorted(list(data.get("symbols", {}).keys()))

# For easier dev: expose unit schemas
@app.get("/openapi-schema", tags=["unit-conversion"], summary="Get OpenAPI schema")
def openapi_schema():
    return app.openapi()

# ----------- Error Handler -----------

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# ---------------- USAGE NOTE (for API documentation route) ----------------

@app.get("/api-usage", tags=["health"], summary="API usage notes")
def api_usage_help():
    """
    Project Usage Note:
    
    - For currency APIs, CURRENCY_API_KEY is not required (using exchangerate.host - free).
    - Unit endpoints expect lowercase category/unit names as above.
    - All endpoints support CORS for frontend integration.
    """
    return {
        "note": (
            "Currency conversion uses exchangerate.host (API key not required). "
            "All categories, units and currencies are case-insensitive, but use lowercase as recommended. "
            "Use `/categories` and `/units?category=...` for populating selection menus in frontend."
        )
    }
