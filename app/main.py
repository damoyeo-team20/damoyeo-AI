from fastapi import FastAPI

app = FastAPI(title="damoyeo-ai")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
