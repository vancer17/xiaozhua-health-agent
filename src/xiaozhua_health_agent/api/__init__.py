"""HTTP API 层 — FastAPI 机械分诊门面（WP6 阶段 2）。

包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.api import create_app, run_health_api_server

跨包引用请使用 ``pipeline``、``schemas``、``eval`` 等包的 ``__init__`` 门面，
勿直接依赖 ``api`` 子模块实现文件（测试除外）。
"""

from __future__ import annotations

from xiaozhua_health_agent.api.app_factory import (
    create_app,
    register_health_triage_exception_handlers,
)
from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.errors import (
    HealthTriageHttpError,
    map_pipeline_result_to_http_error,
    map_pipeline_result_to_http_error_async,
)
from xiaozhua_health_agent.api.pipeline_http_mapping import (
    ERROR_INPUT_VALIDATION,
    ERROR_OUTPUT_MERGE_FAILED,
    ERROR_OUTPUT_NOT_MERGE_READY,
    ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED,
    ERROR_PIPELINE_FAILED,
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_UNPROCESSABLE_ENTITY,
    PipelineFailureHttpMapping,
    build_health_triage_error_body_from_pipeline_result,
    build_health_triage_error_body_from_pipeline_result_async,
    resolve_pipeline_failure_http_mapping,
    resolve_pipeline_failure_http_mapping_async,
)
from xiaozhua_health_agent.api.http_types import (
    HealthTriageErrorBody,
    HealthTriageRequestBody,
    LivenessResponse,
    ReadinessResponse,
)
from xiaozhua_health_agent.api.intelligent_http_mapping import (
    ERROR_INTELLIGENT_DISABLED,
    ERROR_INTELLIGENT_INPUT_VALIDATION,
    HTTP_STATUS_NOT_FOUND,
    build_intelligent_disabled_http_error,
    build_intelligent_input_validation_http_error,
    map_intelligent_validation_to_http_error,
    map_intelligent_validation_to_http_error_async,
)
from xiaozhua_health_agent.api.server import (
    run_health_api_server,
    run_health_api_server_async,
)
from xiaozhua_health_agent.api.settings import (
    DEFAULT_HEALTH_API_HOST,
    DEFAULT_HEALTH_API_PORT,
    HealthApiSettings,
    get_health_api_settings,
)

__all__ = [
    "DEFAULT_HEALTH_API_HOST",
    "DEFAULT_HEALTH_API_PORT",
    "ERROR_INPUT_VALIDATION",
    "ERROR_OUTPUT_MERGE_FAILED",
    "ERROR_OUTPUT_NOT_MERGE_READY",
    "ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED",
    "ERROR_PIPELINE_FAILED",
    "HTTP_STATUS_BAD_REQUEST",
    "HTTP_STATUS_INTERNAL_SERVER_ERROR",
    "HTTP_STATUS_UNPROCESSABLE_ENTITY",
    "HealthApiAppState",
    "HealthApiSettings",
    "HealthTriageErrorBody",
    "HealthTriageHttpError",
    "HealthTriageRequestBody",
    "ERROR_INTELLIGENT_DISABLED",
    "ERROR_INTELLIGENT_INPUT_VALIDATION",
    "HTTP_STATUS_NOT_FOUND",
    "build_intelligent_disabled_http_error",
    "build_intelligent_input_validation_http_error",
    "map_intelligent_validation_to_http_error",
    "map_intelligent_validation_to_http_error_async",
    "LivenessResponse",
    "PipelineFailureHttpMapping",
    "ReadinessResponse",
    "build_health_triage_error_body_from_pipeline_result",
    "build_health_triage_error_body_from_pipeline_result_async",
    "create_app",
    "get_health_api_settings",
    "map_pipeline_result_to_http_error",
    "map_pipeline_result_to_http_error_async",
    "register_health_triage_exception_handlers",
    "resolve_pipeline_failure_http_mapping",
    "resolve_pipeline_failure_http_mapping_async",
    "run_health_api_server",
    "run_health_api_server_async",
]
