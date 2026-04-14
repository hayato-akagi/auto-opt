from __future__ import annotations


class RecipeServiceError(Exception):
    pass


class ResourceNotFoundError(RecipeServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class TrialAlreadyCompletedError(RecipeServiceError):
    def __init__(self, detail: str = "trial already completed") -> None:
        super().__init__(detail)
        self.detail = detail


class DownstreamServiceError(RecipeServiceError):
    def __init__(
        self,
        detail: str,
        downstream: str,
        status_code: int = 502,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.downstream = downstream
        self.status_code = status_code


class DownstreamTimeoutError(DownstreamServiceError):
    def __init__(self, detail: str, downstream: str) -> None:
        super().__init__(detail=detail, downstream=downstream, status_code=504)
