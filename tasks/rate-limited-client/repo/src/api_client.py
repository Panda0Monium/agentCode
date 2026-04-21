class ApiClient:
    def __init__(
        self,
        base_url: str,
        requests_per_sec: float,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ):
        raise NotImplementedError

    def get(self, path: str) -> dict:
        raise NotImplementedError

    def post(self, path: str, data: dict) -> dict:
        raise NotImplementedError
