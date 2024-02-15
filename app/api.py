from fastapi import FastAPI

app = FastAPI()

@app.get("/", tags=["Root"])
async def serverUp():
    return {"serverUp": "Server running !!"}
