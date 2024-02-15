from fastapi import FastAPI

app = FastAPI()

@app.get("/", tags=["Root"])
async def serverUp():
    return {"serverUp": "Server running !!"}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Custom Title",
        version="2.5.0",
        description="This is a very custom OpenAPI schema",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Custom Swagger UI")

@app.get("/openapi.json", include_in_schema=False)
async def get_custom_openapi():
    return custom_openapi()
