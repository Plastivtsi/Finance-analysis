from datetime import date
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field


app = FastAPI(
    title="Smart Spend Tracker API",
    version="1.0.0",
    description="API для обліку, аналізу та класифікації витрат.",
)

security = HTTPBearer(auto_error=False)

DEMO_TOKEN = "demo-token"


# ==================================================
# Обробка помилок
# ==================================================

def error_body(
    status: int,
    code: str,
    title: str,
    detail: str,
    instance: str,
    errors=None,
    retry_after_seconds=None,
):
    body = {
        "type": (
            "https://api.smartspendtracker.com/errors/"
            + code.lower().replace("_", "-")
        ),
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": instance,
        "traceId": "trace-" + uuid4().hex[:12],
    }

    if errors:
        body["errors"] = errors

    if retry_after_seconds is not None:
        body["retryAfterSeconds"] = retry_after_seconds

    return body


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException):
    mapping = {
        401: (
            "AUTHENTICATION_REQUIRED",
            "Необхідна автентифікація",
            "Потрібно увійти в систему.",
        ),
        403: (
            "RESOURCE_ACCESS_DENIED",
            "Доступ заборонено",
            "Недостатньо прав для операції.",
        ),
        404: (
            "RESOURCE_NOT_FOUND",
            "Ресурс не знайдено",
            "Запитаний ресурс не знайдено.",
        ),
        409: (
            "RESOURCE_CONFLICT",
            "Конфлікт",
            "Запит конфліктує з поточним станом ресурсу.",
        ),
        429: (
            "RATE_LIMIT_EXCEEDED",
            "Перевищено ліміт запитів",
            "Спробуйте пізніше.",
        ),
        503: (
            "SERVICE_UNAVAILABLE",
            "Сервіс недоступний",
            "Необхідний сервіс тимчасово недоступний.",
        ),
    }

    code, title, detail = mapping.get(
        exc.status_code,
        ("HTTP_ERROR", "Помилка запиту", str(exc.detail)),
    )

    headers = dict(exc.headers or {})

    body = error_body(
        exc.status_code,
        code,
        title,
        detail,
        request.url.path,
    )

    if exc.status_code == 429:
        try:
            body["retryAfterSeconds"] = int(
                headers.get("Retry-After", "60")
            )
        except (TypeError, ValueError):
            body["retryAfterSeconds"] = 60

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=headers,
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
):
    errors = {}

    for item in exc.errors():
        field = ".".join(
            str(part)
            for part in item.get("loc", [])
            if part != "body"
        ) or "request"

        errors.setdefault(field, []).append(
            item.get("msg", "Некоректне значення")
        )

    body = error_body(
        422,
        "VALIDATION_FAILED",
        "Помилка перевірки даних",
        "Одне або декілька полів не пройшли перевірку.",
        request.url.path,
        errors=errors,
    )

    return JSONResponse(
        status_code=422,
        content=body,
        media_type="application/problem+json",
    )


# ==================================================
# Авторизація
# ==================================================

def auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        security
    ),
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if (
        credentials.scheme.lower() != "bearer"
        or credentials.credentials != DEMO_TOKEN
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==================================================
# Моделі даних
# ==================================================

class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Login(BaseModel):
    email: EmailStr
    password: str


class ExpenseIn(BaseModel):
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    description: str = Field(min_length=1, max_length=500)
    date: date
    categoryId: Optional[UUID] = None


class ExpenseUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=3,
    )
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    date: Optional[date] = None
    categoryId: Optional[UUID] = None


class NaturalText(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = "#4F46E5"


# ==================================================
# Тимчасове сховище
# ==================================================

expenses: dict[str, dict[str, Any]] = {}
categories: dict[str, dict[str, Any]] = {}


# ==================================================
# System
# ==================================================

@app.get("/api/health", tags=["System"])
def health():
    return {"status": "ok"}


# ==================================================
# Auth
# ==================================================

@app.post(
    "/api/auth/register",
    status_code=201,
    tags=["Auth"],
)
def register(data: Register):
    # Демонстраційна реєстрація без збереження користувача.
    return {
        "id": str(uuid4()),
        "email": data.email,
        "message": "Демонстраційна реєстрація",
    }


@app.post("/api/auth/login", tags=["Auth"])
def login(data: Login):
    # Демонстраційний вхід.
    # Пароль і email поки не перевіряються.
    return {
        "accessToken": DEMO_TOKEN,
        "tokenType": "Bearer",
    }


# ==================================================
# Expenses
# ==================================================

@app.get("/api/expenses", tags=["Expenses"])
def list_expenses(
    dateFrom: Optional[date] = None,
    dateTo: Optional[date] = None,
    categoryId: Optional[UUID] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: None = Depends(auth),
):
    if dateFrom and dateTo and dateFrom > dateTo:
        raise HTTPException(
            status_code=422,
            detail="dateFrom must be before dateTo",
        )

    result = list(expenses.items())

    if categoryId:
        result = [
            (key, value)
            for key, value in result
            if value.get("categoryId") == str(categoryId)
        ]

    if dateFrom:
        result = [
            (key, value)
            for key, value in result
            if value["date"] >= dateFrom.isoformat()
        ]

    if dateTo:
        result = [
            (key, value)
            for key, value in result
            if value["date"] <= dateTo.isoformat()
        ]

    return [
        {"id": key, **value}
        for key, value in result[offset:offset + limit]
    ]


@app.post(
    "/api/expenses",
    status_code=201,
    tags=["Expenses"],
)
def create_expense(
    data: ExpenseIn,
    _: None = Depends(auth),
):
    if (
        data.categoryId
        and str(data.categoryId) not in categories
    ):
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    key = str(uuid4())

    expenses[key] = data.model_dump(mode="json")
    expenses[key]["status"] = "confirmed"

    return {"id": key, **expenses[key]}


@app.post(
    "/api/expenses/natural-language",
    status_code=503,
    tags=["Expenses"],
)
def natural_language(
    data: NaturalText,
    _: None = Depends(auth),
):
    raise HTTPException(
        status_code=503,
        detail="AI service is not configured yet",
    )


@app.get("/api/expenses/{expenseId}", tags=["Expenses"])
def get_expense(
    expenseId: UUID,
    _: None = Depends(auth),
):
    key = str(expenseId)

    if key not in expenses:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    return {"id": key, **expenses[key]}


@app.put("/api/expenses/{expenseId}", tags=["Expenses"])
def update_expense(
    expenseId: UUID,
    data: ExpenseUpdate,
    _: None = Depends(auth),
):
    key = str(expenseId)

    if key not in expenses:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    update_data = data.model_dump(
        exclude_unset=True,
        mode="json",
    )

    if (
        "categoryId" in update_data
        and update_data["categoryId"] is not None
        and update_data["categoryId"] not in categories
    ):
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    expenses[key].update(update_data)

    return {"id": key, **expenses[key]}


@app.delete(
    "/api/expenses/{expenseId}",
    status_code=204,
    tags=["Expenses"],
)
def delete_expense(
    expenseId: UUID,
    _: None = Depends(auth),
):
    key = str(expenseId)

    if key not in expenses:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    del expenses[key]

    return Response(status_code=204)


# ==================================================
# Categories
# ==================================================

@app.get("/api/categories", tags=["Categories"])
def list_categories(
    _: None = Depends(auth),
):
    return list(categories.values())


@app.post(
    "/api/categories",
    status_code=201,
    tags=["Categories"],
)
def create_category(
    data: CategoryIn,
    _: None = Depends(auth),
):
    if any(
        category["name"].casefold() == data.name.casefold()
        for category in categories.values()
    ):
        raise HTTPException(
            status_code=409,
            detail="Category already exists",
        )

    key = str(uuid4())

    categories[key] = {
        "id": key,
        **data.model_dump(),
    }

    return categories[key]

@app.put("/api/categories/{category_id}", tags=["Categories"])
def update_category(
    category_id: str,
    category: CategoryIn,
    _: None = Depends(auth),
):
    if category_id not in categories:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    categories[category_id].update(
        category.model_dump()
    )

    return categories[category_id]

@app.delete("/api/categories/{category_id}", tags=["Categories"])
def delete_category(
    category_id: str,
    _: None = Depends(auth),
):
    if category_id not in categories:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    del categories[category_id]

    return {
        "message": "Category deleted successfully"
    }

# ==================================================
# Analytics
# ==================================================

@app.get("/api/analytics/summary", tags=["Analytics"])
def summary(
    dateFrom: Optional[date] = None,
    dateTo: Optional[date] = None,
    _: None = Depends(auth),
):
    if dateFrom and dateTo and dateFrom > dateTo:
        raise HTTPException(
            status_code=422,
            detail="Invalid date range",
        )

    values = list(expenses.values())

    if dateFrom:
        values = [
            item
            for item in values
            if item["date"] >= dateFrom.isoformat()
        ]

    if dateTo:
        values = [
            item
            for item in values
            if item["date"] <= dateTo.isoformat()
        ]

    totals_by_currency = {}

    for item in values:
        currency = item["currency"]
        totals_by_currency[currency] = (
            totals_by_currency.get(currency, 0)
            + item["amount"]
        )

    if len(totals_by_currency) == 1:
        currency = next(iter(totals_by_currency))
        total_amount = round(
            totals_by_currency[currency], 2
        )
    elif not totals_by_currency:
        currency = "UAH"
        total_amount = 0
    else:
        # Не підсумовуємо різні валюти в одну суму.
        currency = None
        total_amount = None

    return {
        "totalAmount": total_amount,
        "currency": currency,
        "totalsByCurrency": {
            key: round(value, 2)
            for key, value in totals_by_currency.items()
        },
        "expenseCount": len(values),
        "period": {
            "dateFrom": dateFrom,
            "dateTo": dateTo,
        },
    }


@app.get("/api/analytics/by-category", tags=["Analytics"])
def by_category(
    dateFrom: Optional[date] = None,
    dateTo: Optional[date] = None,
    _: None = Depends(auth),
):
    if dateFrom and dateTo and dateFrom > dateTo:
        raise HTTPException(
            status_code=422,
            detail="Invalid date range",
        )

    totals = {}

    for item in expenses.values():
        if dateFrom and item["date"] < dateFrom.isoformat():
            continue

        if dateTo and item["date"] > dateTo.isoformat():
            continue

        key = item.get("categoryId") or "uncategorized"

        totals[key] = totals.get(key, 0) + item["amount"]

    total = sum(totals.values())

    return [
        {
            "categoryId": (
                None if key == "uncategorized" else key
            ),
            "categoryName": categories.get(
                key, {}
            ).get("name", "Без категорії"),
            "totalAmount": round(value, 2),
            "percentage": (
                round(value / total * 100, 2)
                if total
                else 0
            ),
        }
        for key, value in totals.items()
    ]


# ==================================================
# AI classification
# ==================================================

@app.post(
    "/api/expenses/{expenseId}/classify",
    tags=["Expenses"],
)
def classify(
    expenseId: UUID,
    _: None = Depends(auth),
):
    if str(expenseId) not in expenses:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    raise HTTPException(
        status_code=503,
        detail="AI service is not configured yet",
    )
