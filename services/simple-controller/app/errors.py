class DownstreamServiceError(Exception):
    def __init__(self, detail: str, downstream: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.downstream = downstream
        self.status_code = status_code


class UnsupportedAlgorithmError(Exception):
    def __init__(self, algorithm: str) -> None:
        super().__init__(f"unsupported algorithm: {algorithm}")
        self.detail = f"unsupported algorithm: {algorithm}"
