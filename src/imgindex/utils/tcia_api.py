"""
Main TCIA API calls required for indexing.
"""

import aiohttp
from enum import StrEnum


class NBIA_BASE_URLS(StrEnum):  # noqa: N801
    """
    This enum class defines the NBIA base URLs used in the NBIA toolkit.
    """

    NBIA: str = "https://services.cancerimagingarchive.net/nbia-api/services/"
    NLST: str = "https://nlst.cancerimagingarchive.net/nbia-api/services/"
    LOGOUT_URL: str = (
        "https://services.cancerimagingarchive.net/nbia-api/logout"
    )


class NBIA_ENDPOINT(StrEnum):  # noqa: N801
    """
    This enum class defines the NBIA endpoints used in the NBIA toolkit.
    """

    GET_COLLECTIONS: str = "v2/getCollectionValues"
    GET_COLLECTION_PATIENT_COUNT: str = "getCollectionValuesAndCounts"
    GET_COLLECTION_DESCRIPTIONS: str = "getCollectionDescriptions"

    GET_MODALITY_VALUES: str = "v2/getModalityValues"
    GET_MODALITY_PATIENT_COUNT: str = "v2/getModalityValuesAndCounts"

    GET_PATIENTS: str = "v2/getPatient"
    GET_NEW_PATIENTS_IN_COLLECTION: str = "v2/NewPatientsInCollection"
    GET_PATIENT_BY_COLLECTION_AND_MODALITY: str = (
        "v2/getPatientByCollectionAndModality"
    )
    GET_BODY_PART_PATIENT_COUNT: str = "getBodyPartValuesAndCounts"

    GET_STUDIES: str = "v2/getPatientStudy"

    GET_SERIES: str = "v2/getSeries"
    GET_UPDATED_SERIES: str = "v2/getUpdatedSeries"
    GET_SERIES_SIZE: str = "v2/getSeriesSize"

    GET_SERIES_METADATA: str = "v1/getSeriesMetaData"

    DOWNLOAD_SERIES_MD5: str = "v2/getImageWithMD5Hash"
    DOWNLOAD_SERIES: str = "v2/getImage"

    DOWNLOAD_IMAGE: str = "v1/getSingleImage"

    GET_DICOM_TAGS: str = "getDicomTags"

    GET_SOP_INSTANCE_UIDS: str = "v1/getSOPInstanceUIDs"


class TCIAClient:
    """
    Async client for the TCIA NBIA API.
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str,
        token_url: str,
        timeout: int = 400,
    ):
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.token_url = token_url

        self.timeout = aiohttp.ClientTimeout(
            total=timeout
        )

        self.session: aiohttp.ClientSession | None = None
        self.headers: dict[str, str] = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=self.timeout
        )

        await self._authenticate()

        return self

    async def __aexit__(self, exc_type, exc, traceback):
        await self.close()

    async def close(self):
        """
        Close HTTP session.
        """

        if self.session:
            await self.session.close()

    async def _authenticate(self):
        """
        Retrieve and store API access token.
        """

        if self.session is None:
            raise RuntimeError(
                "Client session has not been initialized."
            )

        async with self.session.post(
            self.token_url,
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            },
        ) as response:
            response.raise_for_status()

            data = await response.json()

            self.headers.update(
                {
                    "Authorization": (
                        f"Bearer {data['access_token']}"
                    ),
                    "Content-Type": "application/json",
                }
            )

    async def _request(
        self,
        endpoint: NBIA_ENDPOINT,
        params: dict | None = None,
        retry: bool = True,
    ) -> aiohttp.ClientResponse:
        """
        Perform authenticated GET request.

        Retries once if token expired.
        """

        if self.session is None:
            raise RuntimeError(
                "Client session has not been initialized."
            )

        url = f"{self.base_url}/{endpoint.value}"

        response = await self.session.get(
            url,
            params=params,
            headers=self.headers,
        )

        if response.status == 401 and retry:
            await response.release()

            await self._authenticate()

            return await self._request(
                endpoint,
                params,
                retry=False,
            )

        response.raise_for_status()

        return response

    async def query_json(
        self,
        endpoint: NBIA_ENDPOINT,
        params: dict | None = None,
    ) -> dict:
        """
        Query endpoint and return JSON response.
        """

        response = await self._request(
            endpoint,
            params,
        )

        async with response:
            return await response.json()

    async def query_bytes(
        self,
        endpoint: NBIA_ENDPOINT,
        params: dict | None = None,
    ) -> bytes:
        """
        Query endpoint and return raw bytes.
        """

        response = await self._request(
            endpoint,
            params,
        )

        async with response:
            return await response.read()