from __future__ import annotations

from collections.abc import Mapping

from ..contracts import ExtractionRequest, ExtractionResponse, SearchQuery, SearchResponse


class FakeSearchProvider:
    def __init__(self, response: SearchResponse):
        self.response = response
        self.calls: list[SearchQuery] = []

    async def search(self, request: SearchQuery) -> SearchResponse:
        self.calls.append(request)
        return self.response


class FakeContentExtractor:
    def __init__(self, responses: Mapping[str, ExtractionResponse]):
        self.responses = dict(responses)
        self.calls: list[ExtractionRequest] = []

    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.calls.append(request)
        response = self.responses.get(request.url)
        if response is None:
            raise KeyError("FAKE_EXTRACTION_NOT_CONFIGURED")
        return response
