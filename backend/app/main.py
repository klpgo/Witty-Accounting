from fastapi import FastAPI

app = FastAPI(
    title="Witty Accounting",
)


@app.get("/")
def root():
    return {
        "application": "Witty Accounting",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }
