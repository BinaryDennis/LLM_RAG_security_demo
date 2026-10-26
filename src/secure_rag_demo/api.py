from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Secure RAG Demo")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
