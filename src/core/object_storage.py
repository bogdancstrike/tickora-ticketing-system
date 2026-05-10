"""Back-compat shim — moved to `src.common.object_storage`."""
from src.common.object_storage import (  # noqa: F401
    ensure_bucket,
    get_s3_client,
    object_exists,
    presigned_get_url,
    presigned_put_url,
)
