from __future__ import annotations

import json
import typing as t
import logging
import dataclasses
from typing import TYPE_CHECKING

import attr
from starlette.requests import Request
from starlette.responses import Response

from .base import IODescriptor
from ..types import LazyType
from ..utils import LazyLoader
from ..utils import bentoml_cattr
from ..utils.http import set_cookies
from ...exceptions import BadInput
from ..service.openapi import REF_PREFIX
from ..service.openapi import SUCCESS_DESCRIPTION
from ..service.openapi.specification import Schema
from ..service.openapi.specification import Response as OpenAPIResponse
from ..service.openapi.specification import MediaType
from ..service.openapi.specification import RequestBody

if TYPE_CHECKING:
    from types import UnionType

    import pydantic
    import pydantic.schema as schema

    from .. import external_typing as ext
    from ..context import InferenceApiContext as Context

    _Serializable = ext.NpNDArray | ext.PdDataFrame | t.Type[pydantic.BaseModel] | type
else:
    _exc_msg = "'pydantic' must be installed to use 'pydantic_model'. Install with 'pip install pydantic'."
    pydantic = LazyLoader("pydantic", globals(), "pydantic", exc_msg=_exc_msg)
    schema = LazyLoader("schema", globals(), "pydantic.schema", exc_msg=_exc_msg)


JSONType = t.Union[str, t.Dict[str, t.Any], "pydantic.BaseModel", None]

MIME_TYPE_JSON = "application/json"

logger = logging.getLogger(__name__)


class DefaultJsonEncoder(json.JSONEncoder):
    def default(self, o: _Serializable) -> t.Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if LazyType["ext.NpNDArray"]("numpy.ndarray").isinstance(o):
            return o.tolist()
        if LazyType["ext.NpGeneric"]("numpy.generic").isinstance(o):
            return o.item()
        if LazyType["ext.PdDataFrame"]("pandas.DataFrame").isinstance(o):
            return o.to_dict()  # type: ignore
        if LazyType["ext.PdSeries"]("pandas.Series").isinstance(o):
            return o.to_dict()  # type: ignore
        if LazyType["pydantic.BaseModel"]("pydantic.BaseModel").isinstance(o):
            obj_dict = o.dict()
            if "__root__" in obj_dict:
                obj_dict = obj_dict.get("__root__")
            return obj_dict
        if attr.has(o):  # type: ignore (trivial case)
            return bentoml_cattr.unstructure(o)

        return super().default(o)


class JSON(IODescriptor[JSONType]):
    """
    :obj:`JSON` defines API specification for the inputs/outputs of a Service, where either
    inputs will be converted to or outputs will be converted from a JSON representation
    as specified in your API function signature.

    A sample service implementation:

    .. code-block:: python
       :caption: `service.py`

       from __future__ import annotations

       import typing
       from typing import TYPE_CHECKING
       from typing import Any
       from typing import Optional

       import bentoml
       from bentoml.io import NumpyNdarray
       from bentoml.io import JSON

       import numpy as np
       import pandas as pd
       from pydantic import BaseModel

       iris_clf_runner = bentoml.sklearn.get("iris_clf_with_feature_names:latest").to_runner()

       svc = bentoml.Service("iris_classifier_pydantic", runners=[iris_clf_runner])

       class IrisFeatures(BaseModel):
           sepal_len: float
           sepal_width: float
           petal_len: float
           petal_width: float

           # Optional field
           request_id: Optional[int]

           # Use custom Pydantic config for additional validation options
           class Config:
               extra = 'forbid'


       input_spec = JSON(pydantic_model=IrisFeatures)

       @svc.api(input=input_spec, output=NumpyNdarray())
       def classify(input_data: IrisFeatures) -> NDArray[Any]:
           if input_data.request_id is not None:
               print("Received request ID: ", input_data.request_id)

           input_df = pd.DataFrame([input_data.dict(exclude={"request_id"})])
           return iris_clf_runner.run(input_df)

    Users then can then serve this service with :code:`bentoml serve`:

    .. code-block:: bash

        % bentoml serve ./service.py:svc --reload

    Users can then send requests to the newly started services with any client:

    .. tab-set::

        .. tab-item:: Bash

            .. code-block:: bash

               % curl -X POST -H "content-type: application/json" \\
                   --data '{"sepal_len": 6.2, "sepal_width": 3.2, "petal_len": 5.2, "petal_width": 2.2}' \\
                   http://127.0.0.1:3000/classify

               # [2]%

        .. tab-item:: Python

            .. code-block:: python
               :caption: `request.py`

                import requests

                requests.post(
                    "http://0.0.0.0:3000/predict",
                    headers={"content-type": "application/json"},
                    data='{"sepal_len": 6.2, "sepal_width": 3.2, "petal_len": 5.2, "petal_width": 2.2}'
                ).text

    Args:
        pydantic_model: Pydantic model schema. When used, inference API callback
                        will receive an instance of the specified ``pydantic_model`` class.
        json_encoder: JSON encoder class. By default BentoML implements a custom JSON encoder that
                      provides additional serialization supports for numpy arrays, pandas dataframes,
                      dataclass-like (`attrs <https://www.attrs.org/en/stable/>`_, dataclass, etc.).
                      If you wish to use a custom encoder, make sure to support the aforementioned object.

    Returns:
        :obj:`JSON`: IO Descriptor that represents JSON format.
    """

    _mime_type: str = MIME_TYPE_JSON

    def __init__(
        self,
        *,
        pydantic_model: t.Type[pydantic.BaseModel] | None = None,
        validate_json: bool | None = None,
        json_encoder: t.Type[json.JSONEncoder] = DefaultJsonEncoder,
    ):
        if pydantic_model:
            assert issubclass(
                pydantic_model, pydantic.BaseModel
            ), "'pydantic_model' must be a subclass of 'pydantic.BaseModel'."

        self._pydantic_model = pydantic_model
        self._json_encoder = json_encoder

        # Remove validate_json in version 1.0.2
        if validate_json is not None:
            logger.warning(
                "'validate_json' option from 'bentoml.io.JSON' has been deprecated. Use a Pydantic model to specify validation options instead."
            )

    def input_type(self) -> UnionType:
        return JSONType

    def openapi_schema(self) -> Schema:
        if not self._pydantic_model:
            return Schema(type="object")

        # returns schemas from pydantic_model.
        return Schema(
            **schema.model_process_schema(
                self._pydantic_model,
                model_name_map=schema.get_model_name_map(
                    schema.get_flat_models_from_model(self._pydantic_model)
                ),
                ref_prefix=REF_PREFIX,
            )[0]
        )

    def openapi_components(self) -> dict[str, t.Any] | None:
        if not self._pydantic_model:
            return {}

        from ..service.openapi.utils import pydantic_components_schema

        return {"schemas": pydantic_components_schema(self._pydantic_model)}

    def openapi_request_body(self) -> RequestBody:
        return RequestBody(
            content={self._mime_type: MediaType(schema=self.openapi_schema())},
            required=True,
        )

    def openapi_responses(self) -> OpenAPIResponse:
        return OpenAPIResponse(
            description=SUCCESS_DESCRIPTION,
            content={self._mime_type: MediaType(schema=self.openapi_schema())},
        )

    async def from_http_request(self, request: Request) -> JSONType:
        json_str = await request.body()
        try:
            json_obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise BadInput(f"Invalid JSON input received: {e}") from None

        if self._pydantic_model is not None:
            try:
                pydantic_model = self._pydantic_model.parse_obj(json_obj)
                return pydantic_model
            except pydantic.ValidationError as e:
                raise BadInput(f"Invalid JSON input received: {e}") from None
        else:
            return json_obj

    async def to_http_response(
        self, obj: JSONType | pydantic.BaseModel, ctx: Context | None = None
    ):
        if isinstance(obj, pydantic.BaseModel):
            obj = obj.dict()

        json_str = (
            json.dumps(
                obj,
                cls=self._json_encoder,
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                separators=(",", ":"),
            )
            if obj is not None
            else None
        )

        if ctx is not None:
            res = Response(
                json_str,
                media_type=MIME_TYPE_JSON,
                headers=ctx.response.metadata,  # type: ignore (bad starlette types)
                status_code=ctx.response.status_code,
            )
            set_cookies(res, ctx.response.cookies)
            return res
        else:
            return Response(json_str, media_type=MIME_TYPE_JSON)
